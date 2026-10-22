"""Transcription d'une phrase, sur notre machine : la voix ne quitte pas le serveur.

Deux moteurs :
- le FastConformer français de NVIDIA (CC-BY-4.0) en version ONNX, via onnx-asr (MIT) : 0,05 s par
  phrase sur ce PC au lieu de 2,3 s, sans invention de valeurs métier sur du silence, mais sans
  vocabulaire métier possible ;
- faster-whisper (licence MIT), guidé par le vocabulaire métier, mais ~2 s par phrase sur ce
  processeur quelle que soit sa longueur (le modèle traite toujours 30 s de son).
Par défaut (étape 5, « rapide ») : le FastConformer pour chaque phrase, Whisper en second avis
seulement quand les règles n'ont pas compris. Les modèles sont chargés une seule fois (téléchargés au
premier lancement dans le cache Hugging Face).
"""

from __future__ import annotations

import logging
import os
import threading
import time

import numpy as np

from .lexique import CONTEXTE_WHISPER, corriger, est_hallucination, est_recopie_du_contexte

log = logging.getLogger(__name__)


class TranscripteurSimulation:
    """Sans moteur de transcription : on écrit la phrase dans la page à la place."""

    nom = "simulation (pas de transcription : écrivez les phrases dans la page)"

    def prechauffer(self) -> None:
        pass

    def transcrire(self, audio: np.ndarray) -> str:
        return ""


# Mesuré le 22/10/2026 sur ce PC (12 cœurs, sans carte graphique), phrase de 5,7 s :
# small ≈ 2 s, large-v3-turbo ≈ 8 à 10 s, medium ≈ 7 s avec des boucles à plus de 40 s.
# D'où « auto » : turbo sur carte graphique, small sur processeur.
MODELE_GPU, MODELE_CPU = "large-v3-turbo", "small"

# Whisper invente parfois sur un passage sans vraie parole, en recopiant son vocabulaire de contexte
# (« Laine de verre. » deux fois sur l'enregistrement de Noah). Seuils mesurés sur ces 52 phrases : les
# inventions avaient une probabilité « pas de parole » de 0,39 à 0,50 et une confiance de −0,8 à −1,3 ;
# les vraies phrases, au plus 0,09, et les vraies réponses reprises du vocabulaire (« Extérieur. », « Eau
# chaude. », « Basse. »), au plus 0,02 avec une confiance d'au moins −0,71.
SEUIL_SANS_PAROLE, SEUIL_CONFIANCE, SEUIL_RECOPIE = 0.3, -0.8, 0.2


def transcription_douteuse(texte: str, segments: list) -> bool:
    """Vrai si Whisper a probablement inventé ce texte sur un passage sans parole."""
    if not segments:
        return False
    sans_parole = max(s.no_speech_prob for s in segments)
    confiance = min(s.avg_logprob for s in segments)
    return (sans_parole >= SEUIL_SANS_PAROLE and confiance <= SEUIL_CONFIANCE) or (
        sans_parole >= SEUIL_RECOPIE and est_recopie_du_contexte(texte))


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
                # Garde-fous mesurés sur le test de Noah : sans eux, Whisper recommençait plusieurs fois
                # quand il hésitait (jusqu'à 14 s) ou bouclait (« plafondage, plafondage… »).
                temperature=0.0,
                no_repeat_ngram_size=3,
                max_new_tokens=int(len(audio) / 16_000 * 8) + 8,
            )
            segments = list(segments)
            texte = " ".join(s.text.strip() for s in segments)
        if est_hallucination(texte) or transcription_douteuse(texte, segments):
            if texte:
                log.info("Transcription écartée (probablement inventée sur du silence) : %r", texte)
            return ""
        return corriger(texte)

    def transcrire_guide(self, audio: np.ndarray, attendues: list[str]) -> str:
        """Réécoute d'une réponse courte, en donnant à Whisper les réponses attendues à la question posée (« VMC,
        naturelle ») : il retrouve « VMC » là où la transcription rapide entendait « Vaime s. ». Sur un bruit, Whisper
        recopie souvent cette liste : une réponse qui en contient plusieurs est écartée."""
        indices = ", ".join(attendues[:12])
        with self._verrou:
            segments, _ = self._charger().transcribe(
                audio, language="fr", beam_size=self.faisceau, initial_prompt=f"Réponses possibles : {indices}.",
                condition_on_previous_text=False, without_timestamps=True, vad_filter=False, temperature=0.0,
                no_repeat_ngram_size=3, max_new_tokens=int(len(audio) / 16_000 * 8) + 8,
            )
            segments = list(segments)
            texte = " ".join(s.text.strip() for s in segments)
        if est_hallucination(texte) or (segments and max(s.no_speech_prob for s in segments) >= SEUIL_SANS_PAROLE
                                        and min(s.avg_logprob for s in segments) <= SEUIL_CONFIANCE):
            return ""
        return corriger(texte)


class TranscripteurFastConformer:
    """Option : FastConformer français de NVIDIA (CC-BY-4.0, mention de la source requise), version ONNX
    d'OpenVoiceOS, via onnx-asr (MIT). Pas de vocabulaire de contexte possible."""

    MODELE = "OpenVoiceOS/stt_fr_fastconformer_hybrid_large_pc_onnx"

    def __init__(self) -> None:
        self._modele = None
        self._verrou = threading.Lock()

    nom = "FastConformer FR de NVIDIA (ONNX, option à l'essai)"

    def _charger(self):
        if self._modele is None:
            import onnx_asr
            import onnxruntime

            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = min(8, os.cpu_count() or 4)
            debut = time.perf_counter()
            self._modele = onnx_asr.load_model(self.MODELE, sess_options=options)
            log.info("Modèle %s chargé en %.1f s", self.MODELE, time.perf_counter() - debut)
        return self._modele

    def prechauffer(self) -> None:
        with self._verrou:
            self._charger()
        self.transcrire(np.zeros(16_000, dtype=np.float32))

    def transcrire(self, audio: np.ndarray) -> str:
        with self._verrou:
            texte = str(self._charger().recognize(audio.astype(np.float32))).strip()
        return "" if est_hallucination(texte) else corriger(texte)


class TranscripteurRapide:
    """Mode par défaut depuis l'étape 5 : le FastConformer transcrit chaque phrase (0,05 s au lieu de 2,3 s sur ce
    PC). Whisper, plus lent mais guidé par le vocabulaire métier, ne donne un second avis que pour une phrase que
    les règles n'ont pas comprise ; il dit aussi si ce n'était que du bruit (son garde-fou sur le silence).

    Mesuré sur le test réel de Noah (19 phrases, rejeu du 22/10/2026) : le FastConformer a mieux transcrit que
    Whisper « Et le mur est en brique » (Whisper : « embrique »), « Le plafond n'est pas isolé » (« des pays
    isolés »), « Il te faut quoi d'autre comme information ? » (« d'être ») ; moins bien « combles perdus »
    (« comblots », rattrapé par le lexique)."""

    def __init__(self, whisper: TranscripteurWhisper) -> None:
        self.rapide = TranscripteurFastConformer()
        self.whisper = whisper

    @property
    def nom(self) -> str:
        return f"FastConformer FR (rapide) + {self.whisper.nom} en second avis"

    def prechauffer(self) -> None:
        self.rapide.prechauffer()
        self.whisper.prechauffer()

    def transcrire(self, audio: np.ndarray) -> str:
        return self.rapide.transcrire(audio)

    def second_avis(self, audio: np.ndarray) -> str:
        """Transcription Whisper (vocabulaire métier) ; chaîne vide si ce n'était probablement pas de la parole."""
        return self.whisper.transcrire(audio)

    def reecoute_guidee(self, audio: np.ndarray, attendues: list[str]) -> str:
        """Whisper guidé par les réponses attendues à la question posée (voir TranscripteurWhisper.transcrire_guide)."""
        return self.whisper.transcrire_guide(audio, attendues)


def creer_transcripteur(mode: str, modele: str, appareil: str, faisceau: int):
    """« rapide » (FastConformer + Whisper en second avis), « whisper », « fastconformer », « simulation » ou « auto »
    (rapide si les deux moteurs sont installés, sinon whisper)."""
    if mode == "simulation":
        return TranscripteurSimulation()
    if mode == "fastconformer":
        import onnx_asr  # noqa: F401  (erreur claire si l'option n'est pas installée)

        return TranscripteurFastConformer()
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        if mode in ("whisper", "rapide"):
            raise
        log.warning("faster-whisper n'est pas installé : transcription en simulation")
        return TranscripteurSimulation()
    if mode in ("rapide", "auto"):
        try:
            import onnx_asr  # noqa: F401
        except ImportError:
            if mode == "rapide":
                raise
            log.warning("onnx-asr n'est pas installé : transcription par Whisper seul (plus lente)")
        else:
            return TranscripteurRapide(TranscripteurWhisper(modele, appareil, faisceau))
    return TranscripteurWhisper(modele, appareil, faisceau)
