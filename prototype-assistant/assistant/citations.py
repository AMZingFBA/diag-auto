"""Garde-fou « jamais de valeur sans citation » (docs/02-capture-video.md § 3.6).

Une valeur proposée par l'IA n'est acceptée que si sa citation se retrouve, presque mot pour
mot, dans ce que le diagnostiqueur a réellement dit (phrases transcrites récentes).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .checklist import cle_texte

# Part minimale de la citation retrouvée dans une phrase (tolère une ponctuation ou un
# accord différents, pas une phrase inventée).
SEUIL = 0.85


def _normaliser(texte: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", cle_texte(texte)).split())


def part_retrouvee(citation: str, phrase: str) -> float:
    """Part (0 à 1) des caractères de la citation retrouvés, dans l'ordre, dans la phrase."""
    c, p = _normaliser(citation), _normaliser(phrase)
    if not c:
        return 0.0
    if c in p:
        return 1.0
    blocs = SequenceMatcher(None, c, p, autojunk=False).get_matching_blocks()
    # Les tout petits fragments communs (une lettre, un espace) ne prouvent rien.
    return sum(b.size for b in blocs if b.size >= 3) / len(c)


def citation_trouvee(citation: str, phrases: list[str], seuil: float = SEUIL) -> bool:
    return any(part_retrouvee(citation, p) >= seuil for p in phrases)
