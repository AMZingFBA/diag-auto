"""Cerveau de simulation : sans Claude, pour tester toute la chaîne gratuitement (page, voix,
checklist, journal).

Les valeurs dites sont déjà notées par l'extraction immédiate (extraction.py), avant tout appel au
cerveau. La simulation ne fait donc que choisir la question suivante : le premier manque de la
pièce (puis du logement) qui n'a pas été demandé récemment. Elle ne voit pas les images.
"""

from __future__ import annotations

from .cerveau import Contexte, Decision


class CerveauSimulation:
    nom = "simulation (extraction par règles et questions de la checklist, sans Claude)"

    async def demarrer(self) -> None:
        pass

    async def fermer(self) -> None:
        pass

    async def decider(self, contexte: Contexte, sur_dire=None) -> Decision:
        checklist = contexte.checklist
        recentes = set(contexte.questions_recentes)
        manques = checklist.manques_piece() or checklist.manques_logement()
        prochain = next((m for m in manques if m.code not in recentes), None)
        if prochain is None:
            return Decision(mesures={"premier_mot_s": 0.0, "total_s": 0.0})
        if sur_dire:
            await sur_dire(prochain.question, prochain.code)
        return Decision(dire=prochain.question, cible=prochain.code, mesures={"premier_mot_s": 0.0, "total_s": 0.0})
