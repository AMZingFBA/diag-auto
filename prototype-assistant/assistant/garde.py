"""Garde-fous sur les questions de l'assistant (retour de Noah après son test du 22/10/2026) :
une seule question à la fois, jamais « répétez », jamais un champ déjà renseigné ni un champ déjà
demandé récemment. Le serveur filtre ce que propose le cerveau (Claude ou simulation) avant de
le faire dire.
"""

from __future__ import annotations

import re

from .checklist import TYPES, Checklist, ErreurChecklist, cle_texte
from .extraction import Cible

DELAI_REDEMANDE_S = 120.0
_REPETER = re.compile(
    r"r[ée]p[ée]t|\bpardon\b|pas (?:bien )?(?:compris|entendu|saisi|clair)|\bredi(?:re|tes)\b|reformul|je n'ai pas (?:compris|entendu)",
    re.IGNORECASE,
)


def champ_rempli(cible: Cible, checklist: Checklist) -> bool:
    if cible.champ == "presence":
        piece = checklist.piece_courante if TYPES[cible.type].niveau == "piece" else None
        absences = checklist.pieces[piece].absences if piece in checklist.pieces else checklist.absences_logement
        return cible.type in absences or any(e.type == cible.type for e in checklist.elements_de(piece))
    try:
        return checklist.trouver_element(cible.element_id or "").est_rempli(cible.champ)
    except ErreurChecklist:
        return False


class Questions:
    """Mémoire des questions posées : par champ visé (« M1.isolation »), sinon par texte. Une question
    de présence (« Y a-t-il une fenêtre ? ») est retenue pour la pièce où elle a été posée."""

    def __init__(self) -> None:
        self._posees: dict[str, float] = {}

    @staticmethod
    def _cle(texte: str, cible: Cible | None, piece: str | None) -> str:
        if cible is None:
            return "texte:" + cle_texte(texte)
        if cible.champ == "presence" and TYPES[cible.type].niveau == "piece":
            return f"{cible.code}@{piece}"
        return cible.code

    def recentes(self, maintenant: float, piece: str | None = None) -> list[str]:
        """Codes des champs demandés il y a moins de DELAI_REDEMANDE_S (présences : dans cette pièce)."""
        codes = []
        for cle, t in self._posees.items():
            code, _, lieu = cle.partition("@")
            if not cle.startswith("texte:") and maintenant - t < DELAI_REDEMANDE_S and (not lieu or lieu == str(piece)):
                codes.append(code)
        return codes

    def noter(self, texte: str, cible: Cible | None, maintenant: float, piece: str | None = None) -> None:
        self._posees[self._cle(texte, cible, piece)] = maintenant

    def filtrer(self, texte: str, code_cible: str, checklist: Checklist, maintenant: float) -> tuple[str, Cible | None, str]:
        """(question à dire ou "", champ visé, raison du refus)."""
        texte = " ".join((texte or "").split())
        if not texte:
            return "", None, ""
        if _REPETER.search(texte):
            return "", None, "demande de répétition interdite"
        if "?" in texte:
            texte = texte[: texte.index("?") + 1]  # une seule question : ce qui suit le premier « ? » est coupé
        cible = Cible.depuis_code(code_cible, checklist) if code_cible else None
        if cible and champ_rempli(cible, checklist):
            return "", cible, f"{cible.code} déjà renseigné"
        if maintenant - self._posees.get(self._cle(texte, cible, checklist.piece_courante), -1e9) < DELAI_REDEMANDE_S:
            return "", cible, "déjà demandé il y a moins de 2 minutes"
        return texte, cible, ""
