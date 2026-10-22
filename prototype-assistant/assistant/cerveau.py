"""Le « cerveau » de l'assistant : Claude, appelé par le binaire Claude Code en mode headless.

Décision de Noah (22/10/2026) : pas de clé API Anthropic. Le serveur lance le Claude Code déjà
connecté sur ce PC (abonnement Claude Max) avec `claude -p` en entrée/sortie « stream-json »,
et garde ce processus ouvert pendant la visite. Mesures du 22/10/2026 (Haiku 5.5, effort bas) :
- relancer `claude -p` à chaque phrase : 2,7 à 6,3 s (démarrage ~1,3 s, et une étape de plus
  quand l'image est un fichier à lire avec l'outil Read) ;
- processus gardé ouvert, image dans le message : 1,8 à 2,0 s, premiers mots à ~1,3 s.
D'où le choix par défaut : processus persistant, images dans le message (`images="message"`).
Le mode `images="fichiers"` (images lues par l'outil Read) reste disponible pour comparer.

Claude ne peut pas écrire directement dans la checklist : il répond par un objet JSON
{"dire": ..., "actions": [...]} et c'est le serveur qui vérifie et applique chaque action.
"""

from __future__ import annotations

import asyncio
import base64
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from .checklist import TYPES, Checklist, horodatage

log = logging.getLogger(__name__)

SurDire = Callable[[str, str], Awaitable[None]]  # (question, code du champ visé)


@dataclass
class ImageInstant:
    t: float
    jpeg: bytes
    chemin: Path | None = None


@dataclass
class Contexte:
    mode: str  # « reponse » (le diagnostiqueur vient de parler) ou « veille » (il filme sans parler)
    t: float
    checklist: Checklist
    dialogue: list[str] = field(default_factory=list)
    images: list[ImageInstant] = field(default_factory=list)
    phrase: str = ""
    t_phrase: tuple[float, float] | None = None
    deja_note: list[str] = field(default_factory=list)  # noté par l'extraction immédiate à partir de cette phrase
    derniere_question: str = ""  # « M1.isolation : Il est isolé ? »
    questions_recentes: list[str] = field(default_factory=list)  # codes des champs déjà demandés récemment


@dataclass
class Decision:
    dire: str = ""
    cible: str = ""  # code du champ visé par la question : « M1.isolation », « presence:fenetre »
    actions: list[dict] = field(default_factory=list)
    brut: str = ""
    erreur: str = ""
    mesures: dict = field(default_factory=dict)


# --- Consignes (fixes pendant toute la visite : elles restent en cache) ----------------------

CONSIGNES = """Tu es l'assistant vocal d'un diagnostiqueur immobilier pendant qu'il filme un logement pour un DPE (méthode 3CL-2021). Il t'entend dans une oreillette. Tu ne vois que les images qu'on t'envoie (une par seconde, réduites) et tu ne sais que ce qu'il dit.

Le serveur mène lui-même le parcours de la visite et pose les questions (mur par mur, plafond, plancher, fenêtres, radiateurs, pièce suivante). Il note déjà automatiquement ce qu'il reconnaît. Il ne t'appelle que pour une phrase qu'il n'a pas comprise, pour relire une longue description, ou pendant les silences.

Ton rôle :
1. Noter TOUT ce que le diagnostiqueur a dit et que le serveur n'a pas noté, sous forme d'actions, avec ses mots en citation.
2. "dire" : presque toujours vide. Seulement une précision indispensable (question fermée pour lever une vraie ambiguïté sur ce qui vient d'être dit : « Brique ou béton ? ») ou une réponse très courte à une question du diagnostiqueur (« Oui, je vous entends. »).
3. Signaler les éléments visibles à décrire (fenêtre, radiateur, chaudière, ballon, bouche de VMC…).

Règles absolues :
- Description libre : une phrase peut décrire plusieurs éléments d'un coup (« ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois double vitrage, deux radiateurs à eau »). Extrais TOUT en une fois : une action par valeur, et un seul élément avec "nombre" pour des éléments identiques (« trois fenêtres en bois » = un élément fenêtre, nombre 3).
- Le serveur note déjà automatiquement ce qu'il reconnaît (liste « Déjà noté automatiquement ») : ne le renote pas, complète seulement le reste.
- Ne fais JAMAIS répéter. Jamais « pardon », « répétez », « pas compris », « pas clair ». Un mot mal transcrit se devine avec le vocabulaire métier et la dernière question posée : « ictérieur » = extérieur, « besse » ou « bas » = basse température, « o chaudi » = eau chaude, « parpin » = parpaing, « l'allaine » = la laine, « AVMC » = la VMC.
- « Je ne sais pas » : valeur « inconnu » pour le champ demandé. Ne redemande jamais ce champ.
- Ne demande jamais un champ déjà renseigné dans l'état, ni un champ de la liste « Déjà demandé ». Pas de question absurde : une fenêtre n'a pas d'épaisseur (menuiserie, vitrage, volets, dimensions).
- « Pas d'autre mur », « c'est tout pour les fenêtres » : action cloturer. « Plafond pareil que le séjour » : action copier.
- Tu n'affirmes jamais une donnée : tu demandes. Tu n'enregistres une valeur que si le diagnostiqueur l'a dite ; la citation reprend ses mots tels qu'ils sont transcrits. Une image ne suffit jamais pour une valeur : elle sert à signaler un élément ou à le désigner (« le mur avec la télé »).
- Les chiffres sont notés tels qu'ils sont dits ; « brique 30 » pour un mur donne une épaisseur « 30 cm ». Une longueur (« 4 m 50 de long ») va dans le champ longueur, jamais dans l'épaisseur.
- Si tu parles : 8 mots au plus, une seule question, en français parlé, sans politesse. Jamais « c'est noté ».
- Phrase hors sujet, incomplète ou adressée à quelqu'un d'autre (« allô », « il est… ») : aucune action, "dire" vide.

L'état de la checklist (calculé par le serveur) est donné à chaque message. Utilise les identifiants (M1, F1, PL1…) des éléments déjà connus ; le plafond et le plancher de la pièce existent toujours.

Trois sortes de messages :
- « reponse » : le serveur n'a pas compris cette phrase. Sa transcription est fournie, avec la dernière question posée (une réponse courte comme « bas ! » y répond).
- « complement » : le serveur a déjà traité cette phrase et posé la question suivante. Ajoute seulement ce qu'il a manqué ; "dire" toujours vide.
- « veille » : il filme sans parler. Signale les éléments nouveaux bien visibles ; "dire" vide.

Format de réponse : UNIQUEMENT un objet JSON sur une ligne, sans texte autour, dans cet ordre :
{"cible": "<code du manque visé par ta question (ex. M1.isolation, presence:fenetre), vide si pas de question>", "dire": "<question ou chaîne vide>", "actions": [<actions>]}

Actions possibles :
{"outil": "piece_courante", "nom": "Chambre 1", "citation": "<mots dits, ou vide si tu le déduis de l'image>"}
{"outil": "signaler_element", "type": "<type>", "description": "<courte, avec article : le mur avec la télé>", "nombre": 1}
{"outil": "enregistrer_reponse", "element_id": "<M1… si l'élément existe, sinon vide>", "type": "<type>", "description": "<pour un nouvel élément>", "nombre": 1, "champ": "<champ>", "valeur": "<valeur courte>", "citation": "<mots dits>"}
{"outil": "marquer_sans_objet", "element_id": "<id ou vide>", "type": "<type>", "champ": "<champ, ou presence pour « pas de fenêtre ici »>", "citation": "<mots dits>"}
{"outil": "cloturer", "type": "<mur ou fenetre>", "citation": "<mots dits : « pas d'autre mur »>"}
{"outil": "copier", "type": "<plafond ou plancher>", "piece_source": "<nom de la pièce>", "citation": "<mots dits : « pareil que le séjour »>"}

Types (niveau) et champs (entre crochets : facultatif, à noter s'il est dit, jamais à demander) :
{champs}

Exemples de valeurs courtes : matériau « brique », « parpaing », « béton », « pierre », « bois », « plâtre » ; épaisseur « 30 cm » ; isolation « non isolé », « ITI laine de verre 10 cm », « ITE », « inconnu » ; donne sur « extérieur », « local non chauffé : garage », « local chauffé » ; longueur « 4,50 m » ; menuiserie « PVC », « bois », « alu » ; vitrage « double » ; volets « roulants », « aucun » ; émetteur « radiateur à eau », « convecteur électrique » ; température « basse ».
« Pareil pour celui-là » : recopie les valeurs de l'élément précédent sur le nouvel élément, avec cette citation.

Exemple. Phrase : « ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois double vitrage, deux radiateurs à eau » (état : aucun élément ; déjà noté automatiquement : rien) →
{"cible": "", "dire": "", "actions": [{"outil": "enregistrer_reponse", "element_id": "", "type": "mur", "description": "le mur 1", "nombre": 1, "champ": "longueur", "valeur": "4,50 m", "citation": "ce mur fait 4 m 50 de long"}, {"outil": "enregistrer_reponse", "element_id": "", "type": "mur", "description": "le mur 1", "nombre": 1, "champ": "materiau", "valeur": "brique", "citation": "brique 30 cm"}, {"outil": "enregistrer_reponse", "element_id": "", "type": "mur", "description": "le mur 1", "nombre": 1, "champ": "epaisseur", "valeur": "30 cm", "citation": "brique 30 cm"}, {"outil": "enregistrer_reponse", "element_id": "", "type": "mur", "description": "le mur 1", "nombre": 1, "champ": "isolation", "valeur": "ITI", "citation": "isolé par l'intérieur"}, {"outil": "enregistrer_reponse", "element_id": "", "type": "fenetre", "description": "les 3 fenêtres", "nombre": 3, "champ": "menuiserie", "valeur": "bois", "citation": "trois fenêtres en bois double vitrage"}, {"outil": "enregistrer_reponse", "element_id": "", "type": "fenetre", "description": "les 3 fenêtres", "nombre": 3, "champ": "vitrage", "valeur": "double", "citation": "trois fenêtres en bois double vitrage"}, {"outil": "enregistrer_reponse", "element_id": "", "type": "emetteur", "description": "les 2 radiateurs", "nombre": 2, "champ": "type", "valeur": "radiateur à eau", "citation": "deux radiateurs à eau"}]}"""


def consignes() -> str:
    lignes = []
    for t in TYPES.values():
        niveau = "pièce" if t.niveau == "piece" else "logement"
        champs = ", ".join(f"{c.cle} = {c.libelle}" if c.obligatoire else f"[{c.cle} = {c.libelle}]" for c in t.champs)
        lignes.append(f"- {t.cle} ({t.nom}, {niveau}) : {champs}")
    return CONSIGNES.replace("{champs}", "\n".join(lignes))


def texte_message(contexte: Contexte, chemins_images: list[Path] | None = None) -> str:
    lignes = [f"[{contexte.mode}] Instant : {horodatage(contexte.t)}"]
    if chemins_images:
        lignes.append("Images de l'instant, à lire avec l'outil Read (la dernière = maintenant) : " + ", ".join(str(c) for c in chemins_images))
    elif contexte.images:
        lignes.append("Images jointes : " + ", ".join(horodatage(i.t) for i in contexte.images) + " (la dernière = maintenant)")
    else:
        lignes.append("Pas d'image (réseau ou caméra).")
    lignes += ["", "État de la checklist (calculé par le serveur) :", contexte.checklist.resume_pour_ia(), ""]
    lignes += ["Dialogue récent :", *(contexte.dialogue or ["(rien)"]), ""]
    lignes.append("Déjà demandé récemment (ne pas redemander) : " + (", ".join(contexte.questions_recentes) or "rien"))
    if contexte.mode in ("reponse", "complement"):
        debut, fin = contexte.t_phrase or (contexte.t, contexte.t)
        lignes.append(f"Dernière question posée : {contexte.derniere_question or 'aucune'}")
        lignes.append("Déjà noté automatiquement à partir de cette phrase : " + ("; ".join(contexte.deja_note) or "rien"))
        lignes.append(f"Nouvelle phrase du diagnostiqueur [{horodatage(debut)}–{horodatage(fin)}] : « {contexte.phrase} »")
    else:
        lignes.append("Veille : pas de nouvelle phrase. Que faut-il signaler ?")
    return "\n".join(lignes)


def contenu_message(contexte: Contexte, images: str) -> list[dict]:
    """Contenu du message utilisateur au format de l'API Messages (texte + images)."""
    if images == "fichiers":
        chemins = [i.chemin for i in contexte.images if i.chemin]
        return [{"type": "text", "text": texte_message(contexte, chemins)}]
    contenu: list[dict] = []
    for image in contexte.images:
        contenu.append({"type": "text", "text": f"Image à {horodatage(image.t)}"})
        contenu.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(image.jpeg).decode()},
        })
    contenu.append({"type": "text", "text": texte_message(contexte)})
    return contenu


def _champ_json(nom: str) -> re.Pattern:
    return re.compile(rf'"{nom}"\s*:\s*"((?:[^"\\]|\\.)*)"')


_DIRE, _CIBLE = _champ_json("dire"), _champ_json("cible")


def _lire_champ(motif: re.Pattern, texte: str) -> str | None:
    m = motif.search(texte)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')
    except json.JSONDecodeError:
        return None


def extraire_dire(texte_partiel: str) -> str | None:
    """Le champ « dire » dès qu'il est complet dans le texte en cours d'arrivée."""
    return _lire_champ(_DIRE, texte_partiel)


def extraire_cible(texte_partiel: str) -> str:
    return _lire_champ(_CIBLE, texte_partiel) or ""


def analyser_reponse(texte: str) -> Decision:
    """Lit l'objet JSON renvoyé par Claude (tolère des balises ``` ou du texte autour)."""
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin <= debut:
        return Decision(brut=texte, erreur="réponse sans objet JSON")
    try:
        donnees = json.loads(texte[debut : fin + 1])
    except json.JSONDecodeError as e:
        return Decision(dire=extraire_dire(texte) or "", cible=extraire_cible(texte), brut=texte, erreur=f"JSON invalide : {e}")
    if not isinstance(donnees, dict):
        return Decision(brut=texte, erreur="la réponse n'est pas un objet JSON")
    dire = donnees.get("dire") if isinstance(donnees.get("dire"), str) else ""
    cible = donnees.get("cible") if isinstance(donnees.get("cible"), str) else ""
    actions = [a for a in donnees.get("actions") or [] if isinstance(a, dict)]
    return Decision(dire=dire.strip(), cible=cible.strip(), actions=actions, brut=texte)


# --- Lancement de Claude Code ----------------------------------------------------------------


def trouver_claude() -> str | None:
    """Chemin du binaire Claude Code : DIAGAUTO_CLAUDE, sinon `claude` dans le PATH, sinon celui
    installé avec l'extension VS Code (le plus récent), sinon l'installation native."""
    if os.environ.get("DIAGAUTO_CLAUDE"):
        return os.environ["DIAGAUTO_CLAUDE"]
    if trouve := shutil.which("claude"):
        return trouve
    accueil = Path.home()
    candidats = []
    for motif in (".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude*",
                  ".vscode-insiders/extensions/anthropic.claude-code-*/resources/native-binary/claude*"):
        candidats += [Path(c) for c in glob.glob(str(accueil / motif)) if Path(c).name in ("claude", "claude.exe")]

    def version(chemin: Path) -> tuple[int, ...]:
        m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", str(chemin))
        return tuple(int(x) for x in m.groups()) if m else (0,)

    if candidats:
        return str(max(candidats, key=version))
    for natif in (accueil / ".local/bin/claude.exe", accueil / ".local/bin/claude"):
        if natif.exists():
            return str(natif)
    return None


# Variables retirées de l'environnement de Claude Code :
# - une clé API ferait payer l'API au lieu d'utiliser l'abonnement (décision de Noah : pas de clé) ;
# - celles d'une session Claude Code parente (quand le serveur est lancé depuis Claude Code).
_RETIRER = {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_EFFORT"}


def env_claude() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _RETIRER and not k.startswith("CLAUDE_CODE_")}


def commande_claude(binaire: str, modele: str, effort: str, images: str) -> list[str]:
    outils = ["--tools", "Read", "--allowedTools", "Read"] if images == "fichiers" else ["--tools", ""]
    return [
        binaire, "-p",
        "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        "--model", modele, "--effort", effort,
        "--safe-mode",  # ignore CLAUDE.md, hooks, extensions et MCP personnels ; garde la connexion
        "--no-session-persistence",  # rien n'est gardé dans l'historique de Claude Code
        "--permission-prompts", "none",  # personne pour répondre : tout ce qui demanderait est refusé
        "--system-prompt", consignes(),
        *outils,
    ]


class ProcessusClaude:
    """Un processus Claude Code ouvert : on lui écrit des messages, il répond au fil de l'eau."""

    def __init__(self, commande: list[str], dossier: Path) -> None:
        self.commande = commande
        self.dossier = dossier
        self.tours = 0
        self.erreurs: list[str] = []
        self._p: subprocess.Popen | None = None
        self._file: asyncio.Queue | None = None
        self._verrou = asyncio.Lock()

    @property
    def vivant(self) -> bool:
        return self._p is not None and self._p.poll() is None

    async def demarrer(self) -> None:
        boucle = asyncio.get_running_loop()
        self._file = asyncio.Queue()
        self.dossier.mkdir(parents=True, exist_ok=True)
        self._p = subprocess.Popen(
            self.commande, cwd=self.dossier, env=env_claude(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._lire, args=(boucle,), daemon=True).start()
        threading.Thread(target=self._lire_erreurs, daemon=True).start()

    def _lire(self, boucle: asyncio.AbstractEventLoop) -> None:
        assert self._p and self._p.stdout and self._file
        try:
            for ligne in self._p.stdout:
                try:
                    evenement = json.loads(ligne.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                boucle.call_soon_threadsafe(self._file.put_nowait, evenement)
            boucle.call_soon_threadsafe(self._file.put_nowait, None)  # fin du processus
        except RuntimeError:
            pass  # la visite est terminée (boucle fermée) : plus personne n'attend ces messages

    def _lire_erreurs(self) -> None:
        assert self._p and self._p.stderr
        for ligne in self._p.stderr:
            texte = ligne.decode("utf-8", "replace").strip()
            if texte:
                self.erreurs = (self.erreurs + [texte])[-20:]

    def _ecrire(self, donnees: bytes) -> None:
        assert self._p and self._p.stdin
        self._p.stdin.write(donnees)
        self._p.stdin.flush()

    async def demander(self, contenu: list[dict], sur_texte: Callable[[str], Awaitable[None]] | None, delai_s: float) -> tuple[str, dict, dict]:
        """Envoie un message ; renvoie (texte complet, événement « result », mesures)."""
        async with self._verrou:
            if not self.vivant or self._file is None:
                raise RuntimeError("Claude Code n'est pas lancé : " + " | ".join(self.erreurs[-3:]))
            ligne = json.dumps({"type": "user", "message": {"role": "user", "content": contenu}}, ensure_ascii=False) + "\n"
            debut = time.perf_counter()
            await asyncio.to_thread(self._ecrire, ligne.encode("utf-8"))
            self.tours += 1
            texte, premier_mot, reflexion = "", None, False
            while True:
                restant = delai_s - (time.perf_counter() - debut)
                try:
                    evenement = await asyncio.wait_for(self._file.get(), max(restant, 0.01))
                except asyncio.TimeoutError:
                    self.arreter()
                    raise TimeoutError(f"pas de réponse de Claude en {delai_s:.0f} s") from None
                if evenement is None:
                    raise RuntimeError("Claude Code s'est arrêté : " + " | ".join(self.erreurs[-3:]))
                if evenement.get("type") == "stream_event":
                    e = evenement.get("event", {})
                    if e.get("type") == "content_block_start" and e.get("content_block", {}).get("type") == "thinking":
                        reflexion = True
                    if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                        if premier_mot is None:
                            premier_mot = time.perf_counter() - debut
                        texte += e["delta"]["text"]
                        if sur_texte:
                            await sur_texte(texte)
                elif evenement.get("type") == "result":
                    usage = evenement.get("usage") or {}
                    mesures = {
                        "premier_mot_s": round(premier_mot, 3) if premier_mot is not None else None,
                        "total_s": round(time.perf_counter() - debut, 3),
                        "api_cumule_s": round((evenement.get("duration_api_ms") or 0) / 1000, 3),  # depuis le lancement du processus
                        "etapes": evenement.get("num_turns"),
                        # Claude Code fait toujours réfléchir Haiku 5.5 avant de répondre (mesuré le 22/10/2026 :
                        # ni alwaysThinkingEnabled=false, ni MAX_THINKING_TOKENS=0 ne l'empêchent).
                        "reflexion": reflexion,
                        "jetons_entree": usage.get("input_tokens"),
                        "jetons_cache_lus": usage.get("cache_read_input_tokens"),
                        "jetons_cache_ecrits": usage.get("cache_creation_input_tokens"),
                        "jetons_sortie": usage.get("output_tokens"),
                        # Estimation fournie par Claude Code au tarif API : non facturée avec l'abonnement.
                        "cout_equivalent_api_usd": evenement.get("total_cost_usd"),
                    }
                    if evenement.get("is_error"):
                        raise RuntimeError(f"erreur Claude Code : {evenement.get('result') or evenement.get('subtype')}")
                    return (evenement.get("result") or texte), evenement, mesures

    def arreter(self) -> None:
        if self._p and self._p.poll() is None:
            try:
                if self._p.stdin:
                    self._p.stdin.close()
                self._p.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self._p.kill()


MESSAGE_PRECHAUFFAGE = "Début de la visite : rien n'est encore filmé. Réponds exactement {\"dire\": \"\", \"actions\": []}"


class CerveauClaudeCode:
    """Claude via Claude Code (abonnement). Un processus ouvert, remplacé tous les `tours_max`
    messages par un processus neuf préparé à l'avance (la conversation ne grossit pas sans fin ;
    l'état utile est de toute façon renvoyé à chaque message)."""

    def __init__(self, dossier: Path, modele: str = "claude-haiku-5-5", effort: str = "low", images: str = "message",
                 tours_max: int = 30, delai_s: float = 25.0, binaire: str | None = None, commande: list[str] | None = None) -> None:
        self.dossier = dossier
        self.modele = modele
        self.images = images
        self.tours_max = tours_max
        self.delai_s = delai_s
        if commande is None:
            binaire = binaire or trouver_claude()
            if not binaire:
                raise FileNotFoundError("Claude Code introuvable : installez-le ou indiquez son chemin dans DIAGAUTO_CLAUDE")
            commande = commande_claude(binaire, modele, effort, images)
        self.commande = commande
        self._actuel: ProcessusClaude | None = None
        self._suivant: asyncio.Task | None = None
        self.prechauffage: dict = {}

    @property
    def nom(self) -> str:
        return f"Claude Code (abonnement), modèle {self.modele}, images {'dans le message' if self.images == 'message' else 'en fichiers'}"

    async def _nouveau_processus(self) -> ProcessusClaude:
        processus = ProcessusClaude(self.commande, self.dossier)
        await processus.demarrer()
        _, _, mesures = await processus.demander([{"type": "text", "text": MESSAGE_PRECHAUFFAGE}], None, self.delai_s * 2)
        self.prechauffage = mesures
        return processus

    async def demarrer(self) -> None:
        self._actuel = await self._nouveau_processus()

    async def _processus(self) -> ProcessusClaude:
        if self._actuel is None or not self._actuel.vivant:
            self._actuel = await self._nouveau_processus()
        if self._actuel.tours >= self.tours_max - 5 and self._suivant is None:
            self._suivant = asyncio.create_task(self._nouveau_processus())
        if self._actuel.tours >= self.tours_max and self._suivant is not None and self._suivant.done():
            tache, self._suivant = self._suivant, None
            if tache.exception() is None:
                ancien, self._actuel = self._actuel, tache.result()
                asyncio.get_running_loop().run_in_executor(None, ancien.arreter)
            else:
                log.warning("Processus Claude de relève en échec : %s", tache.exception())
        return self._actuel

    async def decider(self, contexte: Contexte, sur_dire: SurDire | None = None) -> Decision:
        dire_envoye = False

        async def sur_texte(texte_partiel: str) -> None:
            nonlocal dire_envoye
            if dire_envoye or sur_dire is None:
                return
            dire = extraire_dire(texte_partiel)
            if dire is not None:
                dire_envoye = True
                if dire.strip():
                    await sur_dire(dire.strip(), extraire_cible(texte_partiel))

        try:
            processus = await self._processus()
            texte, _, mesures = await processus.demander(contenu_message(contexte, self.images), sur_texte, self.delai_s)
        except (RuntimeError, TimeoutError, OSError) as e:
            log.warning("Cerveau Claude : %s", e)
            return Decision(erreur=str(e))
        decision = analyser_reponse(texte)
        decision.mesures = mesures
        if decision.dire and not dire_envoye and sur_dire:
            await sur_dire(decision.dire, decision.cible)
        return decision

    async def fermer(self) -> None:
        if self._suivant:
            self._suivant.cancel()
        if self._actuel:
            self._actuel.arreter()
