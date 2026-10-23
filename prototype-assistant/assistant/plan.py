"""Plan du logement à partir de la trajectoire du téléphone (Noah, 23/10 : « un croquis fondé sur une reconstruction
spatiale : suivre les déplacements du téléphone dans un repère commun, positionner les murs et les portes, puis rattacher
les pièces à cette géométrie »).

Chaque pièce est placée là où l'on a marché pendant qu'on y était (tous ses séjours, revisites comprises) : un rectangle
de sa taille habituelle (séjour, chambre, WC…), agrandi si l'on y a marché plus loin, aligné sur l'axe du logement
(direction dominante des marches, à 90° près) ; deux pièces qui se chevauchent sont écartées sans changer de taille, deux
pièces presque jointives partagent leur mur ; la porte entre deux pièces est là où l'on est passé de l'une à l'autre,
posée sur leur mur commun. Pas de cotes : des
proportions approximatives, à la mesure des pas (0,6 m par pas, hypothèse).

Une pièce tracée sur la caméra (web/trace.js : chaque coin validé, la position du téléphone suivie par le sol filmé) est
dessinée telle quelle, à sa place, avec ses angles : ni déplacée, ni déformée, ni remise d'équerre (Noah, 23/10 : « le plan
2D doit se construire à partir des points réellement enregistrés, en respectant les changements de direction et les angles
entre les murs »). Les pièces seulement estimées s'écartent d'elle ou s'étendent jusqu'à ses murs ; ses murs donnent l'axe
du logement, plus sûr que la direction des marches.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .trajectoire import Trajectoire, tourner

MARGE_M = 0.6  # on reste à ~60 cm des murs en marchant
# Tailles habituelles (grand côté, petit côté, en mètres) : une pièce où l'on a peu marché garde une taille vraisemblable
# (hypothèse ; le croquis est sans cotes).
TAILLES = {"sejour": (5.0, 4.0), "salon": (5.0, 4.0), "salle a manger": (4.0, 3.5), "cuisine": (3.2, 3.0),
           "chambre": (3.6, 3.2), "salle de bains": (2.6, 2.2), "salle d eau": (2.2, 2.0), "wc": (1.6, 1.2),
           "toilettes": (1.6, 1.2), "entree": (2.4, 2.0), "couloir": (4.0, 1.2), "degagement": (3.0, 1.2),
           "escalier": (3.0, 1.2), "palier": (1.8, 1.6), "bureau": (3.0, 3.0), "buanderie": (2.4, 2.0),
           "cellier": (2.0, 2.0), "garage": (5.5, 3.0), "dressing": (2.0, 1.8), "placard": (1.2, 0.8),
           "veranda": (4.0, 3.0), "mezzanine": (3.0, 3.0)}
TAILLE_DEFAUT = (3.0, 3.0)
PAS_TRAJET_M = 0.3  # le trajet affiché : un point tous les 30 cm
VISEE_M = 2.0  # une pièce regardée depuis sa porte, sans y marcher : posée à 2 m dans la direction filmée


@dataclass
class Sejour:
    cle: str
    t_entree: float  # passage de la porte (milieu de la marche qui y mène), ou instant connu
    porte: tuple[float, float] | None = None  # où l'on est passé (repère de la trajectoire)
    t_nomme: float = 0.0  # quand la pièce a été nommée ou reconnue (la caméra la filmait)


@dataclass
class Rectangle:
    u0: float
    v0: float
    u1: float
    v1: float
    mesure: bool = False  # pièce tracée : sa taille ne change jamais
    fixe: bool = False  # pièce tracée : elle ne bouge pas non plus (elle est là où ses coins ont été validés)

    @property
    def centre(self) -> tuple[float, float]:
        return (self.u0 + self.u1) / 2, (self.v0 + self.v1) / 2

    def chevauche(self, autre: "Rectangle") -> bool:
        return self.u0 < autre.u1 and autre.u0 < self.u1 and self.v0 < autre.v1 and autre.v0 < self.v1


@dataclass
class Plan:
    pieces: dict[str, list[tuple[float, float]]] = field(default_factory=dict)  # sommets, repère d'affichage
    portes: list[tuple[str, str, float, float]] = field(default_factory=list)
    trajet: list[tuple[float, float]] = field(default_factory=list)
    position: tuple[float, float] = (0.0, 0.0)
    depuis_la_porte: set[str] = field(default_factory=set)  # pièces seulement regardées depuis leur porte
    # Le sens de la marche (repère d'affichage), pour dessiner le plan comme un croquis à la main : ce qui est devant en
    # haut (2e test de Noah, 23/10 : nord en haut, en marchant vers le sud tout paraissait « dans le mauvais sens »).
    sens_marche: float | None = None  # celui de la dernière marche
    sens_entree: float | None = None  # celui de la première marche (le plan d'ensemble, entrée en bas)
    axe: float = 0.0
    oriente: bool = False
    mesurees: set[str] = field(default_factory=set)  # pièces dont les murs ont été relevés (forme exacte)
    murs: dict[str, list[float]] = field(default_factory=dict)  # longueur de chaque mur relevé, dans l'ordre des sommets
    coins: list[tuple[float, float]] = field(default_factory=list)  # coins du relevé en cours (repère d'affichage)


def axe_du_logement(directions: list[float]) -> float:
    """Direction dominante des marches, à 90° près (les murs d'une maison sont d'équerre) : moyenne circulaire de 4θ."""
    if len(directions) < 4:
        return 0.0
    s = sum(math.sin(math.radians(4 * d)) for d in directions)
    c = sum(math.cos(math.radians(4 * d)) for d in directions)
    if math.hypot(s, c) < 0.25 * len(directions):
        return 0.0  # pas de direction nette
    return (math.degrees(math.atan2(s, c)) / 4.0) % 90.0


def axe_des_releves(releves: dict[str, list[tuple[float, float]]]) -> float:
    """L'axe du logement donné par les murs relevés (à 90° près) : moyenne circulaire de 4θ, pondérée par la longueur."""
    s = c = 0.0
    for poly in releves.values():
        for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
            angle = math.radians(4.0 * math.degrees(math.atan2(x2 - x1, y2 - y1)))
            s, c = s + math.dist((x1, y1), (x2, y2)) * math.sin(angle), c + math.dist((x1, y1), (x2, y2)) * math.cos(angle)
    return (math.degrees(math.atan2(s, c)) / 4.0) % 90.0 if math.hypot(s, c) > 1e-9 else 0.0


def _aire(poly: list[tuple[float, float]]) -> float:
    """Aire signée : positive si les sommets tournent dans le sens inverse des aiguilles d'une montre."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1])) / 2.0


def entrees(trajectoire: Trajectoire, changements: list[tuple[str, float]]) -> list[Sejour]:
    """Les séjours dans chaque pièce : un changement de pièce reconnu à l'instant t (souvent quelques secondes après être
    entré) est rapporté au milieu de la dernière marche qui l'a précédé, celle qui a mené dans la pièce."""
    marches = trajectoire.marches()
    sejours: list[Sejour] = []
    for k, (cle, t) in enumerate(changements):
        if sejours and sejours[-1].cle == cle:
            continue
        precedente = sejours[-1].t_entree if sejours else -math.inf
        candidates = [m for m in marches if precedente < m.t_debut and m.t_fin <= t + 1.0]
        if candidates and k > 0:
            m = candidates[-1]
            t_entree = (m.t_debut + m.t_fin) / 2
            sejours.append(Sejour(cle, t_entree, trajectoire.position(t_entree), t))
        else:
            sejours.append(Sejour(cle, t if k > 0 else -math.inf, trajectoire.position(t) if k > 0 else None, t))
    return sejours


def construire(trajectoire: Trajectoire, changements: list[tuple[str, float]], t_actuel: float,
               correction: float | None = None, vues: list[tuple[str, float]] | None = None,
               relations: list[tuple[str, tuple[str, ...]]] | None = None,
               releves: dict[str, list[tuple[float, float]]] | None = None,
               coins: list[tuple[float, float]] | None = None, piece_des_coins: str | None = None) -> Plan:
    """Le plan : pièces (rectangles, ou forme relevée), portes, trajet et position, dans le repère d'affichage (nord en haut
    si la correction boussole − gyroscope est connue, ou si la trajectoire est déjà en caps). `releves` : les contours
    relevés (repère de la trajectoire) ; `coins` : ceux du relevé en cours dans la pièce `piece_des_coins`."""
    sejours = entrees(trajectoire, changements)
    positions = trajectoire.positions()
    releves = {cle: poly for cle, poly in (releves or {}).items() if len(poly) >= 3}
    directions = [p.direction for p in trajectoire.pas if p.compte and p.direction is not None]
    axe = axe_des_releves(releves) if releves else axe_du_logement(directions)

    def vers_axe(x: float, y: float) -> tuple[float, float]:
        return tourner(x, y, -axe)  # les murs alignés sur les axes u, v

    points: dict[str, list[tuple[float, float]]] = {}
    marchees: set[str] = set()
    for k, s in enumerate(sejours):
        fin = sejours[k + 1].t_entree if k + 1 < len(sejours) else t_actuel
        direction = trajectoire.direction(s.t_nomme)
        if k > 0 and direction is not None and s.t_nomme > s.t_entree and trajectoire.distance(s.t_nomme, fin) < 1.0:
            # Regardée depuis sa porte, sans y marcher ensuite (une chambre occupée, une salle d'eau ; test de Noah du
            # 23/10) : la pièce est devant, dans la direction filmée quand elle a été nommée ; la marche jusqu'à la porte
            # était dans la pièce d'avant, et la porte est là où l'on se tenait.
            avant = [(x, y) for t, x, y in positions if s.t_entree <= t < s.t_nomme]
            points.setdefault(sejours[k - 1].cle, []).extend(vers_axe(x, y) for x, y in avant)
            x, y = trajectoire.position(s.t_nomme)
            s.porte = (x, y)
            dedans = [(x, y), (x + VISEE_M * math.sin(math.radians(direction)), y + VISEE_M * math.cos(math.radians(direction)))]
        else:
            dedans = [(x, y) for t, x, y in positions if s.t_entree <= t < fin]
            dedans.append(trajectoire.position(fin if fin != math.inf else t_actuel))
            if s.porte is not None:
                dedans.append(s.porte)
            marchees.add(s.cle)
        points.setdefault(s.cle, []).extend(vers_axe(x, y) for x, y in dedans)

    portes_vues: list[tuple[str, str, tuple[float, float]]] = []
    for cle, t in vues or []:
        # Montré sans y entrer (« ça c'est l'entrée », « au bout du salon, une chambre ») : devant, dans la direction filmée.
        direction = trajectoire.direction(t)
        if cle in marchees or direction is None:
            continue
        x, y = trajectoire.position(t)
        loin = (x + VISEE_M * math.sin(math.radians(direction)), y + VISEE_M * math.cos(math.radians(direction)))
        points.setdefault(cle, []).extend([vers_axe(x, y), vers_axe(*loin)])
        ici = next((s.cle for s in reversed(sejours) if s.t_entree <= t), sejours[0].cle if sejours else None)
        if ici is not None and ici != cle:
            portes_vues.append((ici, cle, (x, y)))
    formes: dict[str, list[tuple[float, float]]] = {}
    for cle, poly in releves.items():
        uv = [vers_axe(x, y) for x, y in poly]
        formes[cle] = uv[::-1] if _aire(uv) < 0 else uv  # sens inverse des aiguilles d'une montre (lettres A, B, C…)
    rectangles = {cle: _rectangle(cle, pts) for cle, pts in points.items() if cle not in formes}
    for cle, uv in formes.items():
        rectangles[cle] = Rectangle(min(u for u, _ in uv), min(v for _, v in uv), max(u for u, _ in uv),
                                    max(v for _, v in uv), mesure=True, fixe=True)
    depart = {cle: r.centre for cle, r in rectangles.items()}
    _ecarter(rectangles)
    for x, avec in relations or []:  # « la salle de bain est dans le couloir » : elle le touche
        for y in avec:
            if x in rectangles and y in rectangles and x != y:
                _contre(rectangles[x], rectangles[y])
        _ecarter(rectangles)
    _accoler(rectangles)

    plan = Plan(axe=axe)
    plan.depuis_la_porte = {cle for cle in points if cle not in marchees and cle not in formes
                            and (not sejours or cle != sejours[0].cle)}
    plan.oriente = correction is not None or trajectoire.repere == "cap"
    vers_affichage = correction if (correction is not None and trajectoire.repere == "lacet") else 0.0

    def afficher(u: float, v: float) -> tuple[float, float]:
        x, y = tourner(u, v, axe)  # retour au repère de la trajectoire
        return tourner(x, y, vers_affichage)

    def decalage(cle: str) -> tuple[float, float]:
        (u0, v0), (u1, v1) = depart[cle], rectangles[cle].centre
        return u1 - u0, v1 - v0

    for cle, r in rectangles.items():
        if cle in formes:  # la forme relevée, déplacée comme son rectangle (jamais déformée)
            du, dv = decalage(cle)
            sommets = [(u + du, v + dv) for u, v in formes[cle]]
            plan.pieces[cle] = [afficher(u, v) for u, v in sommets]
            plan.murs[cle] = [math.dist(a, b) for a, b in zip(sommets, sommets[1:] + sommets[:1])]
            plan.mesurees.add(cle)
        else:
            plan.pieces[cle] = [afficher(r.u0, r.v0), afficher(r.u1, r.v0), afficher(r.u1, r.v1), afficher(r.u0, r.v1)]
    du, dv = decalage(piece_des_coins) if piece_des_coins in rectangles else (0.0, 0.0)
    plan.coins = [afficher(u + du, v + dv) for u, v in (vers_axe(x, y) for x, y in coins or [])]
    passages = [(sejours[k - 1].cle, sejours[k].cle, sejours[k].porte) for k in range(1, len(sejours))] + portes_vues
    for a, b, porte in passages:
        if porte is None or a == b or a not in rectangles or b not in rectangles:
            continue
        u, v = _sur_le_mur_commun(rectangles[a], rectangles[b], vers_axe(*porte))
        if not any({pa, pb} == {a, b} for pa, pb, _, _ in plan.portes):
            plan.portes.append((a, b, *afficher(u, v)))
    plan.trajet = [tourner(x, y, vers_affichage) for x, y in _alleger([(x, y) for _, x, y in positions])]
    marches = [m for m in trajectoire.marches() if m.distance >= 1.0]
    if marches:
        plan.sens_entree = _sens(trajectoire, marches[0], vers_affichage)
        plan.sens_marche = _sens(trajectoire, marches[-1], vers_affichage)
    plan.position = tourner(*trajectoire.position(t_actuel), vers_affichage)
    return plan


def _type_de(cle: str) -> str | None:
    return next((t for t in sorted(TAILLES, key=len, reverse=True) if cle == t or cle.startswith(t + " ")), None)


def _rectangle(cle: str, pts: list[tuple[float, float]]) -> Rectangle:
    """La pièce : sa taille habituelle (un séjour plus grand qu'un WC), centrée là où l'on y a marché, le grand côté dans
    le sens où l'on s'y est le plus déplacé ; agrandie si l'on a marché plus loin."""
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    cu, cv = (min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2
    long, court = TAILLES.get(_type_de(cle) or "", TAILLE_DEFAUT)
    etendue_u, etendue_v = max(us) - min(us), max(vs) - min(vs)
    lu, lv = (long, court) if etendue_u >= etendue_v else (court, long)
    lu, lv = max(lu, etendue_u + 2 * MARGE_M), max(lv, etendue_v + 2 * MARGE_M)
    return Rectangle(cu - lu / 2, cv - lv / 2, cu + lu / 2, cv + lv / 2)


def _sens(trajectoire: Trajectoire, marche, decalage: float) -> float | None:
    """Direction moyenne des pas d'une marche (repère d'affichage)."""
    directions = [p.direction for p in trajectoire.pas if p.compte and p.direction is not None and marche.t_debut <= p.t <= marche.t_fin]
    if not directions:
        return None
    s = sum(math.sin(math.radians(d)) for d in directions)
    c = sum(math.cos(math.radians(d)) for d in directions)
    return (math.degrees(math.atan2(s, c)) + decalage) % 360.0


def _contre(r: Rectangle, autre: Rectangle) -> None:
    """Déplace r pour qu'il touche `autre`, du côté où il se trouve déjà (relation dite par le diagnostiqueur). Une pièce
    tracée ne bouge pas."""
    if r.fixe:
        return
    (cu, cv), (au, av) = r.centre, autre.centre
    if r.u1 >= autre.u0 and autre.u1 >= r.u0 and r.v1 >= autre.v0 and autre.v1 >= r.v0:
        return  # elles se touchent déjà
    if abs(cu - au) * (autre.v1 - autre.v0) >= abs(cv - av) * (autre.u1 - autre.u0):
        du = (autre.u1 - r.u0) if cu > au else (autre.u0 - r.u1)
        r.u0, r.u1 = r.u0 + du, r.u1 + du
        dv = min(0.0, autre.v1 - r.v0 - 0.5) if r.v0 > autre.v1 - 0.5 else max(0.0, autre.v0 - r.v1 + 0.5)
        r.v0, r.v1 = r.v0 + dv, r.v1 + dv
    else:
        dv = (autre.v1 - r.v0) if cv > av else (autre.v0 - r.v1)
        r.v0, r.v1 = r.v0 + dv, r.v1 + dv
        du = min(0.0, autre.u1 - r.u0 - 0.5) if r.u0 > autre.u1 - 0.5 else max(0.0, autre.u0 - r.u1 + 0.5)
        r.u0, r.u1 = r.u0 + du, r.u1 + du


def _ecarter(rectangles: dict[str, Rectangle]) -> None:
    """Deux pièces qui se chevauchent sont écartées l'une de l'autre (chacune de la moitié), sur l'axe où elles se
    chevauchent le moins : elles gardent leur taille et leur place relative (avant : découpées, une petite pièce peu
    parcourue devenait une fente)."""
    cles = list(rectangles)
    for _ in range(60):
        bouge = False
        for i, a in enumerate(cles):
            for b in cles[i + 1:]:
                ra, rb = rectangles[a], rectangles[b]
                if not ra.chevauche(rb):
                    continue
                if ra.fixe and rb.fixe:
                    continue  # deux pièces tracées : chacune est là où ses coins ont été validés
                pu = min(ra.u1, rb.u1) - max(ra.u0, rb.u0)
                pv = min(ra.v1, rb.v1) - max(ra.v0, rb.v0)
                (cau, cav), (cbu, cbv) = ra.centre, rb.centre
                ka, kb = (0.0, 2.0) if ra.fixe else (2.0, 0.0) if rb.fixe else (1.0, 1.0)  # seule la pièce estimée s'écarte
                if pu <= pv:
                    d = (pu / 2 + 1e-6) * (1 if cbu >= cau else -1)
                    ra.u0, ra.u1, rb.u0, rb.u1 = ra.u0 - ka * d, ra.u1 - ka * d, rb.u0 + kb * d, rb.u1 + kb * d
                else:
                    d = (pv / 2 + 1e-6) * (1 if cbv >= cav else -1)
                    ra.v0, ra.v1, rb.v0, rb.v1 = ra.v0 - ka * d, ra.v1 - ka * d, rb.v0 + kb * d, rb.v1 + kb * d
                bouge = True
        if not bouge:
            break


def _accoler(rectangles: dict[str, Rectangle], ecart_max: float = 0.8) -> None:
    """Deux pièces presque jointives (moins de 0,8 m entre elles, face à face) partagent leur mur : un croquis sans couloir
    fantôme entre deux pièces voisines."""
    cles = list(rectangles)
    for i, a in enumerate(cles):
        for b in cles[i + 1:]:
            ra, rb = rectangles[a], rectangles[b]
            face_v = min(ra.v1, rb.v1) - max(ra.v0, rb.v0) > 0.5  # elles se font face selon u
            face_u = min(ra.u1, rb.u1) - max(ra.u0, rb.u0) > 0.5
            if face_v:
                gauche, droite = (ra, rb) if ra.u0 < rb.u0 else (rb, ra)
                ecart = droite.u0 - gauche.u1
                if 0 < ecart < ecart_max:
                    if gauche.fixe and droite.fixe:
                        continue
                    if gauche.mesure and droite.mesure:  # deux pièces relevées : la seconde vient contre la première
                        droite.u0, droite.u1 = droite.u0 - ecart, droite.u1 - ecart
                    elif gauche.mesure or droite.mesure:  # seule la pièce estimée s'étend jusqu'au mur relevé
                        gauche.u1, droite.u0 = (gauche.u1, gauche.u1) if gauche.mesure else (droite.u0, droite.u0)
                    else:
                        milieu = (gauche.u1 + droite.u0) / 2
                        gauche.u1, droite.u0 = milieu, milieu
            elif face_u:
                bas, haut = (ra, rb) if ra.v0 < rb.v0 else (rb, ra)
                ecart = haut.v0 - bas.v1
                if 0 < ecart < ecart_max:
                    if bas.fixe and haut.fixe:
                        continue
                    if bas.mesure and haut.mesure:
                        haut.v0, haut.v1 = haut.v0 - ecart, haut.v1 - ecart
                    elif bas.mesure or haut.mesure:
                        bas.v1, haut.v0 = (bas.v1, bas.v1) if bas.mesure else (haut.v0, haut.v0)
                    else:
                        milieu = (bas.v1 + haut.v0) / 2
                        bas.v1, haut.v0 = milieu, milieu


def _sur_le_mur_commun(ra: Rectangle, rb: Rectangle, porte: tuple[float, float]) -> tuple[float, float]:
    """La porte posée sur le mur que partagent les deux pièces (si elles se touchent), au plus près de l'endroit du passage."""
    u, v = porte
    if abs(ra.u1 - rb.u0) < 1e-6 or abs(rb.u1 - ra.u0) < 1e-6:
        limite = ra.u1 if abs(ra.u1 - rb.u0) < 1e-6 else ra.u0
        bas, haut = max(ra.v0, rb.v0), min(ra.v1, rb.v1)
        if bas < haut:
            return limite, min(max(v, bas + 0.45), haut - 0.45) if haut - bas > 0.9 else (bas + haut) / 2
    if abs(ra.v1 - rb.v0) < 1e-6 or abs(rb.v1 - ra.v0) < 1e-6:
        limite = ra.v1 if abs(ra.v1 - rb.v0) < 1e-6 else ra.v0
        gauche, droite = max(ra.u0, rb.u0), min(ra.u1, rb.u1)
        if gauche < droite:
            return (min(max(u, gauche + 0.45), droite - 0.45) if droite - gauche > 0.9 else (gauche + droite) / 2), limite
    return u, v


def _alleger(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    garde: list[tuple[float, float]] = []
    for p in points:
        if not garde or math.dist(garde[-1], p) >= PAS_TRAJET_M:
            garde.append(p)
    if points and (not garde or garde[-1] != points[-1]):
        garde.append(points[-1])
    return garde


LETTRES = "ABCDEFGH"


def _distance_au_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    longueur = dx * dx + dy * dy
    k = 0.0 if longueur == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / longueur))
    return math.dist(p, (ax + k * dx, ay + k * dy))


def lettres(sommets: list[tuple[float, float]], entree: tuple[float, float] | None) -> list[str]:
    """La lettre de chaque mur (dans l'ordre des sommets) : A est le mur le plus proche de l'endroit où l'on est entré
    dans la pièce (sa porte d'entrée ; pour la première pièce, le départ de la visite, près de la porte du logement),
    puis B, C, D dans le sens des aiguilles d'une montre vu de dessus (les sommets tournent dans l'autre sens)."""
    n = len(sommets)
    depart = 0 if entree is None else min(range(n), key=lambda i: _distance_au_segment(entree, sommets[i], sommets[(i + 1) % n]))
    resultat = [""] * n
    for k in range(n):
        resultat[(depart - k) % n] = LETTRES[k] if k < len(LETTRES) else ""
    return resultat


def vers_dict(plan: Plan, noms: dict[str, str], sources: dict[str, str], courante: str | None) -> dict:
    arrondi = lambda p: [round(p[0], 2), round(p[1], 2)]  # noqa: E731
    entrees_par_piece = {b: (x, y) for a, b, x, y in reversed(plan.portes)}  # la première porte par laquelle on y est entré
    depart = plan.trajet[0] if plan.trajet else None
    return {
        "oriente": plan.oriente,
        "courante": courante,
        "pieces": [{"cle": cle, "nom": noms.get(cle, cle), "source": sources.get(cle, ""), "polygone": [arrondi(p) for p in sommets],
                    "lettres": lettres(sommets, entrees_par_piece.get(cle, depart if k == 0 else None)),
                    "depuis_la_porte": cle in plan.depuis_la_porte, "mesuree": cle in plan.mesurees,
                    "murs": [round(m, 2) for m in plan.murs.get(cle, [])]}
                   for k, (cle, sommets) in enumerate(plan.pieces.items())],
        "portes": [{"a": a, "b": b, "x": round(x, 2), "y": round(y, 2)} for a, b, x, y in plan.portes],
        "trajet": [arrondi(p) for p in plan.trajet],
        "position": arrondi(plan.position),
        "coins": [arrondi(p) for p in plan.coins],
        "sens_marche": None if plan.sens_marche is None else round(plan.sens_marche, 1),
        "sens_entree": None if plan.sens_entree is None else round(plan.sens_entree, 1),
    }
