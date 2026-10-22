"""Transcription d'une phrase (faster-whisper, licence MIT), sur notre machine : la voix ne
quitte pas le serveur.

Le modèle est chargé une seule fois (téléchargé au premier lancement dans le cache
Hugging Face : environ 1,6 Go pour « large-v3-turbo »).
"""

from __future__ import annotations

import logging
import os
import threading
import time

import numpy as np

from .lexique import CONTEXTE_WHISPER, corriger, est_hallucination

log = logging.getLogger(__name__)


class TranscripteurSimulation:
    """Sans faster-whisper : aucune transcription (on écrit la phrase dans la page à la place)."""

    nom = "simulation (pas de transcription : écrivez les phrases dans la page)"

    def prechauffer(self) -> None:
        pass

    def transcrire(self, audio: np.ndarray) -> str:
        return ""


# Mesuré le 22/10/2026 sur ce PC (12 cœurs, sans carte graphique), phrase de 5,7 s :
# small ≈ 2 s, large-v3-turbo ≈ 8 à 10 s, medium ≈ 7 s avec des boucles à plus de 40 s.
# D'où « auto » : turbo sur carte graphique, small sur processeur.
MODELE_GPU, MODELE_CPU = "large-v3-turbo", "small"


class TranscripteurWhisper:
    def __init__(self, modele: str = "auto", appareil: str = "auto", faisceau: int = 1) -> None:
        self.modele = modele
        self.appareil = appareil
        self.faisceau = faisceau
        self._whisper = None
        self._verrou = threading.Lock()

    @property
    def nom(self) -> str:
        return f"faster-whisper {self.modele} ({self.appareil})"

    def _charger(self):
        if self._whisper is None:
            import ctranslate2
            from faster_whisper import WhisperModel

            if self.appareil == "auto":
                self.appareil = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            if self.modele == "auto":
                self.modele = MODELE_GPU if self.appareil == "cuda" else MODELE_CPU
            calcul = "float16" if self.appareil == "cuda" else "int8"
            fils = min(8, os.cpu_count() or 4)
            debut = time.perf_counter()
            self._whisper = WhisperModel(self.modele, device=self.appareil, compute_type=calcul, cpu_threads=fils)
            log.info("Modèle %s chargé en %.1f s (%s, %s)", self.modele, time.perf_counter() - debut, self.appareil, calcul)
        return self._whisper

    def prechauffer(self) -> None:
        """Charge le modèle et fait une première transcription à vide (évite la lenteur du 1er appel)."""
        with self._verrou:
            self._charger()
        self.transcrire(np.zeros(16_000, dtype=np.float32))

    def transcrire(self, audio: np.ndarray) -> str:
        with self._verrou:  # un seul calcul à la fois sur le processeur ou la carte graphique
            segments, _ = self._charger().transcribe(
                audio,
                language="fr",
                beam_size=self.faisceau,
                initial_prompt=CONTEXTE_WHISPER,
                condition_on_previous_text=False,
                without_timestamps=True,
                vad_filter=False,  # la détection de phrase est déjà faite
            )
            texte = " ".join(s.text.strip() for s in segments)
        return "" if est_hallucination(texte) else corriger(texte)


def creer_transcripteur(mode: str, modele: str, appareil: str, faisceau: int):
    """« whisper », « simulation » ou « auto » (whisper s'il est installé)."""
    if mode == "simulation":
        return TranscripteurSimulation()
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        if mode == "whisper":
            raise
        log.warning("faster-whisper n'est pas installé : transcription en simulation")
        return TranscripteurSimulation()
    return TranscripteurWhisper(modele, appareil, faisceau)
