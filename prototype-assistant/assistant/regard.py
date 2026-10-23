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
        self.delai_s = delai_s
        self.mesures: dict = {}

    async def demarrer(self) -> None:
        await self._cerveau.demarrer()

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
