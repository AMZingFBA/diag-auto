"""Forme d'une pièce à partir des coins vus pendant un tour (assistant/geometrie.py), sur des pièces dont on connaît la
forme : rectangles et pièces en L, tournés, caméra pas au milieu, directions bruitées, pied des coins (échelle)."""

import math
import random

import pytest

from assistant.geometrie import (Coin, VueCoin, ajuster, direction, distance_au_sol, lettrer, mur_vers, placer_ouvertures,
                                 regrouper)


def tourner(points, angle_deg):
    a = math.radians(angle_deg)
    return [(x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)) for x, y in points]


def coins_vus(sommets, camera=(0.0, 0.0), bruit=0.0, hasard=None, avec_distance=False):
    coins = []
    for x, y in sommets:
        dx, dy = x - camera[0], y - camera[1]
        d = (math.degrees(math.atan2(dx, dy)) + (hasard.gauss(0, bruit) if hasard and bruit else 0.0)) % 360.0
        coins.append(Coin(d, 1.0, 2, math.hypot(dx, dy) if avec_distance else None))
    return sorted(coins, key=lambda c: c.direction)


def proportions(sommets):
    """Longueurs des murs divisées par la plus longue, rangées : comparables à rotation et échelle près."""
    longueurs = [math.dist(sommets[i], sommets[(i + 1) % len(sommets)]) for i in range(len(sommets))]
    plus_long = max(longueurs)
    return sorted(round(l / plus_long, 3) for l in longueurs)


@pytest.mark.parametrize("largeur, profondeur, rotation, camera", [
    (5.0, 3.6, 0.0, (0.0, 0.0)),
    (6.0, 3.2, 23.0, (0.8, -0.4)),  # pièce tournée (aucun mur face au nord), caméra pas au milieu
    (3.0, 3.0, 47.0, (-0.5, 0.3)),
    (9.0, 2.5, 80.0, (2.0, 0.2)),  # couloir long
])
def test_rectangle_retrouve_a_l_echelle_pres(largeur, profondeur, rotation, camera):
    rect = tourner([(-largeur / 2, -profondeur / 2), (largeur / 2, -profondeur / 2), (largeur / 2, profondeur / 2),
                    (-largeur / 2, profondeur / 2)], rotation)
    forme = ajuster(coins_vus(rect, camera))
    assert forme is not None and len(forme.sommets) == 4 and forme.residu < 0.1
    assert proportions(forme.sommets) == pytest.approx(proportions(rect), abs=0.01)
    assert forme.echelle == "relative"
    # Les murs restent d'équerre et leur orientation est retrouvée (à 90° près).
    assert min(abs((forme.orientation - rotation) % 90), 90 - abs((forme.orientation - rotation) % 90)) < 0.5


def test_rectangle_avec_directions_bruitees():
    hasard = random.Random(3)
    rect = tourner([(-2.5, -1.8), (2.5, -1.8), (2.5, 1.8), (-2.5, 1.8)], 12.0)
    erreurs = []
    for _ in range(30):
        forme = ajuster(coins_vus(rect, (0.4, 0.2), bruit=1.0, hasard=hasard))  # 1° d'erreur sur chaque coin
        assert forme is not None
        vrai, trouve = proportions(rect), proportions(forme.sommets)
        erreurs.append(abs(trouve[0] - vrai[0]) / vrai[0])
    assert sorted(erreurs)[len(erreurs) // 2] < 0.05  # rapport largeur/longueur juste à 5 % près (médiane)


def test_piece_en_l():
    # Pièce en L vue depuis un point d'où l'on voit les 6 coins (dont le coin rentrant).
    l_forme = [(0, 0), (6, 0), (6, 2.5), (3, 2.5), (3, 5), (0, 5)]
    camera = (2.0, 1.5)
    forme = ajuster(coins_vus(l_forme, camera))
    assert forme is not None and len(forme.sommets) == 6 and forme.residu < 0.1
    assert proportions(forme.sommets) == pytest.approx(proportions(l_forme), abs=0.01)


def test_echelle_par_le_pied_des_coins():
    rect = [(-2.0, -1.5), (3.0, -1.5), (3.0, 2.0), (-2.0, 2.0)]
    forme = ajuster(coins_vus(rect, avec_distance=True))
    assert forme.echelle == "sol"
    longueurs = sorted(round(m.longueur, 2) for m in forme.murs)
    assert longueurs == pytest.approx([3.5, 3.5, 5.0, 5.0], abs=0.05)


def test_pas_de_forme_sans_assez_de_coins_ou_incoherente():
    assert ajuster([Coin(10, 1, 1), Coin(100, 1, 1), Coin(200, 1, 1)]) is None  # trois coins
    assert ajuster([Coin(10, 1, 1), Coin(60, 1, 1), Coin(100, 1, 1), Coin(200, 1, 1), Coin(300, 1, 1)]) is None  # impair


def test_vues_d_un_meme_coin_reunies_y_compris_au_bout_du_tour():
    vues = [VueCoin(358.0, 1.0), VueCoin(3.0, 0.5), VueCoin(91.0, 1.0), VueCoin(93.0, 1.0), VueCoin(200.0, 1.0)]
    coins = regrouper(vues)
    assert sorted((round(c.direction) % 360, c.vues) for c in coins) == [(0, 2), (92, 2), (200, 1)]


def test_direction_d_un_point_de_l_image():
    assert direction(0.5, 80.0) == pytest.approx(80.0)
    assert direction(1.0, 80.0, champ=42.0) == pytest.approx(101.0)  # bord droit : la moitié du champ à droite
    assert direction(0.0, 10.0, champ=42.0) == pytest.approx(349.0)


def test_distance_par_le_pied_du_mur():
    # Caméra horizontale, pied du mur vu 25° sous l'horizon : 1,40 / tan(25°) = 3,0 m.
    champ_v = 68.0
    y = 0.5 + math.tan(math.radians(25.0)) / (2 * math.tan(math.radians(champ_v / 2)))
    assert distance_au_sol(y, 0.0, champ_v) == pytest.approx(3.0, abs=0.01)
    assert distance_au_sol(0.5, 0.0, champ_v) is None  # sur l'horizon : trop loin pour être mesuré


def test_fenetre_et_porte_sur_leur_mur_et_lettres_depuis_la_porte_d_entree():
    rect = [(-2.5, -1.8), (2.5, -1.8), (2.5, 1.8), (-2.5, 1.8)]  # x vers l'est, y vers le nord
    forme = ajuster(coins_vus(rect))
    # Fenêtre au milieu du mur nord, porte à l'est du mur sud (par où l'on est entré, en marchant vers le nord).
    nord = mur_vers(forme, 0.0)
    sud = mur_vers(forme, 180.0)
    vers = lambda x, y: math.degrees(math.atan2(x, y)) % 360  # noqa: E731
    placer_ouvertures(forme, [("fenetre", vers(-0.6, 1.8), vers(0.6, 1.8)), ("porte", vers(1.4, -1.8), vers(2.2, -1.8)),
                              ("fenetre", vers(-0.5, 1.8), vers(0.7, 1.8))])  # la même fenêtre vue sur une autre image
    assert [o["type"] for o in forme.murs[nord].ouvertures] == ["fenetre"]
    fenetre = forme.murs[nord].ouvertures[0]
    assert fenetre["fin"] - fenetre["debut"] == pytest.approx(1.3 / 5.0, abs=0.02)
    lettrer(forme, direction_entree=0.0)  # on marchait vers le nord en entrant
    assert forme.murs[sud].lettre == "A" and forme.murs[nord].lettre == "C"
    ouest = mur_vers(forme, 270.0)
    assert forme.murs[ouest].lettre == "B"  # à gauche en entrant : sens horaire vu de dessus
