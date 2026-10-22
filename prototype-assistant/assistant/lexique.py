"""Lexique métier imposé à la transcription et correction des confusions connues
(docs/02-capture-video.md, constats du 1er test video-001 et § 3.4)."""

from __future__ import annotations

import re
import unicodedata

# Donné à Whisper comme contexte : il oriente l'orthographe des mots métier et des réponses courtes.
# Comparé sur l'enregistrement de Noah (22/10/2026) : meilleur que le contexte précédent (« eau chaude » au
# lieu de « Chaude », « Basse » au lieu de « BAS », plus de « 100 cm » inventé), même vitesse. Ne jamais y
# mettre « je ne sais pas », « oui » ou « non » : Whisper les inventait alors sur du silence. Les « hotwords »
# de faster-whisper ont été écartés : plus lents, et des phrases métier inventées sur du silence.
CONTEXTE_WHISPER = (
    "Diagnostic immobilier, DPE. Réponses courtes : extérieur, local chauffé, local non chauffé, garage, cave. "
    "Brique, parpaing, béton, pierre, 20 cm, 30 cm. Isolé par l'intérieur, ITI, ITE, laine de verre, laine de roche, "
    "polystyrène. Combles perdus, combles aménagés, terre-plein, vide sanitaire. Trois fenêtres PVC, bois, alu, "
    "double vitrage, volets roulants. Deux radiateurs à eau, eau chaude, électrique, basse température. "
    "Chaudière gaz à condensation, PAC air/eau, ballon thermodynamique, VMC hygro B."
)

# (motif, remplacement) appliqués dans l'ordre, sans tenir compte des majuscules.
CORRECTIONS: list[tuple[str, str]] = [
    (r"\bça se (?:meur(?:t|e)?|mur)(?:-| )?(?:là|la)\b", "ce mur-là"),
    (r"\bça se (?:meur(?:t|e)?|mur)\b", "ce mur"),
    (r"\bce meurt(?:t)?(?:-| )?là\b", "ce mur-là"),
    (r"\bce meurt?\b", "ce mur"),
    (r"\bparpins?\b", "parpaing"),
    (r"\bpar pain(s)?\b", "parpaing"),
    (r"\bVMCE\b", "VMC"),
    (r"\bV\.?M\.?C\.?\b", "VMC"),
    (r"\bI\.?T\.?E\.?\b", "ITE"),
    (r"\bI\.?T\.?I\.?\b", "ITI"),
    (r"\bhygro ?b[ée]\b", "hygro B"),
    (r"\bplacot?\b", "placo"),
    # Confusions entendues pendant le test de Noah sur iPhone (22/10/2026).
    (r"\bl'?allaine\b", "la laine"),
    (r"\bbesse\b", "basse"),
    (r"\b(?:o|oh|ouh|au|eau)[ ,]+chaud(?:i|ie|e)?\b", "eau chaude"),
    (r"\bl'?AVMC\b", "la VMC"),
    # Sigles épelés (« pévécé », « vé emme cé ») et confusions de sons.
    (r"\bp[ée][ -]?v[ée][ -]?c[ée]\b", "PVC"),
    (r"\bv[ée][ -]?(?:emm?e|èm|m)[ -]?c[ée]\b", "VMC"),
    (r"\bhydro[ -]?b[ée]?\b", "hygro B"),
    (r"\bict[ée]rieur\b", "extérieur"),  # « Ictérieur » : « Extérieur » mal transcrit (test de Noah)
]

# Phrases que Whisper invente sur du silence ou du bruit (connu en français).
HALLUCINATIONS = (
    "sous-titres réalisés par",
    "sous-titrage st'",
    "sous-titrage société radio-canada",
    "merci d'avoir regardé",
    "abonnez-vous",
    "amara.org",
    "thank you",
)


def corriger(texte: str) -> str:
    for motif, remplacement in CORRECTIONS:
        texte = re.sub(motif, remplacement, texte, flags=re.IGNORECASE)
    return " ".join(texte.split())


def _comparable(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9/]+", " ", sans_accents).split())


def est_recopie_du_contexte(texte: str) -> bool:
    """Le texte n'est-il qu'un morceau recopié du vocabulaire donné en contexte à Whisper ?"""
    morceau = _comparable(texte)
    return bool(morceau) and f" {morceau} " in f" {_comparable(CONTEXTE_WHISPER)} "


def est_hallucination(texte: str) -> bool:
    bas = texte.lower().strip()
    return not bas or any(h in bas for h in HALLUCINATIONS)
