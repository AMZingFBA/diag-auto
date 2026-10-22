"""Lexique métier imposé à la transcription et correction des confusions connues
(docs/02-capture-video.md, constats du 1er test video-001 et § 3.4)."""

from __future__ import annotations

import re

# Donné à Whisper comme contexte : il oriente l'orthographe des mots métier.
CONTEXTE_WHISPER = (
    "Visite de diagnostic immobilier, DPE. Ce mur-là : brique de 30 cm, parpaing de 20, béton, "
    "pierre, pan de bois, ossature bois, placo, isolé par l'intérieur (ITI) ou par l'extérieur (ITE), "
    "laine de verre, polystyrène, donne sur l'extérieur, local non chauffé, garage, cave, combles. "
    "Fenêtre PVC, double vitrage, volets roulants. Radiateur à eau, convecteur, plancher chauffant, "
    "robinets thermostatiques. Chaudière gaz à condensation, ballon d'eau chaude, cumulus, "
    "pompe à chaleur, VMC simple flux hygro B, double flux."
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


def est_hallucination(texte: str) -> bool:
    bas = texte.lower().strip()
    return not bas or any(h in bas for h in HALLUCINATIONS)
