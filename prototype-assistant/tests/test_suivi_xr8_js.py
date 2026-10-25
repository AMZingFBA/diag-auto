"""Calculs du suivi par le moteur de 8th Wall (web/suivi-xr8.js), exécutés avec Node : le point du sol sous la croix, un
coin redessiné à l'écran par la projection du moteur, le passage du repère du moteur à celui de l'application (aligné sur
le gyroscope). Le moteur lui-même ne s'essaie que sur le téléphone."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node n'est pas installé")

# Projection d'un écran 390 × 844 (focale de 2,4 en hauteur : champ vertical ~45°), proche 0,1 m, loin 100 m.
F, ASPECT, N, L = 2.4, 390 / 844, 0.1, 100.0
K = [F / ASPECT, 0, 0, 0, 0, F, 0, 0, 0, 0, (L + N) / (N - L), -1, 0, 0, 2 * L * N / (N - L), 0]


def node(script: str):
    code = f"const X = require({json.dumps(str(WEB / 'suivi-xr8.js'))});\nconst K = {json.dumps(K)};\n{script}"
    return json.loads(subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=30, check=True).stdout)


def pose(cap: float, elevation: float, x=0.0, y=1.4, z=0.0) -> str:
    """Pose du moteur : caméra au point (x, y, z), tournée vers le cap (0 = -z, 90 = +x), levée de `elevation` degrés."""
    lacet, tangage = math.radians(-cap) / 2, math.radians(elevation) / 2
    qy = (0.0, math.sin(lacet), 0.0, math.cos(lacet))  # autour de la verticale
    qx = (math.sin(tangage), 0.0, 0.0, math.cos(tangage))  # puis de l'axe horizontal de la caméra
    q = {"x": qy[3] * qx[0], "y": qy[1] * qx[3], "z": -qy[1] * qx[0], "w": qy[3] * qx[3]}
    return json.dumps({"position": {"x": x, "y": y, "z": z}, "rotation": q})


def test_le_point_vise_au_sol_et_sous_la_croix():
    vise, ecran, avant = node(f"""const p = {pose(0, -35)};
        const v = X.viseAuSol(p, 0);
        console.log(JSON.stringify([v, X.projeter(p, K, v, 390, 844), X.avant(p)]));""")
    assert abs(avant[1] + math.sin(math.radians(35))) < 1e-9
    assert abs(vise[2] + 1.4 / math.tan(math.radians(35))) < 1e-9 and abs(vise[0]) < 1e-9 and vise[1] == 0
    assert abs(ecran[0] - 195) < 1e-6 and abs(ecran[1] - 422) < 1e-6


def test_tourner_vers_la_droite_le_coin_passe_a_gauche():
    a, b = node(f"""const v = X.viseAuSol({pose(0, -35)}, 0);
        console.log(JSON.stringify([X.projeter({pose(20, -35)}, K, v, 390, 844), X.cap(X.avant({pose(20, -35)}))]));""")
    assert a[0] < 195 - 40 and abs(b - 20) < 1e-6


def test_repere_de_l_application_aligne_sur_le_gyroscope():
    # Décalage de 30° : le cap 0 du moteur est la direction 30° du lacet. Un point 2 m devant le moteur (-z) est donc à 2 m
    # dans la direction 30° de l'application ; et retour.
    app, retour = node("""const a = X.versApp([0, 0, -2], 30);
        console.log(JSON.stringify([a, X.versMoteur(a, 30, 0)]));""")
    assert math.dist(app, (2 * math.sin(math.radians(30)), 2 * math.cos(math.radians(30)))) < 1e-9
    assert math.dist(retour, (0, 0, -2)) < 1e-9


def test_le_suivi_apprend_le_decalage_et_redessine_le_coin():
    resultat = node(f"""global.XR8 = {{XrController: {{hitTest: () => [{{position: {{x: 0, y: 0.02, z: -2}}}}]}}}};
        const S = new X.Suivi();
        const reality = Object.assign({pose(0, -35)}, {{intrinsics: K, trackingStatus: 'NORMAL'}});
        for (let k = 0; k < 5; k++) {{ S.derniereVisee = 0; S.noter(reality, 30); }}
        const v = S.vise();
        console.log(JSON.stringify([S.decalage(), S.sol(), v, S.ecran(v, 390, 844), S.position()]));""")
    decalage, sol, vise, ecran, position = resultat
    assert abs(decalage - 30) < 1e-6 and abs(sol - 0.02) < 1e-9
    d = 1.38 / math.tan(math.radians(35))
    assert math.dist(vise, (d * math.sin(math.radians(30)), d * math.cos(math.radians(30)))) < 1e-6
    assert abs(ecran[0] - 195) < 1e-6 and abs(ecran[1] - 422) < 1e-6 and math.dist(position, (0, 0)) < 1e-9


def test_un_mur_coupe_derriere_la_camera():
    devant, coupe, derriere = node(f"""const p = {pose(0, -35)};
        console.log(JSON.stringify([X.segment(p, K, [-1, 0, -2], [1, 0, -2], 390, 844), X.segment(p, K, [0, 0, -2], [0, 0, 3], 390, 844),
                                    X.segment(p, K, [-1, 0, 2], [1, 0, 2], 390, 844)]));""")
    assert devant[0][0] < 195 < devant[1][0]
    assert coupe is not None and all(math.isfinite(c) for q in coupe for c in q)
    assert derriere is None
