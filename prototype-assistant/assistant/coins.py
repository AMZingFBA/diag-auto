"""Relevé des murs : la forme exacte de chaque pièce, par la géométrie (Noah, 23/10, après son essai de 15:06 : « le plus
safe, ce serait de suivre les murs de la maison »).

Dans chaque pièce, le diagnostiqueur ouvre le relevé (bouton « Murs », ou « les murs » à la voix), puis vise chaque coin
au ras du sol avec la croix du milieu de l'écran et s'y arrête une seconde : un bip par coin. Revenir sur le premier coin
ferme la pièce. Le téléphone donne la direction de la caméra (gyroscope : à 1° près sur une pièce) et son inclinaison vers
le sol (pesanteur, téléphone immobile : à 1° près) : le coin est devant lui, à h / tan(inclinaison), h étant la hauteur du
téléphone (1,40 m, hypothèse). Un coin caché par un meuble se vise au plafond : à (H − h) / tan(angle), H étant la hauteur
sous plafond (2,50 m, hypothèse). Ni intelligence artificielle ni reconnaissance d'image : de la géométrie, sur n'importe
quel téléphone.

Les coins d'une pièce donnent son contour d'équerre (assistant/geometrie.py : rectangle, L, couloir…). Simulation (main
qui tremble de 1°, téléphone 5 cm plus bas que supposé) : la forme exacte, les murs à 2 à 5 % près ; une erreur sur h
agrandit ou rétrécit toute la pièce sans la déformer. Les cotes restent « estimées » : le Carrez se mesure au laser.

Pourquoi un relevé qu'on ouvre, et pas des coins pris à chaque arrêt : dans les visites de Noah du 23/10, la caméra s'arrête
11 à 17 fois par visite en regardant le sol (téléphone tenu à −22° en marchant, arrêts pour parler) ; ce seraient autant de
faux coins.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .geometrie import HAUTEUR_CAMERA_M, RESIDU_MAX_DEG, Coin, Forme, ajuster, ecart, regrouper, VueCoin

HAUTEUR_PLAFOND_M = 2.50  # hauteur sous plafond habituelle (hypothèse), pour un coin visé au plafond
IMMOBILE_S = 0.8  # la croix reste sur le coin 0,8 s
TOLERANCE_DEG = 2.0  # la main tremble : la croix bouge de moins de 2° autour de sa moyenne
DERIVE_MAX_DEG = 1.5  # et pas plus de 1,5° du début à la fin (un balayage lent n'est pas un arrêt)
SOUS_HORIZON_DEG = (8.0, 72.0)  # un coin au sol : de 8° (à 10 m) à 72° sous l'horizon (au-delà : on regarde ses pieds)
PLAFOND_DEG = (12.0, 70.0)  # un coin au plafond : au-dessus de l'horizon
REARMEMENT_DEG = 6.0  # la croix doit quitter le coin avant d'en viser un autre
MEME_COIN_DEG = 8.0  # revenir à moins de 8° du premier coin ferme la pièce
HISTORIQUE_S = 15.0


@dataclass
class Visee:
    """La croix arrêtée sur un coin : direction de la caméra (lacet, ou cap sans gyroscope) et élévation (négative vers le
    sol), moyennes sur l'arrêt."""
    t: float
    direction: float
    elevation: float
    plafond: bool

    def vers_dict(self) -> dict:
        return {"t": self.t, "direction": round(self.direction, 1), "elevation": round(self.elevation, 1), "plafond": self.plafond}


def distance(visee: Visee, hauteur: float = HAUTEUR_CAMERA_M, plafond: float = HAUTEUR_PLAFOND_M) -> float:
    """Distance horizontale du téléphone au coin visé."""
    angle = math.radians(abs(visee.elevation))
    return (plafond - hauteur) / math.tan(angle) if visee.plafond else hauteur / math.tan(angle)


class DetecteurCoins:
    """Repère les arrêts de la croix sur un coin dans les mesures du téléphone (≈ 15 par seconde)."""

    def __init__(self) -> None:
        self._mesures: deque[tuple[float, float, float]] = deque()  # (t, direction déroulée, élévation)
        self._repere: str | None = None
        self._derniere: tuple[float, float] | None = None  # (direction déroulée, élévation) du dernier coin
        self._arme = True

    def reprendre(self) -> None:
        """Le relevé s'ouvre : un arrêt d'avant ne compte pas, il faut viser."""
        self._mesures.clear()
        self._derniere, self._arme = None, True

    def ajouter(self, mesure: dict) -> Visee | None:
        t, lacet, cap, elevation = (mesure.get(k) for k in ("t", "lacet", "cap", "elevation"))
        if not isinstance(t, (int, float)) or not isinstance(elevation, (int, float)):
            return None
        if isinstance(lacet, (int, float)):
            repere, angle = "lacet", float(lacet)
        elif isinstance(cap, (int, float)) and self._repere != "lacet":
            repere, angle = "cap", float(cap)
        else:
            return None
        self._repere = self._repere or repere
        if repere != self._repere or (self._mesures and t <= self._mesures[-1][0]):
            return None
        deroule = angle if not self._mesures else self._mesures[-1][1] + ecart(self._mesures[-1][1] % 360.0, angle)
        self._mesures.append((float(t), deroule, float(elevation)))
        while self._mesures[0][0] < t - HISTORIQUE_S:
            self._mesures.popleft()
        if not self._arme:
            if self._derniere is None or (abs(deroule - self._derniere[0]) < REARMEMENT_DEG
                                          and abs(elevation - self._derniere[1]) < REARMEMENT_DEG):
                return None
            self._arme = True
        fenetre = [m for m in self._mesures if m[0] >= t - IMMOBILE_S]
        if len(fenetre) < 6 or fenetre[0][0] > t - IMMOBILE_S + 0.15:
            return None
        directions, elevations = [m[1] for m in fenetre], [m[2] for m in fenetre]
        d, e = sum(directions) / len(directions), sum(elevations) / len(elevations)
        if (max(abs(x - d) for x in directions) > TOLERANCE_DEG or max(abs(x - e) for x in elevations) > TOLERANCE_DEG
                or abs(directions[-1] - directions[0]) > DERIVE_MAX_DEG or abs(elevations[-1] - elevations[0]) > DERIVE_MAX_DEG):
            return None
        if SOUS_HORIZON_DEG[0] <= -e <= SOUS_HORIZON_DEG[1]:
            plafond = False
        elif PLAFOND_DEG[0] <= e <= PLAFOND_DEG[1]:
            plafond = True
        else:
            return None
        self._derniere, self._arme = (d, e), False
        return Visee(round((fenetre[0][0] + t) / 2.0, 3), d % 360.0, e, plafond)


@dataclass
class CoinVise:
    """Un coin relevé, dans le repère de la trajectoire (celui du plan) : le téléphone était en `depuis`."""
    visee: Visee
    x: float
    y: float
    depuis: tuple[float, float]

    def vers_dict(self) -> dict:
        return {**self.visee.vers_dict(), "x": round(self.x, 3), "y": round(self.y, 3),
                "depuis": [round(self.depuis[0], 3), round(self.depuis[1], 3)]}


def coin_vise(visee: Visee, depuis: tuple[float, float], hauteur: float = HAUTEUR_CAMERA_M,
              plafond: float = HAUTEUR_PLAFOND_M) -> CoinVise:
    d = distance(visee, hauteur, plafond)
    a = math.radians(visee.direction)
    return CoinVise(visee, depuis[0] + d * math.sin(a), depuis[1] + d * math.cos(a), depuis)


def ferme(coins: list[CoinVise], visee: Visee) -> bool:
    """Revenir sur le premier coin (au moins 4 coins relevés) ferme la pièce."""
    if len(coins) < 4:
        return False
    premier = coins[0].visee
    return abs(ecart(premier.direction, visee.direction)) < MEME_COIN_DEG and abs(premier.elevation - visee.elevation) < 6.0 \
        and premier.plafond == visee.plafond


def _rectangle_de_trois(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Trois coins d'un rectangle (le quatrième caché) : le quatrième, en face de celui qui fait l'angle droit."""
    meilleur = None
    for k in range(3):
        b, a, c = points[k], points[(k + 1) % 3], points[(k + 2) % 3]
        u, v = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        if nu < 0.3 or nv < 0.3:
            return None
        cosinus = abs(u[0] * v[0] + u[1] * v[1]) / (nu * nv)
        if meilleur is None or cosinus < meilleur[0]:
            meilleur = (cosinus, (a[0] + c[0] - b[0], a[1] + c[1] - b[1]))
    return meilleur[1] if meilleur and meilleur[0] < math.sin(math.radians(15.0)) else None


def forme(coins: list[CoinVise]) -> Forme | None:
    """La pièce d'équerre dont ces coins ont été relevés, dans le repère de la trajectoire (ses sommets dans l'ordre des
    aiguilles d'une montre vu de dessus). Les directions et distances sont prises depuis le point moyen d'où l'on a visé ;
    un coin visé deux fois (au sol puis au plafond) compte une fois ; trois coins d'un rectangle suffisent ; un coin de
    trop (une visée ratée) est écarté si la pièce est alors d'équerre."""
    if len(coins) < 3:
        return None
    ox = sum(c.depuis[0] for c in coins) / len(coins)
    oy = sum(c.depuis[1] for c in coins) / len(coins)
    vues = [VueCoin(math.degrees(math.atan2(c.x - ox, c.y - oy)) % 360.0, 1.0, math.hypot(c.x - ox, c.y - oy)) for c in coins]
    groupes = regrouper(vues)
    if len(groupes) == 3:
        points = [(g.distance * math.sin(math.radians(g.direction)), g.distance * math.cos(math.radians(g.direction)))
                  for g in groupes]
        quatrieme = _rectangle_de_trois(points)
        if quatrieme is None:
            return None
        groupes = sorted(groupes + [Coin(math.degrees(math.atan2(*quatrieme)) % 360.0, 1.0, 0, math.hypot(*quatrieme))],
                         key=lambda g: g.direction)
    essais = [groupes] if len(groupes) % 2 == 0 else [groupes[:k] + groupes[k + 1:] for k in range(len(groupes))]
    meilleure = None
    for essai in essais:
        f = ajuster(essai) if len(essai) >= 4 else None
        if f is not None and f.echelle == "sol" and (meilleure is None or f.residu < meilleure.residu):
            meilleure = f
    if meilleure is None or meilleure.residu > RESIDU_MAX_DEG:
        return None
    meilleure.sommets = [(x + ox, y + oy) for x, y in meilleure.sommets]
    for mur in meilleure.murs:
        mur.debut, mur.fin = (mur.debut[0] + ox, mur.debut[1] + oy), (mur.fin[0] + ox, mur.fin[1] + oy)
    return meilleure
