"""Boussole du téléphone et orientation des murs et des fenêtres (étape 6 de Noah).

Dans LICIEL et en DPE 3CL, les parois et surtout les fenêtres sont décrites par leur orientation
(nord, est, sud, ouest) : elle sert au calcul des apports solaires.

Principe : quand le diagnostiqueur filme un mur de face, depuis l'intérieur de la pièce, la caméra
regarde vers l'extérieur de ce mur ; l'orientation du mur est donc le cap de la caméra, arrondi au
point cardinal le plus proche. Le cap brut est gardé.

Le téléphone envoie chaque seconde deux mesures :
- le **cap** de la boussole (magnétomètre) : absolu, mais faussé près du métal ou de l'électricité ;
- le **lacet** du gyroscope : juste pour les angles entre deux murs, mais sans origine (pas de nord).
La différence « cap − lacet » est la même pour toute la visite tant que la boussole n'est pas perturbée :
c'est la **correction**. Estimée sur de nombreuses mesures (médiane), elle donne l'orientation de chaque
mur par son lacet, même filmé là où la boussole est faussée ; et deux murs face à face sont toujours
opposés (nord ↔ sud). Si la boussole n'est pas fiable, l'orientation d'un seul mur, dite à l'oral,
fixe la correction : tous les autres murs s'en déduisent.
"""

from __future__ import annotations

import math
import tomllib
from collections import deque
from dataclasses import dataclass
from pathlib import Path

POINTS = ("nord", "est", "sud", "ouest")
CAP_DU_POINT = {"nord": 0.0, "est": 90.0, "sud": 180.0, "ouest": 270.0}
POINTS_8 = ("nord", "nord-est", "est", "sud-est", "sud", "sud-ouest", "ouest", "nord-ouest")

# Seuils : dans boussole.toml (à côté du dossier « assistant »), pour les ajuster sur le terrain sans toucher au code.
FICHIER_REGLAGES = Path(__file__).resolve().parents[1] / "boussole.toml"
REGLAGES_PAR_DEFAUT = {
    "precision": {"bonne": 15.0, "faible": 30.0},
    "dispersion": {"bonne": 12.0, "faible": 25.0},
    "visee": {"stabilite": 25.0, "inclinaison_min": 45.0, "inclinaison_max": 135.0},
    "correction": {"mesures_minimum": 5, "dementi": 45.0, "perturbation": 30.0},
    "coherence": {"face_a_face": 150.0, "meme_cote": 30.0},
    "iphone": {"inclinaison_calibrage": 60.0},
}


def lire_reglages(fichier: Path = FICHIER_REGLAGES) -> dict:
    """Seuils du fichier, complétés par les valeurs par défaut (fichier absent ou incomplet)."""
    lus = tomllib.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {}
    return {section: {**valeurs, **lus.get(section, {})} for section, valeurs in REGLAGES_PAR_DEFAUT.items()}


REGLAGES = lire_reglages()
PRECISION_BONNE, PRECISION_FAIBLE = REGLAGES["precision"]["bonne"], REGLAGES["precision"]["faible"]
DISPERSION_BONNE, DISPERSION_FAIBLE = REGLAGES["dispersion"]["bonne"], REGLAGES["dispersion"]["faible"]
STABILITE_VISEE = REGLAGES["visee"]["stabilite"]
INCLINAISON_MIN, INCLINAISON_MAX = REGLAGES["visee"]["inclinaison_min"], REGLAGES["visee"]["inclinaison_max"]
MESURES_MINIMUM = int(REGLAGES["correction"]["mesures_minimum"])
DEMENTI, PERTURBATION = REGLAGES["correction"]["dementi"], REGLAGES["correction"]["perturbation"]
FACE_A_FACE, MEME_COTE = REGLAGES["coherence"]["face_a_face"], REGLAGES["coherence"]["meme_cote"]


def point_cardinal(cap: float) -> str:
    """Cap en degrés (0 = nord, 90 = est) → « nord », « est », « sud » ou « ouest »."""
    return POINTS[int(((cap % 360) + 45) // 90) % 4]


def point_cardinal_8(cap: float) -> str:
    return POINTS_8[int(((cap % 360) + 22.5) // 45) % 8]


def ecart(a: float, b: float) -> float:
    """Écart signé entre deux caps, de −180 à 180 degrés (a − b)."""
    return (a - b + 180) % 360 - 180


def oppose(point: str) -> str:
    return POINTS[(POINTS.index(point) + 2) % 4]


def moyenne_circulaire(angles: list[float]) -> float:
    x = sum(math.cos(math.radians(a)) for a in angles)
    y = sum(math.sin(math.radians(a)) for a in angles)
    return math.degrees(math.atan2(y, x)) % 360


def mediane_circulaire(angles: list[float]) -> float:
    """Médiane d'angles (robuste aux mesures aberrantes), autour de leur moyenne circulaire."""
    centre = moyenne_circulaire(angles)
    ecarts = sorted(ecart(a, centre) for a in angles)
    return (centre + ecarts[len(ecarts) // 2]) % 360


def dispersion(angles: list[float]) -> float:
    """Écart médian à la médiane, en degrés."""
    centre = mediane_circulaire(angles)
    return sorted(abs(ecart(a, centre)) for a in angles)[len(angles) // 2]


@dataclass
class Mesure:
    t: float
    cap: float | None = None  # boussole, en degrés (0 = nord) : direction visée par la caméra
    lacet: float | None = None  # gyroscope, en degrés, origine quelconque
    precision: float | None = None  # précision annoncée (iPhone), en degrés ; None si inconnue
    inclinaison: float | None = None  # 90 = téléphone droit (caméra à l'horizontale)


@dataclass
class Visee:
    """Où visait la caméra pendant une phrase."""

    cap: float | None
    lacet: float | None
    stable: bool  # la caméra n'a pas balayé la pièce pendant la phrase


# « Le mur de gauche » : pas celui que la caméra regarde, mais celui à sa gauche (étape 13 : face au nord, c'est le mur
# ouest). Le cap croît vers la droite (nord 0°, est 90°), le lacet du gyroscope aussi.
DECALAGES = {"de gauche": -90.0, "de droite": 90.0, "de derrière": 180.0, "d'en face": 0.0, "du fond": 0.0}


def visee_decalee(visee: Visee, position: str) -> Visee:
    """La visée du mur désigné par sa position par rapport à la caméra (« de gauche », « de droite », « de derrière »)."""
    decalage = DECALAGES.get(position, 0.0)
    if not decalage:
        return visee
    return Visee(None if visee.cap is None else (visee.cap + decalage) % 360,
                 None if visee.lacet is None else (visee.lacet + decalage) % 360, visee.stable)


class Boussole:
    """Les mesures reçues du téléphone pendant la visite."""

    def __init__(self) -> None:
        self.mesures: deque[Mesure] = deque(maxlen=7200)  # 2 h à une mesure par seconde

    def ajouter(self, mesure: Mesure) -> None:
        self.mesures.append(mesure)

    def visee(self, t_debut: float, t_fin: float) -> Visee | None:
        """Cap et lacet de la caméra pendant la phrase, téléphone tenu à peu près droit (on filme un mur, pas le sol)."""
        mesures = [m for m in self.mesures if t_debut - 0.5 <= m.t <= t_fin + 0.5
                   and (m.inclinaison is None or INCLINAISON_MIN <= m.inclinaison <= INCLINAISON_MAX)]
        caps = [m.cap for m in mesures if m.cap is not None]
        lacets = [m.lacet for m in mesures if m.lacet is not None]
        if not caps and not lacets:
            return None
        reference = lacets or caps
        return Visee(cap=mediane_circulaire(caps) if caps else None, lacet=mediane_circulaire(lacets) if lacets else None,
                     stable=len(reference) == 1 or dispersion(reference) <= STABILITE_VISEE)

    def _ecarts(self) -> list[float]:
        return [ecart(m.cap, m.lacet) for m in self.mesures if m.cap is not None and m.lacet is not None
                and (m.precision is None or 0 <= m.precision <= PRECISION_FAIBLE)]

    def correction(self) -> float | None:
        """« cap = lacet + correction », estimée sur la visite ; None si la boussole n'est pas assez fiable."""
        ecarts = self._ecarts()
        if len(ecarts) < MESURES_MINIMUM or dispersion(ecarts) > DISPERSION_FAIBLE:
            return None
        return mediane_circulaire(ecarts)

    def fiabilite(self) -> str:
        """« bonne », « moyenne », « faible », « absente » (le téléphone n'a pas de boussole, ou l'accès est refusé) ou
        « inconnue » (rien reçu du téléphone : essai écrit, rejeu d'une ancienne visite)."""
        if not self.mesures:
            return "inconnue"
        caps = [m for m in self.mesures if m.cap is not None]
        if not caps:
            return "absente"
        precisions = [m.precision for m in caps[-30:] if m.precision is not None]
        if precisions and (min(precisions) < 0 or sorted(precisions)[len(precisions) // 2] > PRECISION_FAIBLE):
            return "faible"
        ecarts = self._ecarts()
        if len(ecarts) >= MESURES_MINIMUM:
            d = dispersion(ecarts)
            if d > DISPERSION_FAIBLE:
                return "faible"
            if d > DISPERSION_BONNE:
                return "moyenne"
        if precisions and sorted(precisions)[len(precisions) // 2] > PRECISION_BONNE:
            return "moyenne"
        return "bonne"

    @property
    def gyroscope(self) -> bool:
        """Le téléphone donne un lacet : les angles entre murs sont connus, même sans boussole fiable."""
        return any(m.lacet is not None for m in self.mesures)
