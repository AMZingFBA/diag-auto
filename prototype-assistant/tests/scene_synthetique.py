"""Vidéo de synthèse pour tester la carte des pièces : pièces en forme de boîte, murs texturés, caméra tenue à la main.

Chaque pièce est un rectangle (X vers l'est, Y vers le nord, Z vers le haut). Ses quatre murs portent chacun une image
différente (cadres, meubles, fenêtre, porte, texte), générée à partir d'une graine. La caméra (téléphone en portrait)
balaie la pièce, marche jusqu'à la porte, passe dans l'autre pièce et revient. Le rendu est un lancer de rayons simple :
pour chaque pixel, le premier mur, le sol ou le plafond touché.

La vérité est connue à chaque image : pièce, cap de la caméra, mur visé (celui du centre de l'image). Les capteurs du
téléphone (boussole) sont simulés à partir du vrai cap, avec du bruit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

LARGEUR, HAUTEUR = 240, 320  # téléphone en portrait
FOCALE = 260.0  # ~49° de champ horizontal
HAUTEUR_PIECE = 2.5
PIXELS_PAR_METRE = 110
MURS = ("nord", "est", "sud", "ouest")
CAPS_MURS = {"nord": 0.0, "est": 90.0, "sud": 180.0, "ouest": 270.0}


def texture_mur(graine: int, longueur_m: float, porte: bool = False, fenetre: bool = False) -> np.ndarray:
    """Un mur meublé : couleur de fond, cadres, meubles, étiquettes de texte, éventuellement une porte et une fenêtre."""
    rng = np.random.default_rng(graine)
    l, h = int(longueur_m * PIXELS_PAR_METRE), int(HAUTEUR_PIECE * PIXELS_PAR_METRE)
    fond = rng.integers(150, 235, 3)
    img = np.empty((h, l, 3), np.uint8)
    img[:] = fond
    img = cv2.add(img, rng.integers(0, 12, (h, l, 1), dtype=np.uint8).repeat(3, 2))  # grain du mur
    for _ in range(rng.integers(7, 12)):
        lw, lh = int(rng.integers(25, 110)), int(rng.integers(20, 90))
        x, y = int(rng.integers(0, max(1, l - lw))), int(rng.integers(10, max(11, h - lh - 10)))
        couleur = tuple(int(c) for c in rng.integers(0, 255, 3))
        forme = rng.integers(0, 4)
        if forme == 0:  # cadre avec un motif
            cv2.rectangle(img, (x, y), (x + lw, y + lh), couleur, -1)
            cv2.rectangle(img, (x, y), (x + lw, y + lh), (20, 20, 20), 3)
            for _ in range(6):
                cx, cy = int(rng.integers(x, x + lw)), int(rng.integers(y, y + lh))
                cv2.circle(img, (cx, cy), int(rng.integers(3, 12)), tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
        elif forme == 1:  # meuble à tiroirs
            cv2.rectangle(img, (x, y), (x + lw, y + lh), couleur, -1)
            for k in range(1, 4):
                yy = y + k * lh // 4
                cv2.line(img, (x, yy), (x + lw, yy), (30, 30, 30), 2)
                cv2.circle(img, (x + lw // 2, yy - lh // 8), 3, (240, 240, 240), -1)
        elif forme == 2:  # étiquette de texte
            texte = "".join(chr(int(c)) for c in rng.integers(65, 91, int(rng.integers(3, 8))))
            cv2.putText(img, texte, (x, y + 20), cv2.FONT_HERSHEY_SIMPLEX, float(rng.uniform(0.5, 1.1)), couleur, 2)
        else:  # objet rond
            cv2.ellipse(img, (x + lw // 2, y + lh // 2), (lw // 2, lh // 2), 0, 0, 360, couleur, -1)
            cv2.ellipse(img, (x + lw // 2, y + lh // 2), (lw // 4, lh // 4), 0, 0, 360, (25, 25, 25), 2)
    if fenetre:
        x, y, lw, lh = l // 2 - 70, 45, 140, 120
        cv2.rectangle(img, (x, y), (x + lw, y + lh), (250, 245, 235), -1)
        cv2.line(img, (x + lw // 2, y), (x + lw // 2, y + lh), (90, 90, 90), 4)
        cv2.line(img, (x, y + lh // 2), (x + lw, y + lh // 2), (90, 90, 90), 4)
        cv2.rectangle(img, (x, y), (x + lw, y + lh), (60, 60, 60), 5)
    if porte:
        x, lw = l // 2 - 45, 90
        cv2.rectangle(img, (x, h - 225), (x + lw, h), (35, 45, 70), -1)
        cv2.rectangle(img, (x - 6, h - 231), (x + lw + 6, h), (230, 230, 230), 6)
    return cv2.GaussianBlur(img, (3, 3), 0)


def texture_sol(graine: int) -> np.ndarray:
    rng = np.random.default_rng(graine)
    tuile = np.empty((60, 60, 3), np.uint8)
    tuile[:] = rng.integers(140, 200, 3)
    cv2.rectangle(tuile, (0, 0), (59, 59), (90, 90, 90), 2)
    sol = np.tile(tuile, (10, 10, 1))
    return cv2.add(sol, rng.integers(0, 25, sol.shape[:2] + (1,), dtype=np.uint8).repeat(3, 2))


@dataclass
class Piece:
    nom: str
    x0: float
    y0: float
    largeur: float  # selon X (est-ouest)
    profondeur: float  # selon Y (nord-sud)
    graine: int
    porte: str = "est"  # mur qui porte la porte
    fenetre: str = "nord"
    textures: dict = field(default_factory=dict)

    def __post_init__(self):
        for k, mur in enumerate(MURS):
            longueur = self.largeur if mur in ("nord", "sud") else self.profondeur
            self.textures[mur] = texture_mur(self.graine * 10 + k, longueur, porte=mur == self.porte, fenetre=mur == self.fenetre)
        self.textures["sol"] = texture_sol(self.graine)

    @property
    def x1(self) -> float:
        return self.x0 + self.largeur

    @property
    def y1(self) -> float:
        return self.y0 + self.profondeur

    @property
    def centre(self) -> tuple[float, float]:
        return self.x0 + self.largeur / 2, self.y0 + self.profondeur / 2

    def devant_porte(self, recul: float = 0.6) -> tuple[float, float]:
        cx, cy = self.centre
        return {"est": (self.x1 - recul, cy), "ouest": (self.x0 + recul, cy),
                "nord": (cx, self.y1 - recul), "sud": (cx, self.y0 + recul)}[self.porte]


_U, _V = np.meshgrid((np.arange(LARGEUR) - LARGEUR / 2) / FOCALE, (np.arange(HAUTEUR) - HAUTEUR / 2) / FOCALE)


def rendre(piece: Piece, x: float, y: float, cap: float, tangage: float = 0.0, roulis: float = 0.0,
           z: float = 1.5) -> tuple[np.ndarray, str]:
    """Image vue depuis (x, y, z), caméra tournée vers ``cap`` (degrés, 0 = nord). Renvoie l'image (BGR) et le mur au
    centre de l'image (« nord », « est »…, ou « sol »/« plafond »)."""
    psi, theta, phi = math.radians(cap), math.radians(tangage), math.radians(roulis)
    avant = np.array([math.sin(psi) * math.cos(theta), math.cos(psi) * math.cos(theta), math.sin(theta)])
    droite0 = np.array([math.cos(psi), -math.sin(psi), 0.0])
    haut0 = np.cross(droite0, avant)
    droite = math.cos(phi) * droite0 + math.sin(phi) * haut0
    haut = np.cross(droite, avant)
    d = (_U[..., None] * droite - _V[..., None] * haut + avant).reshape(-1, 3)
    with np.errstate(divide="ignore", invalid="ignore"):
        tx = np.where(d[:, 0] > 0, (piece.x1 - x) / d[:, 0], np.where(d[:, 0] < 0, (piece.x0 - x) / d[:, 0], np.inf))
        ty = np.where(d[:, 1] > 0, (piece.y1 - y) / d[:, 1], np.where(d[:, 1] < 0, (piece.y0 - y) / d[:, 1], np.inf))
        tz = np.where(d[:, 2] > 0, (HAUTEUR_PIECE - z) / d[:, 2], np.where(d[:, 2] < 0, -z / d[:, 2], np.inf))
    t = np.minimum(np.minimum(tx, ty), tz)
    p = np.array([x, y, z]) + d * t[:, None]
    image = np.empty((len(d), 3), np.uint8)
    choix = np.argmin(np.stack([tx, ty, tz]), axis=0)
    for code, mur, masque in (
        ("est", "est", (choix == 0) & (d[:, 0] > 0)), ("ouest", "ouest", (choix == 0) & (d[:, 0] <= 0)),
        ("nord", "nord", (choix == 1) & (d[:, 1] > 0)), ("sud", "sud", (choix == 1) & (d[:, 1] <= 0)),
    ):
        tex = piece.textures[mur]
        th, tw = tex.shape[:2]
        if mur == "nord":
            u = (p[masque, 0] - piece.x0) / piece.largeur
        elif mur == "sud":
            u = (piece.x1 - p[masque, 0]) / piece.largeur
        elif mur == "est":
            u = (piece.y1 - p[masque, 1]) / piece.profondeur
        else:
            u = (p[masque, 1] - piece.y0) / piece.profondeur
        v = (HAUTEUR_PIECE - p[masque, 2]) / HAUTEUR_PIECE
        image[masque] = tex[np.clip((v * th).astype(int), 0, th - 1), np.clip((u * tw).astype(int), 0, tw - 1)]
    sol = (choix == 2) & (d[:, 2] < 0)
    tex = piece.textures["sol"]
    image[sol] = tex[(p[sol, 1] * 100).astype(int) % tex.shape[0], (p[sol, 0] * 100).astype(int) % tex.shape[1]]
    image[(choix == 2) & (d[:, 2] >= 0)] = (236, 236, 236)  # plafond blanc, sans texture (comme en vrai)
    image = image.reshape(HAUTEUR, LARGEUR, 3)
    centre = int(np.argmin([tx[len(d) // 2 + LARGEUR // 2], ty[len(d) // 2 + LARGEUR // 2], tz[len(d) // 2 + LARGEUR // 2]]))
    dc = d[len(d) // 2 + LARGEUR // 2]
    vise = (("est" if dc[0] > 0 else "ouest"), ("nord" if dc[1] > 0 else "sud"), ("plafond" if dc[2] > 0 else "sol"))[centre]
    return image, vise


@dataclass
class Instant:
    t: float
    piece: str
    cap: float
    mur: str  # mur au centre de l'image


@dataclass
class Tournage:
    """Une vidéo de synthèse : images, vérité à chaque image, capteurs simulés."""

    images: list[np.ndarray]
    verite: list[Instant]
    fps: float
    capteurs: list[dict]

    def instant_face(self, piece: str, mur: str, apres: float = 0.0) -> float:
        """Premier instant (après ``apres``) où la caméra vise ce mur de face, dans cette pièce."""
        for v in self.verite:
            if v.t >= apres and v.piece == piece and v.mur == mur and abs(((v.cap - CAPS_MURS[mur] + 180) % 360) - 180) < 12:
                return v.t
        raise ValueError(f"{piece} / {mur} jamais visé de face après {apres} s")

    def ecrire(self, chemin) -> None:
        """Écrit la vidéo (mp4) : pour tester la lecture d'un vrai fichier."""
        import av

        with av.open(str(chemin), "w") as sortie:
            flux = sortie.add_stream("libx264", rate=int(self.fps))
            flux.width, flux.height, flux.pix_fmt = LARGEUR, HAUTEUR, "yuv420p"
            for image in self.images:
                for paquet in flux.encode(av.VideoFrame.from_ndarray(image, format="bgr24")):
                    sortie.mux(paquet)
            for paquet in flux.encode():
                sortie.mux(paquet)


def tourner(pieces: dict[str, Piece], parcours: list[tuple], fps: float = 10.0, graine: int = 0,
            bruit_boussole: float = 6.0, nord: float = 0.0) -> Tournage:
    """Filme un parcours. Chaque étape : (« balayer », pièce, cap de début, cap de fin, durée) ou
    (« passer », pièce de départ, pièce d'arrivée, durée). Le balayage se fait au centre de la pièce, avec un léger
    tremblement ; le passage marche jusqu'à la porte puis entre dans l'autre pièce.

    ``nord`` décale la boussole simulée (téléphone mal calibré)."""
    rng = np.random.default_rng(graine)
    images, verite, capteurs = [], [], []
    t = 0.0
    dt = 1.0 / fps

    def filmer(piece: Piece, x, y, cap, tangage=None):
        nonlocal t
        tangage = float(rng.normal(-3, 2)) if tangage is None else tangage
        image, mur = rendre(piece, x + rng.normal(0, 0.02), y + rng.normal(0, 0.02), cap % 360, tangage, float(rng.normal(0, 1.5)))
        bruit = rng.normal(0, 2.5, image.shape)
        images.append(np.clip(image + bruit, 0, 255).astype(np.uint8))
        verite.append(Instant(round(t, 3), piece.nom, cap % 360, mur))
        capteurs.append({"t": round(t, 3), "cap": round((cap + nord + rng.normal(0, bruit_boussole)) % 360, 1)})
        t += dt

    position = {nom: p.centre for nom, p in pieces.items()}
    for etape in parcours:
        if etape[0] == "balayer":
            _, nom, debut, fin, duree = etape
            piece = pieces[nom]
            x, y = position[nom]
            n = max(2, int(duree * fps))
            for k in range(n):
                a = k / (n - 1)
                filmer(piece, x, y, debut + (fin - debut) * (0.5 - 0.5 * math.cos(math.pi * a)))
        elif etape[0] == "passer":
            _, depart, arrivee, duree = etape
            a, b = pieces[depart], pieces[arrivee]
            cap_porte = CAPS_MURS[a.porte]
            (x0, y0), (x1, y1) = position[depart], a.devant_porte(0.25)
            n = max(2, int(duree * fps * 0.6))
            for k in range(n):  # marche vers la porte
                s = k / (n - 1)
                filmer(a, x0 + (x1 - x0) * s, y0 + (y1 - y0) * s, cap_porte + rng.normal(0, 2), tangage=-2.0)
            cap_entree = (CAPS_MURS[b.porte] + 180) % 360
            (x0, y0), (x1, y1) = b.devant_porte(0.3), b.centre
            n = max(2, int(duree * fps * 0.4))
            for k in range(n):  # entrée dans l'autre pièce
                s = k / (n - 1)
                filmer(b, x0 + (x1 - x0) * s, y0 + (y1 - y0) * s, cap_entree + rng.normal(0, 2), tangage=-2.0)
            position[arrivee] = (x1 + rng.normal(0, 0.2), y1 + rng.normal(0, 0.2))
    return Tournage(images, verite, fps, capteurs)


def deux_pieces() -> dict[str, Piece]:
    """Un séjour et une cuisine, porte à porte."""
    return {
        "Séjour": Piece("Séjour", 0.0, 0.0, 4.6, 3.8, graine=1, porte="est", fenetre="nord"),
        "Cuisine": Piece("Cuisine", 4.6, 0.0, 3.0, 3.0, graine=2, porte="ouest", fenetre="sud"),
    }
