"""Briques de vision classiques (OpenCV, Apache-2.0), sans IA ni GPU : lecture de la vidéo, suivi continu du mouvement,
points d'intérêt ORB, recherche d'images qui se ressemblent et vérification géométrique.

Tout tourne sur le processeur du serveur, à partir d'une vidéo de n'importe quel téléphone (pas de LiDAR, pas de
capteur particulier). Utilisé par ``assistant.carte``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

COTE_MAX = 512  # les images sont réduites à 512 pixels au plus (comme celles envoyées pendant la visite)
NOM_IMAGE = re.compile(r"^(\d+(?:\.\d+)?)\.jpg$")


@dataclass
class Vue:
    """Une image de la vidéo : instant, niveaux de gris, et ce qu'on en tire."""

    t: float
    gris: np.ndarray
    netete: float = 0.0
    points: np.ndarray | None = None  # coordonnées des points ORB (n × 2)
    descripteurs: np.ndarray | None = None  # descripteurs ORB (n × 32 octets)
    mots: np.ndarray | None = None  # sac de mots visuels (TF-IDF normalisé)
    fichier: str = ""
    vignette: bytes = b""  # petite image en couleur (JPEG), montrée à Claude quand la géométrie ne suffit pas

    @property
    def exploitable(self) -> bool:
        """Assez nette et assez texturée pour être reconnue (un plafond blanc ou une image floue ne l'est pas)."""
        return self.descripteurs is not None and len(self.descripteurs) >= 60


def reduire(image: np.ndarray, cote_max: int = COTE_MAX) -> np.ndarray:
    h, w = image.shape[:2]
    echelle = cote_max / max(h, w)
    if echelle < 1:
        image = cv2.resize(image, (round(w * echelle), round(h * echelle)), interpolation=cv2.INTER_AREA)
    return image


def image_noire(jpeg: bytes, seuil: float = 3.0) -> bool:
    """Image toute noire : caméra coupée par le téléphone (page en arrière-plan sur iPhone : 4 visites sur 11 du 22-23/10,
    jusqu'à 168 s). Une image illisible n'est pas dite noire."""
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_REDUCED_GRAYSCALE_8)
    return image is not None and float(image.mean()) < seuil


def redresser(couleur: np.ndarray, rotation: float) -> np.ndarray:
    """L'image d'une vidéo de téléphone telle qu'elle s'affiche. ``rotation`` (PyAV, matrice d'affichage) est l'angle dont
    l'affichage tourne l'image dans le sens direct : −90 pour un iPhone en portrait, soit un quart de tour dans le sens des
    aiguilles d'une montre (comme le fait ffmpeg). Avant le 23/10, le sens était inversé : ces vidéos sortaient à l'envers
    et le cap suivi sur la vidéo tournait à rebours du gyroscope."""
    k = round(rotation / 90) % 4
    return np.ascontiguousarray(np.rot90(couleur, k)) if k else couleur


def lire_video(chemin: Path, fps_max: float = 10.0) -> tuple[list[Vue], float]:
    """Toutes les images de la vidéo, jusqu'à ``fps_max`` par seconde (suivi continu, pas une photo toutes les n s).
    Renvoie aussi la cadence d'origine."""
    import av

    vues: list[Vue] = []
    with av.open(str(chemin)) as conteneur:
        flux = conteneur.streams.video[0]
        cadence = float(flux.average_rate or flux.guessed_rate or 30)
        pas = 1.0 / fps_max
        prochain = 0.0
        for image in conteneur.decode(flux):
            if image.time is None:
                continue
            t = float(image.time)
            if t + 1e-6 < prochain:
                continue
            prochain = t + pas * 0.999
            couleur = redresser(image.to_ndarray(format="bgr24"), getattr(image, "rotation", 0) or 0)
            gris = cv2.cvtColor(couleur, cv2.COLOR_BGR2GRAY)
            _, jpeg = cv2.imencode(".jpg", reduire(couleur, 320), [cv2.IMWRITE_JPEG_QUALITY, 70])
            vues.append(Vue(round(t, 3), reduire(gris), vignette=jpeg.tobytes()))
    return vues, cadence


def lire_images(dossier: Path) -> list[Vue]:
    """Les images d'une visite (une par seconde, nommées par leur instant : « 00031.20.jpg »)."""
    vues = []
    for f in sorted(dossier.glob("*.jpg")):
        m = NOM_IMAGE.match(f.name)
        if m:
            gris = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            if gris is not None:
                vues.append(Vue(float(m.group(1)), reduire(gris), fichier=f.name, vignette=f.read_bytes()))
    return sorted(vues, key=lambda v: v.t)


# --- Suivi continu du mouvement ---------------------------------------------------------------------------------


@dataclass
class Mouvement:
    """Mouvement de la caméra entre deux images successives, mesuré sur l'image."""

    t: float
    suivi: bool  # le suivi des points a tenu
    dx: float = 0.0  # glissement horizontal de l'image (pixels) : la caméra tourne
    dy: float = 0.0
    echelle: float = 1.0  # > 1 : la scène grossit, la caméra avance
    points: int = 0
    rotation: np.ndarray | None = None  # rotation 3D de la caméra (repère de la caméra), si le mouvement en est une


_PARAMS_LK = dict(winSize=(21, 21), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))


def rotation_camera(a: np.ndarray, b: np.ndarray, focale: float, taille: tuple[int, int]) -> np.ndarray | None:
    """Rotation de la caméra entre deux images, déduite de l'homographie des points suivis (caméra qui tourne : x_b ~
    K R K⁻¹ x_a). Juste quand la caméra tourne sur elle-même, approchée quand elle avance un peu."""
    h, w = taille
    H, garde = cv2.findHomography(a, b, cv2.RANSAC, 2.0)
    if H is None or garde.sum() < 15:
        return None
    K = np.array([[focale, 0, w / 2], [0, focale, h / 2], [0, 0, 1]])
    M = np.linalg.inv(K) @ H @ K
    u, _, vt = np.linalg.svd(M)
    R = u @ vt
    if np.linalg.det(R) < 0:
        R = -R
    return R


def suivre(precedente: Vue, vue: Vue, focale: float | None = None) -> Mouvement:
    """Suivi des points (Lucas-Kanade) d'une image à la suivante, puis mouvement global (similitude robuste) et, si la
    focale est donnée, rotation 3D de la caméra."""
    coins = cv2.goodFeaturesToTrack(precedente.gris, maxCorners=300, qualityLevel=0.01, minDistance=7)
    if coins is None or len(coins) < 20 or precedente.gris.shape != vue.gris.shape:
        return Mouvement(vue.t, False)
    suivants, statut, _ = cv2.calcOpticalFlowPyrLK(precedente.gris, vue.gris, coins, None, **_PARAMS_LK)
    retour, statut2, _ = cv2.calcOpticalFlowPyrLK(vue.gris, precedente.gris, suivants, None, **_PARAMS_LK)
    bons = (statut.ravel() == 1) & (statut2.ravel() == 1) & (np.linalg.norm((retour - coins).reshape(-1, 2), axis=1) < 1.0)
    if bons.sum() < 20:
        return Mouvement(vue.t, False, points=int(bons.sum()))
    a, b = coins.reshape(-1, 2)[bons], suivants.reshape(-1, 2)[bons]
    m, inliers = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if m is None or inliers.sum() < 15:
        return Mouvement(vue.t, False, points=int(bons.sum()))
    echelle = math.hypot(m[0, 0], m[1, 0])
    rotation = rotation_camera(a, b, focale, vue.gris.shape) if focale else None
    return Mouvement(vue.t, True, float(m[0, 2]), float(m[1, 2]), float(echelle), int(inliers.sum()), rotation)


# --- Points d'intérêt, mots visuels, vérification ----------------------------------------------------------------

_ORB = None
_CLAHE = None


def decrire(vue: Vue) -> None:
    """Netteté et points ORB (contraste égalisé : murs pâles, rideaux)."""
    global _ORB, _CLAHE
    if _ORB is None:
        _ORB = cv2.ORB_create(nfeatures=1000, fastThreshold=10)
        _CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    vue.netete = float(cv2.Laplacian(vue.gris, cv2.CV_64F).var())
    points, descripteurs = _ORB.detectAndCompute(_CLAHE.apply(vue.gris), None)
    vue.points = np.float32([p.pt for p in points]) if points else np.zeros((0, 2), np.float32)
    vue.descripteurs = descripteurs


@dataclass
class Vocabulaire:
    """Sac de mots visuels appris sur la visite elle-même (k-moyennes sur les descripteurs ORB) : il sert à trouver vite
    les images qui se ressemblent, avant la vérification géométrique."""

    centres: np.ndarray  # k × 256 (bits)
    idf: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @classmethod
    def apprendre(cls, vues: list[Vue], k: int = 200, graine: int = 0) -> Vocabulaire:
        rng = np.random.default_rng(graine)
        tous = np.vstack([v.descripteurs for v in vues if v.exploitable])
        if len(tous) > 30000:
            tous = tous[rng.choice(len(tous), 30000, replace=False)]
        bits = np.unpackbits(tous, axis=1).astype(np.float32)
        k = min(k, max(2, len(bits) // 20))
        cv2.setRNGSeed(graine)
        _, _, centres = cv2.kmeans(bits, k, None, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5), 2,
                                   cv2.KMEANS_PP_CENTERS)
        voc = cls(centres)
        presence = np.zeros(k)
        for v in vues:
            if v.exploitable:
                presence[np.unique(voc._mots_bruts(v.descripteurs))] += 1
        voc.idf = np.log((1 + sum(v.exploitable for v in vues)) / (1 + presence))
        return voc

    def _mots_bruts(self, descripteurs: np.ndarray) -> np.ndarray:
        bits = np.unpackbits(descripteurs, axis=1).astype(np.float32)
        distances = (bits ** 2).sum(1)[:, None] - 2 * bits @ self.centres.T + (self.centres ** 2).sum(1)[None, :]
        return distances.argmin(1)

    def histogramme(self, vue: Vue) -> np.ndarray:
        h = np.bincount(self._mots_bruts(vue.descripteurs), minlength=len(self.centres)).astype(np.float64) * self.idf
        n = np.linalg.norm(h)
        return h / n if n else h


_APPARIEUR = cv2.BFMatcher(cv2.NORM_HAMMING)


@dataclass
class Lien:
    """Deux images qui montrent la même chose, vérifié par la géométrie (et non par une simple ressemblance)."""

    i: int
    j: int
    points: int  # points communs cohérents avec un même déplacement de caméra
    rotation_pure: bool  # une homographie explique presque tout : la caméra a tourné sur place (ou un même mur plan)
    dx: float = 0.0  # glissement horizontal médian des points communs, de i vers j (pixels)
    lacet: float | None = None  # rotation de la caméra de i vers j autour de la verticale (degrés), si la focale est connue


def lacet_relatif(R: np.ndarray) -> float:
    """Rotation autour de la verticale (degrés, vers la droite positif) d'une rotation de caméra."""
    axe = R.T @ np.array([0.0, 0.0, 1.0])
    return math.degrees(math.atan2(axe[0], axe[2]))


def verifier(a: Vue, b: Vue, i: int, j: int, minimum: int = 20, focale: float | None = None) -> Lien | None:
    """Appariement ORB (test du rapport de Lowe) puis matrice fondamentale robuste (RANSAC)."""
    if not (a.exploitable and b.exploitable):
        return None
    paires = _APPARIEUR.knnMatch(a.descripteurs, b.descripteurs, k=2)
    bons = [m for m, n in (p for p in paires if len(p) == 2) if m.distance < 0.8 * n.distance]
    if len(bons) < minimum:
        return None
    pa = a.points[[m.queryIdx for m in bons]]
    pb = b.points[[m.trainIdx for m in bons]]
    _, masque = cv2.findFundamentalMat(pa, pb, cv2.FM_RANSAC, 2.0, 0.99)
    if masque is None:
        return None
    n = int(masque.sum())
    if n < minimum or n < 0.3 * len(bons):
        return None
    _, masque_h = cv2.findHomography(pa, pb, cv2.RANSAC, 3.0)
    rotation = masque_h is not None and masque_h.sum() >= 0.85 * n
    garde = masque.ravel() == 1
    R = rotation_camera(pa[garde], pb[garde], focale, b.gris.shape) if focale else None
    return Lien(i, j, n, bool(rotation), float(np.median(pb[garde, 0] - pa[garde, 0])),
                None if R is None else lacet_relatif(R))
