"""Cerveau de simulation : sans Claude, pour tester toute la chaîne gratuitement (page, voix,
checklist, journal).

Les valeurs dites sont notées par l'extraction immédiate (extraction.py) et les questions viennent
du parcours (parcours.py), décidé par le serveur. Sans Claude, une phrase que les règles n'ont pas
comprise reste simplement sans suite. La simulation ne voit pas les images.
"""

from __future__ import annotations

from .cerveau import Contexte, Decision


class CerveauSimulation:
    nom = "simulation (extraction par règles et parcours du serveur, sans Claude)"

    async def demarrer(self) -> None:
        pass

    async def fermer(self) -> None:
        pass

    async def decider(self, contexte: Contexte, sur_dire=None) -> Decision:
        return Decision(mesures={"premier_mot_s": 0.0, "total_s": 0.0})
