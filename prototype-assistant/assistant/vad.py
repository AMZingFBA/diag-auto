"""Détection de début et de fin de phrase (VAD) sur le son reçu du téléphone.

Méthode simple, sans modèle (donc sans question de licence) : énergie du son, comparée à un
plancher de bruit qui s'adapte au lieu. Silero VAD reste à évaluer (licence à lever, voir
docs/02-capture-video.md § 3.6).

Le son arrive en morceaux de PCM 16 bits mono à 16 kHz, chacun avec l'instant de son premier
échantillon dans la vidéo (horloge du téléphone). Un trou dans les instants (perte de réseau)
coupe proprement la phrase en cours.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

TAUX = 16_000
TRAME = 480  # 30 ms


@dataclass
class ReglagesVad:
    fin_silence_s: float = 0.7  # silence qui termine une phrase (docs : 0,5 à 0,8 s)
    debut_s: float = 0.09  # parole continue avant de déclarer un début
    # Son gardé avant le début détecté et après la fin. Mesuré sur le test de Noah (iPhone, 22/10/2026) :
    # avec 0,3 s avant et 0,2 s après, Whisper se trompait sur les réponses d'un ou deux mots
    # (« BESSE » pour « bas », « O, chaudi » pour « eau chaude ») ; avec 1 s et 0,5 s, il les comprend.
    pre_roll_s: float = 1.0
    fin_gardee_s: float = 0.5
    duree_min_s: float = 0.35  # en dessous : bruit (toux, porte), ignoré
    duree_max_s: float = 15.0  # au-delà : phrase coupée de force
    marge_db: float = 12.0  # au-dessus du plancher de bruit = parole
    seuil_absolu_db: float = -48.0  # jamais de parole en dessous
    marge_ia_parle_db: float = 10.0  # marge en plus quand l'IA parle (écho du haut-parleur)
    # Parole confirmée (étape 8) : c'est seulement là que la voix de l'assistant est coupée. Test de Noah du 22/10/2026 :
    # un claquement de 0,1 à 0,3 s arrivait juste après chaque phrase de l'assistant (le téléphone qui bascule sa sortie
    # son) ; détecté comme un début de parole, il coupait la voix, et la réponse n'était jamais entendue.
    confirmation_s: float = 0.35
    confirmation_ia_parle_s: float = 0.6  # plus long quand l'assistant parle : son écho n'est pas une prise de parole
    # Bruit de fond suivi même pendant la « parole » : les 10 % de trames les plus faibles des 2 dernières secondes. La
    # parole a toujours des creux (entre les mots), pas un bruit continu. Visite de Noah du 22/10 au soir : bruit à −45 dB
    # dès le lancement, au-dessus du seuil de départ (−48 dB) ; tout était « parole », le plancher ne s'adaptait jamais, et
    # la première phrase n'était coupée qu'au bout de 15 s.
    fenetre_fond_s: float = 2.0


@dataclass
class Phrase:
    """Une phrase détectée : son (float32, -1..1) et instants de début et de fin dans la vidéo."""

    audio: np.ndarray
    t_debut: float
    t_fin: float

    @property
    def duree(self) -> float:
        return self.t_fin - self.t_debut


@dataclass
class Evenement:
    type: str  # « debut », « parole » (parole confirmée : assez longue pour ne pas être un bruit) ou « fin »
    t: float
    phrase: Phrase | None = None


@dataclass
class DetecteurPhrases:
    reglages: ReglagesVad = field(default_factory=ReglagesVad)
    ia_parle: bool = False

    def __post_init__(self) -> None:
        self.plancher_db = -60.0
        self._reste = np.zeros(0, dtype=np.float32)
        self._t_reste = 0.0  # instant du premier échantillon de _reste
        self._t_attendu: float | None = None
        self._historique: list[np.ndarray] = []  # trames récentes (pré-roll)
        self._en_parole = False
        self._trames_parole = 0
        self._trames_silence = 0
        self._phrase: list[np.ndarray] = []
        self._trames_avant = 0
        self._t_debut_phrase = 0.0
        self._trames_parlees = 0  # trames de parole depuis le début de la phrase (pour la confirmer)
        self._confirmee = False
        self._niveaux: deque[float] = deque(maxlen=max(1, int(self.reglages.fenetre_fond_s * TAUX / TRAME)))

    @staticmethod
    def niveau_db(trame: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(trame.astype(np.float64) ** 2)))
        return 20 * np.log10(max(rms, 1e-6))

    def ajouter(self, pcm16: bytes | np.ndarray, t_debut: float) -> list[Evenement]:
        """Ajoute un morceau de son ; renvoie les débuts et fins de phrase détectés."""
        audio = np.frombuffer(pcm16, dtype="<i2") if isinstance(pcm16, (bytes, bytearray)) else pcm16
        audio = audio.astype(np.float32) / 32768.0
        evenements: list[Evenement] = []
        if self._t_attendu is not None and abs(t_debut - self._t_attendu) > 0.25:
            evenements += self.terminer()  # trou dans le son : on clôt ce qui était en cours
            self._reste = np.zeros(0, dtype=np.float32)
        if not len(self._reste):
            self._t_reste = t_debut
        self._t_attendu = t_debut + len(audio) / TAUX
        self._reste = np.concatenate([self._reste, audio])
        while len(self._reste) >= TRAME:
            trame, self._reste = self._reste[:TRAME], self._reste[TRAME:]
            evenements += self._trame(trame, self._t_reste)
            self._t_reste += TRAME / TAUX
        return evenements

    def _trame(self, trame: np.ndarray, t: float) -> list[Evenement]:
        r = self.reglages
        db = self.niveau_db(trame)
        if db > -100:  # en dessous : silence numérique (micro pas encore ouvert), pas un bruit de fond
            self._niveaux.append(db)
        if len(self._niveaux) * 2 >= self._niveaux.maxlen and (fond := float(np.percentile(self._niveaux, 10))) > self.plancher_db:
            self.plancher_db += 0.1 * (fond - self.plancher_db)
        seuil = max(r.seuil_absolu_db, self.plancher_db + r.marge_db)
        if self.ia_parle:
            seuil += r.marge_ia_parle_db
        parole = db > seuil
        if not parole:
            # Le plancher suit le bruit ambiant : vite vers le bas, lentement vers le haut.
            vitesse = 0.3 if db < self.plancher_db else 0.02
            self.plancher_db += vitesse * (db - self.plancher_db)

        n_pre = int(r.pre_roll_s * TAUX / TRAME)
        evenements: list[Evenement] = []
        if not self._en_parole:
            self._historique = (self._historique + [trame])[-(n_pre + 1):]
            self._trames_parole = self._trames_parole + 1 if parole else 0
            if self._trames_parole * TRAME / TAUX >= r.debut_s:
                self._en_parole = True
                self._trames_silence = 0
                self._phrase = list(self._historique)
                self._trames_avant = len(self._phrase) - self._trames_parole  # pré-roll (sans la parole déjà là)
                self._t_debut_phrase = t + TRAME / TAUX - len(self._phrase) * TRAME / TAUX
                self._historique = []
                self._trames_parlees = self._trames_parole
                self._confirmee = False
                evenements.append(Evenement("debut", t))
            return evenements

        self._phrase.append(trame)
        self._trames_silence = 0 if parole else self._trames_silence + 1
        if parole and not self._confirmee:
            self._trames_parlees += 1
            seuil_s = r.confirmation_ia_parle_s if self.ia_parle else r.confirmation_s
            if self._trames_parlees * TRAME / TAUX >= seuil_s:
                self._confirmee = True
                evenements.append(Evenement("parole", t))
        duree = len(self._phrase) * TRAME / TAUX
        if self._trames_silence * TRAME / TAUX >= r.fin_silence_s or duree >= r.duree_max_s:
            evenements += self._clore(t + TRAME / TAUX)
        return evenements

    def _clore(self, t_fin: float) -> list[Evenement]:
        r = self.reglages
        silence_final = self._trames_silence * TRAME
        audio = np.concatenate(self._phrase) if self._phrase else np.zeros(0, dtype=np.float32)
        if silence_final:
            audio = audio[: max(0, len(audio) - silence_final + min(silence_final, int(r.fin_gardee_s * TAUX)))]
        parole_s = (len(self._phrase) - self._trames_avant - self._trames_silence) * TRAME / TAUX
        self._en_parole = False
        self._phrase = []
        self._trames_parole = 0
        self._trames_silence = 0
        if parole_s < r.duree_min_s:
            return [Evenement("fin", t_fin, None)]  # trop court : bruit
        return [Evenement("fin", t_fin, Phrase(audio, self._t_debut_phrase, self._t_debut_phrase + len(audio) / TAUX))]

    def terminer(self) -> list[Evenement]:
        """Clôt la phrase en cours (fin du flux, coupure réseau)."""
        if not self._en_parole:
            return []
        return self._clore(self._t_attendu or self._t_debut_phrase)
