"""Position du téléphone par le sol filmé (web/odometrie.js), exécuté avec Node sur une visite de synthèse
(tests/synthese.py) : tourner sur place ne déplace pas le téléphone ; marcher le déplace d'autant, à quelques centimètres
près ; un sol uni ne se suit pas (et ne trompe pas)."""

import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from synthese import Piece, angles, parcours

WEB = Path(__file__).resolve().parents[1] / "web"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node n'est pas installé")
HAUTEUR = 1.40
CHAMP = 45.0

SCRIPT = """
const fs = require("fs");
const B = require(%(boussole)s);
const O = require(%(odometrie)s);
const brut = fs.readFileSync(%(images)s);
const [n, l, h] = [brut.readUInt32LE(0), brut.readUInt32LE(4), brut.readUInt32LE(8)];
const poses = JSON.parse(fs.readFileSync(%(poses)s, "utf8"));
const odo = new O.Odometrie({ hauteur: %(hauteur)s, champ: %(champ)s });
const sortie = [];
for (let k = 0; k < n; k++) {
  const data = new Uint8Array(brut.buffer, brut.byteOffset + 12 + k * l * h, l * h);
  const r = odo.image({ data, largeur: l, hauteur: h }, B.matrice(...poses[k]));
  sortie.push([r.C[0], r.C[1], r.details, r.perdu]);
}
console.log(JSON.stringify(sortie));
"""


def suivre_en_node(dossier: Path, images: list[np.ndarray], poses: list[tuple[float, float, float]]) -> list:
    h, l = images[0].shape
    fichier = dossier / "images.bin"
    fichier.write_bytes(struct.pack("<III", len(images), l, h) + b"".join(i.tobytes() for i in images))
    (dossier / "poses.json").write_text(json.dumps(poses), encoding="utf-8")
    script = SCRIPT % {"boussole": json.dumps(str(WEB / "boussole.js")), "odometrie": json.dumps(str(WEB / "odometrie.js")),
                       "images": json.dumps(str(fichier)), "poses": json.dumps(str(dossier / "poses.json")),
                       "hauteur": HAUTEUR, "champ": CHAMP}
    sortie = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=300, check=True)
    return json.loads(sortie.stdout)


@pytest.fixture(scope="module")
def visite(tmp_path_factory):
    """Une visite de 10 s à 12 images par seconde : immobile, tour sur place de 70°, 1,5 m de marche, nouveau tour,
    1 m de marche ; la caméra regarde le sol devant (20 à 40° sous l'horizon)."""
    piece = Piece()
    etapes = [(0.0, (1.5, 1.2), 30.0, -35.0), (1.0, (1.5, 1.2), 30.0, -35.0), (2.0, (1.5, 1.2), 100.0, -30.0),
              (3.0, (2.977, 0.940), 100.0, -30.0), (2.0, (2.977, 0.940), 40.0, -40.0), (2.0, (3.620, 1.706), 40.0, -40.0)]
    poses = parcours(etapes, fps=12.0)
    images = [piece.rendre(pos, HAUTEUR, *angles(cap, elev), finesse=1) for _, pos, cap, elev in poses]
    sortie = suivre_en_node(tmp_path_factory.mktemp("odometrie"), images, [angles(cap, elev) for _, _, cap, elev in poses])
    return poses, sortie


def ecart(poses, sortie, k):
    """Écart (m) entre la position calculée à l'image k et la vraie (toutes deux depuis le départ)."""
    (x0, y0), (x, y) = poses[0][1], poses[k][1]
    return math.dist((sortie[k][0], sortie[k][1]), (x - x0, y - y0))


def test_tourner_sur_place_ne_deplace_pas(visite):
    poses, sortie = visite
    fin_du_tour = next(k for k, p in enumerate(poses) if p[0] >= 3.0)
    assert max(ecart(poses, sortie, k) for k in range(fin_du_tour)) < 0.05
    assert all(not perdu for _, _, _, perdu in sortie[1:fin_du_tour])


def test_marcher_deplace_d_autant(visite):
    poses, sortie = visite
    fin_marche = next(k for k, p in enumerate(poses) if p[0] >= 6.0)
    assert ecart(poses, sortie, fin_marche) < 0.10  # 1,5 m de marche
    assert ecart(poses, sortie, len(poses) - 1) < 0.15  # 2,5 m de marche et deux tours


def test_sol_uni_ne_se_suit_pas(tmp_path):
    uni = [np.full((427, 240), 128, dtype=np.uint8) for _ in range(5)]
    sortie = suivre_en_node(tmp_path, uni, [angles(0.0, -35.0)] * 5)
    assert all(details == 0 and perdu for _, _, details, perdu in sortie)
    assert all(abs(x) < 1e-9 and abs(y) < 1e-9 for x, y, _, _ in sortie)


def test_avec_les_defauts_d_un_vrai_telephone(tmp_path):
    # Flou de bouger, bruit de l'image, gyroscope bruité (0,3°) et en retard d'une image sur la caméra : la position reste
    # juste à quelques centimètres près, car l'image corrige aussi l'orientation (sans cette correction : 15 à 19 cm
    # d'écart en tournant sur place).
    piece = Piece()
    etapes = [(0.0, (1.5, 1.2), 30.0, -35.0), (1.0, (1.5, 1.2), 30.0, -35.0), (2.0, (1.5, 1.2), 100.0, -30.0),
              (3.0, (2.977, 0.940), 100.0, -30.0), (2.0, (2.977, 0.940), 40.0, -40.0), (2.0, (3.620, 1.706), 40.0, -40.0)]
    poses = parcours(etapes, fps=12.0)
    rnd = np.random.default_rng(1)
    images = []
    for k, (_, pos, cap, elev) in enumerate(poses):
        a = piece.rendre(pos, HAUTEUR, *angles(cap, elev), finesse=1).astype(float)
        if k:
            _, pos0, cap0, elev0 = poses[k - 1]
            milieu = ((pos[0] + pos0[0]) / 2, (pos[1] + pos0[1]) / 2)
            a = (a + piece.rendre(milieu, HAUTEUR, *angles(cap0 + ((cap - cap0 + 180) % 360 - 180) / 2, (elev + elev0) / 2),
                                  finesse=1)) / 2
        images.append(np.clip(a + rnd.normal(0, 4, a.shape), 0, 255).astype(np.uint8))
    mesures = [angles(poses[max(0, k - 1)][2] + rnd.normal(0, 0.3), poses[max(0, k - 1)][3] + rnd.normal(0, 0.3))
               for k in range(len(poses))]
    sortie = suivre_en_node(tmp_path, images, mesures)
    fin_du_tour = next(k for k, p in enumerate(poses) if p[0] >= 3.0)
    assert max(ecart(poses, sortie, k) for k in range(fin_du_tour)) < 0.05
    assert ecart(poses, sortie, len(poses) - 1) < 0.12
    assert not any(perdu for _, _, _, perdu in sortie[1:])
