"""Géométrie du tracé guidé sur la caméra (web/trace.js), exécutée avec Node : le point du sol sous la croix, et les coins
validés redessinés à leur place dans l'image quand le téléphone tourne ou avance."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from synthese import angles

WEB = Path(__file__).resolve().parents[1] / "web"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node n'est pas installé")


def node(script: str):
    code = (f"const T = require({json.dumps(str(WEB / 'trace.js'))});\n"
            f"const B = require({json.dumps(str(WEB / 'boussole.js'))});\n{script}")
    return json.loads(subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=30, check=True).stdout)


def test_point_vise_au_sol_et_retour_sous_la_croix():
    # Téléphone à 1,40 m, caméra vers la direction 30°, 35° sous l'horizon : le coin visé est à 1,40 / tan(35°) = 2,0 m.
    a, b, g = angles(30.0, -35.0)
    P, uv = node(f"""const R = B.matrice({a}, {b}, {g});
        const P = T.auSol([1, 2], 1.4, T.rayon(R));
        console.log(JSON.stringify([P, T.projeter(R, [1, 2], 1.4, P)]));""")
    d = 1.4 / math.tan(math.radians(35))
    assert math.dist(P, (1 + d * math.sin(math.radians(30)), 2 + d * math.cos(math.radians(30)))) < 1e-9
    assert math.hypot(*uv) < 1e-9  # il est sous la croix


def test_le_coin_reste_a_sa_place_quand_on_tourne_ou_avance():
    # Le coin vu sous la croix ; le téléphone tourne de 10° vers la droite : le coin passe à gauche de la croix ; puis on
    # avance de 1 m vers lui (sans tourner) : il est de nouveau droit devant, plus bas dans l'image.
    a, b, g = angles(0.0, -30.0)
    a2, b2, g2 = angles(10.0, -30.0)
    u_tourne, uv_avance = node(f"""const R = B.matrice({a}, {b}, {g});
        const P = T.auSol([0, 0], 1.4, T.rayon(R));
        const tourne = T.projeter(B.matrice({a2}, {b2}, {g2}), [0, 0], 1.4, P);
        console.log(JSON.stringify([tourne[0], T.projeter(R, [0, 1], 1.4, P)]));""")
    d, h, t, p = 1.4 / math.tan(math.radians(30)), 1.4, math.radians(10), math.radians(30)
    attendu = -d * math.sin(t) / (d * math.cos(t) * math.cos(p) + h * math.sin(p))  # caméra penchée de 30° : pas tan(10°)
    assert abs(u_tourne - attendu) < 1e-9
    assert abs(uv_avance[0]) < 1e-9 and uv_avance[1] < 0  # droit devant, sous le centre de l'image


def test_un_mur_coupe_derriere_la_camera():
    a, b, g = angles(0.0, -30.0)
    devant, coupe, derriere = node(f"""const R = B.matrice({a}, {b}, {g});
        console.log(JSON.stringify([T.segment(R, [0, 0], 1.4, [-1, 2], [1, 2]), T.segment(R, [0, 0], 1.4, [0, 2], [0, -3]),
                                    T.segment(R, [0, 0], 1.4, [-1, -2], [1, -2])]));""")
    assert devant is not None and devant[0][0] < 0 < devant[1][0]
    assert coupe is not None and all(math.isfinite(c) for p in coupe for c in p)  # la partie devant la caméra seulement
    assert derriere is None


def test_ecran_et_image_la_croix_au_centre():
    # Vidéo 1080 × 1920 (portrait), champ de 45°, écran 390 × 844 : l'image couvre l'écran (rognée sur les côtés).
    f, centre, retour = node("""const f = T.focaleEcran(45, 1080, 1920, 390, 844);
        console.log(JSON.stringify([f, T.versEcran([0, 0], f, 390, 844), T.depuisEcran(T.versEcran([0.1, -0.2], f, 390, 844), f, 390, 844)]));""")
    assert abs(f - 540 / math.tan(math.radians(22.5)) * 844 / 1920) < 1e-6
    assert centre == [195, 422]
    assert abs(retour[0] - 0.1) < 1e-12 and abs(retour[1] + 0.2) < 1e-12
