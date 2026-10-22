"""État « checklist DPE » d'une visite, tenu par NOTRE serveur (docs/02-capture-video.md § 3.6).

C'est ce module, et non l'IA, qui sait ce qui manque : il calcule les champs manquants par
priorité à partir des éléments signalés (vus à l'image ou dits) et des valeurs enregistrées.

Règles :
- une valeur n'existe que si le diagnostiqueur l'a dite : elle est toujours stockée avec sa
  citation et son horodatage (instant dans la vidéo, en secondes) ;
- une valeur redite différemment n'écrase rien : l'historique est gardé et le champ passe
  « à vérifier » (orange à l'écran de validation) ;
- les champs viennent de docs/checklist-dpe.md, réduits au périmètre de V1bis (murs, fenêtres,
  émetteurs de la pièce ; chauffage, ECS et ventilation du logement).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


class ErreurChecklist(ValueError):
    """Demande invalide (type ou champ inconnu, élément introuvable…)."""


@dataclass(frozen=True)
class Champ:
    cle: str
    libelle: str
    question: str  # complète « Pour <élément>, … »


@dataclass(frozen=True)
class TypeElement:
    cle: str
    nom: str  # nom affiché : « mur », « fenêtre »…
    prefixe: str  # préfixe des identifiants : M1, F2…
    niveau: str  # « piece » ou « logement »
    champs: tuple[Champ, ...]
    question_presence: str  # posée quand aucun élément de ce type n'est encore signalé


TYPES: dict[str, TypeElement] = {
    t.cle: t
    for t in (
        TypeElement(
            "mur", "mur", "M", "piece",
            (
                Champ("materiau", "matériau", "quel matériau ?"),
                Champ("epaisseur", "épaisseur", "quelle épaisseur ?"),
                Champ("isolation", "isolation", "il est isolé ? Par l'intérieur ou l'extérieur ?"),
                Champ("donne_sur", "donne sur", "il donne sur l'extérieur, un local non chauffé ou un local chauffé ?"),
            ),
            "Décrivez un premier mur : matériau, épaisseur, isolation, et sur quoi il donne.",
        ),
        TypeElement(
            "fenetre", "fenêtre", "F", "piece",
            (
                Champ("menuiserie", "menuiserie", "quelle menuiserie : PVC, bois ou alu ?"),
                Champ("vitrage", "vitrage", "simple, double ou triple vitrage ?"),
                Champ("volets", "volets", "quels volets, ou pas de volet ?"),
            ),
            "Y a-t-il une fenêtre dans cette pièce ?",
        ),
        TypeElement(
            "emetteur", "émetteur de chauffage", "E", "piece",
            (
                Champ("type", "type", "quel type : radiateur à eau, convecteur électrique, plancher chauffant ?"),
                Champ("temperature", "température", "basse ou haute température ?"),
                Champ("annee", "année", "quelle année d'installation, à peu près ?"),
            ),
            "Y a-t-il un radiateur ou un autre émetteur de chauffage dans cette pièce ?",
        ),
        TypeElement(
            "chauffage", "générateur de chauffage", "CH", "logement",
            (
                Champ("energie", "énergie", "quelle énergie : gaz, fioul, électricité, bois, pompe à chaleur ?"),
                Champ("type", "type", "quel type de générateur ?"),
                Champ("annee", "année", "quelle année ? Sinon, filmez la plaque de près."),
            ),
            "Où est le chauffage principal du logement ?",
        ),
        TypeElement(
            "ecs", "eau chaude sanitaire", "ECS", "logement",
            (
                Champ("systeme", "système", "quel système : chaudière, ballon électrique, thermodynamique ?"),
                Champ("energie", "énergie", "quelle énergie ?"),
                Champ("annee", "année", "quelle année ? Sinon, filmez la plaque de près."),
            ),
            "Comment est produite l'eau chaude ?",
        ),
        TypeElement(
            "ventilation", "ventilation", "V", "logement",
            (Champ("type", "type", "quel type : naturelle, VMC simple flux, hygro, double flux ?"),),
            "Quelle est la ventilation du logement ?",
        ),
    )
}

# Pièce par défaut quand un élément de pièce arrive avant qu'une pièce soit nommée.
PIECE_PAR_DEFAUT = "Pièce 1"
# Ordre des contrôles de présence dans une pièce, puis dans le logement.
PRESENCES_PIECE = ("mur", "fenetre", "emetteur")
PRESENCES_LOGEMENT = ("chauffage", "ecs", "ventilation")


def cle_texte(texte: str) -> str:
    """Forme comparable d'un texte : minuscules, sans accents ni espaces superflus."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(sans_accents.lower().split())


def horodatage(t: float) -> str:
    """Instant dans la vidéo au format m:ss."""
    t = max(0, int(round(t)))
    return f"{t // 60}:{t % 60:02d}"


@dataclass
class Valeur:
    valeur: str
    citation: str
    t: float


@dataclass
class Element:
    id: str
    type: str
    description: str
    piece: str | None  # None pour un équipement du logement
    t: float
    source: str  # « image » (signalé par l'IA) ou « voix » (cité par le diagnostiqueur)
    valeurs: dict[str, list[Valeur]] = field(default_factory=dict)
    sans_objet: dict[str, Valeur] = field(default_factory=dict)

    @property
    def type_element(self) -> TypeElement:
        return TYPES[self.type]

    def valeur(self, champ: str) -> Valeur | None:
        historique = self.valeurs.get(champ)
        return historique[-1] if historique else None

    def a_verifier(self, champ: str) -> bool:
        """Vrai si le champ a reçu plusieurs valeurs différentes (correction ou contradiction)."""
        return len({cle_texte(v.valeur) for v in self.valeurs.get(champ, [])}) > 1

    def est_rempli(self, champ: str) -> bool:
        return champ in self.sans_objet or bool(self.valeurs.get(champ))

    def champs_manquants(self) -> list[Champ]:
        return [c for c in self.type_element.champs if not self.est_rempli(c.cle)]


@dataclass
class Piece:
    nom: str
    t: float
    citation: str = ""
    absences: dict[str, Valeur] = field(default_factory=dict)  # type -> « pas de fenêtre » cité


@dataclass
class Manque:
    """Une information manquante : un champ d'un élément, ou la présence d'un type d'élément."""

    type: str
    piece: str | None
    element: Element | None = None
    champ: Champ | None = None

    @property
    def code(self) -> str:
        if self.element and self.champ:
            return f"{self.element.id}.{self.champ.cle}"
        return f"presence:{self.type}"

    @property
    def libelle(self) -> str:
        if self.element and self.champ:
            return f"{self.champ.libelle} de {self.element.description}"
        if self.type == "mur":
            return "aucun mur décrit"
        return f"{TYPES[self.type].nom} : présence à confirmer"

    @property
    def question(self) -> str:
        if self.element and self.champ:
            return f"Pour {self.element.description}, {self.champ.question}"
        return TYPES[self.type].question_presence


class Checklist:
    def __init__(self) -> None:
        self.pieces: dict[str, Piece] = {}
        self.elements: list[Element] = []
        self.piece_courante: str | None = None
        self.absences_logement: dict[str, Valeur] = {}  # type -> « pas de VMC » cité
        self._compteurs: dict[str, int] = {}

    # --- Pièces ---------------------------------------------------------------------------

    def definir_piece(self, nom: str, t: float, citation: str = "") -> Piece:
        """Change de pièce. Revenir dans une pièce déjà vue la reprend, sans doublon."""
        nom = " ".join(nom.split())
        if not nom:
            raise ErreurChecklist("nom de pièce vide")
        cle = cle_texte(nom)
        if cle not in self.pieces:
            self.pieces[cle] = Piece(nom=nom[0].upper() + nom[1:], t=t, citation=citation)
        self.piece_courante = cle
        return self.pieces[cle]

    def _piece_pour_element(self) -> str:
        if self.piece_courante is None:
            self.definir_piece(PIECE_PAR_DEFAUT, 0.0)
        return self.piece_courante  # type: ignore[return-value]

    def nom_piece(self, cle: str | None) -> str:
        return self.pieces[cle].nom if cle in self.pieces else "Logement"

    # --- Éléments -------------------------------------------------------------------------

    def _type(self, type_element: str) -> TypeElement:
        if type_element not in TYPES:
            raise ErreurChecklist(f"type d'élément inconnu : {type_element!r}")
        return TYPES[type_element]

    def trouver_element(self, element_id: str) -> Element:
        for element in self.elements:
            if element.id == element_id.strip().upper():
                return element
        raise ErreurChecklist(f"élément inconnu : {element_id!r}")

    def elements_de(self, piece: str | None) -> list[Element]:
        return [e for e in self.elements if e.piece == piece]

    def signaler_element(self, type_element: str, description: str, t: float, source: str = "image") -> Element:
        """Ajoute un élément à décrire (ex. « le mur avec la télé »). Une description déjà connue
        dans la même pièce renvoie l'élément existant."""
        te = self._type(type_element)
        description = " ".join(description.split()) or f"le {te.nom}"
        piece = self._piece_pour_element() if te.niveau == "piece" else None
        for element in self.elements_de(piece):
            if element.type == te.cle and cle_texte(element.description) == cle_texte(description):
                return element
        self._compteurs[te.prefixe] = self._compteurs.get(te.prefixe, 0) + 1
        element = Element(
            id=f"{te.prefixe}{self._compteurs[te.prefixe]}",
            type=te.cle,
            description=description,
            piece=piece,
            t=t,
            source=source,
        )
        self.elements.append(element)
        return element

    def _element_cible(self, type_element: str, element_id: str | None, description: str, t: float) -> Element:
        if element_id:
            element = self.trouver_element(element_id)
            if element.type != type_element:
                raise ErreurChecklist(f"{element.id} est un {element.type_element.nom}, pas un {TYPES[type_element].nom}")
            return element
        return self.signaler_element(type_element, description, t, source="voix")

    def _champ(self, type_element: str, champ: str) -> Champ:
        for c in self._type(type_element).champs:
            if c.cle == champ:
                return c
        raise ErreurChecklist(f"champ {champ!r} inconnu pour un {TYPES[type_element].nom}")

    def enregistrer(
        self,
        *,
        type_element: str,
        champ: str,
        valeur: str,
        citation: str,
        t: float,
        element_id: str | None = None,
        description: str = "",
    ) -> Element:
        """Enregistre une valeur dite par le diagnostiqueur. Sans citation, elle est refusée."""
        self._champ(type_element, champ)
        valeur = " ".join(valeur.split())
        citation = " ".join(citation.split())
        if not valeur:
            raise ErreurChecklist("valeur vide")
        if not citation:
            raise ErreurChecklist("valeur refusée : aucune citation du diagnostiqueur")
        element = self._element_cible(type_element, element_id, description, t)
        element.valeurs.setdefault(champ, []).append(Valeur(valeur, citation, t))
        element.sans_objet.pop(champ, None)
        return element

    def marquer_sans_objet(
        self,
        *,
        type_element: str,
        champ: str,
        citation: str,
        t: float,
        element_id: str | None = None,
        description: str = "",
    ) -> None:
        """Champ sans objet pour un élément, ou absence d'un type d'élément (champ « presence »),
        par exemple « pas de fenêtre ici ». Toujours avec citation."""
        te = self._type(type_element)
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("« sans objet » refusé : aucune citation du diagnostiqueur")
        if champ == "presence":
            if te.cle == "mur":
                raise ErreurChecklist("une pièce a toujours des murs")
            if te.niveau == "piece":
                self.pieces[self._piece_pour_element()].absences[te.cle] = Valeur("absent", citation, t)
            else:
                self.absences_logement[te.cle] = Valeur("absent", citation, t)
            return
        self._champ(te.cle, champ)
        element = self._element_cible(te.cle, element_id, description, t)
        element.sans_objet[champ] = Valeur("sans objet", citation, t)

    # --- Ce qui manque ---------------------------------------------------------------------

    def _manques_presence(self, types: tuple[str, ...], piece: str | None, absences: dict[str, Valeur]) -> list[Manque]:
        presents = {e.type for e in self.elements_de(piece)}
        return [Manque(type=t, piece=piece) for t in types if t not in presents and t not in absences]

    def manques_piece(self, piece: str | None = None) -> list[Manque]:
        """Manques d'une pièce (la pièce courante par défaut), par ordre de priorité :
        « aucun mur décrit », puis les champs des éléments déjà commencés, puis les présences."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return []
        presences = self._manques_presence(PRESENCES_PIECE, piece, self.pieces[piece].absences)
        manques = [m for m in presences if m.type == "mur"]
        for element in self.elements_de(piece):
            manques += [Manque(element.type, piece, element, c) for c in element.champs_manquants()]
        return manques + [m for m in presences if m.type != "mur"]

    def manques_logement(self) -> list[Manque]:
        manques: list[Manque] = []
        for element in self.elements_de(None):
            manques += [Manque(element.type, None, element, c) for c in element.champs_manquants()]
        return manques + self._manques_presence(PRESENCES_LOGEMENT, None, self.absences_logement)

    def manques_visite(self) -> list[Manque]:
        """Tout ce qui manque : pièce courante d'abord, puis les autres pièces, puis le logement."""
        ordre = [self.piece_courante] if self.piece_courante else []
        ordre += [cle for cle in self.pieces if cle != self.piece_courante]
        manques: list[Manque] = []
        for cle in ordre:
            manques += self.manques_piece(cle)
        return manques + self.manques_logement()

    def taux_remplissage(self, piece: str | None = None) -> float:
        """Part des informations attendues dans la pièce qui sont renseignées (0 à 1)."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return 0.0
        elements = self.elements_de(piece)
        attendus = sum(len(e.type_element.champs) for e in elements) + len(PRESENCES_PIECE)
        return round(1 - len(self.manques_piece(piece)) / attendus, 3) if attendus else 0.0

    # --- Restitution -----------------------------------------------------------------------

    def _ligne_element(self, element: Element) -> str:
        champs = []
        for c in element.type_element.champs:
            v = element.valeur(c.cle)
            if c.cle in element.sans_objet:
                champs.append(f"{c.libelle} = sans objet")
            elif v:
                note = " (à vérifier : valeurs différentes dites)" if element.a_verifier(c.cle) else ""
                champs.append(f"{c.libelle} = {v.valeur}{note}")
            else:
                champs.append(f"{c.libelle} = ?")
        origine = "vu à l'image" if element.source == "image" else "dit"
        return f"- {element.id} {element.type_element.nom} « {element.description} » ({origine}) : " + ", ".join(champs)

    def resume_pour_ia(self, max_manques: int = 12) -> str:
        """État compact envoyé à l'IA à chaque appel (le serveur reste la source de vérité)."""
        lignes: list[str] = []
        if self.piece_courante:
            piece = self.pieces[self.piece_courante]
            lignes.append(f"Pièce courante : {piece.nom} (entrée à {horodatage(piece.t)})")
            elements = self.elements_de(self.piece_courante)
            lignes.append("Éléments de la pièce :" if elements else "Éléments de la pièce : aucun signalé")
            lignes += [self._ligne_element(e) for e in elements]
            absents = ", ".join(TYPES[t].nom for t in piece.absences)
            if absents:
                lignes.append(f"Absents (dit) : {absents}")
            manques = self.manques_piece()
            codes = ", ".join(f"{m.code} ({m.libelle})" for m in manques[:max_manques])
            lignes.append(f"Manques de la pièce, par priorité : {codes or 'aucun'}")
        else:
            lignes.append("Pièce courante : pas encore nommée")
        autres = [cle for cle in self.pieces if cle != self.piece_courante]
        for cle in autres:
            manques = self.manques_piece(cle)
            detail = ", ".join(m.code for m in manques[:5]) or "rien"
            lignes.append(f"Autre pièce : {self.pieces[cle].nom} ({round(100 * self.taux_remplissage(cle))} % rempli, manque : {detail})")
        equipements = self.elements_de(None)
        lignes.append("Équipements du logement :" if equipements else "Équipements du logement : aucun signalé")
        lignes += [self._ligne_element(e) for e in equipements]
        manques = self.manques_logement()
        lignes.append("Manques du logement : " + (", ".join(f"{m.code} ({m.libelle})" for m in manques) or "aucun"))
        return "\n".join(lignes)

    def vers_dict(self) -> dict:
        def valeur(v: Valeur) -> dict:
            return {"valeur": v.valeur, "citation": v.citation, "t": round(v.t, 2)}

        def element(e: Element) -> dict:
            return {
                "id": e.id,
                "type": e.type,
                "description": e.description,
                "piece": self.nom_piece(e.piece) if e.piece else None,
                "t": round(e.t, 2),
                "source": e.source,
                "champs": {
                    c.cle: {
                        "libelle": c.libelle,
                        "valeur": valeur(e.valeur(c.cle)) if e.valeur(c.cle) else None,
                        "historique": [valeur(v) for v in e.valeurs.get(c.cle, [])],
                        "sans_objet": valeur(e.sans_objet[c.cle]) if c.cle in e.sans_objet else None,
                        "a_verifier": e.a_verifier(c.cle),
                    }
                    for c in e.type_element.champs
                },
            }

        def manque(m: Manque) -> dict:
            return {"code": m.code, "piece": self.nom_piece(m.piece) if m.piece else None, "libelle": m.libelle}

        return {
            "piece_courante": self.nom_piece(self.piece_courante) if self.piece_courante else None,
            "pieces": [
                {
                    "nom": p.nom,
                    "t": round(p.t, 2),
                    "taux_remplissage": self.taux_remplissage(cle),
                    "absences": {t: valeur(v) for t, v in p.absences.items()},
                    "elements": [element(e) for e in self.elements_de(cle)],
                    "manques": [manque(m) for m in self.manques_piece(cle)],
                }
                for cle, p in self.pieces.items()
            ],
            "logement": {
                "elements": [element(e) for e in self.elements_de(None)],
                "absences": {t: valeur(v) for t, v in self.absences_logement.items()},
                "manques": [manque(m) for m in self.manques_logement()],
            },
        }
