"""Une visite en cours : relie le téléphone, la détection de phrases, la transcription, le
cerveau et la checklist, et mesure chaque étape (journal + bilan).

Chaîne pour chaque phrase : fin de phrase détectée → transcription → cerveau (question dite dès
qu'elle est écrite) → actions vérifiées et appliquées → bip si quelque chose a été noté sans
question. En parallèle, une « veille » regarde les images pendant les silences et peut poser
une question, jamais pendant que le diagnostiqueur parle.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import statistics
import time
import wave
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from . import parcours, plausibilite
from .actions import appliquer
from .cerveau import Contexte, Decision, ImageInstant, phrases_finies
from .checklist import ORIENTABLES, TOUJOURS_PRESENTS, Checklist, Element, cle_texte, horodatage
from .extraction import VOCABULAIRE, Cible, extraire, valeur_normalisee
from .boussole import Boussole, Mesure
from .garde import Questions, champ_rempli, demande_de_repeter, nom_abstrait
from .simulation import CerveauSimulation
from .reglages import Reglages
from .vad import TAUX, DetecteurPhrases, Phrase, ReglagesVad

log = logging.getLogger(__name__)

Envoyer = Callable[[dict], Awaitable[None]]

# Ce qui manque, dit simplement (« il te faut quoi d'autre ? » « Pour ce mur, il me manque le matériau et l'épaisseur. »).
LIBELLES_ORAUX = {"donne_sur": "sur quoi il donne", "materiau": "le matériau", "epaisseur": "l'épaisseur",
                  "isolation": "l'isolation", "menuiserie": "la menuiserie", "vitrage": "le vitrage", "volets": "les volets",
                  "type": "le type", "energie": "l'énergie", "annee": "l'année", "systeme": "le système"}

# Phrase assez longue pour que Claude la relise en arrière-plan après les règles (description libre).
MOTS_POUR_COMPLEMENT = 8

# Derniers mots qui montrent que la phrase n'est pas finie (« Il est… », « Et il fait… »).
_SUSPENDUS = {"est", "fait", "de", "du", "des", "la", "le", "les", "et", "en", "avec", "a", "au", "aux", "sur", "par",
              "il", "elle", "un", "une", "mais", "donc", "ou", "euh", "heu", "sont", "son", "sa", "ses", "qui", "que",
              "pour", "dans", "c", "cest"}


def valeurs_attendues(cible: Cible | None) -> list[str]:
    """Les réponses possibles à la dernière question, pour que Claude interprète une transcription
    fautive par rapport à elles (« Oh ! est chaude » à « à eau ou électrique ? » = eau chaude)."""
    if cible is None or cible.genre == "piece":
        return []
    if cible.genre in ("presence", "suite", "pareil"):
        return ["oui", "non"]
    if cible.genre == "orientation":
        return ["nord", "sud", "est", "ouest"]
    valeurs = list(dict.fromkeys(v for _, v in VOCABULAIRE.get((cible.type, cible.champ), [])))
    return ["oui", "non", *valeurs] if cible.genre == "confirmation" else valeurs


def _de(nom: str) -> str:
    """« le mur côté cave » → « du mur côté cave », « la fenêtre » → « de la fenêtre », « les 3 fenêtres » → « des 3 fenêtres »."""
    for article, contraction in (("le ", "du "), ("les ", "des ")):
        if nom.startswith(article):
            return contraction + nom[len(article):]
    return "de " + nom


def _normaliser(actions) -> list[dict]:
    """Valeurs proposées par Claude ramenées au vocabulaire du serveur (« toilettes » → « local chauffé : WC »),
    pour que les règles (paroi sur local chauffé, questions utiles) s'y appliquent."""
    normalisees = []
    for a in actions:
        if a.get("outil") == "enregistrer_reponse" and isinstance(a.get("valeur"), str):
            a = {**a, "valeur": valeur_normalisee(str(a.get("type", "")), str(a.get("champ", "")), a["valeur"])}
        normalisees.append(a)
    return normalisees


_CONSIGNE = re.compile(r"(?:^|[,;:] )(?:et )?(?:decrivez|decris|dites|dis|precisez|precise|indiquez|indique|montrez|montre|donnez|donne)\b")


def _consigne(phrase: str) -> bool:
    """« Décrivez le premier mur. », « Dans la chambre, décrivez le premier mur. » : une demande, donc la question de la
    réponse, même sans point d'interrogation."""
    return bool(_CONSIGNE.search(cle_texte(phrase)))


def _sans_ponctuation(texte: str) -> str:
    return cle_texte(re.sub(r"[^\w\s']", " ", texte))


def phrase_inachevee(texte: str) -> bool:
    texte = texte.strip()
    if texte.endswith(("...", "…")):
        return True
    mots = cle_texte(texte).replace("'", " ").rstrip(" ,;:").split()
    return bool(mots) and mots[-1] in _SUSPENDUS


def rappel_fin(checklist: Checklist, maximum: int = 3) -> str:
    """Phrase dite à la fin de la visite : ce qui manque encore (3 premiers points)."""
    manques = checklist.manques_visite()
    if not manques:
        return "Tout est renseigné. Vous pouvez arrêter."
    points = [f"{checklist.nom_piece(m.piece) if m.piece else 'logement'}, {m.libelle}" for m in manques[:maximum]]
    texte = f"Avant d'arrêter, il manque {len(manques)} information{'s' if len(manques) > 1 else ''}. " + " ; ".join(points)
    if len(manques) > maximum:
        texte += f" ; et {len(manques) - maximum} autres, à l'écran"
    return texte + "."


class Session:
    def __init__(self, ident: str, dossier: Path, cerveau, cerveau_veille, transcripteur, reglages: Reglages) -> None:
        self.id = ident
        self.dossier = dossier
        (dossier / "images").mkdir(parents=True, exist_ok=True)
        self.cerveau = cerveau
        self.cerveau_veille = cerveau_veille
        self.transcripteur = transcripteur
        self.reglages = reglages
        self.checklist = Checklist()
        # Étape 7 : Claude cerveau de chaque phrase (sauf en simulation, ou si DIAGAUTO_CONVERSATION=rapide).
        self.conversation = reglages.conversation == "claude" and not isinstance(cerveau, CerveauSimulation)
        self.en_pause = False  # « on fait une pause » : plus de question du parcours jusqu'à « on reprend »
        self.vad = DetecteurPhrases(ReglagesVad(fin_silence_s=reglages.fin_silence_s))
        self.images: deque[ImageInstant] = deque(maxlen=30)
        self.phrases: list[tuple[float, float, str]] = []
        self.dialogue: list[str] = []
        self.mesures: list[dict] = []  # une entrée par phrase traitée
        self.envoyer: Envoyer | None = None
        self.t_video = 0.0
        self.muet = False
        self.termine = False
        # Deux postes en chaîne : la phrase suivante est transcrite pendant que le cerveau répond.
        self._file: asyncio.Queue = asyncio.Queue()  # phrases à transcrire (son ou texte écrit)
        self._file_textes: asyncio.Queue = asyncio.Queue()  # phrases transcrites, en attente du cerveau
        # Conversation (étape 7) : un troisième poste. Les règles pré-remplissent chaque phrase dès qu'elle est transcrite,
        # même pendant que Claude répond encore à la précédente ; les phrases attendent ici leur tour auprès de Claude.
        self._file_claude: asyncio.Queue = asyncio.Queue()
        self._transcription_en_cours = False
        self._reponse_en_cours = False
        self._claude_en_cours = False
        self._en_parole = False
        self._paroles = 0  # nombre de débuts de parole (sert à abandonner une question de veille périmée)
        self._fin_parole = 0.0
        self._derniere_question = 0.0
        self._questions: deque[float] = deque()
        self._image_veille = -1.0
        self._veille_bientot = False
        self._compteur_dire = 0
        self._mesure_par_dire: dict[int, tuple[dict, float]] = {}
        self.questions = Questions()  # pour ne jamais redemander la même chose
        self._cible: Cible | None = None  # champ visé par la dernière question (pour comprendre « bas ! »)
        self._derniere_question_texte = ""
        self._dernier_element_id: str | None = None  # « Il est isolé ? » plutôt que « Le mur 2 est isolé ? »
        self._annonce = ""  # contradiction à dire avant la prochaine question : « Noté : parpaing au lieu de brique. »
        self._derniere_cle = ""  # clé de la dernière question du parcours (pour la reposer après une digression)
        self.boussole = Boussole()  # boussole et gyroscope du téléphone (étape 6)
        self._calibration_demandee = False  # « faites un 8 avec le téléphone » : dit une seule fois
        self._complements: set[asyncio.Task] = set()  # relectures de Claude en arrière-plan
        self._compteurs = {"acceptees": 0, "refusees": 0, "questions": 0, "retenues": 0, "veilles": 0, "bips": 0, "relectures_claude": 0,
                           "phrases_dites": 0}
        self._pret = asyncio.Event()
        self._journal = open(dossier / "journal.jsonl", "a", encoding="utf-8")
        self._wav = wave.open(str(dossier / "audio.wav"), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(TAUX)
        self._wav_echantillons = 0
        self._taches: list[asyncio.Task] = []

    # --- Cycle de vie ----------------------------------------------------------------------

    async def demarrer(self, piece: str = "") -> None:
        if piece.strip():
            self.checklist.definir_piece(piece, 0.0, citation="")
        self.journaliser("debut", cerveau=self.cerveau.nom, transcription=self.transcripteur.nom, piece=piece)
        self._taches = [
            asyncio.create_task(self._demarrer_cerveaux()),
            asyncio.create_task(self._boucle_transcription()),
            asyncio.create_task(self._boucle_reponses()),
            asyncio.create_task(self._boucle_conversation()),
            asyncio.create_task(self._boucle_veille()),
        ]

    @property
    def occupe(self) -> bool:
        """Une phrase est en cours de traitement ou en attente."""
        return (self._transcription_en_cours or self._reponse_en_cours or self._claude_en_cours or bool(self._complements)
                or not self._file.empty() or not self._file_textes.empty() or not self._file_claude.empty())

    def _cerveaux(self) -> list:
        """Cerveaux distincts (en simulation, réponses et veille sont le même objet)."""
        return [self.cerveau] if self.cerveau is self.cerveau_veille else [self.cerveau, self.cerveau_veille]

    async def _demarrer_cerveaux(self) -> None:
        debut = time.perf_counter()
        try:
            await asyncio.gather(*(c.demarrer() for c in self._cerveaux()))
            mesures = getattr(self.cerveau, "prechauffage", {})
            self.journaliser("cerveau_pret", duree_s=round(time.perf_counter() - debut, 2), prechauffage=mesures)
        except Exception as e:  # le cerveau reste indisponible : on le dit, la capture continue
            log.exception("Démarrage du cerveau")
            self.journaliser("erreur", etape="demarrage_cerveau", message=str(e))
            await self._envoyer({"type": "erreur", "message": f"Assistant indisponible : {e}"})
        finally:
            self._pret.set()

    async def terminer(self) -> dict:
        if self.termine:
            return self.bilan()
        self.termine = True
        for tache in [*self._taches, *self._complements]:
            tache.cancel()
        for c in self._cerveaux():
            await c.fermer()
        bilan = self.bilan()
        (self.dossier / "etat.json").write_text(json.dumps(self.checklist.vers_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (self.dossier / "bilan.json").write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding="utf-8")
        self.journaliser("fin", bilan=bilan)
        self._wav.close()
        self._journal.close()
        return bilan

    # --- Échanges avec le téléphone ------------------------------------------------------------

    def journaliser(self, evenement: str, **donnees) -> None:
        if self._journal.closed:
            return
        ligne = {"horloge": datetime.now().isoformat(timespec="milliseconds"), "evenement": evenement, "t": round(self.t_video, 2), **donnees}
        self._journal.write(json.dumps(ligne, ensure_ascii=False, default=str) + "\n")
        self._journal.flush()

    async def _envoyer(self, message: dict) -> None:
        if self.envoyer is None:
            return
        try:
            await self.envoyer(message)
        except Exception:  # téléphone déconnecté : la visite continue, il se reconnectera
            self.envoyer = None

    async def envoyer_etat(self) -> None:
        manques = self.checklist.manques_piece()
        await self._envoyer({
            "type": "etat",
            "piece": self.checklist.nom_piece(self.checklist.piece_courante) if self.checklist.piece_courante else None,
            "taux": self.checklist.taux_remplissage(),
            "manques": [m.libelle for m in manques[:8]],
            "nb_manques_visite": len(self.checklist.manques_visite()),
            "checklist": self.checklist.vers_dict(),
        })

    def _ecrire_wav(self, t: float, pcm: bytes) -> None:
        # Le fichier son suit l'horloge de la vidéo : un trou (réseau coupé) est rempli de silence.
        attendu = int(round(t * TAUX))
        trou = attendu - self._wav_echantillons
        if 0 < trou <= 600 * TAUX:
            self._wav.writeframes(b"\x00\x00" * trou)
            self._wav_echantillons += trou
        self._wav.writeframes(pcm)
        self._wav_echantillons += len(pcm) // 2

    async def recevoir_audio(self, t: float, pcm: bytes) -> None:
        if self.termine:
            return
        self.t_video = max(self.t_video, t + len(pcm) / 2 / TAUX)
        self._ecrire_wav(t, pcm)
        for ev in self.vad.ajouter(pcm, t):
            if ev.type == "debut":
                self._en_parole = True
                self._paroles += 1
                await self._envoyer({"type": "parole_debut", "t": round(ev.t, 2)})
            else:
                self._en_parole = False
                self._fin_parole = time.monotonic()
                if ev.phrase is not None:
                    await self._file.put(("audio", ev.phrase, self._fin_parole))

    async def recevoir_image(self, t: float, jpeg: bytes) -> None:
        if self.termine or not jpeg.startswith(b"\xff\xd8"):
            return
        self.t_video = max(self.t_video, t)
        chemin = self.dossier / "images" / f"{t:08.2f}.jpg"
        chemin.write_bytes(jpeg)
        self.images.append(ImageInstant(t, jpeg, chemin))

    async def recevoir_controle(self, message: dict) -> None:
        genre = message.get("type")
        if genre == "texte" and str(message.get("texte", "")).strip():
            # Phrase écrite dans la page (tests sans micro, ou sans transcription).
            self._paroles += 1
            await self._file.put(("texte", str(message["texte"]).strip(), time.monotonic()))
        elif genre == "tts":
            self.vad.ia_parle = message.get("etat") == "debut"
            if message.get("etat") == "debut" and isinstance(message.get("id"), int):
                mesure, reference = self._mesure_par_dire.pop(message["id"], (None, 0.0))
                if mesure is not None and reference:
                    mesure["voix_s"] = round(time.monotonic() - reference, 3)
                    self.journaliser("voix_debut", id=message["id"], voix_s=mesure["voix_s"])
        elif genre == "silence":
            self.muet = bool(message.get("actif"))
            self.journaliser("silence", actif=self.muet)
        elif genre == "capteurs" and isinstance(message.get("t"), (int, float)):
            # Boussole et gyroscope du téléphone, une mesure par seconde (étape 6) ; valeurs absentes si pas de capteur.
            def nombre(cle: str) -> float | None:
                v = message.get(cle)
                return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None

            cap, lacet = nombre("cap"), nombre("lacet")
            self.boussole.ajouter(Mesure(float(message["t"]), None if cap is None else cap % 360, None if lacet is None else lacet % 360,
                                         nombre("precision"), nombre("inclinaison")))
            self.checklist.regler_boussole(self.boussole.correction(), self.boussole.fiabilite(), self.boussole.gyroscope)
        elif genre == "fin":
            await self.fin_visite()

    # --- Phrases --------------------------------------------------------------------------------

    async def _boucle_transcription(self) -> None:
        while True:
            genre, donnee, reference = await self._file.get()
            self._transcription_en_cours = True
            try:
                await self._transcrire(genre, donnee, reference)
            except Exception as e:
                log.exception("Transcription d'une phrase")
                self.journaliser("erreur", etape="transcription", message=str(e))
            finally:
                self._transcription_en_cours = False

    async def _transcrire(self, genre: str, donnee, reference: float) -> None:
        attente = time.monotonic() - reference
        son = None
        if genre == "audio":
            phrase: Phrase = donnee
            debut = time.perf_counter()
            texte = await asyncio.to_thread(self.transcripteur.transcrire, phrase.audio)
            duree = time.perf_counter() - debut
            t_debut, t_fin, son = phrase.t_debut, phrase.t_fin, phrase.audio
        else:
            texte, t_debut, t_fin, duree = donnee, self.t_video, self.t_video, 0.0
        if not texte:
            self.journaliser("phrase_vide", t_phrase=round(t_fin, 2), transcription_s=round(duree, 3))
            return
        ligne = f"[{horodatage(t_fin)}] Diagnostiqueur : « {texte} »"
        self.phrases.append((t_debut, t_fin, texte))
        self.dialogue.append(ligne)
        await self._envoyer({"type": "transcription", "t": round(t_fin, 2), "texte": texte})
        await self._file_textes.put({
            "source": genre, "texte": texte, "t_debut": t_debut, "t_fin": t_fin, "ligne": ligne, "reference": reference,
            "attente_transcription_s": attente, "transcription_s": duree, "pret": time.monotonic(), "audio": son,
        })

    async def _boucle_reponses(self) -> None:
        while True:
            lot = [await self._file_textes.get()]
            self._reponse_en_cours = True
            try:
                # Phrases transcrites pendant la réponse précédente : un seul appel au cerveau pour toutes,
                # plutôt qu'une file d'attente qui retarde chaque réponse.
                while not self._file_textes.empty():
                    lot.append(self._file_textes.get_nowait())
                if phrase_inachevee(lot[-1]["texte"]):
                    await self._attendre_suite(lot)
                await self._repondre(lot)
            except Exception as e:
                log.exception("Réponse à une phrase")
                self.journaliser("erreur", etape="reponse", message=str(e))
            finally:
                self._reponse_en_cours = False

    async def _attendre_suite(self, lot: list[dict], calme_s: float = 1.2, maximum_s: float = 8.0) -> None:
        """« Il est… » : le diagnostiqueur cherche ses mots. On attend la suite tant qu'il parle encore
        ou qu'une phrase est en cours de transcription, puis on répond à l'ensemble."""
        limite = time.monotonic() + maximum_s
        calme_depuis = time.monotonic()
        while time.monotonic() < limite:
            try:
                lot.append(await asyncio.wait_for(self._file_textes.get(), timeout=0.2))
                while not self._file_textes.empty():
                    lot.append(self._file_textes.get_nowait())
                if not phrase_inachevee(lot[-1]["texte"]):
                    return
                calme_depuis = time.monotonic()
            except asyncio.TimeoutError:
                if self._en_parole or self._transcription_en_cours or not self._file.empty():
                    calme_depuis = time.monotonic()
                elif time.monotonic() - calme_depuis > calme_s:
                    return

    async def _repondre(self, lot: list[dict]) -> None:
        # Les mesures portent sur la DERNIÈRE phrase du lot : c'est après elle que le diagnostiqueur attend.
        dernier = lot[-1]
        audio = dernier["source"] == "audio"
        texte = " ".join(p["texte"] for p in lot)
        mesure: dict = {
            "source": dernier["source"],
            "fin_silence_s": self.reglages.fin_silence_s if audio else 0.0,
            "transcription_s": round(dernier["transcription_s"], 3),
            "attente_s": round(dernier["attente_transcription_s"] + time.monotonic() - dernier["pret"], 3),
            "t": round(dernier["t_fin"], 2),
            "texte": texte,
            "phrases_regroupees": len(lot),
        }
        lignes = {p["ligne"] for p in lot}
        contexte = Contexte(
            mode="reponse", t=dernier["t_fin"], checklist=self.checklist,
            dialogue=[l for l in self.dialogue if l not in lignes][-8:],
            images=self._images_pour(lot[0]["t_debut"], dernier["t_fin"]), phrase=texte,
            t_phrase=(lot[0]["t_debut"], dernier["t_fin"]),
            derniere_question=self._derniere_question_texte,
            valeurs_attendues=valeurs_attendues(self._cible),
        )
        self.mesures.append(mesure)
        reference = dernier["reference"]

        # 1. Extraction immédiate, sans IA : tout ce qui est reconnu est noté tout de suite (en conversation, c'est un
        # pré-remplissage que Claude vérifie : il peut le corriger ou l'annuler).
        debut = time.perf_counter()
        avant = {"ids": {e.id for e in self.checklist.elements}, "signalements": len(self.checklist.signalements)}
        extraction, resultats, notes, proposition = await self._noter(texte, contexte, lot)
        mesure["extraction_ms"] = round((time.perf_counter() - debut) * 1000, 1)
        compris = [r for r in resultats if r["statut"] == "accepte"]
        son = lot[0].get("audio") if len(lot) == 1 else None
        # Second avis de Whisper : sans conversation, pour toute phrase non comprise ; en conversation, Claude comprend les
        # mots abîmés, Whisper sert seulement à reconnaître un bruit (phrase très courte et incomprise).
        court = len(texte.split()) <= 2 or not self.conversation
        if (court and not compris and not proposition and not extraction.demande and son is not None
                and hasattr(self.transcripteur, "second_avis")):
            # 1 bis. Pas compris : second avis de Whisper, guidé par le vocabulaire métier (moteur « rapide »).
            debut = time.perf_counter()
            texte_whisper = await asyncio.to_thread(self.transcripteur.second_avis, son)
            mesure["second_avis_s"] = round(time.perf_counter() - debut, 3)
            self.journaliser("second_avis", rapide=texte, whisper=texte_whisper, duree_s=mesure["second_avis_s"])
            if not texte_whisper:
                self.journaliser("decision", mode="bruit", mesures=mesure)  # pas de vraie parole selon Whisper : rien à dire
                return
            if cle_texte(texte_whisper) != cle_texte(texte):
                contexte.autre_transcription = texte_whisper
                extraction2, resultats2, notes2, proposition2 = await self._noter(texte_whisper, contexte, lot)
                if any(r["statut"] == "accepte" for r in resultats2) or proposition2 or extraction2.demande:
                    texte, extraction, resultats, notes, proposition = texte_whisper, extraction2, resultats2, notes2, proposition2
                    contexte.phrase, contexte.autre_transcription, mesure["texte"] = texte, "", texte
                    compris = [r for r in resultats if r["statut"] == "accepte"]
                    await self._envoyer({"type": "transcription", "t": round(dernier["t_fin"], 2), "texte": texte})
        mesure["valeurs_extraites"] = len(notes)
        contexte.deja_note = self._deja_note(resultats)
        if self._cible and champ_rempli(self._cible, self.checklist):
            self._cible = None  # la dernière question a eu sa réponse
        # Question restée sans réponse alors que la phrase a été comprise (une correction, un autre élément) : elle
        # pourra être reposée une fois, après la prise en compte de ce qui vient d'être dit.
        en_attente = self._derniere_cle if self._cible is not None and self._cible.genre != "confirmation" else ""
        # Après l'extraction : la phrase a pu changer de pièce (« ici c'est la cuisine »).
        contexte.questions_recentes = self.questions.recentes(time.monotonic(), self.checklist.piece_courante)

        if self.conversation:
            # Pré-rempli par les règles : « noté » tout de suite (bip et écran), puis la phrase va à Claude, qui la vérifie.
            if notes:
                await self._bip(round(time.monotonic() - reference, 3))
                mesure["bip_s"] = round(time.monotonic() - reference, 3)
                await self.envoyer_etat()
            pre_rempli = {"phrases": [texte], "signalements": avant["signalements"],
                          "valeurs": {(r.get("element"), r["action"].get("champ")) for r in notes
                                      if r["action"].get("outil") == "enregistrer_reponse"},
                          "crees": [e.id for e in self.checklist.elements if e.id not in avant["ids"]]}
            await self._file_claude.put({"contexte": contexte, "reference": reference, "mesure": mesure, "demande": extraction.demande,
                                         "notes": notes, "proposition": proposition, "en_attente": en_attente,
                                         "pre_rempli": pre_rempli, "lignes": lignes})
        elif not compris and not proposition and extraction.demande:
            # « Quel mur ? », « il te faut quoi d'autre ? » : réponse du serveur, puis la question en attente reposée.
            await self._repondre_a_la_demande(extraction.demande, reference, mesure, texte)
            await self.envoyer_etat()
            self.journaliser("decision", mode="demande", mesures=mesure)
        elif compris or proposition:
            # 2. Compris : la question suivante du parcours part tout de suite, sans attendre Claude. Compris avec
            # un doute : on propose l'interprétation la plus probable (« J'ai compris…, c'est bien ça ? »).
            question = proposition is not None and await self._confirmer(proposition, reference, mesure)
            if (not question and not await self._question_du_parcours(reference, mesure, reposer=en_attente)
                    and not await self._annoncer(reference, mesure) and notes):
                await self._bip(round(time.monotonic() - reference, 3))
                mesure["bip_s"] = round(time.monotonic() - reference, 3)
            await self.envoyer_etat()
            self.journaliser("decision", mode="parcours", mesures=mesure)
            # Phrase longue : Claude relit en arrière-plan, au cas où les règles auraient manqué quelque chose.
            if len(texte.split()) >= MOTS_POUR_COMPLEMENT and not isinstance(self.cerveau, CerveauSimulation):
                contexte.mode = "complement"
                tache = asyncio.create_task(self._completer(contexte))
                self._complements.add(tache)
                tache.add_done_callback(self._complements.discard)
        else:
            # 3. Pas compris par les règles : Claude essaie, puis le parcours reprend.
            await self._decider(self.cerveau, contexte, reference, mesure)

    async def _boucle_conversation(self) -> None:
        while True:
            attente = [await self._file_claude.get()]
            self._claude_en_cours = True
            try:
                # Phrases dites pendant la réponse précédente de Claude : un seul appel pour toutes.
                while not self._file_claude.empty():
                    attente.append(self._file_claude.get_nowait())
                await self._converser(**self._fusionner(attente))
            except Exception as e:
                log.exception("Conversation avec Claude")
                self.journaliser("erreur", etape="conversation", message=str(e))
            finally:
                self._claude_en_cours = False

    def _fusionner(self, attente: list[dict]) -> dict:
        """Plusieurs phrases en attente de Claude réunies en une : texte, déjà-noté et pré-remplissage mis bout à bout ;
        la dernière question et la question en attente sont celles d'avant la première phrase."""
        premier, dernier = attente[0], attente[-1]
        if len(attente) == 1:
            return {cle: v for cle, v in premier.items() if cle != "lignes"}
        contexte = dernier["contexte"]
        lignes = {l for a in attente for l in a["lignes"]}
        contexte.phrase = " ".join(a["contexte"].phrase for a in attente)
        contexte.t_phrase = (premier["contexte"].t_phrase or (0, 0))[0], (contexte.t_phrase or (0, 0))[1]
        contexte.deja_note = [n for a in attente for n in a["contexte"].deja_note]
        contexte.dialogue = [l for l in self.dialogue if l not in lignes][-8:]
        contexte.derniere_question, contexte.valeurs_attendues = premier["contexte"].derniere_question, premier["contexte"].valeurs_attendues
        for a in attente[:-1]:
            a["mesure"]["regroupee_avec_la_suivante"] = True
        return {
            "contexte": contexte, "reference": dernier["reference"], "mesure": dernier["mesure"],
            "demande": next((a["demande"] for a in reversed(attente) if a["demande"]), ""),
            "notes": [n for a in attente for n in a["notes"]],
            "proposition": next((a["proposition"] for a in reversed(attente) if a["proposition"]), None),
            "en_attente": premier["en_attente"],
            "pre_rempli": {"phrases": [p for a in attente for p in a["pre_rempli"]["phrases"]],
                           "signalements": premier["pre_rempli"]["signalements"],
                           "valeurs": set().union(*(a["pre_rempli"]["valeurs"] for a in attente)),
                           "crees": [i for a in attente for i in a["pre_rempli"]["crees"]]},
        }

    async def _converser(self, contexte: Contexte, reference: float, mesure: dict, demande: str, notes: list[dict],
                         proposition: dict | None, en_attente: str, pre_rempli: dict) -> None:
        """Étape 7 : Claude, cerveau de CHAQUE phrase. Les règles ont déjà pré-rempli (et bippé) ; Claude comprend la
        phrase quelle qu'elle soit, y répond, corrige le pré-remplissage s'il le faut, et reprend la visite avec la
        question que propose le parcours. Sa réponse est lue phrase par phrase, dès la première ; si le diagnostiqueur
        reparle entre-temps, elle est abandonnée (sa nouvelle phrase est déjà pré-remplie et attend son tour)."""
        if en_attente and not notes:
            # Il parle d'autre chose (une question, une remarque) : la question restée sans réponse est reposée à la fin
            # de la réponse de Claude, autant de fois qu'il le faut. C'est la reprise naturelle de la visite.
            self.questions.autoriser_encore(en_attente)
        plan = None if self.en_pause else self._prochaine_question(en_attente)
        contexte.en_pause = self.en_pause
        nom = ""
        if plan is not None and "." in plan.code:
            try:
                nom = self.checklist.nom(self.checklist.trouver_element(plan.code.split(".")[0]), demonstratif=False)
            except ValueError:
                pass
        contexte.suggestion = (f"« {plan.texte} » [{plan.code}]" + (f" (élément : « {nom} »)" if nom else "") if plan
                               else "" if self.en_pause else "aucune : tout est renseigné ici, propose de passer à la pièce suivante")
        if plan is not None:  # la question proposée n'est pas « déjà demandée » : elle est à reposer
            contexte.questions_recentes = [c for c in contexte.questions_recentes if c != plan.code]
        remarques = [self._annonce] if self._annonce else []
        self._annonce = ""
        if proposition:
            question = proposition.get("question") or f"J'ai compris {proposition['valeur']}, c'est bien ça ?"
            remarques.append(f"Interprétation douteuse, à faire confirmer : « {question} » [confirmer:{proposition.get('element_id')}."
                             f"{proposition.get('champ')}={proposition.get('valeur')}].")
        if demande:
            remarques.append(f"Il demande quelque chose ; réponse possible : « {self._texte_demande(demande, contexte.phrase)} »")
        contexte.remarques = remarques
        await self._pret.wait()
        debut = time.perf_counter()
        dit = {"phrases": 0, "question": False}
        paroles = self._paroles

        async def sur_dire(texte: str, code_cible: str) -> None:
            for phrase in phrases_finies(texte):
                if dit["question"]:
                    return  # une seule question, toujours la dernière chose dite
                if self._paroles != paroles:
                    self.journaliser("reponse_abandonnee", texte=phrase, raison="le diagnostiqueur reparle")
                    return
                premiere = dit["phrases"] == 0
                if "?" in phrase or _consigne(phrase) or (plan is not None and _sans_ponctuation(phrase) == _sans_ponctuation(plan.texte)):
                    cle = plan.cle if plan is not None and code_cible == plan.code else None
                    question, cible, raison, cle = self.questions.filtrer(phrase, code_cible, self.checklist, time.monotonic(),
                                                                          cle=cle, reposer=en_attente)
                    if raison:
                        self.journaliser("question_filtree", texte=phrase, cible=code_cible, raison=raison)
                        return
                    await self.dire(question, reference, mesure if premiere else None, cible=cible, cle=cle,
                                    une_fois=plan is not None and cle == plan.cle, suite=not premiere)
                    dit["question"] = True
                elif demande_de_repeter(phrase) or nom_abstrait(phrase):
                    self.journaliser("phrase_filtree", texte=phrase)
                    continue
                else:
                    await self.dire(phrase, reference, mesure if premiere else None, suite=not premiere, question=False)
                if premiere:
                    mesure["cerveau_dire_s"] = round(time.perf_counter() - debut, 3)
                    mesure["question_s"] = round(time.monotonic() - reference, 3)
                    mesure["question_dite"] = True
                dit["phrases"] += 1

        decision = await self.cerveau.decider(contexte, sur_dire)
        mesure["cerveau_total_s"] = round(time.perf_counter() - debut, 3)
        mesure["cerveau"] = decision.mesures
        actions, commandes = self._commandes(decision.actions, pre_rempli)
        probables = [a for a in actions if a.get("certitude") == "probable" and a.get("outil") == "enregistrer_reponse"]
        actions, invraisemblables, ecartees = plausibilite.filtrer(_normaliser(a for a in actions if a not in probables))
        signales = len(self.checklist.signalements)
        resultats = appliquer(self.checklist, actions, contexte.t, self._phrases_recentes(contexte))
        notes_claude = self._compter(resultats)
        self._noter_contradictions(signales)
        if contexte.t_phrase:
            self._situer(resultats, *contexte.t_phrase)
        if resultats:
            await self._envoyer_actions(resultats, "cerveau")
        quelque_chose = (dit["phrases"] or notes or notes_claude or commandes or decision.erreur
                         or any(r["statut"] == "accepte" for r in resultats))
        if decision.erreur and demande and not dit["phrases"]:
            # Claude indisponible : le serveur répond seul à « quel mur ? », comme sans conversation.
            self._annonce = f"{self._annonce} {self._texte_demande(demande, contexte.phrase)}".strip()
        if self._paroles == paroles and not dit["question"] and quelque_chose:
            # Claude n'a pas posé de question : une interprétation à confirmer, sinon la question du parcours (la visite
            # reprend), sauf pendant une pause.
            suite = dit["phrases"] > 0
            mesure_question = None if suite else mesure
            for doute in (*_normaliser(probables), *invraisemblables):
                if (doute := self._resoudre({**doute, "note": doute.get("note") or "interprété par Claude"})) and await self._confirmer(
                        doute, reference, mesure_question, suite=suite):
                    break
            else:
                if not self.en_pause and not await self._question_du_parcours(reference, mesure_question, reposer=en_attente, suite=suite):
                    await self._annoncer(reference, mesure_question)
        self.journaliser("decision", mode="conversation", dire=decision.dire, cible=decision.cible, commandes=commandes,
                         resultats=resultats, invraisemblables=ecartees, erreur=decision.erreur, brut=decision.brut[:2000],
                         mesures=mesure)
        if decision.erreur:
            await self._envoyer({"type": "erreur", "message": f"Assistant : {decision.erreur}"})
        await self.envoyer_etat()

    def _deja_note(self, resultats: list[dict]) -> list[str]:
        """Ce que les règles ont noté pour cette phrase, dit à Claude (éléments créés compris : il peut les retirer)."""
        lignes = []
        for r in resultats:
            action = r["action"]
            if r["statut"] != "accepte":
                continue
            if action.get("outil") == "signaler_element" and not action.get("element_id") and r.get("element"):
                try:
                    element = self.checklist.trouver_element(r["element"])
                except ValueError:
                    continue
                lieu = f"pièce {self.checklist.nom_piece(element.piece)}" if element.piece else "logement"
                lignes.append(f"nouvel élément {element.id} (« {element.description} », {lieu})")
            elif action.get("outil") in ("enregistrer_reponse", "marquer_sans_objet", "copier"):
                lignes.append(f"{r.get('element') or action.get('type')}.{action.get('champ')} = {action.get('valeur') or 'sans objet'}")
            elif action.get("outil") in ("compter", "orienter", "piece_courante", "cloturer", "regle"):
                detail = action.get("nombre") or action.get("orientation") or action.get("nom") or action.get("type") or ""
                lignes.append(f"{action['outil']} {r.get('element') or ''} {detail}".replace("  ", " ").strip())
        return lignes

    def _prochaine_question(self, en_attente: str = ""):
        """La question que le parcours poserait maintenant (calculée à blanc : rien n'est noté comme demandé)."""
        if self.en_pause:
            return None
        for plan in parcours.questions(self.checklist, self._dernier_element_id):
            if not self.questions.filtrer(plan.texte, plan.code, self.checklist, time.monotonic(), cle=plan.cle, reposer=en_attente,
                                          a_blanc=True)[2]:
                return plan
        return None

    def _commandes(self, actions: list[dict], pre_rempli: dict) -> tuple[list[dict], list[str]]:
        """Actions de Claude propres à la conversation : pause, reprise, annulation d'un pré-remplissage. Une valeur de
        Claude remplace celle que les règles avaient pré-remplie dans la même phrase, sans contradiction : les règles ne
        le contredisent jamais. Renvoie (autres actions, commandes appliquées)."""
        reste, commandes = [], []
        for action in actions:
            outil = action.get("outil")
            if outil == "pause":
                self.en_pause = True
                commandes.append("pause")
            elif outil == "reprendre":
                self.en_pause = False
                commandes.append("reprendre")
            elif outil == "annuler":
                # Un pré-remplissage faux de cette phrase, ou ce qu'il demande d'oublier (« oublie ce que je viens de dire
                # sur la fenêtre ») : la valeur revient à la précédente ; sans champ, l'élément est retiré.
                ident, champ = str(action.get("element_id") or "").strip().upper(), str(action.get("champ") or "").strip()
                if champ and (ident, champ) in pre_rempli["valeurs"]:
                    self._retirer_pre_rempli(ident, champ, pre_rempli)
                    commandes.append(f"annuler {ident}.{champ}")
                elif champ and self._oublier_valeur(ident, champ):
                    commandes.append(f"annuler {ident}.{champ}")
                elif not champ and self._oublier_element(ident):
                    commandes.append(f"annuler {ident}")
            else:
                if outil == "enregistrer_reponse" and (str(action.get("element_id") or "").strip().upper(), action.get("champ")) in pre_rempli["valeurs"]:
                    self._retirer_pre_rempli(str(action["element_id"]).strip().upper(), str(action["champ"]), pre_rempli)
                reste.append(action)
        if commandes:
            self.journaliser("commandes", commandes=commandes)
        return reste, commandes

    def _oublier_valeur(self, element_id: str, champ: str) -> bool:
        try:
            element = self.checklist.trouver_element(element_id)
        except ValueError:
            return False
        if not element.valeurs.get(champ):
            return False
        element.valeurs[champ].pop()
        if not element.valeurs[champ]:
            del element.valeurs[champ]
        return True

    def _oublier_element(self, element_id: str) -> bool:
        try:
            element = self.checklist.trouver_element(element_id)
        except ValueError:
            return False
        if element.type in TOUJOURS_PRESENTS:  # le plafond et le plancher existent toujours : on oublie leurs valeurs
            element.valeurs.clear()
        else:
            self.checklist.retirer(element_id)
        return True

    def _retirer_pre_rempli(self, element_id: str, champ: str, pre_rempli: dict) -> None:
        try:
            element = self.checklist.trouver_element(element_id)
        except ValueError:
            return
        historique = element.valeurs.get(champ, [])
        if historique and historique[-1].citation in {" ".join(p.split()) for p in pre_rempli["phrases"]}:
            historique.pop()
            if not historique:
                del element.valeurs[champ]
            # La contradiction relevée par ce pré-remplissage n'en est plus une.
            self.checklist.signalements[pre_rempli["signalements"]:] = [
                s for s in self.checklist.signalements[pre_rempli["signalements"]:] if not (s.element_id == element_id and s.champ == champ)]

    async def _noter(self, texte: str, contexte: Contexte, lot: list[dict]) -> tuple:
        """Extraction immédiate d'une phrase et application à la checklist : (extraction, résultats, valeurs notées,
        proposition à confirmer). Une valeur invraisemblable (un mur de 30 m de long) n'est jamais notée : sa
        lecture probable devient la proposition."""
        signales = len(self.checklist.signalements)
        extraction = extraire(texte, self.checklist, self._cible)
        actions, invraisemblables, ecartees = plausibilite.filtrer(extraction.actions)
        resultats = appliquer(self.checklist, actions, contexte.t, self._phrases_recentes(contexte) + [texte])
        notes = self._compter(resultats)
        self._noter_contradictions(signales)
        self._situer(resultats, lot[0]["t_debut"], lot[-1]["t_fin"])
        proposition = extraction.proposition or next(filter(None, (self._resoudre(p) for p in invraisemblables)), None)
        self.journaliser("extraction", texte=texte, resultats=resultats, devines=extraction.devines, contradictions=self._annonce,
                         invraisemblables=ecartees, demande=extraction.demande)
        if resultats:
            await self._envoyer_actions(resultats, "extraction")
        return extraction, resultats, notes, proposition

    async def _confirmer(self, proposition: dict, reference: float, mesure: dict | None, suite: bool = False) -> bool:
        """« J'ai compris eau chaude, c'est bien ça ? » : une seule fois par valeur proposée. Vrai si posée."""
        if not proposition.get("element_id") or not proposition.get("champ") or not proposition.get("valeur"):
            return False
        try:
            type_element = proposition.get("type") or self.checklist.trouver_element(proposition["element_id"]).type
        except ValueError:
            return False
        cible = Cible("confirmation", type_element, proposition["champ"], proposition["element_id"], source=proposition["valeur"])
        texte = proposition.get("question") or f"J'ai compris {proposition['valeur']}, c'est bien ça ?"
        maintenant = time.monotonic()
        question, cible, raison, cle = self.questions.filtrer(texte, cible.code, self.checklist, maintenant)
        if raison:
            return False
        self.journaliser("confirmation_demandee", proposition=proposition)
        if mesure is not None:
            mesure["question_s"] = round(maintenant - reference, 3)
            mesure["question_dite"] = True
        await self.dire(question, reference, mesure, cible=cible, cle=cle, une_fois=True, suite=suite)
        return True

    async def _question_du_parcours(self, reference: float, mesure: dict | None, reposer: str = "", suite: bool = False) -> bool:
        """Pose la première question du parcours que les garde-fous acceptent. Vrai si une question part."""
        if self.en_pause:
            return False
        maintenant = time.monotonic()
        dernier_id = self._dernier_element_id
        for plan in parcours.questions(self.checklist, dernier_id):
            question, cible, raison, cle = self.questions.filtrer(plan.texte, plan.code, self.checklist, maintenant, cle=plan.cle,
                                                                  reposer=reposer)
            if not raison:
                if mesure is not None:
                    mesure["question_s"] = round(maintenant - reference, 3)
                    mesure["question_dite"] = True
                await self.dire(question, reference, mesure, cible=cible, cle=cle, une_fois=True, suite=suite)
                return True
        return False

    async def _completer(self, contexte: Contexte) -> None:
        """Claude relit une phrase longue déjà traitée : il ajoute seulement ce que les règles ont manqué."""
        try:
            self._compteurs["relectures_claude"] += 1
            decision = await self.cerveau.decider(contexte, None)
            # Relecture : seulement des valeurs sûres, et rien sur un champ dont la confirmation est en cours.
            attente = self._cible if self._cible and self._cible.genre == "confirmation" else None
            actions = [a for a in decision.actions if a.get("certitude") != "probable"
                       and not (attente and a.get("element_id") == attente.element_id and a.get("champ") == attente.champ)]
            # Relecture : une valeur invraisemblable (« 30 m » de long) est écartée sans question (la question est déjà partie).
            actions, _, ecartees = plausibilite.filtrer(_normaliser(actions))
            if ecartees:
                self.journaliser("invraisemblables", source="complement", actions=ecartees)
            resultats = appliquer(self.checklist, actions, contexte.t, self._phrases_recentes(contexte))
            self._compter(resultats)
            self.journaliser("complement", resultats=resultats, erreur=decision.erreur, brut=decision.brut[:2000], mesures=decision.mesures)
            if any(r["statut"] == "accepte" for r in resultats):
                await self._envoyer_actions(resultats, "complement")
                await self.envoyer_etat()
        except Exception as e:
            log.exception("Complément de Claude")
            self.journaliser("erreur", etape="complement", message=str(e))

    async def _repondre_a_la_demande(self, demande: str, reference: float, mesure: dict | None, texte: str = "") -> None:
        """« Quel mur ? » : son nom parlant (et sa vignette à l'écran). « Il te faut quoi d'autre ? » : ce qui manque
        pour l'élément de la question. Puis la question en attente est reposée, une fois."""
        self._annonce = self._texte_demande(demande, texte)
        self.questions.autoriser_encore(self._derniere_cle)
        if not await self._question_du_parcours(reference, mesure, reposer=self._derniere_cle):
            await self._annoncer(reference, mesure)

    def _texte_demande(self, demande: str, texte: str = "") -> str:
        """Ce qu'il faut répondre à « quel mur ? » ou à « il te faut quoi d'autre ? » (dit par le serveur, ou proposé à
        Claude en conversation)."""
        annonce = ""
        element = self._element_en_attente()
        if demande == "manques" and (m := re.search(r"\b(mur|fen[eê]tre|radiateur|plafond|plancher)", cle_texte(texte))):
            # « Il te faut quoi d'autre sur ce mur ? » : le mur dont on parlait, même si la question portait sur autre chose.
            type_vise = {"fenetre": "fenetre", "radiateur": "emetteur"}.get(m.group(1), m.group(1))
            ident = self.checklist.dernier.get(type_vise)
            vise = self.checklist.element_de_piece(type_vise) if type_vise in ("plafond", "plancher") else (
                self.checklist.trouver_element(ident) if ident else None)
            element = vise or element
        if element is not None:
            nom = self.checklist.nom(element, demonstratif=False)
            self.checklist.dernier[element.type] = element.id  # on vient de le nommer : « Il est isolé ? » suffit ensuite
            if demande == "lequel":
                affiche = ", affiché à l'écran" if element.image else ""
                annonce = f"Je parle {_de(nom)}{affiche}."
            else:
                manques = [LIBELLES_ORAUX.get(c.cle, c.libelle) for c in element.champs_manquants()]
                liste = ", ".join(manques[:-1]) + f" et {manques[-1]}" if len(manques) > 1 else "".join(manques)
                annonce = f"Pour {nom}, il me manque {liste}." if manques else f"Pour {nom}, j'ai tout."
        elif demande == "manques":
            manques = self.checklist.manques_piece()
            annonce = f"Dans cette pièce, il me manque {len(manques)} informations, à l'écran." if manques else "Rien ne manque ici."
        elif self._cible is not None and self._cible.type == "mur":
            annonce = "Un mur qu'on n'a pas encore décrit."  # « Il reste un mur… » « Quel mur ? »
        return annonce

    def _element_en_attente(self) -> Element | None:
        if self._cible is not None and self._cible.element_id:
            try:
                return self.checklist.trouver_element(self._cible.element_id)
            except ValueError:
                return None
        return None

    def _resoudre(self, proposition: dict) -> dict | None:
        """Une proposition sur un élément créé par la même phrase (nommé par sa description) : son identifiant."""
        if proposition.get("element_id"):
            return proposition
        description = cle_texte(str(proposition.get("description", "")))
        element = next((e for e in reversed(self.checklist.elements) if e.type == proposition.get("type")
                        and cle_texte(e.description) == description), None)
        return {**proposition, "element_id": element.id} if element is not None else None

    def _situer(self, resultats: list[dict], t_debut: float, t_fin: float) -> None:
        """Éléments créés ou désignés par cette phrase : leur vignette (l'image filmée pendant la phrase, montrée avec
        les questions sur eux) et leur orientation d'après la boussole du téléphone (« le mur nord »)."""
        visee = self.boussole.visee(t_debut, t_fin)
        image = min(self.images, key=lambda i: abs(i.t - t_fin), default=None)
        for r in resultats:
            if r["statut"] != "accepte" or not r.get("element"):
                continue
            try:
                element = self.checklist.trouver_element(r["element"])
            except ValueError:
                continue
            if element.piece is None or element.type in ("plafond", "plancher"):
                continue
            if not element.image and image is not None and image.chemin is not None:
                element.image = image.chemin.name
            if visee is not None and element.type in ORIENTABLES and element.cap is None and element.lacet is None:
                # Filmé de face depuis l'intérieur : son orientation est le cap de la caméra (boussole.py).
                self.checklist.mesurer(element.id, visee)
                if self.checklist.boussole_fiabilite == "faible" and not self._calibration_demandee:
                    self._calibration_demandee = True
                    self._annonce = f"{self._annonce} Boussole perturbée : faites un 8 avec le téléphone.".strip()

    def _noter_contradictions(self, depuis: int) -> None:
        """Contradictions relevées par la dernière phrase : la dernière valeur est gardée, et c'est dit au
        diagnostiqueur avant la question suivante (« Noté : parpaing au lieu de brique. »)."""
        textes = list(dict.fromkeys(s.texte for s in self.checklist.signalements[depuis:]))
        if textes:
            self._annonce = " ".join([self._annonce, *textes[:2]]).strip()

    async def _annoncer(self, reference: float, mesure: dict | None) -> bool:
        """Contradiction à dire alors qu'aucune question ne part : dite seule. Vrai si quelque chose est dit."""
        if not self._annonce:
            return False
        await self.dire(self._annonce, reference, mesure, forcer=True)
        return True

    def _compter(self, resultats: list[dict]) -> list[dict]:
        """Met à jour les compteurs ; renvoie les valeurs acceptées (enregistrées ou « sans objet »)."""
        notes = [r for r in resultats if r["action"].get("outil") in ("enregistrer_reponse", "marquer_sans_objet", "copier")]
        self._compteurs["acceptees"] += sum(r["statut"] == "accepte" for r in notes)
        self._compteurs["refusees"] += sum(r["statut"] == "refuse" for r in notes)
        if any(r["action"].get("outil") == "piece_courante" and r["statut"] == "accepte" for r in resultats):
            self._veille_bientot = True
        return [r for r in notes if r["statut"] == "accepte"]

    async def _envoyer_actions(self, resultats: list[dict], source: str) -> None:
        await self._envoyer({"type": "actions", "source": source, "resultats": [
            {"outil": r["action"].get("outil"), "statut": r["statut"], "raison": r["raison"], "champ": r["action"].get("champ"),
             "valeur": r["action"].get("valeur"), "nombre": r["action"].get("nombre"), "element": r.get("element"),
             "type": r["action"].get("type"), "description": r["action"].get("description")}
            for r in resultats
        ]})

    async def _bip(self, latence_s: float | None = None) -> None:
        self._compteurs["bips"] += 1
        await self._envoyer({"type": "bip", "latence_s": latence_s})

    def _images_pour(self, t_debut: float, t_fin: float) -> list[ImageInstant]:
        """Images de la phrase : la plus proche de la fin, du milieu et du début (3 au plus)."""
        images = list(self.images)
        if not images:
            return []
        choisies: list[ImageInstant] = []
        for cible in (t_fin, (t_debut + t_fin) / 2, t_debut):
            image = min(images, key=lambda i: abs(i.t - cible))
            if image not in choisies:
                choisies.append(image)
        return sorted(choisies, key=lambda i: i.t)

    def _phrases_recentes(self, contexte: Contexte) -> list[str]:
        recentes = [texte for _, t_fin, texte in self.phrases if t_fin >= contexte.t - 90]
        # Phrases regroupées : citation à cheval ; second avis de Whisper : Claude peut citer l'une ou l'autre transcription.
        return recentes + [p for p in (contexte.phrase, contexte.autre_transcription) if p]

    async def _decider(self, cerveau, contexte: Contexte, reference: float, mesure: dict) -> Decision:
        """Claude, pour une phrase que les règles n'ont pas comprise. Il note ce qu'il comprend ; il ne
        parle que pour une précision indispensable. Sinon, le parcours pose la question suivante."""
        await self._pret.wait()
        debut = time.perf_counter()
        filtrees: list[str] = []

        async def sur_dire(texte: str, code_cible: str) -> None:
            if mesure.get("question_dite"):
                return
            question, cible, raison, cle = self.questions.filtrer(texte, code_cible, self.checklist, time.monotonic())
            if raison:
                filtrees.append(raison)
                self.journaliser("question_filtree", texte=texte, cible=code_cible, raison=raison)
                return
            mesure["cerveau_dire_s"] = round(time.perf_counter() - debut, 3)
            mesure["question_s"] = round(time.monotonic() - reference, 3)
            mesure["question_dite"] = True
            await self.dire(question, reference, mesure, cible=cible, cle=cle)

        decision = await cerveau.decider(contexte, sur_dire)
        mesure["cerveau_total_s"] = round(time.perf_counter() - debut, 3)
        mesure["cerveau"] = decision.mesures
        # Interprétation seulement probable : pas notée, proposée au diagnostiqueur (« J'ai compris…, c'est bien ça ? »).
        probables = [a for a in decision.actions if a.get("certitude") == "probable" and a.get("outil") == "enregistrer_reponse"]
        actions, invraisemblables, ecartees = plausibilite.filtrer(_normaliser(a for a in decision.actions if a not in probables))
        signales = len(self.checklist.signalements)
        resultats = appliquer(self.checklist, actions, contexte.t, self._phrases_recentes(contexte))
        notes = self._compter(resultats)
        self._noter_contradictions(signales)
        if t_phrase := contexte.t_phrase:
            self._situer(resultats, *t_phrase)
        if resultats:
            await self._envoyer_actions(resultats, "cerveau")
        if probables and not mesure.get("question_dite"):
            await self._confirmer({**_normaliser(probables)[0], "note": "interprété par Claude"}, reference, mesure)
        if invraisemblables and not mesure.get("question_dite") and (proposition := self._resoudre(invraisemblables[0])):
            await self._confirmer(proposition, reference, mesure)
        if any(r["statut"] == "accepte" for r in resultats) and not mesure.get("question_dite"):
            if not await self._question_du_parcours(reference, mesure) and not await self._annoncer(reference, mesure) and notes:
                await self._bip()
        self.journaliser("decision", mode=contexte.mode, dire=decision.dire, cible=decision.cible, filtrees=filtrees,
                         resultats=resultats, erreur=decision.erreur, brut=decision.brut[:2000], mesures=mesure)
        if decision.erreur:
            await self._envoyer({"type": "erreur", "message": f"Assistant : {decision.erreur}"})
        await self.envoyer_etat()
        return decision

    async def dire(self, texte: str, reference: float, mesure: dict | None = None, forcer: bool = False,
                   cible: Cible | None = None, cle: str = "", une_fois: bool = False, suite: bool = False,
                   question: bool = True) -> None:
        """Envoie une phrase à dire au téléphone, dans la limite du plafond de questions par minute. `suite` : la phrase
        prolonge la précédente (réponse de Claude lue phrase par phrase) ; `question=False` : une phrase qui n'est pas
        une question (« Un pont thermique, c'est… ») ne change pas la question en attente."""
        maintenant = time.monotonic()
        while self._questions and maintenant - self._questions[0] > 60:
            self._questions.popleft()
        if not forcer and not suite and len(self._questions) >= self.reglages.questions_par_minute:
            self._compteurs["retenues"] += 1
            self.journaliser("question_retenue", texte=texte, raison="plafond de questions par minute")
            return
        if self._annonce:
            texte = texte if texte == self._annonce else f"{self._annonce} {texte}"
            self._annonce = ""
        self._compteur_dire += 1
        if not suite:
            self._questions.append(maintenant)
        self._derniere_question = maintenant
        self._compteurs["questions" if question else "phrases_dites"] += 1
        if cle:
            self.questions.noter(cle, maintenant, une_fois)
        if not forcer and question:
            self._cible = cible
            self._derniere_cle = cle
            self._dernier_element_id = cible.element_id if cible and cible.element_id else None
            self._derniere_question_texte = f"{cible.code} : « {texte} »" if cible else f"« {texte} »"
        self.dialogue.append(f"[{horodatage(self.t_video)}] Assistant : « {texte} »")
        if mesure is not None:
            self._mesure_par_dire[self._compteur_dire] = (mesure, reference)
        latence = round(maintenant - reference, 2) if mesure is not None else None
        image = self._vignette(cible)
        self.journaliser("dire", id=self._compteur_dire, texte=texte, cible=cible.code if cible else "", muet=self.muet, latence_s=latence)
        await self._envoyer({"type": "dire", "id": self._compteur_dire, "texte": texte, "muet": self.muet, "latence_s": latence,
                             "image": image, "suite": suite})

    def _vignette(self, cible: Cible | None) -> str | None:
        """Adresse de l'image de l'élément dont parle la question, pour que le diagnostiqueur sache lequel c'est."""
        if cible is None or not cible.element_id:
            return None
        try:
            element = self.checklist.trouver_element(cible.element_id)
        except ValueError:
            return None
        return f"/api/sessions/{self.id}/images/{element.image}" if element.image else None

    # --- Veille ---------------------------------------------------------------------------------

    async def _boucle_veille(self) -> None:
        await self._pret.wait()
        derniere = time.monotonic()
        while True:
            await asyncio.sleep(1)
            maintenant = time.monotonic()
            if self.occupe or self._en_parole or maintenant - self._fin_parole < 2:
                continue
            if not (self._veille_bientot or maintenant - derniere >= self.reglages.veille_s):
                continue
            if not self.images or self.images[-1].t == self._image_veille:
                continue  # rien de nouveau filmé
            derniere, self._veille_bientot = maintenant, False
            self._image_veille = self.images[-1].t
            try:
                await self._veiller()
            except Exception as e:
                log.exception("Veille")
                self.journaliser("erreur", etape="veille", message=str(e))

    async def _veiller(self) -> None:
        """Claude regarde les images pendant un silence et signale les éléments visibles (fenêtre,
        radiateur…). La veille ne parle pas : c'est le parcours qui en parlera au bon moment."""
        self._compteurs["veilles"] += 1
        contexte = Contexte(mode="veille", t=self.t_video, checklist=self.checklist, dialogue=self.dialogue[-8:],
                            images=list(self.images)[-2:],
                            questions_recentes=self.questions.recentes(time.monotonic(), self.checklist.piece_courante))
        debut = time.perf_counter()
        decision = await self.cerveau_veille.decider(contexte, None)
        actions = [a for a in decision.actions if a.get("outil") in ("signaler_element", "piece_courante")]
        resultats = appliquer(self.checklist, actions, contexte.t, self._phrases_recentes(contexte))
        self._compter(resultats)
        self.journaliser("decision", mode="veille", resultats=resultats, erreur=decision.erreur, brut=decision.brut[:2000],
                         mesures={"cerveau_total_s": round(time.perf_counter() - debut, 3), "cerveau": decision.mesures})
        if resultats:
            await self._envoyer_actions(resultats, "veille")
            await self.envoyer_etat()

    # --- Fin et bilan ---------------------------------------------------------------------------

    async def fin_visite(self) -> None:
        texte = rappel_fin(self.checklist)
        await self.dire(texte, time.monotonic(), forcer=True)
        await self._envoyer({"type": "bilan", "bilan": self.bilan(), "manques": [
            {"piece": self.checklist.nom_piece(m.piece) if m.piece else "Logement", "libelle": m.libelle}
            for m in self.checklist.manques_visite()
        ]})

    def bilan(self) -> dict:
        def stats(valeurs: list[float]) -> dict | None:
            valeurs = [v for v in valeurs if isinstance(v, (int, float))]
            if not valeurs:
                return None
            valeurs.sort()
            return {"n": len(valeurs), "mediane": round(statistics.median(valeurs), 2),
                    "p90": round(valeurs[min(len(valeurs) - 1, int(0.9 * len(valeurs)))], 2), "max": round(valeurs[-1], 2)}

        phrases = [m for m in self.mesures if m.get("source") in ("audio", "texte")]
        audio = [m for m in phrases if m["source"] == "audio"]
        cout = sum((m.get("cerveau") or {}).get("cout_equivalent_api_usd") or 0 for m in self.mesures)
        return {
            "session": self.id,
            "cerveau": self.cerveau.nom,
            "transcription": self.transcripteur.nom,
            "duree_video_s": round(self.t_video, 1),
            "phrases": len(self.phrases),
            "appels_reponse": len(phrases),  # moins que de phrases quand des phrases ont été regroupées
            "appels_avec_reflexion": sum(bool((m.get("cerveau") or {}).get("reflexion")) for m in self.mesures),
            **self._compteurs,
            "pieces": [{"nom": p.nom, "taux_remplissage": self.checklist.taux_remplissage(cle)} for cle, p in self.checklist.pieces.items()],
            "manques_visite": len(self.checklist.manques_visite()),
            "regles_dites": len(self.checklist.regles),
            "contradictions_signalees": [s.texte for s in self.checklist.signalements],
            "latences_s": {
                "fin_de_phrase (silence attendu)": self.reglages.fin_silence_s,
                "attente_dans_la_file": stats([m.get("attente_s") for m in audio]),
                "transcription": stats([m.get("transcription_s") for m in audio]),
                "fin_de_phrase_detectee_a_question_prete": stats([m.get("question_s") for m in audio]),
                "texte_ecrit_a_question_prete": stats([m.get("question_s") for m in phrases if m["source"] == "texte"]),
                "claude_premier_mot": stats([(m.get("cerveau") or {}).get("premier_mot_s") for m in phrases]),
                "claude_question_prete": stats([m.get("cerveau_dire_s") for m in phrases]),
                "claude_total": stats([m.get("cerveau_total_s") for m in phrases]),
                "fin_de_phrase_detectee_a_voix": stats([m.get("voix_s") for m in audio]),
                "texte_ecrit_a_voix": stats([m.get("voix_s") for m in phrases if m["source"] == "texte"]),
            },
            "cout_equivalent_api_usd (non facturé avec l'abonnement)": round(cout, 4),
        }
