"""Croquis du logement dessiné en direct pendant la visite (Noah, 23/10 : « pour le plomb et l'amiante il faut un plan :
on fait le tour de la maison et le croquis se dessine en même temps, dans un coin du téléphone »).

Choix de Noah : un **croquis sans mesures** (la disposition, comme un croquis papier) ; les pièces **reconnues seules**
(voir assistant/regard.py : Claude regarde la vidéo) ; les murs repérés **A, B, C, D, A étant le mur de la porte par
laquelle on entre dans la pièce, puis dans le sens des aiguilles d'une montre** (convention du repérage plomb ; hypothèse
à confirmer avec la norme NF X46-030 pour les cas particuliers : pièce à plusieurs portes, pièce de départ).

Comment il se dessine : chaque pièce est une case d'une grille ; on entre dans une nouvelle pièce en marchant dans une
direction (cap de la caméra au passage de la porte : boussole, sinon gyroscope) ; elle est posée à côté de la pièce
d'où l'on vient, de ce côté-là, avec la porte entre les deux. Le croquis est recalculé à chaque changement à partir de
la suite des passages : quand le nord devient connu, tout se remet d'aplomb. Les fenêtres et les portes du logement
notées pendant la visite sont posées sur le mur de leur côté. Pas de longueurs : les pièces ont toutes la même taille.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .boussole import point_cardinal

POINTS = ("nord", "est", "sud", "ouest")  # dans le sens des aiguilles d'une montre, nord en haut
PAS = {"nord": (0, -1), "est": (1, 0), "sud": (0, 1), "ouest": (-1, 0)}  # sur la grille (y vers le bas)
OPPOSE = {"nord": "sud", "sud": "nord", "est": "ouest", "ouest": "est"}
LETTRES = "ABCD"


@dataclass
class PieceCroquis:
    cle: str  # la pièce dans la checklist
    nom: str
    source: str  # « image » (reconnue par Claude), « dit », « tapé »


@dataclass
class Passage:
    """On entre dans `vers` en venant de `de`, la caméra vers ce cap (absolu : boussole ; sinon lacet du gyroscope)."""

    de: str | None
    vers: str
    t: float
    cap: float | None = None
    lacet: float | None = None


@dataclass
class Disposition:
    positions: dict[str, tuple[int, int]] = field(default_factory=dict)
    portes: list[tuple[str, str, str]] = field(default_factory=list)  # (pièce, pièce voisine, côté dans la première)
    entrees: dict[str, str] = field(default_factory=dict)  # pièce -> côté de la porte par laquelle on y est entré
    absolu: bool = False  # nord connu : le croquis est orienté


class Croquis:
    def __init__(self) -> None:
        self.pieces: dict[str, PieceCroquis] = {}
        self.passages: list[Passage] = []
        self.courante: str | None = None
        self.fixees: dict[str, tuple[int, int]] = {}  # pièces déplacées à la main sur le croquis
        self.vues: list[tuple[str, float]] = []  # espaces regardés sans y entrer (« au bout du salon, une chambre »)

    def entrer(self, cle: str, nom: str, source: str, t: float, cap: float | None = None, lacet: float | None = None) -> None:
        """On est dans la pièce `cle` (nouvelle, ou déjà vue : une revisite ne crée rien)."""
        if cle not in self.pieces:
            self.pieces[cle] = PieceCroquis(cle, nom, source)
        elif source != "image" or self.pieces[cle].source == "image":
            self.pieces[cle].nom, self.pieces[cle].source = nom, source
        if cle != self.courante:
            self.passages.append(Passage(self.courante, cle, t, cap, lacet))
            self.courante = cle

    def voir(self, cle: str, nom: str, source: str, t: float) -> None:
        """Un espace montré sans y entrer : sur le plan dans la direction filmée à l'instant t ; la pièce courante ne change pas."""
        if cle not in self.pieces:
            self.pieces[cle] = PieceCroquis(cle, nom, source)
        self.vues.append((cle, t))

    def renommer(self, ancienne: str, nouvelle: str, nom: str, source: str) -> None:
        """« Non, c'est la chambre » : la même pièce, un autre nom (la checklist fait de même)."""
        if ancienne not in self.pieces:
            return
        self.pieces = {(nouvelle if k == ancienne else k): (PieceCroquis(nouvelle, nom, source) if k == ancienne else p)
                       for k, p in self.pieces.items()}
        for p in self.passages:
            p.de = nouvelle if p.de == ancienne else p.de
            p.vers = nouvelle if p.vers == ancienne else p.vers
        self.courante = nouvelle if self.courante == ancienne else self.courante
        self.vues = [(nouvelle if c == ancienne else c, t) for c, t in self.vues]

    def fusionner(self, cle: str, dans: str) -> None:
        """La pièce `cle` était `dans` (reconnue à tort) : ses passages deviennent ceux de `dans`."""
        self.pieces.pop(cle, None)
        self.fixees.pop(cle, None)
        for p in self.passages:
            p.de = dans if p.de == cle else p.de
            p.vers = dans if p.vers == cle else p.vers
        self.passages = [p for p in self.passages if p.de != p.vers]
        self.courante = dans if self.courante == cle else self.courante
        self.vues = [(dans if c == cle else c, t) for c, t in self.vues]

    def deplacer(self, cle: str, vers: str, correction: float | None = None) -> None:
        """Déplace une pièce d'une case (ex. deux portes du même côté d'une grande pièce : le croquis ne peut pas le deviner)."""
        x, y = self.disposer(correction).positions.get(cle, (0, 0))
        self.fixees[cle] = (x + PAS[vers][0], y + PAS[vers][1])

    def _direction(self, passage: Passage, correction: float | None) -> str | None:
        """Le côté vers lequel on marchait : gyroscope recalé sur le nord si possible (cohérent sur toute la visite)."""
        if passage.lacet is not None:
            return point_cardinal(passage.lacet + (correction or 0.0))
        return point_cardinal(passage.cap) if passage.cap is not None else None

    def disposer(self, correction: float | None = None) -> Disposition:
        """Les pièces sur la grille, rejouées dans l'ordre des passages."""
        d = Disposition(absolu=correction is not None or (bool(self.passages) and all(
            p.lacet is None and p.cap is not None for p in self.passages[1:])))
        occupees: dict[tuple[int, int], str] = {}
        for cle, position in self.fixees.items():  # placées à la main d'abord
            if cle in self.pieces:
                d.positions[cle] = position
                occupees[position] = cle
        for passage in self.passages:
            if passage.vers not in self.pieces:
                continue
            if passage.de is None or passage.de not in d.positions:
                if passage.vers not in d.positions:
                    position = (0, 0)
                    while position in occupees:  # une pièce de plus sans passage connu : à droite des autres
                        position = (position[0] + 2, position[1])
                    d.positions[passage.vers] = position
                    occupees[position] = passage.vers
                continue
            depart = d.positions[passage.de]
            cote = self._direction(passage, correction)
            if passage.vers in d.positions:  # revisite, ou pièce placée à la main : une porte si les pièces se touchent
                arrivee = d.positions[passage.vers]
                ecart = (arrivee[0] - depart[0], arrivee[1] - depart[1])
                cote = next((c for c, pas in PAS.items() if pas == ecart), None)
            else:
                if cote is None:  # sans boussole ni gyroscope : la première place libre, dans le sens horaire
                    cote = next((c for c in ("est", "sud", "ouest", "nord")
                                 if (depart[0] + PAS[c][0], depart[1] + PAS[c][1]) not in occupees), "est")
                x, y = depart
                while (x, y) in occupees:
                    x, y = x + PAS[cote][0], y + PAS[cote][1]
                d.positions[passage.vers] = (x, y)
                occupees[(x, y)] = passage.vers
                if (x - depart[0], y - depart[1]) != PAS[cote]:
                    cote = None  # posée plus loin (la place voisine était prise) : pas de porte commune dessinée
                d.entrees.setdefault(passage.vers, OPPOSE[cote] if cote else "")
            if cote and not any({a, b} == {passage.de, passage.vers} for a, b, _ in d.portes):
                d.portes.append((passage.de, passage.vers, cote))
        return d

    def murs(self, cle: str, disposition: Disposition, ouvertures: list[dict] | None = None) -> dict[str, str]:
        """Côté -> lettre : A est le mur de la porte par laquelle on est entré, puis B, C, D dans le sens horaire. La pièce
        de départ (on y entre par la porte du logement) : cette porte si elle est notée, sinon sa première porte vers une
        autre pièce, sinon le bas du croquis."""
        porte_du_logement = next((o["cote"] for o in ouvertures or [] if o.get("piece") == cle and o.get("type") == "porte"), None)
        entree = disposition.entrees.get(cle) or porte_du_logement or next(
            (cote if a == cle else OPPOSE[cote] for a, b, cote in disposition.portes if cle in (a, b)), "sud")
        debut = POINTS.index(entree)
        return {POINTS[(debut + k) % 4]: LETTRES[k] for k in range(4)}

    def vers_dict(self, correction: float | None = None, ouvertures: list[dict] | None = None) -> dict:
        """Pour le téléphone : pièces (case, nom, murs A à D), portes entre pièces, fenêtres et portes sur leur mur."""
        d = self.disposer(correction)
        return {
            "oriente": d.absolu,
            "courante": self.courante,
            "pieces": [{"cle": cle, "nom": p.nom, "source": p.source, "x": d.positions[cle][0], "y": d.positions[cle][1],
                        "murs": self.murs(cle, d, ouvertures)} for cle, p in self.pieces.items() if cle in d.positions],
            "portes": [{"a": a, "b": b, "cote": cote} for a, b, cote in d.portes],
            "ouvertures": [o for o in (ouvertures or []) if o.get("piece") in d.positions],
        }
