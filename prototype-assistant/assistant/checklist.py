"""État « checklist DPE » d'une visite, tenu par NOTRE serveur (docs/02-capture-video.md § 3.6).

C'est ce module, et non l'IA, qui sait ce qui manque : il calcule les champs manquants par
priorité à partir des éléments signalés (vus à l'image ou dits) et des valeurs enregistrées.

Règles :
- une valeur n'existe que si le diagnostiqueur l'a dite : elle est toujours stockée avec sa
  citation et son horodatage (instant dans la vidéo, en secondes) ;
- une valeur redite différemment n'écrase rien : la dernière est gardée, l'historique aussi, et la
  contradiction est signalée (au diagnostiqueur tout de suite, et « à vérifier » à l'écran de validation) ;
- les champs viennent de docs/checklist-dpe.md, réduits au périmètre du prototype ;
- seuls les champs UTILES au DPE sont réclamés (retour de Noah du 22/10/2026) :
  - « principal » : réclamé pour chaque élément (isolation, matériau, vitrage…) ;
  - « secondaire » : demandé une seule fois pour tout le logement (date du ballon), et plus du tout
    après « je ne sais pas » ;
  - « facultatif » : jamais réclamé, mais TOUJOURS noté s'il est dit (date et température des
    radiateurs, longueur d'un mur, dimensions d'une fenêtre) ;
- hypothèse (à faire valider) : une paroi qui donne sur un local chauffé n'est pas déperditive en
  3CL-2021 ; son matériau, son épaisseur et son isolation ne sont donc pas réclamés.

Groupes et exceptions (étape 4 de Noah) : rien n'est supposé identique s'il n'a pas été dit.
- un élément peut regrouper plusieurs objets identiques (« 9 radiateurs électriques ») ;
- un groupe peut être scindé (« dont une en bois », « tous sauf un ») : la partie séparée reprend les
  valeurs du groupe (origine « groupe ») et reçoit les siennes ;
- une règle (« toutes les fenêtres sont en bois, sauf celle de la chambre ») vaut pour les éléments
  déjà décrits ET ceux ajoutés plus tard (origine « règle »), avec ses exceptions par pièce ;
- une valeur dite pour un élément l'emporte sur celle reprise d'un groupe ou d'une règle, sans
  contradiction : c'est une exception.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .boussole import CAP_DU_POINT, DEMENTI, FACE_A_FACE, MEME_COTE, PERTURBATION, POINTS, Visee, ecart, oppose, point_cardinal


class ErreurChecklist(ValueError):
    """Demande invalide (type ou champ inconnu, élément introuvable…)."""


@dataclass(frozen=True)
class Champ:
    cle: str
    libelle: str
    importance: str = "principal"  # « principal », « secondaire » ou « facultatif »

    @property
    def obligatoire(self) -> bool:
        return self.importance == "principal"


@dataclass(frozen=True)
class TypeElement:
    cle: str
    nom: str  # nom affiché : « mur », « fenêtre »…
    prefixe: str  # préfixe des identifiants : M1, F2…
    niveau: str  # « piece » ou « logement »
    champs: tuple[Champ, ...]
    designation: str  # avec article, pour les descriptions par défaut : « la fenêtre »


TYPES: dict[str, TypeElement] = {
    t.cle: t
    for t in (
        # « donne sur » d'abord : sur un local chauffé, le reste de la paroi n'est pas réclamé.
        TypeElement("mur", "mur", "M", "piece", (
            Champ("donne_sur", "donne sur"),
            Champ("materiau", "matériau"),
            Champ("epaisseur", "épaisseur"),
            Champ("isolation", "isolation"),
            Champ("longueur", "longueur", "facultatif"),
        ), "le mur"),
        TypeElement("plafond", "plafond", "PL", "piece", (
            Champ("donne_sur", "donne sur"),
            Champ("isolation", "isolation"),
            Champ("structure", "structure", "facultatif"),
        ), "le plafond"),
        TypeElement("plancher", "plancher", "PB", "piece", (
            Champ("donne_sur", "donne sur"),
            Champ("isolation", "isolation"),
            Champ("structure", "structure", "facultatif"),
        ), "le plancher"),
        TypeElement("fenetre", "fenêtre", "F", "piece", (
            Champ("menuiserie", "menuiserie"),
            Champ("vitrage", "vitrage"),
            Champ("volets", "volets"),
            Champ("dimensions", "dimensions", "facultatif"),
        ), "la fenêtre"),
        TypeElement("porte", "porte extérieure", "PO", "piece", (
            Champ("type", "type"),
            Champ("donne_sur", "donne sur"),
        ), "la porte"),
        # Date et température des radiateurs : jamais demandées, toujours notées si elles sont dites (Noah, étape 4).
        TypeElement("emetteur", "émetteur de chauffage", "E", "piece", (
            Champ("type", "type"),
            Champ("temperature", "température", "facultatif"),
            Champ("annee", "année", "facultatif"),
        ), "le radiateur"),
        TypeElement("chauffage", "générateur de chauffage", "CH", "logement", (
            Champ("energie", "énergie"),
            Champ("type", "type"),
            Champ("annee", "année"),
        ), "le chauffage"),
        TypeElement("ecs", "eau chaude sanitaire", "ECS", "logement", (
            Champ("systeme", "système"),
            Champ("energie", "énergie"),
            Champ("annee", "année", "secondaire"),
        ), "l'eau chaude"),
        TypeElement("ventilation", "ventilation", "V", "logement", (
            Champ("type", "type"),
        ), "la ventilation"),
    )
}

PAROIS = ("mur", "plafond", "plancher")
ORIENTABLES = ("mur", "fenetre", "porte")  # éléments décrits par leur orientation dans LICIEL (apports solaires)
# Présent dans toute pièce, créé automatiquement : on ne demande pas s'il existe.
TOUJOURS_PRESENTS = ("plafond", "plancher")
# Présences à confirmer dans une pièce (le mur est forcément là), puis dans le logement.
PRESENCES_PIECE = ("mur", "fenetre", "emetteur")
PRESENCES_LOGEMENT = ("chauffage", "ecs", "ventilation")
# Pièce par défaut quand un élément de pièce arrive avant qu'une pièce soit nommée.
PIECE_PAR_DEFAUT = "Pièce 1"
VALEUR_INCONNUE = "inconnu"  # « je ne sais pas » : champ rempli (on n'y revient pas) mais à vérifier
# Générateurs dont l'année ne se demande pas : en effet Joule, le générateur est le radiateur lui-même.
CHAUFFAGES_SANS_ANNEE = ("electrique direct", "radiateurs electriques", "convecteurs", "panneaux rayonnants")
# Valeurs trop générales pour le DPE : notées, mais on demande une fois de préciser (« Pompe à chaleur air/eau ou
# air/air ? »). La précision qui suit n'est pas une contradiction.
A_PRECISER: dict[tuple[str, str], tuple[str, ...]] = {("chauffage", "type"): ("pompe a chaleur", "chaudiere")}

# Noms des éléments au pluriel et au singulier, pour renommer un groupe dont le nombre change
# (« les 3 fenêtres » scindé en « les 2 fenêtres » et « la fenêtre en bois »).
NOMS: list[tuple[str, str]] = [
    ("portes-fenêtres", "la porte-fenêtre"), ("baies vitrées", "la baie vitrée"), ("fenêtres", "la fenêtre"),
    ("panneaux rayonnants", "le panneau rayonnant"), ("planchers chauffants", "le plancher chauffant"),
    ("sèche-serviettes", "le sèche-serviettes"), ("radiateurs", "le radiateur"), ("convecteurs", "le convecteur"),
    ("portes", "la porte"), ("murs", "le mur"),
]


def cle_texte(texte: str) -> str:
    """Forme comparable d'un texte : minuscules, sans accents ni espaces superflus."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(sans_accents.lower().split())


def nom_groupe(singulier: str, pluriel: str, nombre: int, qualificatif: str = "", autre: bool = False) -> str:
    """« les 2 fenêtres en PVC », « la fenêtre en bois », « l'autre fenêtre », « les 2 autres radiateurs »."""
    suite = f" {qualificatif}" if qualificatif else ""
    if nombre > 1:
        return f"les {nombre} autres {pluriel}{suite}" if autre else f"les {nombre} {pluriel}{suite}"
    if autre:
        return f"l'autre {singulier.split(' ', 1)[-1]}{suite}"  # « la fenêtre » → « l'autre fenêtre »
    return f"{singulier}{suite}"


def nom_de(description: str) -> tuple[str, str] | None:
    """(pluriel, singulier) du nom qui commence la description : « le radiateur sous la fenêtre » est un radiateur,
    « les 3 fenêtres en PVC » des fenêtres."""
    for pluriel, singulier in NOMS:
        if description.startswith(singulier) or re.match(rf"les \d+ (?:autres )?{re.escape(pluriel)}\b", description):
            return pluriel, singulier
    return None


def description_auto(description: str) -> bool:
    """Nom donné par le serveur (« les 3 fenêtres », « le radiateur 2 ») et non par le diagnostiqueur ou
    l'image (« la fenêtre derrière le rideau ») : il peut être remplacé par un nom plus parlant."""
    return any(re.fullmatch(rf"les \d+ (?:autres )?{re.escape(p)}(?: n°\d+)?|{re.escape(s)}(?: \d+)?(?: n°\d+)?", description)
               for p, s in NOMS)


def recompter(description: str, nombre: int) -> str:
    """Le nom d'un groupe dont le nombre change : « les 3 fenêtres » → « les 2 fenêtres » ou « la fenêtre ».
    Seuls les noms donnés par le serveur changent ; « la fenêtre derrière le rideau » (vu à l'image) reste."""
    for pluriel, singulier in NOMS:
        if m := re.fullmatch(rf"les \d+ (autres )?{re.escape(pluriel)}(.*)", description):
            qualificatif = m.group(2).strip()
            if re.fullmatch(r"(?:\d+|n°\d+)?", qualificatif):
                qualificatif = ""  # « les 3 fenêtres n°2 » : le numéro ne sert plus
            return nom_groupe(singulier, pluriel, nombre, qualificatif, autre=bool(m.group(1)))
        if nombre > 1 and (m := re.fullmatch(rf"{re.escape(singulier)}(?: \d+)?(?: n°\d+)?((?: (?!\d).*)?)", description)):
            return nom_groupe(singulier, pluriel, nombre, m.group(1).strip())
    return description


def horodatage(t: float) -> str:
    """Instant dans la vidéo au format m:ss."""
    t = max(0, int(round(t)))
    return f"{t // 60}:{t % 60:02d}"


@dataclass
class Valeur:
    valeur: str
    citation: str
    t: float
    note: str = ""  # ex. « deviné : ictérieur → extérieur », montré à la validation
    # « dit » : dit pour cet élément ; « groupe » : reprise du groupe dont l'élément a été séparé ;
    # « regle » : vient d'une règle (« toutes les fenêtres sont en bois »).
    origine: str = "dit"


def a_preciser(type_element: str, champ: str, valeur: str) -> bool:
    return cle_texte(valeur) in A_PRECISER.get((type_element, champ), ())


def contradiction(ancienne: Valeur, nouvelle: Valeur, generale: bool = False) -> bool:
    """Deux valeurs différentes dites pour le même champ du même élément : la dernière est gardée et
    le champ est signalé. Préciser un champ resté inconnu ou trop général (`generale`), ou dire une
    exception à une valeur reprise d'un groupe ou d'une règle (« toutes en PVC » puis « celle-ci est en
    bois »), n'en est pas une."""
    if generale or VALEUR_INCONNUE in (ancienne.valeur, nouvelle.valeur) or cle_texte(ancienne.valeur) == cle_texte(nouvelle.valeur):
        return False
    if cle_texte(nouvelle.valeur).startswith(cle_texte(ancienne.valeur)):
        return False  # « isolé », puis « isolé laine de verre 30 cm » : une précision (étape 8)
    return ancienne.origine != "groupe" and not (ancienne.origine == "regle" and nouvelle.origine == "dit")


@dataclass
class Element:
    id: str
    type: str
    description: str
    piece: str | None  # None pour un équipement du logement
    t: float
    source: str  # « image » (signalé par l'IA), « voix » (cité par le diagnostiqueur), « auto » (plafond, plancher)
    nombre: int = 1  # éléments identiques décrits ensemble : « trois fenêtres en bois »
    valeurs: dict[str, list[Valeur]] = field(default_factory=dict)
    sans_objet: dict[str, Valeur] = field(default_factory=dict)
    parent: str = ""  # « dont une en bois » : le groupe dont cet élément a été séparé
    # Pour le nommer à l'oral (étape 5) : jamais « le mur 3 », mais ce qui a été dit ou vu de lui.
    repere: str = ""  # repère dit : « avec la télé », « du fond », « de gauche »
    support: str = ""  # fenêtre ou porte : le mur qui la porte (« il y a 3 fenêtres dessus »)
    image: str = ""  # vignette montrée à l'écran avec les questions sur cet élément
    # Orientation (étape 6, voir boussole.py) : utile au DPE (apports solaires), et pour nommer le mur.
    cap: float | None = None  # cap brut de la caméra quand il a été filmé (boussole), en degrés
    lacet: float | None = None  # lacet du gyroscope au même moment (angles entre murs)
    orientation: str = ""  # « nord », « est », « sud » ou « ouest »
    orientation_source: str = ""  # « boussole », « déduit », « dit » ou « mur » (fenêtre : celle de son mur)
    orientation_note: str = ""  # preuve montrée à la validation : « cap 352° », « dit : non, c'est le mur ouest »

    @property
    def type_element(self) -> TypeElement:
        return TYPES[self.type]

    def valeur(self, champ: str) -> Valeur | None:
        historique = self.valeurs.get(champ)
        return historique[-1] if historique else None

    def a_verifier(self, champ: str) -> bool:
        """Vrai si le champ a reçu des valeurs contradictoires (la dernière est gardée), ou si le
        diagnostiqueur a dit ne pas savoir."""
        historique = self.valeurs.get(champ, [])
        if not historique:
            return False
        return historique[-1].valeur == VALEUR_INCONNUE or any(
            contradiction(a, b, a_preciser(self.type, champ, a.valeur)) for a, b in zip(historique, historique[1:]))

    def est_rempli(self, champ: str) -> bool:
        """Champ dit (ou sans objet). Une valeur trop générale (« pompe à chaleur ») reste à préciser."""
        v = self.valeur(champ)
        return champ in self.sans_objet or (v is not None and not a_preciser(self.type, champ, v.valeur))

    @property
    def sur_local_chauffe(self) -> bool:
        """Paroi qui donne sur un local chauffé (hypothèse : non déperditive en 3CL-2021)."""
        v = self.valeur("donne_sur")
        return self.type in PAROIS and v is not None and cle_texte(v.valeur).startswith("local chauffe")

    def est_utile(self, champ: str) -> bool:
        """Faut-il connaître ce champ pour le DPE, vu ce qu'on sait déjà de l'élément ?"""
        if self.sur_local_chauffe and champ != "donne_sur":
            return False
        if self.type == "emetteur" and champ == "temperature":
            # Basse / haute température : n'a de sens que pour des émetteurs à eau.
            type_dit = self.valeur("type")
            return type_dit is not None and any(m in cle_texte(type_dit.valeur) for m in ("eau", "plancher chauffant"))
        if self.type == "ecs" and champ == "annee":
            # Date d'un ballon ; une eau chaude faite par la chaudière a la date de la chaudière.
            systeme = self.valeur("systeme")
            return systeme is not None and "chaudiere" not in cle_texte(systeme.valeur)
        if self.type == "chauffage" and champ == "annee":
            # Radiateurs électriques (effet Joule) : le générateur est le radiateur, dont la date ne se demande pas.
            type_dit = self.valeur("type")
            return type_dit is None or not any(m in cle_texte(type_dit.valeur) for m in CHAUFFAGES_SANS_ANNEE)
        return True

    def champs_manquants(self) -> list[Champ]:
        """Champs principaux encore à demander pour cet élément, dans l'ordre."""
        return [c for c in self.type_element.champs if c.obligatoire and self.est_utile(c.cle) and not self.est_rempli(c.cle)]

    def champs_secondaires_manquants(self) -> list[Champ]:
        return [c for c in self.type_element.champs if c.importance == "secondaire" and self.est_utile(c.cle) and not self.est_rempli(c.cle)]


@dataclass
class Piece:
    nom: str
    t: float
    citation: str = ""
    absences: dict[str, Valeur] = field(default_factory=dict)  # type -> « pas de fenêtre » cité
    clos: dict[str, Valeur] = field(default_factory=dict)  # type -> « pas d'autre mur » cité
    nombre_murs: Valeur | None = None  # « cette pièce fait 4 murs »


@dataclass
class Regle:
    """« Toutes les fenêtres sont en bois, sauf celle de la chambre qui est en PVC » : vaut pour les
    éléments de ce type déjà décrits et pour ceux ajoutés ensuite ; une pièce exceptée reçoit ses
    propres valeurs si elles ont été dites, sinon rien (on demandera)."""

    type: str
    valeurs: dict[str, str]
    citation: str
    t: float
    piece: str | None = None  # None : tout le logement ; sinon cette pièce seulement
    exceptions: dict[str, dict[str, str]] = field(default_factory=dict)  # pièce (clé texte) -> valeurs propres

    def concerne(self, element: Element) -> bool:
        return element.type == self.type and (self.piece is None or element.piece == self.piece)

    def valeurs_pour(self, element: Element) -> tuple[dict[str, str], str]:
        """(valeurs, note) applicables à cet élément."""
        for piece, valeurs in self.exceptions.items():
            if element.piece and (element.piece == piece or element.piece.startswith(piece + " ")):
                return valeurs, "exception à la règle du logement"
        return self.valeurs, "règle du logement" if self.piece is None else "règle de la pièce"


@dataclass
class Signalement:
    """Contradiction relevée : la dernière valeur dite est gardée, l'ancienne reste dans l'historique.
    Dite au diagnostiqueur tout de suite (« Je remplace brique. ») et montrée à la validation. Étape 9 : sans répéter la
    valeur qu'il vient de dire, seulement celle qui est remplacée."""

    element_id: str
    champ: str  # ou « nombre », « orientation »
    ancienne: str
    nouvelle: str
    citation: str
    t: float
    message: str = ""  # texte à dire, s'il n'est pas « Je remplace … »

    @property
    def texte(self) -> str:
        if self.message:
            return self.message
        if self.champ == "nombre":
            return f"Je corrige : il y en avait {self.ancienne}."
        return f"Je remplace {self.ancienne}."


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
            return f"{self.element.description} : {self.champ.libelle}"
        if self.type == "mur":
            return "aucun mur décrit"
        return f"{TYPES[self.type].nom} : présence à confirmer"


class Checklist:
    def __init__(self) -> None:
        self.pieces: dict[str, Piece] = {}
        self.elements: list[Element] = []
        self.piece_courante: str | None = None
        self.absences_logement: dict[str, Valeur] = {}  # type -> « pas de VMC » cité
        self.regles: list[Regle] = []
        self.signalements: list[Signalement] = []
        self.dernier: dict[str, str] = {}  # type -> dernier élément dont le diagnostiqueur a parlé (« ce mur »)
        # Boussole (étape 6) : « cap vrai = lacet du gyroscope + correction », pour toute la visite.
        self.correction_cap: float | None = None
        self.correction_source = ""  # « boussole », ou « dit (M1) » : orientation d'un mur dite à l'oral
        self.boussole_fiabilite = "inconnue"  # « bonne », « moyenne », « faible », « absente » ou « inconnue » (rien reçu)
        self.boussole_gyroscope = False  # le téléphone donne les angles entre murs
        self.boussole_dementie = False  # une orientation dite contredit la boussole : elle est faussée ici
        self._compteurs: dict[str, int] = {}

    # --- Pièces ---------------------------------------------------------------------------

    def _creer_piece(self, nom: str, t: float, citation: str = "") -> str:
        """Clé de la pièce, créée si besoin avec son plafond et son plancher (toujours présents)."""
        nom = " ".join(nom.split())
        if not nom:
            raise ErreurChecklist("nom de pièce vide")
        cle = cle_texte(nom)
        if cle not in self.pieces:
            self.pieces[cle] = Piece(nom=nom[0].upper() + nom[1:], t=t, citation=citation)
            for type_element in TOUJOURS_PRESENTS:
                self.signaler_element(type_element, TYPES[type_element].designation, t, source="auto", piece=cle)
        return cle

    def definir_piece(self, nom: str, t: float, citation: str = "") -> Piece:
        """Change de pièce. Revenir dans une pièce déjà vue la reprend, sans doublon."""
        self.piece_courante = self._creer_piece(nom, t, citation)
        return self.pieces[self.piece_courante]

    def trouver_piece(self, nom: str) -> str | None:
        """« la chambre » → « chambre », ou « chambre 1 » si c'est la seule chambre ; None si inconnue ou ambiguë."""
        cle = cle_texte(nom)
        if cle in self.pieces:
            return cle
        proches = [p for p in self.pieces if p.startswith(cle + " ")]
        return proches[0] if len(proches) == 1 else None

    def piece_pour(self, nom: str, t: float) -> str:
        """« Dans la cuisine, il y a aussi un radiateur » : la pièce nommée, créée si besoin, sans y entrer."""
        return self.trouver_piece(nom) or self._creer_piece(nom, t)

    def _piece_pour_element(self) -> str:
        if self.piece_courante is None:
            self.definir_piece(PIECE_PAR_DEFAUT, 0.0)
        return self.piece_courante  # type: ignore[return-value]

    def nom_piece(self, cle: str | None) -> str:
        return self.pieces[cle].nom if cle in self.pieces else "Logement"

    def cloturer(self, type_element: str, citation: str, t: float) -> None:
        """« Pas d'autre mur » : la liste de ce type est complète dans la pièce courante."""
        self._type(type_element)
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("clôture refusée : aucune citation du diagnostiqueur")
        self.pieces[self._piece_pour_element()].clos[type_element] = Valeur("complet", citation, t)

    def compter_murs(self, nombre: int, citation: str, t: float) -> None:
        """« Cette pièce fait 4 murs » : une fois ce nombre de murs décrits, on ne demande plus s'il y en a d'autres."""
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("nombre de murs refusé : aucune citation du diagnostiqueur")
        if not isinstance(nombre, int) or not 3 <= nombre <= 12:
            raise ErreurChecklist(f"nombre de murs invraisemblable : {nombre!r}")
        self.pieces[self._piece_pour_element()].nombre_murs = Valeur(str(nombre), citation, t)

    def murs_complets(self, piece: str | None = None) -> bool:
        """Tous les murs de la pièce sont annoncés : « pas d'autre mur », ou le nombre dit est atteint."""
        cle = piece or self.piece_courante
        if cle not in self.pieces:
            return False
        p = self.pieces[cle]
        n = sum(e.nombre for e in self.elements_de(cle) if e.type == "mur")
        return "mur" in p.clos or (p.nombre_murs is not None and n >= int(p.nombre_murs.valeur))

    def nom(self, element: Element, demonstratif: bool = True) -> str:
        """Nom à dire à l'oral : « ce mur » (on vient d'en parler), « le mur côté voisin », jamais « le mur 3 »
        (voir noms.py). `demonstratif=False` : jamais « ce mur » (pour l'écran et pour Claude)."""
        from .noms import nom_parlant

        voisins = [e for e in self.elements_de(element.piece) if e.type == element.type]
        fenetres = [e for e in self.elements_de(element.piece) if e.type in ("fenetre", "porte")]
        courant = demonstratif and self.dernier.get(element.type) == element.id and element.piece == self.piece_courante
        return nom_parlant(element, voisins, fenetres, courant)

    def copier(self, type_element: str, piece_source: str, citation: str, t: float) -> Element:
        """« Plafond pareil que le séjour » : recopie les valeurs de l'élément de l'autre pièce."""
        source = next((e for e in self.elements_de(piece_source) if e.type == type_element), None)
        if source is None or not source.valeurs:
            raise ErreurChecklist(f"rien à recopier : pas de {TYPES[type_element].nom} décrit dans {self.nom_piece(piece_source)}")
        cible = next((e for e in self.elements_de(self._piece_pour_element()) if e.type == type_element), None)
        if cible is None:
            cible = self.signaler_element(type_element, TYPES[type_element].designation, t, source="voix")
        for champ, historique in source.valeurs.items():
            note = f"pareil que {self.nom_piece(piece_source)}"
            self.enregistrer(type_element=type_element, champ=champ, valeur=historique[-1].valeur, citation=citation, t=t,
                             element_id=cible.id, note=note)
        return cible

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

    def element_de_piece(self, type_element: str, piece: str | None = None) -> Element | None:
        """Le (dernier) élément de ce type dans la pièce, par exemple son plafond."""
        piece = piece if piece is not None else self.piece_courante
        return next((e for e in reversed(self.elements_de(piece)) if e.type == type_element), None)

    @staticmethod
    def _verifier_nombre(nombre: int | None) -> int | None:
        if nombre is None:
            return None
        if not isinstance(nombre, int) or not 1 <= nombre <= 50:
            raise ErreurChecklist(f"nombre d'éléments invalide : {nombre!r}")
        return nombre

    def _nouvel_id(self, te: TypeElement) -> str:
        self._compteurs[te.prefixe] = self._compteurs.get(te.prefixe, 0) + 1
        return f"{te.prefixe}{self._compteurs[te.prefixe]}"

    def _fixer_nombre(self, element: Element, nombre: int, description: str = "") -> None:
        if nombre != element.nombre or description:
            element.description = description or recompter(element.description, nombre)
            element.nombre = nombre

    def signaler_element(self, type_element: str, description: str, t: float, source: str = "image", nombre: int | None = None,
                         piece: str | None = None, repere: str = "", support: str = "") -> Element:
        """Ajoute un élément à décrire (ex. « le mur avec la télé »), éventuellement en plusieurs
        exemplaires identiques (« trois fenêtres »), dans la pièce courante ou dans `piece` (clé).
        Une description déjà connue dans la même pièce renvoie l'élément existant ; le plafond et le
        plancher sont uniques dans une pièce. Un élément nouveau reçoit les règles du logement.
        `repere` : ce qui a été dit pour le reconnaître (« avec la télé ») ; `support` : pour une
        fenêtre, le mur qui la porte (identifiant ou nom)."""
        te = self._type(type_element)
        nombre = self._verifier_nombre(nombre)
        description = " ".join(description.split()) or te.designation
        if te.niveau == "piece":
            piece = piece if piece in self.pieces else self._piece_pour_element()
        else:
            piece = None
        element = next((e for e in self.elements_de(piece) if e.type == te.cle and (
            te.cle in TOUJOURS_PRESENTS or cle_texte(e.description) == cle_texte(description))), None)
        if element is not None:
            if nombre:
                self._fixer_nombre(element, nombre)
        else:
            element = Element(id=self._nouvel_id(te), type=te.cle, description=description, piece=piece, t=t, source=source,
                              nombre=nombre or 1)
            self.elements.append(element)
            for regle in self.regles:
                if regle.concerne(element):
                    self._appliquer_regle(regle, element)
        if repere and not element.repere:
            element.repere = " ".join(repere.split())
        if support and te.cle in ("fenetre", "porte"):
            mur = next((e for e in self.elements_de(piece) if e.type == "mur" and support in (e.id, e.description)), None)
            element.support = mur.id if mur else element.support
        if source == "voix":
            self.dernier[te.cle] = element.id
        return element

    def retirer(self, element_id: str) -> None:
        """Élément créé à tort (par les règles du serveur, corrigées par Claude) : il disparaît."""
        element = self.trouver_element(element_id)
        self.elements.remove(element)
        for autre in self.elements:
            if autre.support == element.id:
                autre.support = ""
        if self.dernier.get(element.type) == element.id:
            del self.dernier[element.type]

    def fusionner(self, element_id: str, meme_que: str) -> Element:
        """« C'est le même mur que le mur côté couloir ? » « Oui. » : le diagnostiqueur confirme un doublon (étape 9 ;
        jamais sans sa confirmation). Ce qui n'était dit que du doublon passe à l'élément gardé, puis le doublon
        disparaît."""
        doublon, garde = self.trouver_element(element_id), self.trouver_element(meme_que)
        if doublon is garde or doublon.type != garde.type:
            raise ErreurChecklist("fusion impossible : éléments identiques ou de types différents")
        for champ, historique in doublon.valeurs.items():
            if not garde.est_rempli(champ):
                garde.valeurs[champ] = list(historique)
        garde.repere = garde.repere or doublon.repere
        garde.image = garde.image or doublon.image
        if garde.cap is None and garde.lacet is None:
            garde.cap, garde.lacet = doublon.cap, doublon.lacet
        for autre in self.elements:
            if autre.support == doublon.id:
                autre.support = garde.id
        self.retirer(doublon.id)
        self.dernier[garde.type] = garde.id
        return garde

    def completer(self, element_id: str, repere: str = "", support: str = "") -> Element:
        """Ajoute à un élément connu ce qui permet de le reconnaître : un repère dit, le mur qui porte une fenêtre."""
        element = self.trouver_element(element_id)
        if repere and not element.repere:
            element.repere = " ".join(repere.split())
        if support and element.type in ("fenetre", "porte") and not element.support:
            mur = next((e for e in self.elements_de(element.piece) if e.type == "mur" and support in (e.id, e.description)), None)
            element.support = mur.id if mur else ""
        return element

    def _element_cible(self, type_element: str, element_id: str | None, description: str, t: float, nombre: int | None = None,
                       piece: str | None = None) -> Element:
        if element_id:
            element = self.trouver_element(element_id)
            if element.type != type_element:
                raise ErreurChecklist(f"{element.id} est un {element.type_element.nom}, pas un {TYPES[type_element].nom}")
            if self._verifier_nombre(nombre):
                self._fixer_nombre(element, nombre)
            return element
        return self.signaler_element(type_element, description, t, source="voix", nombre=nombre, piece=piece)

    def scinder(self, element_id: str, nombre: int, description: str, t: float, citation: str,
                valeurs: dict[str, str] | None = None) -> Element:
        """« Dont une en bois », « tous sauf un » : sépare `nombre` objets d'un groupe. La partie séparée
        reprend les valeurs du groupe (origine « groupe ») puis reçoit les siennes (`valeurs`, dites).
        Le nombre restant dans le groupe est fixé ensuite par `changer_nombre`."""
        source = self.trouver_element(element_id)
        nombre = self._verifier_nombre(nombre) or 1
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("séparation refusée : aucune citation du diagnostiqueur")
        for champ in valeurs or {}:
            self._champ(source.type, champ)
        description = " ".join(description.split()) or source.type_element.designation
        if any(cle_texte(e.description) == cle_texte(description) for e in self.elements_de(source.piece)):
            description += f" n°{sum(e.type == source.type for e in self.elements) + 1}"
        element = Element(id=self._nouvel_id(source.type_element), type=source.type, description=description, piece=source.piece,
                          t=t, source="voix", nombre=nombre, parent=source.id, sans_objet=dict(source.sans_objet))
        for champ, historique in source.valeurs.items():
            derniere = historique[-1]
            element.valeurs[champ] = [Valeur(derniere.valeur, derniere.citation, derniere.t, f"comme {source.description}", "groupe")]
        # Juste après son groupe : les questions sur la partie séparée viennent à la suite.
        self.elements.insert(self.elements.index(source) + 1, element)
        for champ, valeur in (valeurs or {}).items():
            self.enregistrer(type_element=source.type, champ=champ, valeur=valeur, citation=citation, t=t, element_id=element.id)
        return element

    def changer_nombre(self, element_id: str, nombre: int, citation: str, t: float, description: str = "",
                       correction: bool = False) -> Element:
        """Nouveau nombre d'un groupe (et son nom, s'il a été donné par le serveur). `correction` :
        le diagnostiqueur corrige un nombre déjà dit (« en fait il y en a 3, pas 2 ») : c'est signalé."""
        element = self.trouver_element(element_id)
        nombre = self._verifier_nombre(nombre) or 1
        if not " ".join(citation.split()):
            raise ErreurChecklist("nombre refusé : aucune citation du diagnostiqueur")
        if correction and nombre != element.nombre:
            nom = (nom_de(element.description) or (element.type_element.nom + "s",))[0]
            self.signalements.append(Signalement(element.id, "nombre", str(element.nombre), f"{nombre} {nom}", citation, t))
        self._fixer_nombre(element, nombre, description)
        return element

    # --- Règles du logement -------------------------------------------------------------------

    def ajouter_regle(self, type_element: str, valeurs: dict[str, str], citation: str, t: float, piece: str | None = None,
                      exceptions: dict[str, dict[str, str]] | None = None) -> Regle:
        """« Toutes les fenêtres sont en bois, sauf celle de la chambre qui est en PVC » : appliquée tout de
        suite aux éléments déjà décrits, puis à chaque élément ajouté. `piece` : la règle ne vaut que pour
        cette pièce (« tous les radiateurs de la pièce »)."""
        te = self._type(type_element)
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("règle refusée : aucune citation du diagnostiqueur")
        exceptions = {cle_texte(p): dict(v) for p, v in (exceptions or {}).items()}
        for champ in [*valeurs, *(c for v in exceptions.values() for c in v)]:
            self._champ(te.cle, champ)
        if not valeurs and not exceptions:
            raise ErreurChecklist("règle vide")
        regle = Regle(te.cle, dict(valeurs), citation, t, piece, exceptions)
        self.regles.append(regle)
        for element in [e for e in self.elements if regle.concerne(e)]:
            self._appliquer_regle(regle, element)
        return regle

    def ajouter_exception(self, type_element: str, piece: str, valeurs: dict[str, str], citation: str, t: float) -> Regle | None:
        """« Sauf celle de la chambre, qui est en PVC », dit après coup : complète la dernière règle de ce type."""
        regle = next((r for r in reversed(self.regles) if r.type == type_element and r.piece is None), None)
        if regle is None:
            return None
        cle = cle_texte(piece)
        regle.exceptions[cle] = {**regle.exceptions.get(cle, {}), **valeurs}
        for element in [e for e in self.elements if regle.concerne(e) and e.piece and (e.piece == cle or e.piece.startswith(cle + " "))]:
            for champ in regle.valeurs:
                # La valeur de la règle ne vaut plus pour cette pièce : on la retire (on demandera si rien n'est dit).
                historique = element.valeurs.get(champ, [])
                if historique and historique[-1].origine == "regle" and historique[-1].citation == regle.citation:
                    historique.pop()
                    if not historique:
                        del element.valeurs[champ]
            for champ, valeur in valeurs.items():
                self.enregistrer(type_element=element.type, champ=champ, valeur=valeur, citation=citation, t=t, element_id=element.id,
                                 note="exception à la règle du logement")
        return regle

    # --- Orientation des murs et des fenêtres (boussole, étape 6) ---------------------------------

    def mesurer(self, element_id: str, visee: Visee) -> Element:
        """La caméra visait cet élément quand il a été décrit (boussole et gyroscope du téléphone)."""
        element = self.trouver_element(element_id)
        if element.type in ORIENTABLES and visee.stable:
            element.cap, element.lacet = visee.cap, visee.lacet
            self._deduire_orientations()
            self._verifier_coherence(element)
        return element

    def regler_boussole(self, correction: float | None, fiabilite: str, gyroscope: bool) -> None:
        """État de la boussole estimé sur la visite. Une orientation dite à l'oral l'emporte sur la boussole."""
        self.boussole_fiabilite = "faible" if self.boussole_dementie and fiabilite != "absente" else fiabilite
        self.boussole_gyroscope = gyroscope
        if correction is None or self.correction_source.startswith("dit"):
            return
        if self.correction_cap is None or abs(ecart(correction, self.correction_cap)) > 10:
            self.correction_cap, self.correction_source = correction % 360, "boussole"
            self._deduire_orientations()

    def orienter(self, element_id: str, point: str, citation: str, t: float) -> Element:
        """« Non, c'est le mur ouest » : orientation dite (elle l'emporte sur la boussole). Si le gyroscope a donné
        le lacet de ce mur, elle fixe la correction de toute la visite : les autres murs s'en déduisent."""
        element = self.trouver_element(element_id)
        point = cle_texte(point)
        if point not in POINTS or element.type not in ORIENTABLES:
            raise ErreurChecklist(f"orientation invalide : {point!r} pour {element.id}")
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("orientation refusée : aucune citation du diagnostiqueur")
        avant = element.orientation if element.orientation_source not in ("", "dit") else ""
        if element.orientation_source == "dit" and element.orientation != point:  # deux orientations dites : la dernière compte
            self.signalements.append(Signalement(element.id, "orientation", element.orientation, point, citation, t))
        if element.cap is not None and abs(ecart(element.cap, CAP_DU_POINT[point])) > DEMENTI:
            self.boussole_dementie, self.boussole_fiabilite = True, "faible"  # la boussole se trompe : on ne s'y fie plus
        element.orientation, element.orientation_source = point, "dit"
        element.orientation_note = f"dit : « {citation} »" + (f" (la boussole donnait {avant})" if avant and avant != point else "")
        if element.lacet is not None:
            self.correction_cap, self.correction_source = ecart(CAP_DU_POINT[point], element.lacet) % 360, f"dit ({element.id})"
        self._deduire_orientations()
        self._verifier_coherence(element)
        return element

    def _orientation_auto(self, element: Element) -> tuple[str, str, str]:
        """(point, source, note) d'un élément dont l'orientation n'a pas été dite."""
        if element.type in ("fenetre", "porte") and element.support:
            mur = next((e for e in self.elements if e.id == element.support), None)
            if mur is not None and mur.orientation:
                return mur.orientation, "mur", f"comme {self.nom(mur, demonstratif=False)}"
        if element.lacet is not None and self.correction_cap is not None:
            cap = (element.lacet + self.correction_cap) % 360
            if self.correction_source == "boussole":
                source, note = "boussole", f"cap {cap:.0f}°"
            else:
                reference = next((e for e in self.elements if f"({e.id})" in self.correction_source), None)
                nom = self.nom(reference, demonstratif=False) if reference is not None else "un autre mur"
                source, note = "déduit", f"cap {cap:.0f}°, déduit de l'orientation dite pour {nom}"
            if element.cap is not None and abs(ecart(element.cap, cap)) > PERTURBATION:
                note += f" ; boussole perturbée ici ({point_cardinal(element.cap)} mesuré)"
            return point_cardinal(cap), source, note
        if element.cap is not None and self.boussole_fiabilite in ("bonne", "moyenne"):
            return point_cardinal(element.cap), "boussole", f"cap {element.cap:.0f}° (boussole {self.boussole_fiabilite})"
        return "", "", ""

    def _deduire_orientations(self) -> None:
        # Les murs d'abord : une fenêtre prend l'orientation du mur qui la porte.
        for element in sorted((e for e in self.elements if e.type in ORIENTABLES), key=lambda e: e.type != "mur"):
            if element.orientation_source != "dit":
                element.orientation, element.orientation_source, element.orientation_note = self._orientation_auto(element)

    def _verifier_coherence(self, element: Element) -> None:
        """Deux murs face à face (lacets à ~180°) sont opposés (nord ↔ sud) ; deux murs visés dans la même direction
        ont la même orientation. Sinon (orientations dites ou boussole perturbée), c'est signalé."""
        if element.type != "mur" or element.lacet is None or not element.orientation:
            return
        for autre in self.elements_de(element.piece):
            if autre is element or autre.type != "mur" or autre.lacet is None or not autre.orientation:
                continue
            angle = abs(ecart(element.lacet, autre.lacet))
            attendu = oppose(autre.orientation) if angle >= FACE_A_FACE else autre.orientation if angle <= MEME_COTE else None
            if attendu is not None and element.orientation != attendu:
                relation = "face à face" if angle >= FACE_A_FACE else "du même côté"
                message = (f"Attention : {self.nom(element, demonstratif=False)} et {self.nom(autre, demonstratif=False)} sont "
                           f"{relation}, l'orientation de l'un des deux est fausse.")
                if not any(s.message == message for s in self.signalements):
                    self.signalements.append(Signalement(element.id, "orientation", autre.orientation, element.orientation,
                                                         element.orientation_note, 0.0, message))

    def orientation_a_demander(self, piece: str | None = None) -> Element | None:
        """Boussole absente ou peu fiable, et aucune orientation dite : le mur extérieur filmé dont il faut demander
        l'orientation, une seule fois (avec le gyroscope, les autres murs s'en déduisent)."""
        if self.correction_cap is not None or self.boussole_fiabilite in ("bonne", "moyenne", "inconnue"):
            return None
        murs = [e for e in self.elements_de(piece or self.piece_courante) if e.type == "mur" and not e.orientation
                and (v := e.valeur("donne_sur")) is not None and cle_texte(v.valeur) == "exterieur"]
        dernier = self.dernier.get("mur")
        return next((m for m in murs if m.id == dernier), murs[-1] if murs else None)

    def _appliquer_regle(self, regle: Regle, element: Element) -> None:
        valeurs, note = regle.valeurs_pour(element)
        for champ, valeur in valeurs.items():
            self.enregistrer(type_element=element.type, champ=champ, valeur=valeur, citation=regle.citation, t=regle.t,
                             element_id=element.id, note=note, origine="regle")

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
        nombre: int | None = None,
        note: str = "",
        piece: str | None = None,
        origine: str = "dit",
    ) -> Element:
        """Enregistre une valeur dite par le diagnostiqueur. Sans citation, elle est refusée.
        La même valeur redite n'est pas ajoutée une 2e fois à l'historique (si elle venait d'un
        groupe ou d'une règle, elle devient « dite » pour cet élément). Une valeur différente est
        gardée comme la bonne ; si elle contredit une valeur dite, c'est signalé."""
        self._champ(type_element, champ)
        valeur = " ".join(valeur.split())
        citation = " ".join(citation.split())
        if not valeur:
            raise ErreurChecklist("valeur vide")
        if not citation:
            raise ErreurChecklist("valeur refusée : aucune citation du diagnostiqueur")
        element = self._element_cible(type_element, element_id, description, t, nombre, piece)
        nouvelle = Valeur(valeur, citation, t, note, origine)
        derniere = element.valeur(champ)
        if derniere is None or cle_texte(derniere.valeur) != cle_texte(valeur):
            element.valeurs.setdefault(champ, []).append(nouvelle)
            if derniere is not None and contradiction(derniere, nouvelle, a_preciser(element.type, champ, derniere.valeur)):
                self.signalements.append(Signalement(element.id, champ, derniere.valeur, valeur, citation, t))
        elif derniere.origine != "dit" and origine == "dit":
            element.valeurs[champ][-1] = nouvelle
        element.sans_objet.pop(champ, None)
        if origine == "dit":
            self.dernier[element.type] = element.id
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
            if te.cle == "mur" or te.cle in TOUJOURS_PRESENTS:
                raise ErreurChecklist(f"une pièce a toujours un {te.nom}")
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
        """Manques principaux d'une pièce (la pièce courante par défaut), dans l'ordre du parcours :
        murs, plafond, plancher, fenêtres et portes, émetteurs."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return []
        presences = {m.type: m for m in self._manques_presence(PRESENCES_PIECE, piece, self.pieces[piece].absences)}
        manques: list[Manque] = []
        for type_element in ("mur", "plafond", "plancher", "fenetre", "porte", "emetteur"):
            if type_element in presences:
                manques.append(presences[type_element])
            for element in self.elements_de(piece):
                if element.type == type_element:
                    manques += [Manque(element.type, piece, element, c) for c in element.champs_manquants()]
        return manques

    def manques_logement(self) -> list[Manque]:
        manques: list[Manque] = []
        for type_element in PRESENCES_LOGEMENT:
            elements = [e for e in self.elements_de(None) if e.type == type_element]
            if not elements and type_element not in self.absences_logement:
                manques.append(Manque(type=type_element, piece=None))
            for element in elements:
                manques += [Manque(element.type, None, element, c) for c in element.champs_manquants()]
        return manques

    def manques_secondaires(self) -> dict[tuple[str, str], list[Element]]:
        """Détails secondaires manquants, regroupés pour être demandés une seule fois pour le
        logement : (type, champ) -> éléments concernés."""
        groupes: dict[tuple[str, str], list[Element]] = {}
        for element in self.elements:
            for champ in element.champs_secondaires_manquants():
                groupes.setdefault((element.type, champ.cle), []).append(element)
        return groupes

    def manques_visite(self) -> list[Manque]:
        """Tout ce qui manque : pièce courante d'abord, puis les autres pièces, puis le logement."""
        ordre = [self.piece_courante] if self.piece_courante else []
        ordre += [cle for cle in self.pieces if cle != self.piece_courante]
        manques: list[Manque] = []
        for cle in ordre:
            manques += self.manques_piece(cle)
        return manques + self.manques_logement()

    def piece_terminee(self, piece: str | None = None) -> bool:
        piece = piece if piece is not None else self.piece_courante
        return piece in self.pieces and not self.manques_piece(piece)

    def taux_remplissage(self, piece: str | None = None) -> float:
        """Part des informations utiles attendues dans la pièce qui sont renseignées (0 à 1)."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return 0.0
        attendus = len(PRESENCES_PIECE)
        for e in self.elements_de(piece):
            attendus += sum(c.obligatoire and e.est_utile(c.cle) for c in e.type_element.champs)
        return round(1 - len(self.manques_piece(piece)) / attendus, 3) if attendus else 0.0

    # --- Restitution -----------------------------------------------------------------------

    def _ligne_element(self, element: Element) -> str:
        champs = []
        for c in element.type_element.champs:
            v = element.valeur(c.cle)
            if c.cle in element.sans_objet:
                champs.append(f"{c.libelle} = sans objet")
            elif v:
                note = " (déjà demandé, à vérifier plus tard : ne pas redemander)" if element.a_verifier(c.cle) else ""
                note += {"groupe": " (comme son groupe)", "regle": " (règle du logement)"}.get(v.origine, "")
                note += " (à préciser)" if a_preciser(element.type, c.cle, v.valeur) else ""
                champs.append(f"{c.libelle} = {v.valeur}{note}")
            elif not element.est_utile(c.cle):
                champs.append(f"{c.libelle} = inutile pour le DPE")
            elif c.importance == "principal":
                champs.append(f"{c.libelle} = ?")
            elif c.importance == "secondaire":
                champs.append(f"{c.libelle} = ? (secondaire)")
        origine = {"image": "vu à l'image", "auto": "toujours présent"}.get(element.source, "dit")
        if element.parent:
            origine += f", séparé de {element.parent}"
        if element.support:
            origine += f", sur {element.support}"
        if element.orientation:
            origine += f", orienté {element.orientation} ({element.orientation_source})"
        nombre = f" ×{element.nombre}" if element.nombre > 1 else ""
        return f"- {element.id} {element.type_element.nom}{nombre} « {self.nom(element, demonstratif=False)} » ({origine}) : " + ", ".join(champs)

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
            clos = ", ".join(TYPES[t].nom + "s" for t in piece.clos)
            if clos:
                lignes.append(f"Listes complètes (dit) : {clos}")
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
            # En détail : « tu as noté quoi pour la cuisine ? » (étape 7, conversation libre).
            lignes += ["  " + self._ligne_element(e) for e in self.elements_de(cle) if e.valeurs or e.type not in TOUJOURS_PRESENTS]
        equipements = self.elements_de(None)
        lignes.append("Équipements du logement :" if equipements else "Équipements du logement : aucun signalé")
        lignes += [self._ligne_element(e) for e in equipements]
        manques = self.manques_logement()
        lignes.append("Manques du logement : " + (", ".join(f"{m.code} ({m.libelle})" for m in manques) or "aucun"))
        for regle in self.regles:
            lignes.append(f"Règle dite : {self._texte_regle(regle)}")
        return "\n".join(lignes)

    def _texte_regle(self, regle: Regle) -> str:
        portee = f"toute la pièce {self.nom_piece(regle.piece)}" if regle.piece else "tout le logement"
        valeurs = ", ".join(f"{c} = {v}" for c, v in regle.valeurs.items()) or "rien"
        sauf = "; ".join(f"sauf {p} : " + (", ".join(f"{c} = {v}" for c, v in vals.items()) or "à demander")
                         for p, vals in regle.exceptions.items())
        return f"{TYPES[regle.type].nom}, {portee} : {valeurs}" + (f" ({sauf})" if sauf else "")

    def vers_dict(self) -> dict:
        def valeur(v: Valeur) -> dict:
            return {"valeur": v.valeur, "citation": v.citation, "t": round(v.t, 2), "note": v.note, "origine": v.origine}

        def element(e: Element) -> dict:
            return {
                "id": e.id,
                "type": e.type,
                "description": e.description,
                "piece": self.nom_piece(e.piece) if e.piece else None,
                "t": round(e.t, 2),
                "source": e.source,
                "nombre": e.nombre,
                "parent": e.parent or None,
                "nom": self.nom(e, demonstratif=False),
                "repere": e.repere or None,
                "support": e.support or None,
                "orientation": {"point": e.orientation, "source": e.orientation_source, "note": e.orientation_note,
                                "cap_brut": None if e.cap is None else round(e.cap, 1),
                                "lacet": None if e.lacet is None else round(e.lacet, 1)} if e.type in ORIENTABLES else None,
                "image": e.image or None,
                "champs": {
                    c.cle: {
                        "libelle": c.libelle,
                        "importance": c.importance,
                        "utile": e.est_utile(c.cle),
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
                    "clos": {t: valeur(v) for t, v in p.clos.items()},
                    "nombre_murs": valeur(p.nombre_murs) if p.nombre_murs else None,
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
            "regles": [{"texte": self._texte_regle(r), "citation": r.citation, "t": round(r.t, 2)} for r in self.regles],
            "boussole": {"fiabilite": self.boussole_fiabilite, "gyroscope": self.boussole_gyroscope,
                         "correction": None if self.correction_cap is None else round(self.correction_cap, 1),
                         "source": self.correction_source},
            "signalements": [{"element": s.element_id, "champ": s.champ, "ancienne": s.ancienne, "nouvelle": s.nouvelle,
                              "citation": s.citation, "t": round(s.t, 2)} for s in self.signalements],
        }
