"""Forme d'une pièce à partir d'un tour sur soi-même (étape 15 : « analyser les angles des murs, la taille proportionnelle
des murs, la forme des pièces »).

Principe, essayé sur des pièces de synthèse (moins de 2 % d'erreur sur les proportions) : Claude repère, dans chaque image
du tour, les arêtes verticales où deux murs se rencontrent (les coins) ; la direction de chaque coin vient du gyroscope
(direction de la caméra) et de sa place dans l'image. Vus du milieu de la pièce, les coins rangés par direction sont les
sommets du contour. Les murs étant d'équerre (pièce « rectiligne » : rectangle, L, T…), le contour est fixé à l'échelle
près par ces seules directions : chaque sommet partage une coordonnée avec ses voisins, et sa direction depuis la caméra
donne une équation linéaire. On cherche l'orientation des murs qui rend ces équations compatibles (moindres carrés).
Le pied des coins, quand il est visible, donne en plus les distances (caméra à ~1,40 m du sol) : l'échelle en mètres,
« estimée » seulement (le Carrez reste au laser).

Repère : x vers la direction 90°, y vers la direction 0° (l'est et le nord quand la direction est un cap ; sinon le
repère du gyroscope). La caméra (le milieu du tour) est à l'origine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

CHAMP_PORTRAIT_DEG = 42.0  # champ horizontal de la caméra principale en portrait (mesuré sur l'iPhone de Noah : 40,5 à 42,5°)
HAUTEUR_CAMERA_M = 1.40  # téléphone tenu devant la poitrine (hypothèse ; à recaler sur une mesure)
ECART_MEME_COIN_DEG = 7.0  # deux vues d'un même coin, à moins de 7° l'une de l'autre
RESIDU_MAX_DEG = 4.0  # au-delà, les coins ne forment pas une pièce d'équerre : forme non proposée
LETTRES = "ABCDEFGHIJKLMNOP"


def ecart(a: float, b: float) -> float:
    """b − a, entre −180 et 180 degrés."""
    return (b - a + 180.0) % 360.0 - 180.0


def direction(x: float, direction_image: float, champ: float = CHAMP_PORTRAIT_DEG) -> float:
    """Direction (degrés) d'un point de l'image à l'abscisse x (0 = bord gauche, 1 = bord droit) : celle de la caméra plus
    l'angle sous lequel il est vu (le bord droit est à droite, donc plus loin dans le sens horaire)."""
    return (direction_image + math.degrees(math.atan((x - 0.5) * 2.0 * math.tan(math.radians(champ / 2.0))))) % 360.0


def champ_vertical(champ: float, largeur: int, hauteur: int) -> float:
    return math.degrees(2.0 * math.atan(math.tan(math.radians(champ / 2.0)) * hauteur / largeur))


def distance_au_sol(y_sol: float, elevation: float, champ_v: float, hauteur: float = HAUTEUR_CAMERA_M) -> float | None:
    """Distance horizontale du pied d'un mur vu à la hauteur y_sol de l'image (0 = haut, 1 = bas), caméra levée de
    `elevation` degrés (négatif : vers le sol). None s'il est trop près de l'horizon pour être mesuré."""
    sous_horizon = -elevation + math.degrees(math.atan((y_sol - 0.5) * 2.0 * math.tan(math.radians(champ_v / 2.0))))
    if sous_horizon < 4.0:
        return None
    return hauteur / math.tan(math.radians(sous_horizon))


@dataclass
class VueCoin:
    direction: float
    poids: float  # 1 (certitude forte) ou 0,5 (moyenne)
    distance: float | None = None  # par le pied du coin, si vu


@dataclass
class Coin:
    direction: float
    poids: float
    vues: int
    distance: float | None = None


def regrouper(vues: list[VueCoin], ecart_max: float = ECART_MEME_COIN_DEG) -> list[Coin]:
    """Les vues d'un même coin (le même coin apparaît sur deux ou trois images du tour) réunies, rangées par direction."""
    if not vues:
        return []
    vues = sorted(vues, key=lambda v: v.direction % 360.0)
    groupes: list[list[VueCoin]] = [[vues[0]]]
    for v in vues[1:]:
        if abs(ecart(groupes[-1][-1].direction, v.direction)) <= ecart_max:
            groupes[-1].append(v)
        else:
            groupes.append([v])
    if len(groupes) > 1 and abs(ecart(groupes[-1][-1].direction, groupes[0][0].direction)) <= ecart_max:
        groupes[0] = groupes.pop() + groupes[0]  # le tour se referme : le dernier groupe et le premier sont le même coin
    coins = []
    for g in groupes:
        poids = sum(v.poids for v in g)
        x = sum(v.poids * math.cos(math.radians(v.direction)) for v in g)
        y = sum(v.poids * math.sin(math.radians(v.direction)) for v in g)
        distances = [v.distance for v in g if v.distance is not None]
        coins.append(Coin(math.degrees(math.atan2(y, x)) % 360.0, poids, len(g),
                          float(np.median(distances)) if distances else None))
    return sorted(coins, key=lambda c: c.direction)


@dataclass
class Mur:
    debut: tuple[float, float]
    fin: tuple[float, float]
    lettre: str = ""
    ouvertures: list[dict] = field(default_factory=list)  # {type, debut, fin} : de 0 (début du mur) à 1 (fin)

    @property
    def longueur(self) -> float:
        return math.dist(self.debut, self.fin)


@dataclass
class Forme:
    sommets: list[tuple[float, float]]  # dans l'ordre des directions (sens horaire vu de dessus)
    orientation: float  # direction (degrés) d'un des deux axes des murs, entre 0 et 90
    residu: float  # écart moyen entre les directions des coins vues et celles du contour (degrés)
    echelle: str  # « sol » (pied des coins : mètres estimés) ou « relative » (proportions seules)
    murs: list[Mur] = field(default_factory=list)

    def vers_dict(self) -> dict:
        return {"sommets": [[round(x, 3), round(y, 3)] for x, y in self.sommets], "orientation": round(self.orientation, 1),
                "residu": round(self.residu, 2), "echelle": self.echelle,
                "murs": [{"lettre": m.lettre, "longueur": round(m.longueur, 3),
                          "ouvertures": [{**o, "debut": round(o["debut"], 3), "fin": round(o["fin"], 3)} for o in m.ouvertures]}
                         for m in self.murs]}


def _indices(n: int, depart_u: bool) -> list[tuple[int, int]]:
    """Pour chaque sommet, l'indice de sa coordonnée u et de sa coordonnée v : deux sommets voisins partagent l'une ou
    l'autre (murs d'équerre)."""
    moitie = n // 2
    if depart_u:
        return [(((i + 1) // 2) % moitie, i // 2) for i in range(n)]
    return [(i // 2, ((i + 1) // 2) % moitie) for i in range(n)]


def _resoudre(directions: list[float], distances: list[float | None], poids: list[float], phi: float, depart_u: bool):
    """Contour d'équerre d'orientation phi qui explique au mieux les directions (et distances) des coins. Renvoie
    (écart angulaire moyen, sommets) ou None si aucun contour valable."""
    n = len(directions)
    moitie = n // 2
    idx = _indices(n, depart_u)
    a = np.radians(np.asarray(directions) - phi)
    sin, cos = np.sin(a), np.cos(a)
    avec_distance = [i for i, d in enumerate(distances) if d is not None]
    colonnes = 2 * moitie + (1 if avec_distance else 0)
    lignes = []
    for i, (iu, iv) in enumerate(idx):  # direction : u·cos(β) − v·sin(β) = 0
        ligne = np.zeros(colonnes)
        ligne[iu] += cos[i] * poids[i]
        ligne[moitie + iv] -= sin[i] * poids[i]
        lignes.append(ligne)
    for i in avec_distance:  # distance (à l'échelle s près) : u·sin(β) + v·cos(β) − s·d = 0
        iu, iv = idx[i]
        ligne = np.zeros(colonnes)
        ligne[iu] += sin[i] * 0.5 * poids[i]
        ligne[moitie + iv] += cos[i] * 0.5 * poids[i]
        ligne[-1] -= distances[i] * 0.5 * poids[i]
        lignes.append(ligne)
    _, _, vt = np.linalg.svd(np.asarray(lignes))
    x = vt[-1]
    u, v = x[:moitie], x[moitie:2 * moitie]
    sommets_uv = np.array([[u[iu], v[iv]] for iu, iv in idx])
    portee = sommets_uv[:, 0] * sin + sommets_uv[:, 1] * cos
    if np.all(portee < 0):
        sommets_uv, portee, x = -sommets_uv, -portee, -x
    if not np.all(portee > 1e-6):
        return None  # un sommet derrière la caméra : contour impossible
    if np.ptp(u) < 1e-6 or np.ptp(v) < 1e-6:
        return None  # contour aplati
    # Retour au repère du tour (x vers 90°, y vers 0°) : u est l'axe de direction phi + 90, v celui de direction phi.
    p = math.radians(phi)
    sommets = [(su * math.cos(p) + sv * math.sin(p), -su * math.sin(p) + sv * math.cos(p)) for su, sv in sommets_uv]
    vues = [math.degrees(math.atan2(sx, sy)) % 360.0 for sx, sy in sommets]
    residu = float(np.average([abs(ecart(d, w)) for d, w in zip(directions, vues)], weights=poids))
    echelle = x[-1] if avec_distance and x[-1] > 1e-9 else None
    if echelle is not None:
        sommets = [(sx / echelle, sy / echelle) for sx, sy in sommets]
    else:  # proportions seules : la portée moyenne vaut 1
        moyenne = float(np.mean(portee))
        sommets = [(sx / moyenne, sy / moyenne) for sx, sy in sommets]
    return residu, sommets, echelle is not None


def ajuster(coins: list[Coin]) -> Forme | None:
    """La pièce d'équerre dont les coins sont vus dans ces directions (au moins 4, en nombre pair : rectangle, L…)."""
    if len(coins) < 4 or len(coins) % 2:
        return None
    directions = [c.direction for c in coins]
    distances = [c.distance for c in coins]
    poids = [max(0.25, min(2.0, c.poids)) for c in coins]
    meilleur = None
    for depart_u in (True, False):
        for phi in np.arange(0.0, 90.0, 0.5):
            essai = _resoudre(directions, distances, poids, float(phi), depart_u)
            if essai and (meilleur is None or essai[0] < meilleur[0][0]):
                meilleur = (essai, float(phi), depart_u)
    if meilleur is None:
        return None
    (residu, sommets, metrique), phi, depart_u = meilleur
    for fin in np.linspace(phi - 0.5, phi + 0.5, 21):  # affinage autour du meilleur
        essai = _resoudre(directions, distances, poids, float(fin), depart_u)
        if essai and essai[0] < residu:
            (residu, sommets, metrique), phi = essai, float(fin)
    if residu > RESIDU_MAX_DEG:
        return None
    murs = [Mur(sommets[i], sommets[(i + 1) % len(sommets)]) for i in range(len(sommets))]
    return Forme(sommets, phi % 90.0, residu, "sol" if metrique else "relative", murs)


def _intersection(direction_deg: float, mur: Mur) -> float | None:
    """Où le rayon partant de la caméra dans cette direction coupe le mur : de 0 (début) à 1 (fin), ou None."""
    d = (math.sin(math.radians(direction_deg)), math.cos(math.radians(direction_deg)))
    (x1, y1), (x2, y2) = mur.debut, mur.fin
    ex, ey = x2 - x1, y2 - y1
    det = d[0] * (-ey) - d[1] * (-ex)
    if abs(det) < 1e-12:
        return None
    # rayon t·d = début + s·e
    t = (x1 * (-ey) - y1 * (-ex)) / det
    s = (d[0] * y1 - d[1] * x1) / det
    return s if t > 0 and -0.05 <= s <= 1.05 else None


def mur_vers(forme: Forme, direction_deg: float) -> int | None:
    """Le mur qu'on voit dans cette direction depuis la caméra."""
    for i, mur in enumerate(forme.murs):
        if _intersection(direction_deg, mur) is not None:
            return i
    return None


def placer_ouvertures(forme: Forme, objets: list[tuple[str, float, float]]) -> None:
    """Chaque fenêtre, porte… (type, direction du bord gauche, du bord droit) sur son mur, de 0 à 1 le long du mur. Les vues
    d'un même objet sur deux images (même mur, intervalles qui se chevauchent) n'en font qu'un."""
    for type_objet, gauche, droite in objets:
        milieu = (gauche + ecart(gauche, droite) / 2.0) % 360.0
        i = mur_vers(forme, milieu)
        if i is None:
            continue
        mur = forme.murs[i]
        bornes = [s for s in (_intersection(gauche, mur), _intersection(droite, mur)) if s is not None]
        if not bornes:
            continue
        debut, fin = max(0.0, min(bornes)), min(1.0, max(bornes))
        if len(bornes) == 1:  # un bord au-delà du mur (dans le coin) : jusqu'au bout du mur de ce côté
            centre = _intersection(milieu, mur) or bornes[0]
            debut, fin = (max(0.0, min(bornes[0], centre)), min(1.0, max(bornes[0], centre)))
        for o in mur.ouvertures:
            if o["type"] == type_objet and o["debut"] <= fin and debut <= o["fin"]:
                o["debut"], o["fin"] = min(o["debut"], debut), max(o["fin"], fin)
                break
        else:
            mur.ouvertures.append({"type": type_objet, "debut": debut, "fin": fin})
    for mur in forme.murs:
        mur.ouvertures.sort(key=lambda o: o["debut"])


def lettrer(forme: Forme, direction_entree: float | None) -> None:
    """Murs A, B, C… : A est celui de la porte par laquelle on est entré (derrière soi en entrant : la direction de la
    marche + 180°), puis dans le sens des aiguilles d'une montre (convention du repérage plomb, NF X46-030 : hypothèse
    forte). Sans direction d'entrée : le mur où une porte a été vue, sinon le premier."""
    depart = None
    if direction_entree is not None:
        depart = mur_vers(forme, (direction_entree + 180.0) % 360.0)
    if depart is None:
        depart = next((i for i, m in enumerate(forme.murs) if any(o["type"] == "porte" for o in m.ouvertures)), 0)
    n = len(forme.murs)
    for k in range(n):
        forme.murs[(depart + k) % n].lettre = LETTRES[k] if k < len(LETTRES) else f"Z{k}"
