"""Images de synthèse d'une pièce filmée par le téléphone (tests du suivi de position, web/odometrie.js) : un sol carrelé
et marbré, des murs presque unis, un plafond blanc ; la caméra à la hauteur h, orientée par (alpha, beta, gamma) comme le
donne le téléphone (matrice R = Rz(alpha)·Rx(beta)·Ry(gamma), spécification W3C ; la caméra vise -z du téléphone).
Rendu par lancer de rayons, deux fois plus fin puis réduit (moins de crénelage au loin)."""

from __future__ import annotations

import math

import numpy as np


def matrice(alpha: float, beta: float, gamma: float) -> np.ndarray:
    a, b, g = (math.radians(x) for x in (alpha, beta, gamma))
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    ry = np.array([[math.cos(g), 0, math.sin(g)], [0, 1, 0], [-math.sin(g), 0, math.cos(g)]])
    return rz @ rx @ ry


def angles(cap: float, elevation: float) -> tuple[float, float, float]:
    """(alpha, beta, gamma) d'un téléphone tenu droit (en portrait) dont la caméra vise la direction `cap` (0 = axe y,
    90 = axe x), levée de `elevation` degrés (négatif : vers le sol)."""
    return (-cap) % 360.0, 90.0 + elevation, 0.0


class Piece:
    def __init__(self, longueur: float = 6.0, largeur: float = 5.0, plafond: float = 2.5, graine: int = 3) -> None:
        self.longueur, self.largeur, self.plafond = longueur, largeur, plafond
        rnd = np.random.default_rng(graine)
        self.bruits = [rnd.random((256, 256)) for _ in range(3)]

    def _bruit(self, k: int, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Bruit de valeur lissé (interpolation bilinéaire d'une grille aléatoire), entre −1 et 1."""
        g = self.bruits[k]
        x, y = np.mod(x, 255.0), np.mod(y, 255.0)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x - x0, y - y0
        v = (g[y0, x0] * (1 - fx) + g[y0, x0 + 1] * fx) * (1 - fy) + (g[y0 + 1, x0] * (1 - fx) + g[y0 + 1, x0 + 1] * fx) * fy
        return 2.0 * v - 1.0

    def sol(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        v = 120 + 45 * self._bruit(0, x * 3.0, y * 3.0) + 30 * self._bruit(1, x * 11.0, y * 11.0)
        joint = (np.mod(x, 0.6) < 0.012) | (np.mod(y, 0.6) < 0.012)  # carrelage de 60 cm
        return np.where(joint, v - 55, v)

    def mur(self, a: np.ndarray, z: np.ndarray) -> np.ndarray:
        return 205 + 6 * self._bruit(2, a * 2.0, z * 2.0)  # peinture : presque rien à suivre

    def rendre(self, C, h: float, alpha: float, beta: float, gamma: float, largeur: int = 240, hauteur: int = 427,
               champ: float = 45.0, finesse: int = 2) -> np.ndarray:
        W, H = largeur * finesse, hauteur * finesse
        f = (W / 2) / math.tan(math.radians(champ / 2))
        u, v = np.meshgrid((np.arange(W) + 0.5 - W / 2) / f, (H / 2 - np.arange(H) - 0.5) / f)
        rayons = np.stack([u, v, -np.ones_like(u)], axis=-1) @ matrice(alpha, beta, gamma).T
        dx, dy, dz = rayons[..., 0], rayons[..., 1], rayons[..., 2]
        cx, cy = C
        t_min = np.full(u.shape, np.inf)
        valeur = np.full(u.shape, 230.0)  # plafond
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(dz < 0, -h / dz, np.inf)  # sol
            x, y = cx + t * dx, cy + t * dy
            ok = (t > 0) & (x >= 0) & (x <= self.longueur) & (y >= 0) & (y <= self.largeur)
            valeur = np.where(ok & (t < t_min), self.sol(np.where(ok, x, 0.0), np.where(ok, y, 0.0)), valeur)
            t_min = np.where(ok & (t < t_min), t, t_min)
            for plan, axe in ((0.0, "x"), (self.longueur, "x"), (0.0, "y"), (self.largeur, "y")):
                t = (plan - (cx if axe == "x" else cy)) / (dx if axe == "x" else dy)
                z = h + t * dz
                autre = cy + t * dy if axe == "x" else cx + t * dx
                ok = (t > 0) & (z >= 0) & (z <= self.plafond) & (autre >= 0) & (autre <= (self.largeur if axe == "x" else self.longueur))
                valeur = np.where(ok & (t < t_min), self.mur(np.where(ok, autre, 0.0), np.where(ok, z, 0.0)), valeur)
                t_min = np.where(ok & (t < t_min), t, t_min)
        image = valeur.reshape(hauteur, finesse, largeur, finesse).mean(axis=(1, 3))
        return np.clip(image, 0, 255).astype(np.uint8)


def parcours(etapes: list[tuple[float, tuple[float, float], float, float]], fps: float = 15.0):
    """Les poses image par image, en passant d'une étape (durée, position, cap, élévation) à la suivante à vitesse
    constante. Renvoie [(t, (x, y), cap, élévation)]."""
    poses = []
    t = 0.0
    (_, pos, cap, elev) = etapes[0]
    for duree, pos2, cap2, elev2 in etapes[1:]:
        n = max(1, int(round(duree * fps)))
        ecart = (cap2 - cap + 180.0) % 360.0 - 180.0
        for k in range(n):
            a = k / n
            poses.append((t, (pos[0] + a * (pos2[0] - pos[0]), pos[1] + a * (pos2[1] - pos[1])), (cap + a * ecart) % 360.0,
                          elev + a * (elev2 - elev)))
            t += 1.0 / fps
        pos, cap, elev = pos2, cap2, elev2
    poses.append((t, pos, cap, elev))
    return poses
