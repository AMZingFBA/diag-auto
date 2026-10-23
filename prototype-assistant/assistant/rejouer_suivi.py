"""Rejoue le suivi de position (web/odometrie.js, avec Node) sur une visite enregistrée : les images de la vidéo (debout,
240 pixels de large, 15 par seconde) et l'orientation du téléphone reconstruite à partir des mesures envoyées pendant la
visite (cap de la caméra, élévation et roulis : la matrice exacte du téléphone). Compare au trajet calculé en direct.

    python -m assistant.rejouer_suivi sessions/<visite> [--champ 45] [--options '{"vitesseMax": 1.6}']

Sert à comprendre un essai réel et à régler le suivi (visite de Noah du 23/10, 17:30 : retour à l'entrée calculé à 3,4 m
de son vrai point de départ ; 0,8 à 2 m avec la limite de vitesse)."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np

WEB = Path(__file__).resolve().parents[1] / "web"

SCRIPT = r"""
const fs = require("fs");
const O = require(%(odometrie)s);
const brut = fs.readFileSync(%(images)s);
const [n, l, h] = [brut.readUInt32LE(0), brut.readUInt32LE(4), brut.readUInt32LE(8)];
const R = JSON.parse(fs.readFileSync(%(poses)s, "utf8"));
const T = JSON.parse(fs.readFileSync(%(temps)s, "utf8"));
const odo = new O.Odometrie(Object.assign({ hauteur: %(hauteur)s, champ: %(champ)s }, %(options)s));
const sortie = [];
for (let k = 0; k < n; k++) {
  const r = odo.image({ data: new Uint8Array(brut.buffer, brut.byteOffset + 12 + k * l * h, l * h), largeur: l, hauteur: h }, R[k], T[k]);
  sortie.push([r.C[0], r.C[1], r.details, r.perdu ? 1 : 0]);
}
console.log(JSON.stringify(sortie));
"""


def matrice(psi: float, e: float, r: float) -> np.ndarray:
    """Axes du téléphone (colonnes x, y, z) dans le monde, d'après le cap de la caméra psi, son élévation e et le roulis r
    (degrés) : ceux que calcule web/boussole.js (poseCamera, capCamera) ; la reconstruction est exacte."""
    psi, e, r = map(math.radians, (psi, e, r))
    d = np.array([math.cos(e) * math.sin(psi), math.cos(e) * math.cos(psi), math.sin(e)])
    z = -d
    x0 = np.array([math.cos(psi), -math.sin(psi), 0.0])
    y0 = np.cross(z, x0)
    return np.stack([math.cos(r) * x0 + math.sin(r) * y0, -math.sin(r) * x0 + math.cos(r) * y0, z], axis=1)


def mesures(visite: Path) -> list[dict]:
    return [m for m in (json.loads(l) for l in open(visite / "capteurs-lot.jsonl", encoding="utf-8") if l.strip()) if "t" in m]


def extraire(visite: Path, dossier: Path, par_seconde: float = 15.0) -> list[float]:
    """Les images de la vidéo (debout, niveaux de gris, 240 de large) dans dossier/images.bin ; renvoie leurs instants."""
    import av
    from PIL import Image

    images, temps, prochain = [], [], 0.0
    with av.open(str(visite / "video.mp4")) as conteneur:
        for trame in conteneur.decode(video=0):
            t = float(trame.pts * trame.time_base)
            if t + 1e-6 < prochain:
                continue
            prochain = t + 1 / par_seconde - 0.005
            im = trame.to_image()
            if im.width > im.height:
                im = im.rotate(-90, expand=True)  # enregistrée couchée ; la page la voyait debout
            images.append(np.asarray(im.convert("L").resize((240, round(240 * im.height / im.width)), Image.BILINEAR), dtype=np.uint8))
            temps.append(t)
    h, l = images[0].shape
    with open(dossier / "images.bin", "wb") as f:
        f.write(struct.pack("<III", len(images), l, h))
        for i in images:
            f.write(i.tobytes())
    return temps


def rejouer(visite: Path, champ: float = 45.0, hauteur: float = 1.4, options: dict | None = None, decalage: float = 0.0):
    """Renvoie (instants, [(x, y, détails suivis, perdu)]) pour chaque image rejouée."""
    m = [x for x in mesures(visite) if all(isinstance(x.get(k), (int, float)) for k in ("lacet", "elevation", "roulis"))]
    T = np.array([x["t"] for x in m])
    lacet = np.degrees(np.unwrap(np.radians([x["lacet"] for x in m])))
    elev = np.array([x["elevation"] for x in m])
    roulis = np.degrees(np.unwrap(np.radians([x["roulis"] for x in m])))
    dossier = Path(tempfile.mkdtemp(prefix="rejeu-suivi-"))
    try:
        temps = extraire(visite, dossier)
        poses = [matrice(np.interp(t + decalage, T, lacet), np.interp(t + decalage, T, elev), np.interp(t + decalage, T, roulis)).tolist()
                 for t in temps]
        (dossier / "poses.json").write_text(json.dumps(poses))
        (dossier / "temps.json").write_text(json.dumps(temps))
        script = SCRIPT % {"odometrie": json.dumps(str(WEB / "odometrie.js")), "images": json.dumps(str(dossier / "images.bin")),
                           "poses": json.dumps(str(dossier / "poses.json")), "temps": json.dumps(str(dossier / "temps.json")),
                           "hauteur": hauteur, "champ": champ, "options": json.dumps(options or {})}
        sortie = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=1800, check=True)
        return temps, json.loads(sortie.stdout)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("visite", type=Path)
    parser.add_argument("--champ", type=float, default=45.0)
    parser.add_argument("--hauteur", type=float, default=1.4)
    parser.add_argument("--options", default="{}")
    args = parser.parse_args()
    temps, sortie = rejouer(args.visite, args.champ, args.hauteur, json.loads(args.options))
    direct = {round(m["t"], 1): (m["x"], m["y"]) for m in mesures(args.visite) if "x" in m}
    print(f"{len(sortie)} images ; perdu sur {sum(s[3] for s in sortie)} ; trajet "
          f"{sum(math.dist(a[:2], b[:2]) for a, b in zip(sortie, sortie[1:])):.1f} m")
    for k in range(0, len(sortie), 60):
        d = direct.get(round(temps[k], 1))
        print(f"t={temps[k]:6.1f} s  rejeu ({sortie[k][0]:+6.2f}, {sortie[k][1]:+6.2f})"
              + (f"  en direct ({d[0]:+6.2f}, {d[1]:+6.2f})" if d else "") + f"  détails {sortie[k][2]}")


if __name__ == "__main__":
    main()
