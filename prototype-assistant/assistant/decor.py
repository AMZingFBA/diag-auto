"""Nouveau décor filmé : un signal, pas une décision (étape 8 de Noah, changement de pièce détecté par la vidéo).

Chaque image reçue est résumée par l'histogramme de ses couleurs. Une image qui ne ressemble à aucune de celles déjà
filmées dans la pièce, deux fois de suite, est un « nouveau décor » : le serveur fait alors regarder les images à Claude
(veille), qui dit si l'on a changé de pièce ; le serveur demande ensuite confirmation (« On est dans la cuisine ? »).

Mesuré sur le test de Noah du 22/10/2026 (séjour puis cuisine) : tourner la caméra dans une même pièce change autant
l'histogramme que passer dans une autre (distances de 0,3 à 0,44 dans le séjour). Ce signal ne décide donc jamais
seul : il avance seulement le prochain coup d'œil de Claude.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

SEUIL = 0.3  # distance (0 à 1) à la plus proche image déjà vue dans la pièce
DE_SUITE = 2  # images nouvelles consécutives
MEMOIRE = 120  # images gardées par pièce (une par seconde)


def histogramme(jpeg: bytes) -> np.ndarray | None:
    try:
        image = Image.open(io.BytesIO(jpeg)).convert("HSV").resize((32, 32))
    except Exception:  # image illisible : pas de signal
        return None
    pixels = np.asarray(image).reshape(-1, 3).astype(float)
    h, _ = np.histogramdd(pixels, bins=(8, 4, 4), range=((0, 256), (0, 256), (0, 256)))
    h = h.ravel()
    return h / h.sum()


class Decor:
    def __init__(self) -> None:
        self.vues: list[np.ndarray] = []
        self.nouvelles = 0

    def nouvelle_piece(self) -> None:
        self.vues, self.nouvelles = [], 0

    def ajouter(self, jpeg: bytes) -> bool:
        """Vrai quand le décor devient nouveau (une fois, jusqu'à ce qu'il redevienne familier)."""
        h = histogramme(jpeg)
        if h is None:
            return False
        distance = min((0.5 * float(np.abs(h - v).sum()) for v in self.vues), default=0.0)
        self.vues = (self.vues + [h])[-MEMOIRE:]
        self.nouvelles = self.nouvelles + 1 if distance > SEUIL else 0
        return self.nouvelles == DE_SUITE
