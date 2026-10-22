"""Garde-fous sur les questions de l'assistant (retours de Noah du 22/10/2026) : une seule question à
la fois, jamais « répétez », jamais un champ déjà renseigné, jamais deux fois la même question. Le
serveur filtre tout ce qui doit être dit (parcours ou Claude) avant de le faire dire.
"""

from __future__ import annotations

import re

from .checklist import TOUJOURS_PRESENTS, TYPES, Checklist, ErreurChecklist, cle_texte
from .extraction import Cible

DELAI_REDEMANDE_S = 120.0
# « Le mur 3 », « le quatrième mur » : le diagnostiqueur ne sait pas lequel c'est (test réel de Noah, étape 5).
_NOM_ABSTRAIT = re.compile(r"\b(?:murs?|fen[eê]tres?|radiateurs?)\s+(?:n°\s*)?\d+\b"
                           r"|\b(?:deuxi[eè]me|troisi[eè]me|quatri[eè]me|cinqui[eè]me|sixi[eè]me)\s+mur\b", re.IGNORECASE)
_REPETER = re.compile(
    r"r[ée]p[ée]t|\bpardon\b|pas (?:bien )?(?:compris|entendu|saisi|clair)|\bredi(?:re|tes)\b|reformul|je n'ai pas (?:compris|entendu)",
    re.IGNORECASE,
)


def champ_rempli(cible: Cible, checklist: Checklist) -> bool:
    """La question visée a-t-elle déjà sa réponse ?"""
    piece = checklist.pieces.get(checklist.piece_courante or "")
    if cible.genre == "presence":
        if cible.type in TOUJOURS_PRESENTS:
            return True
        niveau_piece = TYPES[cible.type].niveau == "piece"
        absences = (piece.absences if piece else {}) if niveau_piece else checklist.absences_logement
        lieu = checklist.piece_courante if niveau_piece else None
        return cible.type in absences or any(e.type == cible.type for e in checklist.elements_de(lieu))
    if cible.genre == "suite":
        return piece is not None and (cible.type in piece.clos or (cible.type == "mur" and checklist.murs_complets()))
    if cible.genre == "pareil":
        element = checklist.element_de_piece(cible.type)
        return element is not None and element.est_rempli("donne_sur")
    if cible.genre == "secondaire":
        return (cible.type, cible.champ) not in checklist.manques_secondaires()
    if cible.genre == "orientation":  # orientation dite, ou déduite de la boussole ou d'un autre mur
        try:
            element = checklist.trouver_element(cible.element_id or "")
        except ErreurChecklist:
            return False
        return bool(element.orientation) and (element.orientation_source == "dit" or checklist.correction_cap is not None)
    if cible.genre in ("champ", "confirmation"):
        try:
            element = checklist.trouver_element(cible.element_id or "")
        except ErreurChecklist:
            return False
        return element.est_rempli(cible.champ) or not element.est_utile(cible.champ)
    return False


class Questions:
    """Mémoire des questions posées. Celles du parcours ne sont posées qu'une fois (clé fournie par
    le parcours) ; celles de Claude, pas deux fois en 2 minutes (clé : champ visé, sinon texte)."""

    def __init__(self) -> None:
        self._posees: dict[str, float] = {}
        self._une_fois: set[str] = set()
        self._reposees: set[str] = set()

    @staticmethod
    def _cle(texte: str, cible: Cible | None, piece: str | None) -> str:
        if cible is None:
            return "texte:" + cle_texte(texte)
        if cible.genre == "presence" and TYPES[cible.type].niveau == "piece":
            return f"{cible.code}@{piece}"
        return cible.code

    def recentes(self, maintenant: float, piece: str | None = None) -> list[str]:
        """Codes déjà demandés (récemment, ou une fois pour toutes) : pour dire à Claude de ne pas les reposer.
        Les questions propres à une pièce ne comptent que dans cette pièce."""
        codes: list[str] = []
        for cle, t in self._posees.items():
            if cle.startswith("texte:") or (maintenant - t >= DELAI_REDEMANDE_S and cle not in self._une_fois):
                continue
            code, _, lieu = cle.partition("@")
            if not lieu or lieu.split("#")[0] == str(piece):
                codes.append(code)
        return list(dict.fromkeys(codes))

    def autoriser_encore(self, cle: str) -> None:
        """« Quel mur ? » : le diagnostiqueur demande lui-même qu'on précise ; la question peut être reposée."""
        self._reposees.discard(cle)

    def noter(self, cle: str, maintenant: float, une_fois: bool = False) -> None:
        self._posees[cle] = maintenant
        if une_fois:
            self._une_fois.add(cle)

    def filtrer(self, texte: str, code_cible: str, checklist: Checklist, maintenant: float,
                cle: str | None = None, reposer: str = "") -> tuple[str, Cible | None, str, str]:
        """(question à dire ou "", champ visé, raison du refus, clé de la question). `reposer` : clé de la
        question restée sans réponse parce que le diagnostiqueur a parlé d'autre chose (une correction) ;
        elle peut être reposée une fois (« Noté : béton au lieu de brique. Un autre mur dans cette pièce ? »)."""
        texte = " ".join((texte or "").split())
        if not texte:
            return "", None, "", ""
        if _REPETER.search(texte):
            return "", None, "demande de répétition interdite", ""
        if cle is None and _NOM_ABSTRAIT.search(texte):  # question de Claude : le parcours la reposera avec un nom parlant
            return "", None, "nom abstrait interdit (« le mur 3 »)", ""
        if "?" in texte:
            texte = texte[: texte.index("?") + 1]  # une seule question : ce qui suit le premier « ? » est coupé
        cible = Cible.depuis_code(code_cible, checklist) if code_cible else None
        cle = cle or self._cle(texte, cible, checklist.piece_courante)
        if cible and champ_rempli(cible, checklist):
            return "", cible, f"{cible.code} déjà renseigné", cle
        if reposer and cle == reposer and cle not in self._reposees:
            self._reposees.add(cle)
            return texte, cible, "", cle
        if cle in self._une_fois:
            return "", cible, "déjà demandé une fois", cle
        if maintenant - self._posees.get(cle, -1e9) < DELAI_REDEMANDE_S:
            return "", cible, "déjà demandé il y a moins de 2 minutes", cle
        return texte, cible, "", cle
