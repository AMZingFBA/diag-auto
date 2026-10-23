"""Calcul du cap de la caméra arrière sur le téléphone (web/boussole.js), exécuté avec Node (étape 7).

Hermes : sur iPhone, webkitCompassHeading suit le haut de l'appareil, pas la caméra ; le cap de la caméra doit
venir de la matrice de rotation complète (alpha, beta, gamma), juste quand le téléphone est tenu droit.
Référence indépendante : la même rotation calculée ici en Python (R = Rz(alpha)·Rx(beta)·Ry(gamma), spécification W3C).
"""

import json
import math
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from assistant.boussole import REGLAGES, lire_reglages

BOUSSOLE_JS = Path(__file__).resolve().parents[1] / "web" / "boussole.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node n'est pas installé")


def node(script: str):
    """Exécute un script Node qui a accès à `B` (web/boussole.js) et affiche un JSON."""
    code = f"const B = require({json.dumps(str(BOUSSOLE_JS))});\n{script}"
    sortie = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(sortie.stdout)


def rotation(alpha, beta, gamma):
    a, b, g = (math.radians(x) for x in (alpha, beta, gamma))
    rz = [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]
    rx = [[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]]
    ry = [[math.cos(g), 0, math.sin(g)], [0, 1, 0], [-math.sin(g), 0, math.cos(g)]]

    def produit(m, n):
        return [[sum(m[i][k] * n[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

    return produit(produit(rz, rx), ry)


def cap_de(r, v):
    est, nord = (sum(r[i][k] * v[k] for k in range(3)) for i in range(2))
    return None if math.hypot(est, nord) < 0.05 else math.degrees(math.atan2(est, nord)) % 360


def ecart(a, b):
    return abs((a - b + 180) % 360 - 180)


@pytest.mark.parametrize("alpha, beta, gamma, attendu", [
    (0, 90, 0, 0),  # tenu droit, caméra vers le nord
    (270, 90, 0, 90),  # vers l'est (alpha tourne dans le sens inverse des aiguilles d'une montre)
    (180, 90, 0, 180),  # vers le sud
    (90, 90, 0, 270),  # vers l'ouest
    (0, 60, 0, 0),  # incliné vers le sol : toujours vers le nord
    (0, 120, 0, 0),  # incliné vers le plafond
    (270, 80, 0, 90),  # un peu penché vers l'avant
])
def test_cap_camera_telephone_tenu_droit(alpha, beta, gamma, attendu):
    assert round(node(f"console.log(JSON.stringify(B.capCamera({alpha}, {beta}, {gamma})))")) % 360 == attendu


def test_telephone_a_plat_pas_de_cap_de_camera():
    assert node("console.log(JSON.stringify(B.capCamera(30, 0, 0)))") is None  # la caméra vise le sol


def test_cap_camera_egal_a_la_reference_pour_toute_orientation():
    hasard = random.Random(7)
    poses = [(hasard.uniform(0, 360), hasard.uniform(-180, 180), hasard.uniform(-90, 90)) for _ in range(200)]
    resultats = node(f"console.log(JSON.stringify({json.dumps(poses)}.map(([a, b, g]) => B.capCamera(a, b, g))))")
    for (a, b, g), cap in zip(poses, resultats):
        attendu = cap_de(rotation(a, b, g), (0, 0, -1))
        assert (cap is None) == (attendu is None) and (cap is None or ecart(cap, attendu) < 1e-6), (a, b, g, cap, attendu)


def test_iphone_nord_recale_sur_le_haut_du_telephone_puis_camera_tenue_droite():
    """L'alpha de l'iPhone a une origine quelconque (ici 37° de décalage). Le téléphone est d'abord tenu incliné (le haut
    vise l'horizon : webkitCompassHeading a un sens), puis droit pour filmer les murs."""
    origine = 37.0
    iphone = []
    for alpha_vrai, beta in [(20, 30), (25, 35), (0, 90), (270, 90), (180, 90), (90, 88)]:
        r = rotation(alpha_vrai, beta, 0)
        cap_du_haut = cap_de(r, (0, 1, 0)) if beta < 60 else 123.0  # tenu droit : webkitCompassHeading n'a plus de sens
        iphone.append((alpha_vrai - origine, beta, cap_du_haut, cap_de(r, (0, 0, -1))))
    script = f"""const iphone = new B.CapIphone({REGLAGES['iphone']['inclinaison_calibrage']});
    console.log(JSON.stringify({json.dumps(iphone)}.map(([a, b, haut]) => iphone.mesurer(a, b, 0, haut))));"""
    resultats = node(script)
    for (_, beta, _, attendu), cap in zip(iphone, resultats):
        assert cap is not None and ecart(cap, attendu) < 0.5, (beta, cap, attendu)
    # Avant tout recalage (téléphone toujours tenu droit) : pas de cap, plutôt qu'un cap faux.
    assert node("console.log(JSON.stringify(new B.CapIphone(60).mesurer(0, 90, 0, 200)))") is None


def test_seuils_dans_le_fichier_de_reglages(tmp_path):
    assert REGLAGES["precision"] == {"bonne": 15.0, "faible": 30.0} and REGLAGES["correction"]["dementi"] == 45.0
    fichier = tmp_path / "boussole.toml"
    fichier.write_text("[precision]\nbonne = 10.0\n", encoding="utf-8")
    reglages = lire_reglages(fichier)
    assert reglages["precision"] == {"bonne": 10.0, "faible": 30.0}  # le reste garde sa valeur par défaut
    assert lire_reglages(tmp_path / "absent.toml")["dispersion"]["faible"] == 25.0



def test_elevation_et_roulis_de_la_camera():
    # Étape 15 (tours de pièce) : l'élévation et le roulis de chaque image, justes en portrait comme en paysage.
    cas = node("console.log(JSON.stringify([[0, 90, 0], [0, 70, 0], [0, 110, 0], [0, 0, -90], [0, 0, 90], [0, 0, 0]]"
               ".map(([a, b, g]) => B.poseCamera(a, b, g))))")
    arrondis = [(round(p["elevation"]), round(p["roulis"])) for p in cas]
    assert arrondis[0] == (0, 0)  # portrait, droit
    assert arrondis[1] == (-20, 0) and arrondis[2] == (20, 0)  # penché vers le sol, vers le plafond
    assert arrondis[3] == (0, 90) and arrondis[4] == (0, -90)  # paysage (dans un sens, dans l'autre) : caméra horizontale
    assert arrondis[5][0] == -90  # à plat sur la table : la caméra vise le sol


def test_elevation_et_roulis_egaux_a_la_reference():
    hasard = random.Random(11)
    poses = [(hasard.uniform(0, 360), hasard.uniform(-180, 180), hasard.uniform(-90, 90)) for _ in range(200)]
    resultats = node(f"console.log(JSON.stringify({json.dumps(poses)}.map(([a, b, g]) => B.poseCamera(a, b, g))))")
    for (a, b, g), pose in zip(poses, resultats):
        r = rotation(a, b, g)
        camera_haut = -r[2][2]  # composante verticale de R·(0, 0, -1)
        assert abs(pose["elevation"] - math.degrees(math.asin(max(-1, min(1, camera_haut))))) < 1e-6
        assert ecart(pose["roulis"], math.degrees(math.atan2(r[2][0], r[2][1]))) < 1e-6
