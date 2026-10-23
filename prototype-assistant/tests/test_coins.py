"""Relevé des murs (assistant/coins.py) : la croix arrêtée sur chaque coin, la forme exacte de la pièce."""

import math
import random

from assistant.coins import DetecteurCoins, Visee, coin_vise, distance, ferme, forme

HAUTEUR = 1.40
PLAFOND = 2.50


def cibles(sommets, vue, rotation=17.0, plafond=(), hauteur=HAUTEUR):
    """Direction (lacet) et élévation de la caméra pour viser chaque coin depuis `vue`, dans l'ordre des directions."""
    resultat = []
    for i, (x, y) in enumerate(sommets):
        dx, dy = x - vue[0], y - vue[1]
        d = math.hypot(dx, dy)
        elevation = math.degrees(math.atan2(PLAFOND - hauteur, d)) if i in plafond else -math.degrees(math.atan2(hauteur, d))
        resultat.append(((math.degrees(math.atan2(dx, dy)) + rotation) % 360.0, elevation))
    return sorted(resultat)


def flux(visees, t0=2.0, tenue_s=1.1, vitesse=60.0, tremblement=0.4, graine=0, fermer=True):
    """Mesures du téléphone (15 par seconde) : la croix va d'un coin à l'autre (60°/s) et s'arrête sur chacun."""
    rnd = random.Random(graine)
    if fermer:
        visees = visees + visees[:1]
    mesures, t = [], t0
    direction, elevation = (visees[0][0] - 50.0) % 360.0, -15.0
    for cible_d, cible_e in visees:
        ecart_d = (cible_d - direction + 180.0) % 360.0 - 180.0
        n = max(4, int(max(abs(ecart_d), abs(cible_e - elevation)) / vitesse * 15))
        for k in range(1, n + 1):
            t += 1 / 15
            mesures.append({"t": round(t, 3), "lacet": round((direction + ecart_d * k / n) % 360.0, 2),
                            "elevation": round(elevation + (cible_e - elevation) * k / n, 2)})
        for _ in range(int(tenue_s * 15)):
            t += 1 / 15
            mesures.append({"t": round(t, 3), "lacet": round((cible_d + rnd.gauss(0, tremblement)) % 360.0, 2),
                            "elevation": round(cible_e + rnd.gauss(0, tremblement), 2)})
        direction, elevation = cible_d, cible_e
    return mesures


def visees_de(mesures):
    detecteur = DetecteurCoins()
    return [v for v in map(detecteur.ajouter, mesures) if v is not None]


RECTANGLE = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
EN_L = [(0.0, 0.0), (5.0, 0.0), (5.0, 2.5), (2.0, 2.5), (2.0, 4.0), (0.0, 4.0)]


def longueurs(f):
    return sorted(round(m.longueur, 2) for m in f.murs)


def test_un_arret_par_coin_et_retour_au_premier():
    attendues = cibles(RECTANGLE, (1.2, 1.0))
    visees = visees_de(flux(attendues))
    assert len(visees) == 5  # 4 coins, puis le premier de nouveau (il ferme la pièce)
    for v, (d, e) in zip(visees, attendues + attendues[:1]):
        assert abs((v.direction - d + 180) % 360 - 180) < 1.0 and abs(v.elevation - e) < 1.0 and not v.plafond


def test_ni_balayage_lent_ni_horizon_ni_pieds_ni_un_long_arret():
    lent = [{"t": 2 + k / 15, "lacet": 100 + 3.0 * k / 15, "elevation": -25.0} for k in range(60)]  # 3°/s pendant 4 s
    horizon = [{"t": 10 + k / 15, "lacet": 40.0, "elevation": -3.0} for k in range(30)]  # caméra droite devant
    pieds = [{"t": 14 + k / 15, "lacet": 40.0, "elevation": -82.0} for k in range(30)]  # on regarde ses pieds
    assert visees_de(lent + horizon + pieds) == []
    long = [{"t": 2 + k / 15, "lacet": 200.0, "elevation": -30.0} for k in range(60)]  # 4 s sur le même coin
    assert len(visees_de(long)) == 1


def test_coin_vise_au_plafond():
    v = Visee(1.0, 0.0, math.degrees(math.atan2(PLAFOND - HAUTEUR, 3.0)), True)
    assert abs(distance(v) - 3.0) < 1e-6
    assert abs(coin_vise(v, (1.0, 2.0)).y - 5.0) < 1e-6


def test_forme_d_une_piece_rectangulaire():
    coins = [coin_vise(v, (0.0, 0.0)) for v in visees_de(flux(cibles(RECTANGLE, (1.2, 1.0)), fermer=False))]
    f = forme(coins)
    assert f is not None and f.echelle == "sol"
    assert all(abs(a - b) / b < 0.05 for a, b in zip(longueurs(f), [3.0, 3.0, 4.0, 4.0]))


def test_forme_en_l_et_coin_cache_vise_au_plafond():
    coins = [coin_vise(v, (0.0, 0.0)) for v in visees_de(flux(cibles(EN_L, (1.0, 1.2), plafond=(2,)), fermer=False))]
    assert sum(c.visee.plafond for c in coins) == 1
    f = forme(coins)
    assert f is not None and len(f.murs) == 6
    assert all(abs(a - b) < 0.2 for a, b in zip(longueurs(f), [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]))


def test_trois_coins_suffisent_et_une_visee_ratee_est_ecartee():
    trois = [coin_vise(v, (0.0, 0.0)) for v in visees_de(flux(cibles(RECTANGLE[:3], (1.2, 1.0)), fermer=False))]
    f = forme(trois)  # le 4e coin, caché, est en face de celui qui fait l'angle droit
    assert f is not None and all(abs(a - b) / b < 0.06 for a, b in zip(longueurs(f), [3.0, 3.0, 4.0, 4.0]))
    ratee = cibles([(2.4, 1.6)], (1.2, 1.0))  # la croix arrêtée sur le sol, au milieu de la pièce
    cinq = [coin_vise(v, (0.0, 0.0)) for v in visees_de(flux(sorted(cibles(RECTANGLE, (1.2, 1.0)) + ratee), fermer=False))]
    assert len(cinq) == 5
    f = forme(cinq)
    assert f is not None and len(f.murs) == 4 and all(abs(a - b) / b < 0.06 for a, b in zip(longueurs(f), [3.0, 3.0, 4.0, 4.0]))


def test_revenir_sur_le_premier_coin_ferme_la_piece():
    visees = visees_de(flux(cibles(RECTANGLE, (1.2, 1.0))))
    coins = [coin_vise(v, (0.0, 0.0)) for v in visees[:4]]
    assert not ferme(coins[:3], visees[4])  # trois coins : pas encore
    assert ferme(coins, visees[4]) and not ferme(coins, visees[2])
