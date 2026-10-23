"""L'image propose la réponse (retour de Noah du 23/10 : « rends la vidéo plus utile, on ne l'utilise presque plus »).

Pendant la visite, la vidéo ne servait plus qu'à la boussole et aux vignettes : le coup d'œil de Claude toutes les 10 s
(« veille ») ne disait jamais rien. Désormais, quand l'assistant pose une question sur quelque chose qui se voit (la
menuiserie, le vitrage ou les volets d'une fenêtre, le type de radiateur, la chaudière, le ballon, la VMC, le matériau
d'un mur…), Claude regarde les dernières images de la caméra. S'il voit **clairement** la réponse parmi celles proposées,
le bouton correspondant s'allume sur le téléphone (« 📷 PVC »), avec ce qui se voit. Le diagnostiqueur confirme d'un appui
(ou répond autre chose) : **rien n'est jamais noté sur la seule image** (CLAUDE.md : l'IA ne devine jamais).

Claude par l'abonnement (Claude Code, sans clé API), un processus à part, pour ne jamais retarder la conversation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .cerveau import CerveauClaudeCode, ImageInstant, trouver_claude
from .extraction import Cible

log = logging.getLogger(__name__)

# Ce qui se voit à l'image : (type, information). Pas « donne sur » (ce qu'il y a derrière un mur ne se voit pas), ni
# l'isolation (cachée dans le mur), ni une année (sauf sur une plaque : voir plus tard).
VISIBLES = {("fenetre", "menuiserie"), ("fenetre", "vitrage"), ("fenetre", "volets"), ("porte", "type"), ("emetteur", "type"),
            ("chauffage", "type"), ("chauffage", "energie"), ("ecs", "systeme"), ("ventilation", "type"), ("mur", "materiau")}
# Questions de présence dont la réponse se voit : « Et les radiateurs : à eau ou électriques ? », « Ventilation… ? »…
PRESENCES_VISIBLES = {"emetteur", "chauffage", "ecs", "ventilation"}

CONSIGNES_REGARD = """Tu aides un diagnostiqueur immobilier qui filme un logement avec son téléphone pour un DPE. On te \
donne la question qu'il vient de recevoir, les réponses possibles (valeurs entre guillemets) et les dernières images de \
sa caméra. Si les images montrent CLAIREMENT la réponse (par exemple une fenêtre à cadre PVC blanc, un radiateur en fonte \
avec ses tuyaux, une chaudière murale gaz, un ballon d'eau chaude, une bouche de VMC), choisis-la. Si l'élément n'est pas \
à l'image, si c'est flou, ou si tu hésites entre deux réponses, ne choisis rien : ne devine jamais, c'est le \
diagnostiqueur qui confirme. Réponds uniquement par un JSON sur une ligne : \
{"valeur": "<une des valeurs proposées, exactement, ou vide>", "raison": "<ce qui se voit, en 8 mots au plus>"}"""


# Pièces reconnues sur la vidéo (croquis pour le plomb et l'amiante, Noah, 23/10 : « il faut qu'il reconnaisse lui-même
# quand on change de pièce, et quelle pièce c'est »).
TYPES_PIECES = ["Entrée", "Séjour", "Salle à manger", "Cuisine", "Chambre", "Salle de bains", "Salle d'eau", "WC", "Couloir",
                "Dégagement", "Bureau", "Buanderie", "Cellier", "Garage", "Escalier", "Palier", "Cave", "Grenier", "Combles",
                "Sous-sol", "Véranda", "Placard", "Dressing", "Débarras", "Chaufferie", "Mezzanine", "Pièce"]

CONSIGNES_PIECE = (
    "Tu aides un diagnostiqueur immobilier qui filme tout un logement en une seule vidéo, pièce par pièce. On te donne le "
    "nom de la pièce où il était, quelques images de chaque pièce déjà vue, puis les dernières images de sa caméra. Dis dans "
    "quelle pièce il est maintenant. Une pièce déjà vue (mêmes meubles, mêmes murs, même sol) : donne son nom exact. Une "
    "autre pièce : réponds « nouvelle » et donne son type parmi : " + ", ".join(TYPES_PIECES) + ". S'il filme une porte ou "
    "un passage sans être encore entré, ou si l'image est floue, au plafond ou au sol, réponds la pièce où il était. Les "
    "images d'une pièce n'en montrent qu'une partie : un autre coin de la même pièce reste cette pièce (un grand séjour a "
    "son coin repas et son coin salon : c'est une seule pièce). Une nouvelle pièce se voit à son sol, ses murs et ses "
    "meubles différents, souvent après une porte. Réponds uniquement par un JSON sur une ligne : {\"piece\": \"<nom d'une "
    "pièce déjà vue, ou nouvelle>\", \"type\": \"<type, pour une nouvelle pièce>\", \"confiance\": \"<forte, moyenne ou "
    "faible>\"}")


@dataclass
class AvisPiece:
    piece: str | None  # le nom d'une pièce déjà vue ; None : une nouvelle pièce
    type: str  # pour une nouvelle pièce
    confiance: str  # « forte », « moyenne » ou « faible »


def analyser_piece(texte: str, connues: list[str]) -> AvisPiece | None:
    """La réponse de Claude : une pièce déjà vue (son nom exact), ou une nouvelle d'un type connu ; sinon rien."""
    m = re.search(r"\{.*\}", texte or "", re.DOTALL)
    if not m:
        return None
    try:
        donnees = json.loads(m.group(0))
    except ValueError:
        return None
    confiance = str(donnees.get("confiance") or "faible").strip().lower()
    confiance = confiance if confiance in ("forte", "moyenne", "faible") else "faible"
    piece = " ".join(str(donnees.get("piece") or "").split())
    connue = next((n for n in connues if n.lower() == piece.lower()), None)
    if connue:
        return AvisPiece(connue, "", confiance)
    type_piece = " ".join(str(donnees.get("type") or "").split())
    type_connu = next((t for t in TYPES_PIECES if t.lower() == type_piece.lower()), None)
    if piece.lower() == "nouvelle" and type_connu:
        return AvisPiece(None, type_connu, confiance)
    return None


def contenu_piece(courante: str | None, references: dict[str, list[bytes]], images: list[ImageInstant]) -> list[dict]:
    def image(jpeg: bytes) -> dict:
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}}

    blocs: list[dict] = [{"type": "text", "text": f"Pièce où il était : « {courante or 'aucune encore'} »."}]
    for nom, jpegs in references.items():
        blocs += [{"type": "text", "text": f"Pièce déjà vue « {nom} » :"}, *(image(j) for j in jpegs)]
    blocs.append({"type": "text", "text": "Dernières images de la caméra (la plus récente en dernier) :"})
    blocs += [image(i.jpeg) for i in images]
    return blocs


@dataclass
class Proposition:
    valeur: str
    libelle: str
    raison: str


def visible(cible: Cible | None) -> bool:
    """La réponse à cette question peut-elle se voir à l'image ?"""
    if cible is None:
        return False
    if cible.genre == "presence":
        return cible.type in PRESENCES_VISIBLES
    return cible.genre == "champ" and (cible.type, cible.champ) in VISIBLES


def analyser(texte: str, options: list[dict]) -> Proposition | None:
    """La réponse de Claude : une des valeurs proposées (jamais « je ne sais pas », « non » ni « Autre… »), ou rien."""
    m = re.search(r"\{.*\}", texte or "", re.DOTALL)
    if not m:
        return None
    try:
        donnees = json.loads(m.group(0))
    except ValueError:
        return None
    valeur = str(donnees.get("valeur") or "").strip()
    for option in options:
        if option.get("saisie") or option["valeur"] in ("inconnu", "non", ""):
            continue
        if valeur.lower() in (option["valeur"].lower(), option["libelle"].lower()):
            return Proposition(option["valeur"], option["libelle"], " ".join(str(donnees.get("raison") or "").split())[:80])
    return None


def contenu(question: str, options: list[dict], images: list[ImageInstant]) -> list[dict]:
    valeurs = ", ".join(f"« {o['valeur']} »" for o in options if not o.get("saisie") and o["valeur"] not in ("inconnu", "non"))
    blocs: list[dict] = [{"type": "text", "text": f"Question : « {question} »\nRéponses possibles : {valeurs}\nImages (la dernière en dernier) :"}]
    blocs += [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(i.jpeg).decode()}}
              for i in images]
    return blocs


class RegardClaude:
    """Claude regarde les images pour la question posée. Un processus Claude Code à part, renouvelé régulièrement."""

    # Sonnet : sur les images de la visite de Noah du 22/10, Haiku a pris un store intérieur baissé pour un coffre de volet
    # roulant ; Sonnet s'est abstenu partout où c'était douteux (1,5 à 4 s par image, sans retarder la conversation).
    def __init__(self, dossier: Path, modele: str = "claude-sonnet-5-5", binaire: str | None = None, delai_s: float = 12.0) -> None:
        binaire = binaire or trouver_claude()
        if not binaire:
            raise FileNotFoundError("Claude Code introuvable")
        commande = [binaire, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                    "--model", modele, "--effort", "low", "--safe-mode", "--no-session-persistence",
                    "--permission-prompts", "none", "--system-prompt", CONSIGNES_REGARD, "--tools", ""]
        self._cerveau = CerveauClaudeCode(dossier, modele=modele, tours_max=10, delai_s=delai_s, commande=commande)
        pieces = [*commande[: commande.index("--system-prompt") + 1], CONSIGNES_PIECE, *commande[commande.index("--system-prompt") + 2:]]
        self._pieces = CerveauClaudeCode(dossier / "pieces", modele=modele, tours_max=10, delai_s=delai_s, commande=pieces)
        self.delai_s = delai_s
        self.mesures: dict = {}

    async def demarrer(self, propositions: bool = True, pieces: bool = True) -> None:
        """Seuls les processus utiles sont lancés (un autre partirait à la demande) : amiante et plomb, les pièces seules
        (aucune question, donc rien à proposer ; rejeu du 23/10 : 22 s pour lancer les deux sur un PC chargé) ; DPE, les
        propositions seules (les pièces n'y sont pas regardées)."""
        await asyncio.gather(*([self._cerveau.demarrer()] if propositions else []), *([self._pieces.demarrer()] if pieces else []))

    async def reconnaitre(self, images: list[ImageInstant], references: dict[str, list[bytes]], courante: str | None) -> AvisPiece | None:
        """Dans quelle pièce est-on, d'après les dernières images comparées à une image de chaque pièce déjà vue ?"""
        if not images:
            return None
        try:
            processus = await self._pieces._processus()
            texte, _, self.mesures = await processus.demander(contenu_piece(courante, references, images), None, self.delai_s)
        except (RuntimeError, TimeoutError, OSError) as e:
            log.warning("Pièce vue par Claude : %s", e)
            return None
        return analyser_piece(texte, list(references))

    async def proposer(self, question: str, options: list[dict], images: list[ImageInstant]) -> Proposition | None:
        if not images:
            return None
        try:
            processus = await self._cerveau._processus()
            texte, _, self.mesures = await processus.demander(contenu(question, options, images), None, self.delai_s)
        except (RuntimeError, TimeoutError, OSError) as e:
            log.warning("Regard de Claude : %s", e)
            return None
        return analyser(texte, options)

    async def fermer(self) -> None:
        await self._cerveau.fermer()
        await self._pieces.fermer()
