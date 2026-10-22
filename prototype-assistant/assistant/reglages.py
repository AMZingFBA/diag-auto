"""Réglages du prototype, lus dans les variables d'environnement (valeurs par défaut entre parenthèses)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DOSSIER_PROTOTYPE = Path(__file__).resolve().parents[1]


def _env(nom: str, defaut: str) -> str:
    return os.environ.get(nom, "").strip() or defaut


@dataclass
class Reglages:
    # Cerveau : « auto » (Claude Code s'il est trouvé, sinon simulation), « claude » ou « simulation ».
    cerveau: str = field(default_factory=lambda: _env("DIAGAUTO_CERVEAU", "auto"))
    modele: str = field(default_factory=lambda: _env("DIAGAUTO_MODELE", "claude-haiku-5-5"))
    effort: str = field(default_factory=lambda: _env("DIAGAUTO_EFFORT", "low"))
    # Images envoyées à Claude : « message » (dans le message, le plus rapide) ou « fichiers » (outil Read).
    images: str = field(default_factory=lambda: _env("DIAGAUTO_IMAGES", "message"))
    # Transcription : « auto » (faster-whisper s'il est installé), « whisper » ou « simulation ».
    transcription: str = field(default_factory=lambda: _env("DIAGAUTO_TRANSCRIPTION", "auto"))
    whisper_modele: str = field(default_factory=lambda: _env("DIAGAUTO_WHISPER_MODELE", "auto"))
    whisper_appareil: str = field(default_factory=lambda: _env("DIAGAUTO_WHISPER_APPAREIL", "auto"))
    whisper_faisceau: int = field(default_factory=lambda: int(_env("DIAGAUTO_WHISPER_FAISCEAU", "1")))
    fin_silence_s: float = field(default_factory=lambda: float(_env("DIAGAUTO_FIN_SILENCE", "0.7")))
    veille_s: float = field(default_factory=lambda: float(_env("DIAGAUTO_VEILLE_S", "10")))
    questions_par_minute: int = field(default_factory=lambda: int(_env("DIAGAUTO_QUESTIONS_MINUTE", "6")))
    # Code d'accès facultatif (conseillé dès que le serveur est joignable hors du réseau local).
    code: str = field(default_factory=lambda: _env("DIAGAUTO_CODE", ""))
    dossier_sessions: Path = field(default_factory=lambda: Path(_env("DIAGAUTO_SESSIONS", str(DOSSIER_PROTOTYPE / "sessions"))))
