"""Étape 8 de Noah : le test du 22/10/2026 après l'étape 7 (sessions/20261022-120410-53ecb1, séjour + cuisine).

« Pas assez fluide, il s'arrête de parler, il répète, il ne prend pas toutes les infos, il ne comprend pas quand je change
de pièce, il ne repère pas bien les murs, il parle des lampes. » Chaque constat a ses cas ici, avec un faux Claude écrit à
l'avance (tests/test_conversation.py) et du son fabriqué quand il faut passer par la détection de parole."""

import asyncio
import time

import numpy as np

from assistant.boussole import Mesure
from assistant.cerveau import consignes
from assistant.extraction import normaliser
from assistant.lexique import corriger
from assistant.reglages import Reglages
from assistant.session import _DESIGNATION_MUR, RELANCE_S, RELANCES, Session, sans_accuse
from assistant.simulation import CerveauSimulation
from assistant.vad import TAUX, DetecteurPhrases
from test_conversation import CerveauScenario, attendre, dits, poli, suites, visite

BRUIT = np.random.default_rng(1)


def son(*morceaux) -> np.ndarray:
    """(durée en s, amplitude) : silence de fond, ou voix (sinusoïde)."""
    sortie = []
    for duree, amplitude in morceaux:
        n = int(duree * TAUX)
        if amplitude:
            sortie.append(amplitude * np.sin(2 * np.pi * 220 * np.arange(n) / TAUX))
        else:
            sortie.append(BRUIT.normal(0, 30, n))
    return np.concatenate(sortie).clip(-32768, 32767).astype("<i2")


class TranscripteurFactice:
    """Transcrit chaque phrase de son par le texte suivant de la liste."""

    nom = "factice"

    def __init__(self, textes):
        self.textes = list(textes)

    def prechauffer(self):
        pass

    def transcrire(self, audio):
        return self.textes.pop(0) if self.textes else ""


async def ouvrir(dossier, cerveau, transcripteur=None, cerveau_veille=None):
    reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=dossier, veille_s=1000,
                        questions_par_minute=60, conversation="claude")
    session = Session("fluidite", dossier, cerveau, cerveau_veille or CerveauSimulation(), transcripteur or TranscripteurFactice([]),
                      reglages)
    recus: list[dict] = []

    async def envoyer(message):
        recus.append(message)

    session.envoyer = envoyer
    await session.demarrer()
    return session, recus


async def parler(session, texte):
    await session.recevoir_controle({"type": "texte", "texte": texte})


async def jouer_son(session, signal, t0):
    for i in range(0, len(signal), 1600):
        await session.recevoir_audio(t0 + i / TAUX, signal[i:i + 1600].tobytes())


# --- 1. Silences : « il s'arrête de parler », « tu parles pas ? » -------------------------------------------------

def test_un_claquement_ne_coupe_plus_la_voix():
    # Mesuré sur le son de Noah : un claquement de 0,1 à 0,3 s juste après chaque phrase de l'assistant (le téléphone qui
    # bascule sa sortie son). Il était pris pour une prise de parole et coupait la voix.
    d = DetecteurPhrases()
    evenements = []
    for i, morceau in enumerate(np.array_split(son((1.0, 0), (0.2, 8000), (1.5, 0)), 27)):
        evenements += d.ajouter(morceau.tobytes(), i * 0.1)
    assert [e.type for e in evenements] == ["debut", "fin"] and evenements[1].phrase is None  # ni « parole », ni phrase
    # Une vraie phrase est confirmée après 0,35 s de parole ; 0,6 s quand l'assistant parle (son écho n'est pas une parole).
    d = DetecteurPhrases()
    d.ia_parle = True
    evenements = []
    for i, morceau in enumerate(np.array_split(son((1.0, 0), (0.5, 8000), (1.5, 0)), 30)):
        evenements += d.ajouter(morceau.tobytes(), i * 0.1)
    assert "parole" not in [e.type for e in evenements]


def test_reponse_coupee_par_un_bruit_redite(tmp_path):
    cerveau = CerveauScenario(poli({"C'est quoi un pont thermique ?": "Une fuite de chaleur. Souvent aux jonctions."}), pause_s=0.3)

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau, TranscripteurFactice(["."]))
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        debut = len(recus)
        await parler(session, "C'est quoi un pont thermique ?")
        await asyncio.sleep(0.15)
        await jouer_son(session, son((0.5, 0), (0.5, 8000), (1.0, 0)), 10.0)  # 0,5 s de bruit fort, transcrit « . »
        await attendre(session)
        await session.terminer()
        return session, recus[debut:]

    session, recus = asyncio.run(scenario())
    assert any(m["type"] == "parole_debut" for m in recus)  # l'assistant s'est tu…
    # … puis, ce n'était qu'un bruit : la suite de sa réponse est redite, et « . » n'est jamais allé à Claude.
    assert dits(recus) == ["Une fuite de chaleur.", "Souvent aux jonctions.", "Décrivez le premier mur."]
    assert "." not in cerveau.phrases


def test_reponse_coupee_par_une_vraie_phrase_pas_redite(tmp_path):
    cerveau = CerveauScenario(poli({"C'est quoi un pont thermique ?": "Une fuite de chaleur. Souvent aux jonctions."}), pause_s=0.3)

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau, TranscripteurFactice(["Ce mur donne dehors."]))
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        debut = len(recus)
        await parler(session, "C'est quoi un pont thermique ?")
        await asyncio.sleep(0.15)
        await jouer_son(session, son((0.5, 0), (1.0, 8000), (1.0, 0)), 10.0)
        await attendre(session)
        await session.terminer()
        return recus[debut:]

    recus = asyncio.run(scenario())
    assert dits(recus) == ["Une fuite de chaleur.", "Ce mur est en quoi ?"]  # sa phrase a sa propre réponse


def test_toujours_une_voix_en_moins_de_2_s(tmp_path):
    # Claude réfléchit avant d'écrire (~1,8 s en médiane, 4,7 s au pire au test de Noah).
    class ClaudeLent(CerveauScenario):
        async def decider(self, contexte, sur_dire=None):
            await asyncio.sleep(1.9)
            return await super().decider(contexte, sur_dire)

    cerveau = ClaudeLent(poli({"Comment ça va ?": "Très bien, merci."}))
    _, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Comment ça va ?", "Ce mur donne dehors.", "Euh."], cerveau))
    # Rien de noté : « Alors… » au bout de 1,4 s, puis la réponse de Claude enchaîne sans couper.
    assert dits(apres[1])[0] in RELANCES and dits(apres[1])[1:] == ["Très bien, merci.", "Décrivez le premier mur."]
    assert suites(apres[1]) == [False, True, True]
    relance = next(m for m in apres[1] if m["type"] == "dire")
    assert RELANCE_S <= relance["latence_s"] < 1.6
    # Quelque chose de noté : un bip tout de suite (étape 9 : sans mots), Claude enchaîne avec la question.
    bip = next(m for m in apres[2] if m["type"] == "bip")
    assert bip["latence_s"] < 0.3 and dits(apres[2]) == ["Ce mur est en quoi ?"]
    # Un mot isolé (débris, « euh ») : pas de relance.
    assert not set(dits(apres[3])) & set(RELANCES)


def test_phrase_inachevee_pre_remplie_sans_attendre(tmp_path):
    cerveau = CerveauScenario(poli())

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        debut = len(recus)
        await parler(session, "Ce mur donne dehors, en brique, et l'isolant c'est du")
        await asyncio.sleep(0.5)
        await parler(session, "laine de verre.")
        await attendre(session)
        await session.terminer()
        return session, recus[debut:]

    session, recus = asyncio.run(scenario())
    # Bip tout de suite, sans attendre la fin (au test de Noah, la file restait bloquée 8 s) ; Claude, lui, a attendu la
    # suite et répond à l'ensemble, en un seul appel.
    assert next(m for m in recus if m["type"] == "bip")["latence_s"] < 0.3
    assert cerveau.phrases[-1] == "Ce mur donne dehors, en brique, et l'isolant c'est du laine de verre."


# --- 2. Hors sujet : « il parle des lampes » ---------------------------------------------------------------------

def test_jamais_de_decoration_et_un_bruit_ne_va_pas_a_claude(tmp_path):
    texte = consignes()
    assert "Tu ne parles QUE de ce qui sert au DPE" in texte and "Tu ne décris jamais la décoration" in texte
    # Au test de Noah, « . » (un bruit) était allé à Claude, qui avait décrit « un rideau, une lampe, un climatiseur ».
    cerveau = CerveauScenario(poli(defaut="Je vois une lampe."))
    _, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "."], cerveau))
    assert cerveau.phrases == ["Ici c'est le séjour."] and dits(apres[1]) == []


# --- 3. Infos perdues ou mal rangées -------------------------------------------------------------------------------

def test_phrase_sans_element_rangee_sur_l_element_en_cours(tmp_path):
    def repondre(contexte):
        if contexte.phrase == "Ici c'est le séjour.":
            return "Au-dessus du plafond : combles, terrasse ou logement ?", "PL1.donne_sur", []
        if contexte.phrase.startswith("Attends"):
            return "D'accord.", "", [{"outil": "pause"}]
        return "", "", []

    cerveau = CerveauScenario(repondre)
    session, _, _ = asyncio.run(visite(tmp_path, [
        "Ici c'est le séjour.",  # question sur le plafond…
        "Attends, je décris d'abord le mur.",
        "Ce mur donne dehors, il est en brique.",  # … mais il décrit le mur
        "L'isolant, c'est de la laine de verre 30 cm.",  # sans nommer d'élément : c'est le mur
    ], cerveau))
    c = session.checklist
    assert c.trouver_element("M1").valeur("isolation").valeur == "isolé laine de verre 30 cm"
    assert c.element_de_piece("plafond").valeur("isolation") is None  # au test de Noah, rangé sur le plafond
    assert "Élément en cours de description : M1" in cerveau.messages[-1]


def test_interpretation_probable_de_claude_notee_et_jamais_redemandee(tmp_path):
    voisin = {"outil": "enregistrer_reponse", "element_id": "M1", "champ": "donne_sur", "valeur": "local chauffé (voisin)",
              "citation": "c'est pas la mienne", "certitude": "probable"}
    cerveau = CerveauScenario(poli({"Il donne sur une autre maison derrière, mais c'est pas la mienne.": ("Le voisin, noté.", [voisin], True)},
                                   defaut=""))
    session, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur, là.",
                                                      "Il donne sur une autre maison derrière, mais c'est pas la mienne."], cerveau))
    valeur = session.checklist.trouver_element("M1").valeur("donne_sur")
    assert valeur.valeur == "local chauffé (voisin)" and "à vérifier" in valeur.note
    assert not [t for t in dits(apres[2]) if "donne sur" in t]  # au test de Noah, demandé encore deux fois


# --- 4. Phrases globales -------------------------------------------------------------------------------------------

def test_tous_les_murs_de_la_maison_en_brique(tmp_path):
    cerveau = CerveauScenario(poli(defaut=""))
    session, apres, _ = asyncio.run(visite(tmp_path, [
        "Ici c'est le séjour.", "Ce mur donne dehors.", "Tous les murs de la maison sont en briques.",
        "On passe dans la cuisine.", "Ce mur donne dehors, 20 centimètres, non isolé."], cerveau))
    c = session.checklist
    assert [r.valeurs for r in c.regles] == [{"materiau": "brique"}] and c.regles[0].piece is None  # tout le logement
    assert {e.id: e.valeur("materiau").valeur for e in c.elements if e.type == "mur"} == {"M1": "brique", "M2": "brique"}
    assert not [t for messages in apres[2:] for t in dits(messages) if "en quoi" in t]  # matériau plus jamais demandé


# --- 5. Changement de pièce ----------------------------------------------------------------------------------------

def test_changement_de_piece_dit_autrement(tmp_path):
    cerveau = CerveauScenario(poli(defaut=""))
    session, _, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Onant alors dans ce jour si fini après là, il y a un couloir."],
                                      cerveau))
    assert session.checklist.piece_courante == "couloir"
    assert not [e for e in session.checklist.elements if e.type == "mur"]  # plus de « mur côté couloir » inventé
    session, _, _ = asyncio.run(visite(tmp_path / "2", ["Ici c'est le séjour.", "Là c'est la cuisine."], cerveau))
    assert session.checklist.piece_courante == "cuisine"


def test_piece_reconnue_sur_les_images_demandee_puis_confirmee(tmp_path):
    veille = CerveauScenario(lambda contexte: ("", "", [{"outil": "piece_courante", "nom": "Cuisine", "citation": ""}]))
    cerveau = CerveauScenario(poli(defaut=""))

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau, cerveau_veille=veille)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        debut = len(recus)
        await session._veiller()  # il filme sans parler : Claude reconnaît une cuisine
        question = dits(recus[debut:])
        assert session.checklist.piece_courante == "sejour"  # pas décidé par l'image seule
        await parler(session, "Oui.")
        await attendre(session)
        await session.terminer()
        return session, question

    session, question = asyncio.run(scenario())
    assert question == ["On est dans la cuisine ?"]
    assert session.checklist.piece_courante == "cuisine"


# --- 6. « Ce mur, ce mur et ce mur » -------------------------------------------------------------------------------

def test_murs_montres_un_par_un_crees_avec_image_et_boussole(tmp_path):
    texte = "Bra sur qu'il y a cemur, cemur et cemur."  # transcription réelle (142,8 s)
    normalise = normaliser(texte)
    cerveau = CerveauScenario(poli(defaut="Noté."))

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        # Phrase de 10 à 20 s (son gardé : 1 s avant, 0,5 s après) : chaque « ce mur » est situé d'après sa place.
        instants = [10.0 + 10.0 * (m.start() + m.end()) / 2 / len(normalise)
                    for m in __import__("assistant.session", fromlist=["x"])._DESIGNATION_MUR.finditer(normalise)]
        for k, t in enumerate(instants):
            await session.recevoir_image(t, b"\xff\xd8image " + str(k).encode())
            for dt in (-0.2, 0.0, 0.2):
                session.boussole.ajouter(Mesure(t + dt, 90.0 * k, None, 5.0, 90.0))
        lot = [{"source": "audio", "texte": texte, "t_debut": 9.0, "t_fin": 20.5, "ligne": "", "reference": time.monotonic(),
                "attente_transcription_s": 0.0, "transcription_s": 0.0, "pret": time.monotonic(), "audio": None, "paroles": 99}]
        await session._repondre(lot)
        await attendre(session)
        await session.terminer()
        return session, instants, recus

    session, instants, recus = asyncio.run(scenario())
    murs = [e for e in session.checklist.elements if e.type == "mur"]
    assert len(instants) == 3 and len(murs) == 3
    assert [m.image for m in murs] == [f"{t:08.2f}.jpg" for t in instants]  # l'image de son instant
    assert [round(m.cap) for m in murs] == [0, 90, 180]  # la visée de la boussole à son instant
    assert "Murs montrés un par un" in cerveau.messages[-1] and len(cerveau.messages[-1].split("désigné à")) == 4
    assert not [t for t in dits(recus) if "autre mur" in t]  # plus de « un autre mur ? » : la question porte sur eux


# --- 7. Transcription : débris et mots collés ---------------------------------------------------------------------

def test_debris_et_mots_colles():
    assert corriger("Bra sur qu'il y a cemur, cemur et cemur.") == "Bra sur qu'il y a ce mur, ce mur et ce mur."
    assert corriger("a un murici. un murici et un movicie.") == "a un mur ici. un mur ici et un mur ici."
    assert corriger("Bra sur y a semur, semurure et semure.") == "Bra sur y a ce mur, ce mur et ce mur."  # rejeu du même son
    assert corriger("Qui faut quoi doute?") == "il te faut quoi d'autre?"
    assert corriger("Il te veut quoi d'ôte?") == "il te faut quoi d'autre?"
    assert "Pourourir" in consignes() and "débris" in consignes()


# --- Après le rejeu de la visite (étape 8, second passage) ------------------------------------------------------------

def test_claude_ne_redit_pas_note_apres_le_serveur(tmp_path):
    cerveau = CerveauScenario(poli(defaut="Noté, mur en brique."))
    _, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, en brique."], cerveau))
    assert dits(apres[1]) == ["Ce mur, quelle épaisseur ?"]  # étape 9 : ni « Noté », ni « Mur en brique »
    assert sans_accuse("Oui, brique, c'est noté.") == "Oui, brique." and sans_accuse("D'accord, noté.") == ""


def test_preciser_une_valeur_n_est_pas_une_contradiction(tmp_path):
    cerveau = CerveauScenario(poli(defaut=""))
    session, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, il est isolé.",
                                                      "L'isolant, c'est de la laine de verre 30 cm."], cerveau))
    assert session.checklist.trouver_element("M1").valeur("isolation").valeur == "isolé laine de verre 30 cm"
    assert not session.checklist.signalements and not [t for t in dits(apres[2]) if "au lieu de" in t]


def test_un_mur_dit_deux_fois_n_est_pas_une_designation():
    assert len(_DESIGNATION_MUR.findall(normaliser("Mais derrière un rideau, il y a toujours un un mur, c'est qu'un mur."))) == 0
    assert len(_DESIGNATION_MUR.findall(normaliser("Il y a ce mur, ce mur et ce mur."))) == 3
    assert len(_DESIGNATION_MUR.findall(normaliser("a un murici. un murici et un movicie."))) == 3


def test_l_element_en_cours_reste_dans_sa_piece(tmp_path):
    cerveau = CerveauScenario(poli(defaut=""))
    session, _, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne sur le voisin.",
                                                  "Après, il y a un couloir.", "S'il y a un couloir ?"], cerveau))
    assert session.checklist.piece_courante == "couloir"
    assert session.checklist.trouver_element("M1").valeur("donne_sur").valeur == "local chauffé (voisin)"  # pas « couloir »


def test_relance_meme_quand_claude_repond_encore(tmp_path):
    cerveau = CerveauScenario(poli({"Comment se construit une maison ?": "Sur des fondations. Puis les murs. Puis le toit."}),
                              pause_s=1.0)

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        await parler(session, "Comment se construit une maison ?")  # Claude parle 3 s
        await asyncio.sleep(1.2)
        debut = len(recus)
        await parler(session, "Et ça prend combien de temps ?")  # arrive pendant ce temps
        await attendre(session)
        await session.terminer()
        return recus[debut:]

    recus = asyncio.run(scenario())
    premiere = next(m for m in recus if m["type"] == "dire")
    assert premiere["texte"] in RELANCES and premiere["latence_s"] < 1.6  # sans attendre la fin de la réponse précédente
