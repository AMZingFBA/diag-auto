"""Vidéos de téléphone tournées (iPhone en portrait : matrice d'affichage de −90°) : redressées comme à l'affichage.

Trouvé le 23/10 sur les vraies visites : le serveur lisait ces vidéos à l'envers (ressemblance 0,09 avec les images du
direct, 1,00 une fois corrigé), et le cap suivi sur la vidéo tournait à rebours du gyroscope."""

import io
import shutil
import subprocess

import av
import cv2
import numpy as np
import pytest
from PIL import Image

from assistant.rejouer import decoder_images
from assistant.vision import lire_video, redresser

ROUGE = (0, 0, 255)


def coin_rouge(image: np.ndarray) -> str:
    h, w = image.shape[:2]
    coins = {"haut-gauche": image[2, 2], "haut-droite": image[2, w - 3], "bas-gauche": image[h - 3, 2], "bas-droite": image[h - 3, w - 3]}
    return next(nom for nom, bgr in coins.items() if bgr[2] > 150 and bgr[0] < 100)


def cadre() -> np.ndarray:
    image = np.full((32, 64, 3), 40, np.uint8)  # enregistré couché, comme le capteur de l'iPhone
    image[0:10, 0:12] = ROUGE
    return image


@pytest.mark.parametrize("rotation, attendu", [(0, "haut-gauche"), (-90, "haut-droite"), (90, "bas-gauche"), (180, "bas-droite")])
def test_redresser_comme_ffmpeg(rotation, attendu):
    assert coin_rouge(redresser(cadre(), rotation)) == attendu


FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg absent")
def test_video_d_iphone_en_portrait_lue_a_l_endroit(tmp_path):
    cv2.imwrite(str(tmp_path / "cadre.png"), cadre())
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", str(tmp_path / "cadre.png"), "-t", "0.5", "-r", "10",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-qp", "0", str(tmp_path / "plat.mp4")], check=True)
    # Même matrice d'affichage qu'un iPhone tenu en portrait (−90°), sans réencoder.
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-display_rotation", "-90", "-i", str(tmp_path / "plat.mp4"), "-c", "copy",
                    str(tmp_path / "video.mp4")], check=True)
    with av.open(str(tmp_path / "video.mp4")) as conteneur:
        assert next(conteneur.decode(video=0)).rotation == -90
    # Référence : l'image que montre ffmpeg lui-même (comme un lecteur vidéo, ou le navigateur pendant la visite).
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(tmp_path / "video.mp4"), "-frames:v", "1", str(tmp_path / "vu.png")], check=True)
    assert coin_rouge(cv2.imread(str(tmp_path / "vu.png"))) == "haut-droite"

    vues, _ = lire_video(tmp_path / "video.mp4")
    vignette = cv2.imdecode(np.frombuffer(vues[0].vignette, np.uint8), cv2.IMREAD_COLOR)
    assert vignette.shape[0] > vignette.shape[1] and coin_rouge(vignette) == "haut-droite"  # debout, comme à l'écran

    t, jpeg = decoder_images(tmp_path / "video.mp4")[0]
    image = cv2.cvtColor(np.array(Image.open(io.BytesIO(jpeg)).convert("RGB")), cv2.COLOR_RGB2BGR)
    assert image.shape[0] > image.shape[1] and coin_rouge(image) == "haut-droite"
