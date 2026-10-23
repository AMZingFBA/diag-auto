"""Trajectoire du téléphone dans un repère commun (Noah, 23/10 : « suivre les déplacements du téléphone dans un repère
commun, positionner les murs et les portes, puis rattacher les pièces à cette géométrie. Une rotation du téléphone sur
place ne doit pas être interprétée comme un déplacement ou un changement de pièce »).

Avant, rien ne suivait la position : le croquis était une grille, une case par pièce, posée dans l'ordre de détection du
côté où visait la caméra au moment où la pièce était reconnue.

Ici, navigation à l'estime (podomètre) :
- les pas viennent de l'accéléromètre du téléphone (web/app.js : un pic d'accélération, au plus un pas toutes les 0,3 s) ;
- chaque pas avance de 0,6 m (hypothèse : en marchant lentement en filmant ; à recaler sur une mesure) dans la direction
  de la caméra à cet instant (le lacet du gyroscope : juste pour les angles, sans dérive notable sur une visite) ;
- un pas compté pendant une rotation sur place (vitesse de rotation au-delà de 60°/s, ou pendant un tour de pièce repéré)
  n'est pas un déplacement : ce sont des piétinements.

Quand le téléphone suit lui-même sa position par le sol filmé (web/odometrie.js, tracé guidé du plan), chaque mesure en
donne la position (x, y) : elle remplace les pas (plus juste, à quelques centimètres près sur quelques mètres).

Repère : celui du gyroscope (x vers le lacet 90°, y vers le lacet 0°), le même pendant toute la visite ; tourné vers le
nord pour l'affichage dès que l'écart boussole − gyroscope est connu. Sans gyroscope (téléphone ancien), le cap.
Précision attendue (recherches du 23/10) : 0,5 à 1 m dans le bon cas sur 5 à 15 m, plus si la caméra ne vise pas le sens
de la marche ; c'est assez pour placer les pièces les unes par rapport aux autres, pas pour des cotes.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

LONGUEUR_PAS_M = 0.6
# Pas repérés sur le serveur dans l'accélération lissée (hors pesanteur) que le téléphone envoie avec chaque mesure : en
# marchant lentement en filmant, les pics ne dépassent souvent pas 0,6 m/s² (visite de Noah du 23/10 : le seuil de
# 1 m/s² du téléphone avait manqué tous les pas de 5 à 17 s ; 64 pas trouvés au lieu de 42). Quand ces mesures sont là,
# les pas envoyés par le téléphone sont ignorés (pas de double compte).
SEUIL_PAS_HAUT = 0.6
SEUIL_PAS_BAS = 0.1
ECART_PAS_MIN_S = 0.35
ROTATION_SUR_PLACE_DEG_S = 60.0
FENETRE_VITESSE_S = 0.3
PAUSE_MARCHE_S = 1.5  # plus de 1,5 s sans pas : la marche est finie
PAS_VO_M = 0.10  # position suivie par le téléphone : un point gardé tous les 10 cm (le reste est du tremblement)


def ecart(a: float, b: float) -> float:
    return (b - a + 180.0) % 360.0 - 180.0


@dataclass
class Pas:
    t: float
    direction: float | None  # cap de la caméra à cet instant, dans le repère de la trajectoire
    compte: bool  # faux : piétinement pendant une rotation sur place


@dataclass
class Marche:
    """Une suite de pas sans arrêt de plus de 1,5 s : on passe d'un endroit à un autre (peut-être d'une pièce à l'autre)."""
    t_debut: float
    t_fin: float
    distance: float


class Trajectoire:
    def __init__(self, longueur_pas: float = LONGUEUR_PAS_M) -> None:
        self.longueur_pas = longueur_pas
        self.repere: str | None = None  # « lacet » ou « cap »
        self._t: list[float] = []
        self._angle: list[float] = []  # lacet (ou cap) brut, 0 à 360
        self._deroule: list[float] = []
        self.pas: list[Pas] = []
        self.tours: list[tuple[float, float]] = []
        self._positions: list[tuple[float, float, float]] | None = None  # (t, x, y) après chaque pas compté ; en cache
        self._avec_acc = False  # le téléphone envoie l'accélération : les pas sont repérés ici
        self._pic = False
        self._dernier_pic = -1e9
        # Position suivie par le téléphone (sol filmé) : (t, x, y), un point tous les 10 cm ; les pas en sont déduits.
        self._vo: list[tuple[float, float, float]] = []
        self._vo_pas: tuple[float, float, float] | None = None  # où était le dernier pas déduit

    # --- Entrées ------------------------------------------------------------------------------------------------

    def ajouter_mesure(self, mesure: dict) -> None:
        t = mesure.get("t")
        lacet, cap = mesure.get("lacet"), mesure.get("cap")
        if not isinstance(t, (int, float)):
            return
        if isinstance(lacet, (int, float)):
            repere, angle = "lacet", float(lacet)
        elif isinstance(cap, (int, float)) and self.repere != "lacet":
            repere, angle = "cap", float(cap)
        else:
            return
        if self.repere is None:
            self.repere = repere
        if repere != self.repere or (self._t and t <= self._t[-1]):
            return
        deroule = angle if not self._deroule else self._deroule[-1] + ecart(self._angle[-1], angle)
        self._t.append(float(t))
        self._angle.append(angle % 360.0)
        self._deroule.append(deroule)
        x, y = mesure.get("x"), mesure.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            self._ajouter_position(float(t), float(x), float(y))
            return
        acc = mesure.get("acc")
        if isinstance(acc, (int, float)) and not self._vo:
            self._avec_acc = True
            if not self._pic and acc >= SEUIL_PAS_HAUT and t - self._dernier_pic >= ECART_PAS_MIN_S:
                self._pic, self._dernier_pic = True, float(t)
                self._noter_pas(float(t))
            elif self._pic and acc <= SEUIL_PAS_BAS:
                self._pic = False

    def _ajouter_position(self, t: float, x: float, y: float) -> None:
        """Position suivie par le téléphone. Tous les 0,6 m parcourus, un pas est déduit dans la direction du déplacement
        (les marches, l'axe du logement et le sens de la marche s'en servent comme des pas comptés)."""
        if not self._vo or math.dist(self._vo[-1][1:], (x, y)) >= PAS_VO_M:
            self._vo.append((t, x, y))
            self._positions = None
        if self._vo_pas is None:
            self._vo_pas = (t, x, y)
        elif math.dist(self._vo_pas[1:], (x, y)) >= self.longueur_pas:
            direction = math.degrees(math.atan2(x - self._vo_pas[1], y - self._vo_pas[2])) % 360.0
            self.pas.append(Pas(t, direction, True))
            self._vo_pas = (t, x, y)

    def ajouter_pas(self, t: float) -> None:
        """Un pas repéré par le téléphone (ignoré si le serveur repère lui-même les pas dans l'accélération, ou si le
        téléphone suit sa position)."""
        if not self._avec_acc and not self._vo:
            self._noter_pas(t)

    def _noter_pas(self, t: float) -> None:
        if self.pas and t <= self.pas[-1].t:
            return
        compte = self.vitesse_rotation(t) < ROTATION_SUR_PLACE_DEG_S and not self._pendant_un_tour(t)
        self.pas.append(Pas(float(t), self.direction(t), compte))
        self._positions = None

    def ajouter_tour(self, t_debut: float, t_fin: float) -> None:
        """Un tour de pièce repéré (assistant/tour.py) : les pas comptés pendant ce tour étaient des piétinements."""
        self.tours.append((t_debut, t_fin))
        for p in self.pas:
            if t_debut - 0.2 <= p.t <= t_fin + 0.2:
                p.compte = False
        self._positions = None

    # --- Lectures -----------------------------------------------------------------------------------------------

    def direction(self, t: float) -> float | None:
        """Cap de la caméra (0 à 360) à l'instant t, interpolé entre les deux mesures qui l'encadrent."""
        if not self._t:
            return None
        i = bisect.bisect_left(self._t, t)
        if i <= 0:
            return self._angle[0]
        if i >= len(self._t):
            return self._angle[-1]
        t0, t1 = self._t[i - 1], self._t[i]
        if t1 - t0 > 1.0:  # trou dans les mesures : la plus proche
            return self._angle[i - 1] if t - t0 < t1 - t else self._angle[i]
        k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        return (self._deroule[i - 1] + k * (self._deroule[i] - self._deroule[i - 1])) % 360.0

    def vitesse_rotation(self, t: float) -> float:
        """Vitesse de rotation de la caméra autour de la verticale (degrés par seconde) autour de l'instant t."""
        if len(self._t) < 2:
            return 0.0
        a = bisect.bisect_left(self._t, t - FENETRE_VITESSE_S / 2)
        b = bisect.bisect_right(self._t, t + FENETRE_VITESSE_S / 2) - 1
        a, b = max(0, min(a, len(self._t) - 2)), min(len(self._t) - 1, max(b, 1))
        if b <= a or self._t[b] - self._t[a] <= 0:
            return 0.0
        return abs(self._deroule[b] - self._deroule[a]) / (self._t[b] - self._t[a])

    def _pendant_un_tour(self, t: float) -> bool:
        return any(a - 0.2 <= t <= b + 0.2 for a, b in self.tours)

    def positions(self) -> list[tuple[float, float, float]]:
        """(t, x, y) en mètres : le départ, puis la position après chaque pas compté (ou celle suivie par le téléphone)."""
        if self._vo:
            return self._vo
        if self._positions is None:
            x = y = 0.0
            points = [(self._t[0] if self._t else 0.0, 0.0, 0.0)]
            for p in self.pas:
                if not p.compte or p.direction is None:
                    continue
                x += self.longueur_pas * math.sin(math.radians(p.direction))
                y += self.longueur_pas * math.cos(math.radians(p.direction))
                points.append((p.t, x, y))
            self._positions = points
        return self._positions

    def position(self, t: float) -> tuple[float, float]:
        """Où était le téléphone à l'instant t (la position après le dernier pas compté avant t)."""
        points = self.positions()
        i = bisect.bisect_right([p[0] for p in points], t) - 1
        _, x, y = points[max(0, i)]
        return x, y

    def distance(self, t1: float, t2: float) -> float:
        """Distance marchée entre deux instants (pas comptés seulement : une rotation sur place ne compte pas)."""
        if self._vo:
            points = [(x, y) for t, x, y in self._vo if t1 < t <= t2]
            return sum(math.dist(a, b) for a, b in zip(points, points[1:])) + (
                math.dist(self.position(t1), points[0]) if points else 0.0)
        return self.longueur_pas * sum(1 for p in self.pas if p.compte and t1 < p.t <= t2)

    def marches(self) -> list[Marche]:
        """Les suites de pas comptés (arrêts de plus de 1,5 s entre deux suites)."""
        comptes = [p for p in self.pas if p.compte and p.direction is not None]
        resultat: list[Marche] = []
        for p in comptes:
            if resultat and p.t - resultat[-1].t_fin <= PAUSE_MARCHE_S:
                resultat[-1].t_fin = p.t
                resultat[-1].distance += self.longueur_pas
            else:
                resultat.append(Marche(p.t, p.t, self.longueur_pas))
        return resultat

    def avec_pas(self) -> bool:
        """Le téléphone envoie-t-il des pas (accéléromètre autorisé), ou sa position ?"""
        return bool(self.pas) or bool(self._vo)


def tourner(x: float, y: float, angle: float) -> tuple[float, float]:
    """Le point (x, y) d'un repère dont les directions sont décalées de `angle` degrés (ex. lacet → cap : la correction
    cap − lacet) : une direction d devient d + angle."""
    a = math.radians(angle)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)
