"""Tours de pièce (Noah, 23/10 : « on arrive dans une pièce, on fait un tour très rapide avec notre téléphone, 3 secondes
par pièce maximum »), repérés en direct dans les capteurs du téléphone (environ 15 mesures par seconde, par lots).

Un tour : la caméra tourne presque sur place, à peu près à l'horizontale, et balaie toute la pièce en quelques secondes.
Il est reconnu à sa rotation (lacet du gyroscope, sinon cap de la boussole, déroulé sans saut à 360°) :
- la rotation commence au-dessus de 40°/s et s'arrête quand elle reste sous 20°/s pendant 0,4 s ;
- elle dure 8 s au plus (le balayage lent d'une description de DPE n'est jamais un tour) ;
- elle filme toutes les directions (couverture, champ de la caméra compris, d'au moins 330°), ou tourne d'au moins 270°
  presque dans un seul sens ;
- la caméra est à moins de 45° de l'horizontale au moins 70 % du temps : un téléphone qui bascule vers le plafond, puis
  qu'on pose, n'a pas fait le tour de la pièce (faux tour de la visite du 23/10 au matin, 30,5 à 33,4 s) ;
- deux rotations dans le même sens à moins d'une seconde d'écart n'en font qu'une (une pause au milieu du tour).

Mesuré sur les relevés réels (tests/test_tour.py) : le seul vrai tour enregistré (visite du 23/10 au matin, 14,6 à 17,2 s,
environ 380° en 2,2 s) est trouvé ; aucun faux tour sur les visites sans tour. À 1 mesure par seconde, un tour est
invisible : il faut le relevé à 15 mesures par seconde, envoyé en direct.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

DEBUT_DEG_S = 40.0
FIN_DEG_S = 20.0
CALME_S = 0.4
DUREE_MAX_S = 8.0
TROU_MAX_S = 0.5  # plus de 0,5 s sans mesure (page cachée, caméra vers le sol) : la rotation suivie s'interrompt
COUVERTURE_MIN_DEG = 330.0
NETTE_MIN_DEG = 270.0
PART_NETTE = 0.8  # rotation nette ≥ 80 % de la rotation parcourue : « presque dans un seul sens »
CHAMP_DEG = 45.0  # champ horizontal d'un téléphone tenu en portrait (mesuré sur les visites de Noah : 44 à 45°)
HORIZONTALE_DEG = 45.0
PART_HORIZONTALE = 0.7
FUSION_S = 1.0
AVANT_S = 2.0  # le cap des 2 s avant le tour : la direction de la marche en entrant dans la pièce
FENETRE_VITESSE_S = 0.2


def ecart(a: float, b: float) -> float:
    """b − a, ramené entre −180 et 180 degrés."""
    return (b - a + 180.0) % 360.0 - 180.0


def mediane_circulaire(angles: list[float]) -> float | None:
    if not angles:
        return None
    x = sum(math.cos(math.radians(a)) for a in angles)
    y = sum(math.sin(math.radians(a)) for a in angles)
    centre = math.degrees(math.atan2(y, x)) % 360.0
    # Médiane autour de la moyenne : robuste à quelques mesures fausses.
    return (centre + sorted(ecart(centre, a) for a in angles)[len(angles) // 2]) % 360.0


@dataclass
class Tour:
    t_debut: float
    t_fin: float
    rotation: float  # degrés, signée : positive dans le sens des aiguilles d'une montre vu de dessus (comme le cap)
    couverture: float  # directions filmées, champ de la caméra compris (au plus 360°)
    repere: str  # « lacet » (gyroscope, sans nord) ou « cap » (boussole)
    angle_debut: float  # lacet (ou cap) de la caméra au début du tour, dans ce repère
    cap_avant: float | None = None  # lacet (ou cap) médian des 2 s avant le tour, dans ce repère : la marche à l'entrée
    horizontale: float = 1.0  # part du temps où la caméra était à moins de 45° de l'horizontale

    @property
    def duree(self) -> float:
        return self.t_fin - self.t_debut

    def vers_dict(self) -> dict:
        return {"t_debut": round(self.t_debut, 2), "t_fin": round(self.t_fin, 2), "duree_s": round(self.duree, 2),
                "rotation": round(self.rotation, 1), "couverture": round(self.couverture, 1), "repere": self.repere,
                "angle_debut": round(self.angle_debut, 1),
                "cap_avant": None if self.cap_avant is None else round(self.cap_avant, 1),
                "horizontale": round(self.horizontale, 2)}


@dataclass
class _Point:
    t: float
    brut: float  # angle mesuré (0 à 360) dans le repère du suivi
    deroule: float
    horizontal: bool | None


@dataclass
class _Rotation:
    points: list[_Point] = field(default_factory=list)
    dernier_rapide: float = 0.0


def horizontal(mesure: dict) -> bool | None:
    """Caméra à l'horizontale (± 45°) ? Par l'élévation si le téléphone la donne, sinon par beta (téléphone en portrait :
    90 = droit, élévation ≈ beta − 90). None si rien n'est connu."""
    elevation = mesure.get("elevation")
    if isinstance(elevation, (int, float)):
        return abs(elevation) <= HORIZONTALE_DEG
    beta = mesure.get("inclinaison")
    if isinstance(beta, (int, float)):
        return abs(beta - 90.0) <= HORIZONTALE_DEG
    return None


class DetecteurTour:
    """Reçoit les mesures dans l'ordre (``ajouter``) et rend chaque tour dès qu'il est fini."""

    def __init__(self, champ: float = CHAMP_DEG) -> None:
        self.champ = champ
        self.repere: str | None = None
        self.historique: deque[_Point] = deque(maxlen=400)  # ~25 s à 15 mesures par seconde
        self.rotation: _Rotation | None = None
        self.precedente: _Rotation | None = None  # rotation finie trop courte : un tour avec une pause au milieu ?
        self.tours: list[Tour] = []

    def ajouter(self, mesure: dict) -> Tour | None:
        t = mesure.get("t")
        if not isinstance(t, (int, float)):
            return None
        lacet, cap = mesure.get("lacet"), mesure.get("cap")
        repere, angle = ("lacet", lacet) if isinstance(lacet, (int, float)) else ("cap", cap) if isinstance(cap, (int, float)) else (None, None)
        if repere is None:
            return None  # caméra vers le sol ou le plafond, ou pas de capteur
        dernier = self.historique[-1] if self.historique else None
        if dernier is not None and t <= dernier.t:
            return None  # mesure déjà vue (rattrapage après une coupure) ou dans le désordre
        if dernier is None or repere != self.repere or t - dernier.t > TROU_MAX_S:
            tour = self._interrompre()  # trou ou changement de capteur : la rotation suivie s'arrête là
            self.repere = repere
            self.historique.append(_Point(t, angle % 360.0, angle % 360.0, horizontal(mesure)))
            return tour
        point = _Point(t, angle % 360.0, dernier.deroule + ecart(dernier.brut, angle), horizontal(mesure))
        self.historique.append(point)
        vitesse = self._vitesse()
        if self.rotation is None:
            if vitesse >= DEBUT_DEG_S:
                # Le début vrai : en remontant, tant que la caméra tournait déjà (vitesse d'un point à l'autre ≥ 20°/s).
                passe = list(self.historique)
                debut = len(passe) - 2
                while debut > 0 and _vitesse_entre(passe[debut - 1], passe[debut]) >= FIN_DEG_S:
                    debut -= 1
                self.rotation = _Rotation(passe[debut:], t)
                if self.precedente is not None and passe[debut].t - self.precedente.points[-1].t > FUSION_S:
                    self.precedente = None
            return None
        self.rotation.points.append(point)
        if vitesse >= FIN_DEG_S:
            self.rotation.dernier_rapide = t
        if t - self.rotation.dernier_rapide >= CALME_S:
            return self._finir()
        if t - self.rotation.points[0].t > 3 * DUREE_MAX_S:
            self.rotation = None  # tourne sans fin : ce n'est pas un tour (et la mémoire reste bornée)
        return None

    def finir(self) -> Tour | None:
        """Fin du relevé : une rotation en cours est jugée telle quelle."""
        return self._interrompre()

    def _vitesse(self) -> float:
        dernier = self.historique[-1]
        for point in reversed(self.historique):
            if dernier.t - point.t >= FENETRE_VITESSE_S:
                return abs(dernier.deroule - point.deroule) / (dernier.t - point.t)
        premier = self.historique[0]
        return abs(dernier.deroule - premier.deroule) / (dernier.t - premier.t) if dernier.t > premier.t else 0.0

    def _interrompre(self) -> Tour | None:
        tour = self._finir() if self.rotation is not None else None
        self.precedente = None
        return tour

    def _finir(self) -> Tour | None:
        rotation, self.rotation = self.rotation, None
        # Jusqu'au dernier point atteint en tournant encore (≥ 20°/s depuis le précédent) : la fin calme n'en est pas.
        fin = len(rotation.points) - 1
        while fin > 1 and _vitesse_entre(rotation.points[fin - 1], rotation.points[fin]) < FIN_DEG_S:
            fin -= 1
        points = rotation.points[: fin + 1]
        precedente = self.precedente
        if (precedente is not None and points[0].t - precedente.points[-1].t <= FUSION_S
                and _sens(precedente.points) * _sens(points) > 0):
            points = precedente.points + [p for p in points if p.t > precedente.points[-1].t]
        tour = self._juger(points)
        self.precedente = None if tour else _Rotation(points, points[-1].t)
        if tour:
            self.tours.append(tour)
        return tour

    def _juger(self, points: list[_Point]) -> Tour | None:
        if len(points) < 3:
            return None
        debut, fin = points[0], points[-1]
        if fin.t - debut.t > DUREE_MAX_S or fin.t - debut.t <= 0:
            return None
        nette = fin.deroule - debut.deroule
        parcourue = sum(abs(b.deroule - a.deroule) for a, b in zip(points, points[1:]))
        etendue = max(p.deroule for p in points) - min(p.deroule for p in points)
        couverture = min(360.0, etendue + self.champ)
        tout_vu = couverture >= COUVERTURE_MIN_DEG
        un_sens = abs(nette) >= NETTE_MIN_DEG and abs(nette) >= PART_NETTE * parcourue
        if not (tout_vu or un_sens):
            return None
        connus = [p.horizontal for p in points if p.horizontal is not None]
        part = sum(connus) / len(connus) if connus else 1.0
        if part < PART_HORIZONTALE:
            return None
        avant = [p.brut for p in self.historique if debut.t - AVANT_S <= p.t <= debut.t - 0.2]
        return Tour(debut.t, fin.t, nette, couverture, self.repere or "", debut.brut, mediane_circulaire(avant), part)


def _vitesse_entre(a: _Point, b: _Point) -> float:
    return abs(b.deroule - a.deroule) / (b.t - a.t) if b.t > a.t else 0.0


def _sens(points: list[_Point]) -> float:
    return points[-1].deroule - points[0].deroule


def detecter(mesures: list[dict], champ: float = CHAMP_DEG) -> list[Tour]:
    """Tous les tours d'un relevé complet (capteurs-continus.json, ou les lots reçus en direct)."""
    detecteur = DetecteurTour(champ)
    for mesure in sorted((m for m in mesures if isinstance(m.get("t"), (int, float))), key=lambda m: m["t"]):
        detecteur.ajouter(mesure)
    detecteur.finir()
    return detecteur.tours
