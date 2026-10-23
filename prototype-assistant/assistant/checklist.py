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

Enveloppe (étape 13 de Noah) : le DPE décrit ce qui entoure le logement, pas chaque pièce.
- les murs, le plafond et le plancher sont ceux du LOGEMENT : un « mur ouest » est tous les murs ouest du
  logement, toutes pièces confondues. Un mur filmé dans une autre pièce rejoint le mur de même orientation
  déjà décrit (rien n'est redemandé) ; les pièces où il a été vu sont gardées pour le repérage ;
- un mur peut avoir plusieurs parties : « mur est : 60 % sur le voisin, 40 % dehors », ou côté séjour sur la
  rue et côté chambre sur le voisin. Une valeur dite dans une autre pièce, différente de celle déjà dite, est
  une autre partie (et non une contradiction) ; les fenêtres vont sur la partie qui donne dehors ;
- un mur entre deux pièces du logement est hors de l'enveloppe : noté s'il est dit, jamais demandé ni compté ;
- la pièce où l'on est ne compte pas pour le DPE (Noah : « qu'on soit dans le séjour ou la chambre, pour le DPE on s'en
  fiche ») : elle n'est jamais demandée. Les fenêtres et les portes sont sur leur mur, les émetteurs sont ceux du
  logement. Une pièce nommée par le diagnostiqueur est seulement notée (repérage, Carrez).

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
    niveau: str  # « piece », « enveloppe » (parois du logement, étape 13) ou « logement » (équipements)
    champs: tuple[Champ, ...]
    designation: str  # avec article, pour les descriptions par défaut : « la fenêtre »


TYPES: dict[str, TypeElement] = {
    t.cle: t
    for t in (
        # « donne sur » d'abord : sur un local chauffé, le reste de la paroi n'est pas réclamé.
        TypeElement("mur", "mur", "M", "enveloppe", (
            Champ("donne_sur", "donne sur"),
            Champ("materiau", "matériau"),
            Champ("epaisseur", "épaisseur"),
            Champ("isolation", "isolation"),
            Champ("longueur", "longueur", "facultatif"),
            Champ("part", "part du mur", "facultatif"),  # « 60 % sur le voisin, 40 % dehors » (étape 13)
        ), "le mur"),
        TypeElement("plafond", "plafond", "PL", "enveloppe", (
            Champ("donne_sur", "donne sur"),
            Champ("isolation", "isolation"),
            Champ("structure", "structure", "facultatif"),
        ), "le plafond"),
        TypeElement("plancher", "plancher", "PB", "enveloppe", (
            Champ("donne_sur", "donne sur"),
            Champ("isolation", "isolation"),
            Champ("structure", "structure", "facultatif"),
        ), "le plancher"),
        TypeElement("fenetre", "fenêtre", "F", "enveloppe", (  # sur son mur, un côté du logement (étape 13)
            Champ("menuiserie", "menuiserie"),
            Champ("vitrage", "vitrage"),
            Champ("volets", "volets"),
            Champ("dimensions", "dimensions", "facultatif"),
        ), "la fenêtre"),
        TypeElement("porte", "porte extérieure", "PO", "enveloppe", (
            Champ("type", "type"),
            Champ("donne_sur", "donne sur"),
        ), "la porte"),
        # Date et température des radiateurs : jamais demandées, toujours notées si elles sont dites (Noah, étape 4). Pour le
        # DPE, ce sont les émetteurs du logement (leur type), pas ceux de chaque pièce (étape 13).
        TypeElement("emetteur", "émetteur de chauffage", "E", "logement", (
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

PAROIS = ("mur", "plafond", "plancher")  # les parois de l'enveloppe du logement (étape 13)
OUVERTURES = ("fenetre", "porte")  # sur leur mur
ORIENTABLES = ("mur", "fenetre", "porte")  # éléments décrits par leur orientation dans LICIEL (apports solaires)
# Toujours là, créés automatiquement pour le logement : on ne demande pas s'ils existent.
TOUJOURS_PRESENTS = ("plafond", "plancher")
# Présences à confirmer. Étape 13 : plus rien par pièce ; les fenêtres se demandent mur par mur, le reste pour le logement.
PRESENCES_PIECE: tuple[str, ...] = ()
PRESENCES_LOGEMENT = ("chauffage", "emetteur", "ecs", "ventilation")
# Ce qui fait qu'une paroi est la même : dit différemment dans une autre pièce, c'en est une autre partie (étape 13).
IDENTITE = {"mur": ("donne_sur", "materiau", "epaisseur", "isolation"), "plafond": ("donne_sur", "isolation"),
            "plancher": ("donne_sur", "isolation")}
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


_ARTICLES = {
    "sejour": "le", "salon": "le", "couloir": "le", "degagement": "le", "bureau": "le", "cellier": "le", "garage": "le",
    "grenier": "le", "dressing": "le", "cuisine": "la", "salle": "la", "buanderie": "la", "cave": "la", "chambre": "la",
    "mezzanine": "la", "entree": "l'", "wc": "les", "combles": "les",
}


def avec_article(nom: str) -> str:
    """« Séjour » → « le séjour », « Chambre 1 » → « la chambre 1 », « Entrée » → « l'entrée »."""
    premier = cle_texte(nom).split()[0] if nom.strip() else ""
    article = _ARTICLES.get(premier)
    if article is None:
        return f"la pièce « {nom} »"
    nom = nom if nom.isupper() else nom[:1].lower() + nom[1:]
    return f"{article}{'' if article.endswith(chr(39)) else ' '}{nom}"


def de_la_piece(nom: str) -> str:
    """« Séjour » → « du séjour », « Cuisine » → « de la cuisine », « WC » → « des WC »."""
    groupe = avec_article(nom)
    for article, contracte in (("le ", "du "), ("les ", "des ")):
        if groupe.startswith(article):
            return contracte + groupe[len(article):]
    return "de " + groupe


def categorie(donne_sur: str) -> str:
    """« Sur quoi donne » une paroi, réduit à ce qui la distingue d'une autre partie : « local non chauffé » et « local non
    chauffé : garage » sont la même chose dite plus ou moins précisément."""
    return cle_texte(donne_sur)


def meme_categorie(a: str, b: str) -> bool:
    ca, cb = categorie(a), categorie(b)
    return ca == cb or ca.startswith(cb + " :") or cb.startswith(ca + " :")


def interieur(donne_sur: str) -> bool:
    """Une autre pièce du logement (« local chauffé », « local chauffé : cuisine ») : mur intérieur, hors de l'enveloppe.
    Un voisin (« local chauffé (voisin) ») reste un côté du logement."""
    c = categorie(donne_sur)
    return c == "local chauffe" or c.startswith("local chauffe :")


@dataclass
class Valeur:
    valeur: str
    citation: str
    t: float
    note: str = ""  # ex. « deviné : ictérieur → extérieur », montré à la validation
    # « dit » : dit pour cet élément ; « groupe » : reprise du groupe dont l'élément a été séparé ;
    # « regle » : vient d'une règle (« toutes les fenêtres sont en bois »).
    origine: str = "dit"
    piece: str | None = None  # paroi de l'enveloppe : la pièce où la valeur a été dite (étape 13)


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
    pieces: list[str] = field(default_factory=list)  # paroi de l'enveloppe : pièces où elle a été vue (repérage, étape 13)
    vu_a: dict[str, float] = field(default_factory=dict)  # pièce -> instant où elle y a été vue pour la première fois
    absences: dict[str, Valeur] = field(default_factory=dict)  # mur : « pas de fenêtre sur ce mur » (type -> citation)
    piece_propre: str = ""  # partie d'une paroi propre à une pièce (« ici le plancher donne sur une cave »)

    def voir_dans(self, piece: str | None, t: float) -> None:
        """Paroi vue (ou décrite) dans cette pièce : « le deuxième mur » est le deuxième vu dans la pièce."""
        if piece and piece not in self.pieces:
            self.pieces.append(piece)
        if piece:
            self.vu_a.setdefault(piece, t)

    @property
    def type_element(self) -> TypeElement:
        return TYPES[self.type]

    @property
    def enveloppe(self) -> bool:
        return TYPES[self.type].niveau == "enveloppe"

    @property
    def interieur(self) -> bool:
        """Mur entre deux pièces du logement : hors de l'enveloppe, ignoré pour le DPE (étape 13)."""
        v = self.valeur("donne_sur")
        return self.type == "mur" and v is not None and interieur(v.valeur)

    @property
    def deperditif(self) -> bool:
        """Paroi qui donne dehors ou sur un local non chauffé : celle qui porte les fenêtres."""
        v = self.valeur("donne_sur")
        return v is not None and not categorie(v.valeur).startswith("local chauffe") and categorie(v.valeur) != VALEUR_INCONNUE

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
    source: str = "dit"  # « image » : reconnue sur la vidéo (croquis) ; un nom dit ensuite la renomme


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
        return element.type == self.type and (self.piece is None or element.piece == self.piece or self.piece in element.pieces)

    def valeurs_pour(self, element: Element) -> tuple[dict[str, str], str]:
        """(valeurs, note) applicables à cet élément."""
        lieux = [element.piece] if element.piece else element.pieces
        for piece, valeurs in self.exceptions.items():
            if any(lieu == piece or lieu.startswith(piece + " ") for lieu in lieux):
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
    cote: str = ""  # côté du logement pas encore décrit : « nord »… (étape 13)
    mur: Element | None = None  # fenêtres de ce mur à confirmer (étape 13)

    @property
    def code(self) -> str:
        if self.element and self.champ:
            return f"{self.element.id}.{self.champ.cle}"
        if self.mur is not None:
            return f"fenetres:{self.mur.id}"
        if self.cote:
            return f"cote:{self.cote}"
        return f"presence:{self.type}"

    @property
    def libelle(self) -> str:
        if self.element and self.champ:
            return f"{self.element.description} : {self.champ.libelle}"
        if self.cote:
            return f"côté {self.cote} du logement : sur quoi il donne"
        if self.mur is not None:
            return f"{self.mur.description} : fenêtres ou porte à confirmer"
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
        # Gyroscope reçu, nord pas encore calé (iPhone tenu droit) : on attend avant de demander l'orientation à l'oral ;
        # les murs filmés entre-temps prendront leur côté dès que le nord sera connu (test du 23/10).
        self.attente_boussole = False
        self.boussole_gyroscope = False  # le téléphone donne les angles entre murs
        self.boussole_dementie = False  # une orientation dite contredit la boussole : elle est faussée ici
        self._compteurs: dict[str, int] = {}
        # Élément réuni à un autre (étape 13 : un mur rejoint le mur de même orientation ; étape 9 : doublon confirmé) :
        # son identifiant mène à l'élément gardé.
        self.alias: dict[str, str] = {}
        self.renommages: list[tuple[str, str]] = []  # (ancienne clé, nouvelle) : le croquis suit
        self.clos: dict[str, Valeur] = {}  # « pas d'autre mur » : les côtés du logement sont tous dits (étape 13)
        for type_element in TOUJOURS_PRESENTS:  # le plafond et le plancher du logement, toujours là
            self.signaler_element(type_element, TYPES[type_element].designation, 0.0, source="auto")

    # --- Pièces ---------------------------------------------------------------------------

    def _creer_piece(self, nom: str, t: float, citation: str = "") -> str:
        """Clé de la pièce, créée si besoin (le plafond et le plancher sont ceux du logement : étape 13)."""
        nom = " ".join(nom.split())
        if not nom:
            raise ErreurChecklist("nom de pièce vide")
        cle = cle_texte(nom)
        if cle not in self.pieces:
            self.pieces[cle] = Piece(nom=nom[0].upper() + nom[1:], t=t, citation=citation)
        return cle

    def definir_piece(self, nom: str, t: float, citation: str = "") -> Piece:
        """Change de pièce. Revenir dans une pièce déjà vue la reprend, sans doublon."""
        self.piece_courante = self._creer_piece(nom, t, citation)
        return self.pieces[self.piece_courante]

    def renommer_piece(self, cle: str, nom: str, source: str = "dit") -> str:
        """« Non, c'est la chambre » : la même pièce, un autre nom (reconnue à tort sur l'image). Renvoie la nouvelle clé."""
        nom = " ".join(nom.split())
        nouvelle = cle_texte(nom)
        if cle not in self.pieces or not nom or (nouvelle in self.pieces and nouvelle != cle):
            raise ErreurChecklist(f"renommage impossible : {cle!r} → {nom!r}")
        piece = self.pieces[cle]
        piece.nom, piece.source = nom[0].upper() + nom[1:], source
        self.renommages.append((cle, nouvelle))
        self.pieces = {(nouvelle if k == cle else k): v for k, v in self.pieces.items()}
        self.piece_courante = nouvelle if self.piece_courante == cle else self.piece_courante
        for e in self.elements:
            e.piece = nouvelle if e.piece == cle else e.piece
            e.pieces = [nouvelle if p == cle else p for p in e.pieces]
            e.vu_a = {(nouvelle if p == cle else p): t for p, t in e.vu_a.items()}
            e.piece_propre = nouvelle if e.piece_propre == cle else e.piece_propre
            for historique in e.valeurs.values():
                for v in historique:
                    v.piece = nouvelle if v.piece == cle else v.piece
        for r in self.regles:
            r.piece = nouvelle if r.piece == cle else r.piece
        return nouvelle

    def fusionner_pieces(self, cle: str, dans: str) -> str:
        """« Ce n'est pas une autre pièce, c'est le séjour » : la pièce `cle` (reconnue à tort sur la vidéo) rejoint `dans` ;
        ce qui y a été vu est rangé dans `dans`."""
        if cle not in self.pieces or dans not in self.pieces or cle == dans:
            raise ErreurChecklist(f"fusion impossible : {cle!r} → {dans!r}")
        for e in self.elements:
            e.piece = dans if e.piece == cle else e.piece
            e.pieces = list(dict.fromkeys(dans if p == cle else p for p in e.pieces))
            if cle in e.vu_a:
                e.vu_a[dans] = min(e.vu_a.pop(cle), e.vu_a.get(dans, float("inf")))
            e.piece_propre = dans if e.piece_propre == cle else e.piece_propre
            for historique in e.valeurs.values():
                for v in historique:
                    v.piece = dans if v.piece == cle else v.piece
        del self.pieces[cle]
        self.piece_courante = dans if self.piece_courante == cle else self.piece_courante
        self.renommages.append((cle, dans))
        return dans

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
        """« Pas d'autre mur » : rien d'autre à dire de ce type pour le logement (étape 13 : les côtés qui restent ne sont
        plus demandés). Notée aussi pour la pièce en cours, s'il y en a une."""
        self._type(type_element)
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("clôture refusée : aucune citation du diagnostiqueur")
        self.clos[type_element] = Valeur("complet", citation, t)
        if self.piece_courante in self.pieces:
            self.pieces[self.piece_courante].clos[type_element] = Valeur("complet", citation, t)

    def compter_murs(self, nombre: int, citation: str, t: float) -> None:
        """« Cette pièce fait 4 murs » : une fois ce nombre de murs décrits, on ne demande plus s'il y en a d'autres."""
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("nombre de murs refusé : aucune citation du diagnostiqueur")
        if not isinstance(nombre, int) or not 3 <= nombre <= 12:
            raise ErreurChecklist(f"nombre de murs invraisemblable : {nombre!r}")
        if self.piece_courante in self.pieces:  # utile au plan de la pièce, pas au DPE (étape 13)
            self.pieces[self.piece_courante].nombre_murs = Valeur(str(nombre), citation, t)

    def murs_complets(self, piece: str | None = None) -> bool:
        """Tous les murs de la pièce sont annoncés : « pas d'autre mur », ou le nombre dit est atteint."""
        if "mur" in self.clos:
            return True
        cle = piece or self.piece_courante
        if cle not in self.pieces:
            return False
        p = self.pieces[cle]
        n = sum(e.nombre for e in self.murs_de_la_piece(cle))
        return "mur" in p.clos or (p.nombre_murs is not None and n >= int(p.nombre_murs.valeur))

    def nom(self, element: Element, demonstratif: bool = True) -> str:
        """Nom à dire à l'oral : « ce mur » (on vient d'en parler), « le mur côté voisin », jamais « le mur 3 »
        (voir noms.py). `demonstratif=False` : jamais « ce mur » (pour l'écran et pour Claude)."""
        from .noms import nom_parlant

        if element.enveloppe:  # un mur du logement se distingue des autres murs du logement (étape 13)
            voisins = self.enveloppe(element.type, interieurs=True)
            fenetres = [e for e in self.elements if e.type in ("fenetre", "porte")]
        else:
            voisins = [e for e in self.elements_de(element.piece) if e.type == element.type]
            fenetres = [e for e in self.elements_de(element.piece) if e.type in ("fenetre", "porte")]
        courant = demonstratif and self.dernier.get(element.type) == element.id and (
            self.piece_courante is None or element.piece is None and not element.pieces or self.dans_la_piece(element, self.piece_courante))
        if element.type == "mur" and element.orientation_source == "dit" and element.cap is None and element.lacet is None:
            courant = False  # « à l'est, la cage d'escalier » : un côté dit, pas un mur filmé ; il se nomme par son côté
        rangs = None
        if element.type == "mur":  # « le deuxième mur » : le deuxième vu dans sa pièce (étape 13)
            rangs = (self.murs_de_la_piece(element.pieces[0]) if element.pieces
                     else [e for e in voisins if not e.pieces])
        nom = nom_parlant(element, voisins, fenetres, courant, rangs)
        if (element.type == "mur" and element.pieces and self.piece_courante not in element.pieces
                and re.fullmatch(r"le \w+ mur", nom)):
            nom += " " + de_la_piece(self.nom_piece(element.pieces[0]))  # « le premier mur du séjour », vu d'ailleurs
        return nom

    def libelle(self, manque: Manque) -> str:
        """Ce qui manque, avec le nom parlant de l'élément (« le mur ouest : isolation »), jamais « le mur 3 » (étape 5)."""
        if manque.element is not None and manque.champ:
            return f"{self.nom(manque.element, demonstratif=False)} : {manque.champ.libelle}"
        if manque.mur is not None:
            return f"{self.nom(manque.mur, demonstratif=False)} : fenêtres ou porte à confirmer"
        return manque.libelle

    def dans_la_piece(self, element: Element, piece: str | None) -> bool:
        """Élément de cette pièce, ou paroi du logement vue dans cette pièce."""
        return piece is not None and (element.piece == piece or piece in element.pieces)

    def copier(self, type_element: str, piece_source: str, citation: str, t: float) -> Element:
        """« Plafond pareil que le séjour » : recopie les valeurs de l'élément de l'autre pièce. Pour le plafond et le
        plancher du logement (étape 13), la pièce reprend simplement la partie de la pièce citée."""
        if TYPES[type_element].niveau == "enveloppe":
            source = self.element_de_piece(type_element, piece_source)
            if source is None or not source.valeurs:
                raise ErreurChecklist(f"rien à recopier : pas de {TYPES[type_element].nom} décrit dans {self.nom_piece(piece_source)}")
            ici = self.piece_courante
            if ici is None:
                raise ErreurChecklist("pas de pièce en cours : le plafond et le plancher sont déjà ceux du logement")
            for autre in self.enveloppe(type_element, interieurs=True):
                if autre is not source and ici in autre.pieces:
                    autre.pieces.remove(ici)
            source.voir_dans(ici, t)
            return source
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
        ident, vus = element_id.strip().upper(), set()
        while ident in self.alias and ident not in vus:  # réuni à un autre élément : c'est lui
            vus.add(ident)
            ident = self.alias[ident]
        for element in self.elements:
            if element.id == ident:
                return element
        raise ErreurChecklist(f"élément inconnu : {element_id!r}")

    def elements_de(self, piece: str | None) -> list[Element]:
        """Éléments d'une pièce ; avec `None`, les équipements du logement (l'enveloppe à part : `enveloppe`)."""
        return [e for e in self.elements if e.piece == piece and not e.enveloppe]

    def enveloppe(self, type_element: str | None = None, interieurs: bool = False) -> list[Element]:
        """Murs, plafond et plancher du logement (étape 13), sans les murs intérieurs sauf `interieurs`."""
        return [e for e in self.elements if e.enveloppe and (type_element is None or e.type == type_element)
                and (interieurs or not e.interieur)]

    def murs_de_la_piece(self, piece: str | None = None) -> list[Element]:
        """Murs du logement vus ou décrits dans cette pièce (murs intérieurs compris : ils y ont été dits)."""
        piece = piece if piece is not None else self.piece_courante
        return sorted((e for e in self.enveloppe("mur", interieurs=True) if piece in e.pieces), key=lambda e: e.vu_a.get(piece, e.t))

    def orientations_manquantes(self) -> list[str]:
        """Côtés du logement dont rien n'est encore dit : le DPE décrit tout ce qui entoure le logement (étape 13)."""
        return [p for p in POINTS if not any(m.orientation == p for m in self.enveloppe("mur"))]

    def element_de_piece(self, type_element: str, piece: str | None = None) -> Element | None:
        """Le (dernier) élément de ce type dans la pièce, par exemple sa fenêtre. Plafond et plancher du logement : la
        partie propre à cette pièce s'il y en a une, sinon celle du logement."""
        piece = piece if piece is not None else self.piece_courante
        if TYPES[type_element].niveau == "enveloppe":
            parties = self.enveloppe(type_element, interieurs=True)
            if type_element not in TOUJOURS_PRESENTS:
                return next((e for e in reversed(parties) if piece in e.pieces), None)
            return next((e for e in parties if piece in e.pieces), parties[0] if parties else None)
        return next((e for e in reversed(self.elements_de(piece)) if e.type == type_element), None)

    def sans_mur(self, ouverture: Element) -> bool:
        """Fenêtre ou porte dont on ne connaît pas le mur du logement qui la porte : aucun, ou un mur devenu mur entre
        deux pièces (« en fait il donne sur la cuisine »)."""
        return ouverture.type in OUVERTURES and ouverture.support not in {m.id for m in self.enveloppe("mur")}

    def fenetres_du_mur(self, mur: Element) -> list[Element]:
        """Les fenêtres et portes portées par ce mur (« nombre de fenêtres et portes sur ce mur », étape 13)."""
        return [e for e in self.elements if e.type in OUVERTURES and e.support == mur.id]

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
        lieu = None  # paroi du logement : la pièce où elle est vue (repérage, étape 13)
        if te.niveau == "piece":
            piece = piece if piece in self.pieces else self._piece_pour_element()
        elif te.niveau == "enveloppe":  # vu dans la pièce en cours, s'il y en a une (repérage) ; sinon nulle part
            lieu = None if source == "auto" else piece if piece in self.pieces else self.piece_courante
            piece = None
        else:
            piece = None
        if te.niveau == "enveloppe":
            element = (self.element_de_piece(te.cle, lieu) if te.cle in TOUJOURS_PRESENTS else
                       next((e for e in self.enveloppe(te.cle, interieurs=True) if cle_texte(e.description) == cle_texte(description)), None))
        else:
            element = next((e for e in self.elements_de(piece) if e.type == te.cle and cle_texte(e.description) == cle_texte(description)), None)
        if element is not None:
            if nombre:
                self._fixer_nombre(element, nombre)
        else:
            element = Element(id=self._nouvel_id(te), type=te.cle, description=description, piece=piece, t=t, source=source,
                              nombre=nombre or 1)
            self.elements.append(element)
            element.voir_dans(lieu, t)  # avant les règles : « sauf celle de la chambre » dépend de la pièce où elle est vue
            for regle in self.regles:
                if regle.concerne(element):
                    self._appliquer_regle(regle, element)
        element.voir_dans(lieu, t)
        if repere and not element.repere:
            element.repere = " ".join(repere.split())
        if support and te.cle in ("fenetre", "porte"):
            element.support = self._mur_support(support) or element.support
            self._ranger_fenetres()
            self._deduire_orientations()  # « au nord la cour, avec une porte-fenêtre » : elle est au nord
        if source == "voix":
            self.dernier[te.cle] = element.id
        return element

    def _mur_support(self, support: str) -> str:
        """Le mur qui porte une fenêtre, donné par son identifiant ou son nom (un mur du logement, étape 13)."""
        try:
            return self.trouver_element(support).id if self.trouver_element(support).type == "mur" else ""
        except ErreurChecklist:
            mur = next((e for e in self.enveloppe("mur", interieurs=True) if cle_texte(support) == cle_texte(e.description)), None)
            return mur.id if mur else ""

    def retirer(self, element_id: str) -> None:
        """Élément créé à tort (par les règles du serveur, corrigées par Claude) : il disparaît."""
        element = self.trouver_element(element_id)
        self.elements.remove(element)
        for autre in self.elements:
            if autre.support == element.id:
                autre.support = ""
        for ancien in [a for a, cible in self.alias.items() if cible == element.id]:
            del self.alias[ancien]
        if self.dernier.get(element.type) == element.id:
            del self.dernier[element.type]

    def fusionner(self, element_id: str, meme_que: str) -> Element:
        """« C'est le même mur que le mur côté couloir ? » « Oui. » : le diagnostiqueur confirme un doublon (étape 9 ;
        jamais sans sa confirmation). Étape 13 : un mur du logement filmé dans une autre pièce rejoint aussi le mur de
        même orientation (`_rattacher_murs`). Ce qui n'était dit que du doublon passe à l'élément gardé, puis le doublon
        disparaît ; son identifiant mène désormais à l'élément gardé."""
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
        if not garde.orientation and doublon.orientation:
            garde.orientation, garde.orientation_source, garde.orientation_note = (
                doublon.orientation, doublon.orientation_source, doublon.orientation_note)
        for piece in doublon.pieces:
            garde.voir_dans(piece, doublon.vu_a.get(piece, doublon.t))
        for autre in self.elements:
            if autre.support == doublon.id:
                autre.support = garde.id
        for ancien, cible in self.alias.items():
            if cible == doublon.id:
                self.alias[ancien] = garde.id
        self.retirer(doublon.id)
        self.alias[doublon.id] = garde.id
        self.dernier[garde.type] = garde.id
        return garde

    def completer(self, element_id: str, repere: str = "", support: str = "") -> Element:
        """Ajoute à un élément connu ce qui permet de le reconnaître : un repère dit, le mur qui porte une fenêtre."""
        element = self.trouver_element(element_id)
        if repere and not element.repere:
            element.repere = " ".join(repere.split())
        if support and element.type in ("fenetre", "porte") and not element.support:
            element.support = self._mur_support(support)
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
        semblables = self.enveloppe(source.type, interieurs=True) if source.enveloppe else self.elements_de(source.piece)
        if any(cle_texte(e.description) == cle_texte(description) for e in semblables):
            description += f" n°{sum(e.type == source.type for e in self.elements) + 1}"
        element = Element(id=self._nouvel_id(source.type_element), type=source.type, description=description, piece=source.piece,
                          t=t, source="voix", nombre=nombre, parent=source.id, sans_objet=dict(source.sans_objet),
                          support=source.support)  # « deux en PVC et une en bois » : sur le même mur
        if source.enveloppe:  # « mur est : 60 % sur le voisin, 40 % dehors » : une autre partie du même mur (étape 13)
            element.pieces, element.vu_a = list(source.pieces), dict(source.vu_a)
            element.orientation, element.orientation_source, element.orientation_note = (
                source.orientation, source.orientation_source, source.orientation_note)
            element.cap, element.lacet = source.cap, source.lacet
        for champ, historique in source.valeurs.items():
            if source.type == "mur" and champ in ("longueur", "part"):
                continue  # « 3 mètres sur le voisin, le reste dehors » : la longueur d'une partie n'est pas celle de l'autre
            derniere = historique[-1]
            element.valeurs[champ] = [Valeur(derniere.valeur, derniere.citation, derniere.t, f"comme {source.description}", "groupe",
                                             derniere.piece)]
        # Juste après son groupe : les questions sur la partie séparée viennent à la suite.
        self.elements.insert(self.elements.index(source) + 1, element)
        for champ, valeur in (valeurs or {}).items():
            self.enregistrer(type_element=source.type, champ=champ, valeur=valeur, citation=citation, t=t, element_id=element.id)
        self._ranger_fenetres()
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
        def dans(e: Element) -> bool:
            return any(lieu == cle or lieu.startswith(cle + " ") for lieu in ([e.piece] if e.piece else e.pieces))

        for element in [e for e in self.elements if regle.concerne(e) and dans(e)]:
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
            if element.type in OUVERTURES and element.support:
                self._mur_du_cote(element)
            self._deduire_orientations()
            self._verifier_coherence(element)
            self._rattacher_murs()
        return self.trouver_element(element.id)

    def regler_boussole(self, correction: float | None, fiabilite: str, gyroscope: bool) -> None:
        """État de la boussole estimé sur la visite. Une orientation dite à l'oral l'emporte sur la boussole."""
        self.boussole_fiabilite = "faible" if self.boussole_dementie and fiabilite != "absente" else fiabilite
        self.boussole_gyroscope = gyroscope
        if correction is None or self.correction_source.startswith("dit"):
            return
        if self.correction_cap is None or abs(ecart(correction, self.correction_cap)) > 10:
            self.correction_cap, self.correction_source = correction % 360, "boussole"
            self._deduire_orientations()
            self._rattacher_murs()

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
        self._rattacher_murs()
        return self.trouver_element(element.id)

    def _orientation_auto(self, element: Element) -> tuple[str, str, str]:
        """(point, source, note) d'un élément dont l'orientation n'a pas été dite."""
        if element.type in ("fenetre", "porte") and element.support:
            mur = next((e for e in self.elements if e.id == element.support), None)
            if mur is not None and mur.orientation:
                return mur.orientation, "mur", f"comme {self.nom(mur, demonstratif=False)}"
        return self._orientation_mesuree(element)

    def _orientation_mesuree(self, element: Element) -> tuple[str, str, str]:
        """(point, source, note) d'après la visée de la caméra quand il a été filmé (gyroscope, sinon boussole)."""
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

    def _mur_du_cote(self, ouverture: Element) -> None:
        """Une fenêtre filmée d'un autre côté que le mur auquel elle était rattachée (le mur dont on parlait) : la
        boussole l'emporte, elle va sur le mur de son côté qui donne dehors, ou sur aucun (étape 13)."""
        point = self._orientation_mesuree(ouverture)[0]
        try:
            mur = self.trouver_element(ouverture.support)
        except ErreurChecklist:
            return
        if not point or not mur.orientation or mur.orientation == point:
            return
        du_cote = [e for e in self.enveloppe("mur") if e.orientation == point and e.deperditif]
        ouverture.support = next((e for e in du_cote if set(e.pieces) & set(ouverture.pieces)), du_cote[0]).id if du_cote else ""

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
        for autre in self.enveloppe("mur", interieurs=True):  # le lacet du gyroscope vaut pour toute la visite
            if autre is element or autre.lacet is None or not autre.orientation:
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
        """Boussole absente ou peu fiable, et aucune orientation dite : le mur filmé dans la pièce dont il faut demander
        l'orientation, une seule fois (avec le gyroscope, les autres murs s'en déduisent). Étape 13 : c'est par elle
        qu'un mur rejoint le mur du même côté du logement, donc pour tout mur qui l'entoure (dehors, voisin, local non
        chauffé), pas seulement dehors."""
        if self.correction_cap is not None or self.boussole_fiabilite in ("bonne", "moyenne", "inconnue") or self.attente_boussole:
            return None
        murs = [e for e in (self.murs_de_la_piece(piece) if piece else self.enveloppe("mur"))
                if not e.orientation and not e.interieur and e.valeur("donne_sur") is not None]
        dernier = self.dernier.get("mur")
        return next((m for m in murs if m.id == dernier), murs[-1] if murs else None)

    # --- Enveloppe : un mur par côté du logement, en parties (étape 13) ---------------------------------

    @staticmethod
    def _conflit(a: Element, b: Element) -> bool:
        """Deux parois qui ne peuvent pas être la même : une valeur dite pour l'une et pour l'autre, différente ; ou une
        longueur (une part) dite pour chacune : deux parties du même côté, dont aucune longueur ne doit se perdre."""
        if any(a.valeur(c) is not None and b.valeur(c) is not None for c in ("longueur", "part")):
            return True
        for champ in IDENTITE.get(a.type, ()):
            va, vb = a.valeur(champ), b.valeur(champ)
            if va is None or vb is None or VALEUR_INCONNUE in (va.valeur, vb.valeur):
                continue
            if champ == "donne_sur" and meme_categorie(va.valeur, vb.valeur):
                continue
            if cle_texte(va.valeur) != cle_texte(vb.valeur) and not cle_texte(va.valeur).startswith(cle_texte(vb.valeur)) and not (
                    cle_texte(vb.valeur).startswith(cle_texte(va.valeur))):
                return True
        return False

    def _meme_mur(self, mur: Element, autres: list[Element]) -> Element | None:
        """Le mur du même côté que `mur` est-il celui-ci ? Oui si rien ne les distingue : sans « donne sur » dit, s'il est
        le seul de ce côté (ou le seul déjà vu dans la même pièce) ; avec, s'il donne sur la même chose. Sinon, c'est une
        autre partie de ce côté (on demandera sur quoi il donne s'il ne l'a pas dit)."""
        compatibles = [e for e in autres if not self._conflit(mur, e)]
        donne = mur.valeur("donne_sur")
        if donne is None:
            if len(autres) == 1:
                return compatibles[0] if compatibles else None
            memes_pieces = [e for e in compatibles if set(e.pieces) & set(mur.pieces)]
            return memes_pieces[0] if len(memes_pieces) == 1 else None
        memes = [e for e in compatibles if (v := e.valeur("donne_sur")) is not None and meme_categorie(v.valeur, donne.valeur)]
        return memes[0] if memes else None

    def _rattacher_murs(self) -> None:
        """Un mur orienté rejoint le mur du même côté du logement déjà décrit : « un mur ouest, c'est tous les murs ouest
        du logement, toutes pièces confondues » (Noah, étape 13). Rien n'est redemandé ; les pièces où il a été vu
        s'ajoutent (repérage)."""
        change = True
        while change:
            change = False
            murs = self.enveloppe("mur")
            for mur in reversed(murs):
                if not mur.orientation:
                    continue
                autres = [e for e in murs[: murs.index(mur)] if e.orientation == mur.orientation]
                if autres and (garde := self._meme_mur(mur, autres)) is not None:
                    self.fusionner(mur.id, garde.id)
                    change = True
                    break
        self._ranger_fenetres()

    def _ranger_fenetres(self) -> None:
        """Une fenêtre ne s'ouvre pas sur un voisin : portée par une partie de mur qui ne donne pas dehors, elle va sur la
        partie du même côté qui donne dehors (ou sur un local non chauffé), de préférence vue dans sa pièce."""
        for fenetre in self.elements:
            if fenetre.type not in ("fenetre", "porte") or not fenetre.support:
                continue
            try:
                mur = self.trouver_element(fenetre.support)
            except ErreurChecklist:
                continue
            if mur.deperditif or mur.valeur("donne_sur") is None:
                continue
            parties = [e for e in self.enveloppe("mur") if e is not mur and e.orientation and e.orientation == mur.orientation
                       and e.deperditif]
            if parties:
                fenetre.support = next((e for e in parties if set(fenetre.pieces) & set(e.pieces)), parties[0]).id
        self._deduire_portes()

    def _deduire_portes(self) -> None:
        """Une porte sur un mur qui donne dehors donne dehors ; sur un mur qui donne sur les parties communes, sur le palier :
        on ne le demande pas. Déduction notée comme telle (avec les mots qui ont dit sur quoi donne le mur), qu'un « donne
        sur » dit pour la porte remplace sans contradiction."""
        for porte in self.elements:
            historique = porte.valeurs.get("donne_sur", [])
            if historique and historique[-1].origine == "groupe" and historique[-1].note.startswith("déduit : sur"):
                historique.pop()  # refaite d'après le mur tel qu'il est maintenant (« en fait il donne sur le garage »)
                if not historique:
                    del porte.valeurs["donne_sur"]
            if porte.type != "porte" or not porte.support or porte.valeur("donne_sur") is not None:
                continue
            try:
                mur = self.trouver_element(porte.support)
            except ErreurChecklist:
                continue
            donne = mur.valeur("donne_sur")
            if donne is None:
                continue
            valeur = ("extérieur" if categorie(donne.valeur) == "exterieur" else
                      "palier (local non chauffé)" if "parties communes" in categorie(donne.valeur) else None)
            if valeur:
                porte.valeurs["donne_sur"] = [Valeur(valeur, donne.citation, donne.t,
                                                     f"déduit : sur {self.nom(mur, demonstratif=False)}", "groupe")]

    def _nouvelle_partie(self, source: Element, lieu: str, t: float) -> Element:
        """Une autre partie de cette paroi, celle de la pièce `lieu` : côté séjour, le mur ouest donne sur la rue ; côté
        chambre, sur le voisin (étape 13). Elle reprend ce qui est dit de la paroi (origine « groupe ») et reçoit ensuite
        ses propres valeurs ; les fenêtres de cette pièce passent sur elle."""
        te = source.type_element
        if source.type == "mur":
            description = f"{te.designation} {sum(e.type == 'mur' for e in self.elements) + 1}"
        else:
            description = f"{te.designation} {de_la_piece(self.nom_piece(lieu))}"
        partie = Element(id=self._nouvel_id(te), type=source.type, description=description, piece=None, t=t, source="voix",
                         parent=source.id, orientation=source.orientation, orientation_source=source.orientation_source,
                         orientation_note=source.orientation_note, cap=source.cap, lacet=source.lacet)
        partie.voir_dans(lieu, source.vu_a.get(lieu, t))
        partie.piece_propre = lieu
        for champ, historique in source.valeurs.items():
            derniere = historique[-1]
            partie.valeurs[champ] = [Valeur(derniere.valeur, derniere.citation, derniere.t,
                                            f"comme {self.nom(source, demonstratif=False)}", "groupe", derniere.piece)]
        if lieu in source.pieces:
            source.pieces.remove(lieu)
        self.elements.insert(self.elements.index(source) + 1, partie)
        for fenetre in self.elements:
            if fenetre.type in ("fenetre", "porte") and fenetre.support == source.id and lieu in fenetre.pieces:
                fenetre.support = partie.id
        return partie

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
        demande = (element_id or "").strip().upper()
        if (demande in self.alias and element.type == "mur" and champ in IDENTITE["mur"] and origine == "dit"
                and (avant := element.valeur(champ)) is not None and avant.origine == "dit"
                and contradiction(avant, Valeur(valeur, citation, t), a_preciser("mur", champ, avant.valeur))):
            element = self._separer(demande, element, t)
        # Paroi du logement (étape 13) : la pièce où c'est dit. Dit autrement dans une pièce nommée qu'ailleurs (dans une
        # autre pièce, ou pour tout le logement), c'est une autre partie de la paroi (côté séjour sur la rue, côté chambre
        # sur le voisin ; « ici le plancher donne sur une cave »), pas une contradiction. Sans pièce, c'est une correction.
        lieu = (piece if piece in self.pieces else self.piece_courante) if element.enveloppe and origine == "dit" else None
        if lieu:  # dans une pièce qui a sa propre partie de cette paroi, c'est d'elle qu'il parle
            element = next((e for e in self.elements if e.parent == element.id and e.piece_propre == lieu), element)
        nouvelle = Valeur(valeur, citation, t, note, origine, lieu)
        derniere = element.valeur(champ)
        if (lieu and derniere is not None and derniere.origine == "dit" and derniere.piece != lieu
                and champ in IDENTITE.get(element.type, ()) and contradiction(derniere, nouvelle, a_preciser(element.type, champ, derniere.valeur))):
            element = self._nouvelle_partie(element, lieu, t)
            derniere = element.valeur(champ)
        element.voir_dans(lieu, t)
        if derniere is None or cle_texte(derniere.valeur) != cle_texte(valeur):
            element.valeurs.setdefault(champ, []).append(nouvelle)
            if derniere is not None and contradiction(derniere, nouvelle, a_preciser(element.type, champ, derniere.valeur)):
                self.signalements.append(Signalement(element.id, champ, derniere.valeur, valeur, citation, t))
        elif derniere.origine != "dit" and origine == "dit":
            element.valeurs[champ][-1] = nouvelle
        element.sans_objet.pop(champ, None)
        if origine == "dit":
            self.dernier[element.type] = element.id
        if element.type == "mur" and champ == "donne_sur":
            self._rattacher_murs()  # il donne sur la même chose qu'un mur du même côté : c'est lui
        if (element.type, champ) in (("emetteur", "type"), ("chauffage", "energie")):
            self._deduire_chauffage()
        return self.trouver_element(element.id)

    def _separer(self, ident: str, garde: Element, t: float) -> Element:
        """Un mur réuni d'office à celui du même côté (rien ne les distinguait), dont on dit ensuite autre chose (« celui-là
        donne sur la cuisine ») : ce n'était pas lui. Il redevient un mur à part, du même côté, sans rien changer au premier
        (étape 13)."""
        del self.alias[ident]
        mur = Element(id=ident, type="mur", description=f"le mur {ident[1:]}", piece=None, t=t, source="voix")
        mur.orientation, mur.orientation_source, mur.orientation_note = garde.orientation, garde.orientation_source, garde.orientation_note
        mur.cap, mur.lacet = garde.cap, garde.lacet
        mur.voir_dans(self.piece_courante, t)
        self.elements.insert(self.elements.index(garde) + 1, mur)
        return mur

    def _deduire_chauffage(self) -> None:
        """Chauffage à l'électricité dont le type n'est pas dit, et tous les radiateurs du logement électriques : ce sont
        des radiateurs électriques (effet Joule), quel que soit l'ordre où c'est dit (étape 13 : le chauffage est demandé
        avant les radiateurs). Déduction notée comme telle, avec les mots qui ont dit les radiateurs, et refaite à chaque
        radiateur dit (« et un à eau » : retirée) ; une autre valeur dite ensuite la remplace sans contradiction."""
        emetteurs = [e for e in self.elements if e.type == "emetteur"]
        types = [e.valeur("type") for e in emetteurs]
        electriques = bool(emetteurs) and all(v is not None and "electrique" in cle_texte(v.valeur) for v in types)
        for chauffage in [e for e in self.elements if e.type == "chauffage"]:
            historique = chauffage.valeurs.get("type", [])
            if historique and historique[-1].origine == "groupe" and historique[-1].note.startswith("déduit : émetteurs"):
                historique.pop()
                if not historique:
                    del chauffage.valeurs["type"]
            energie = chauffage.valeur("energie")
            if electriques and energie is not None and cle_texte(energie.valeur) == "electricite" and chauffage.valeur("type") is None:
                source = max(types, key=lambda v: v.t)
                chauffage.valeurs["type"] = [Valeur("radiateurs électriques (effet Joule)", source.citation, source.t,
                                                    f"déduit : émetteurs tous électriques ({', '.join(e.id for e in emetteurs)})",
                                                    "groupe")]

    def marquer_sans_objet(
        self,
        *,
        type_element: str,
        champ: str,
        citation: str,
        t: float,
        element_id: str | None = None,
        description: str = "",
        support: str = "",
    ) -> None:
        """Champ sans objet pour un élément, ou absence d'un type d'élément (champ « presence »), par exemple « pas de
        fenêtre sur ce mur » (`support` : le mur, étape 13) ou « pas de VMC ». Toujours avec citation."""
        te = self._type(type_element)
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("« sans objet » refusé : aucune citation du diagnostiqueur")
        if champ == "presence":
            if te.cle == "mur" or te.cle in TOUJOURS_PRESENTS:
                raise ErreurChecklist(f"un logement a toujours un {te.nom}")
            if support and te.cle in OUVERTURES and (mur := self._mur_support(support)):
                self.trouver_element(mur).absences[te.cle] = Valeur("absent", citation, t)
            elif te.niveau == "piece" and self.piece_courante in self.pieces:
                self.pieces[self.piece_courante].absences[te.cle] = Valeur("absent", citation, t)
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
        """Manques principaux d'une pièce (la pièce courante par défaut), dans l'ordre du parcours : les murs du logement
        décrits dans cette pièce, le plafond et le plancher du logement (une seule fois pour tout le logement), les
        fenêtres et portes, les émetteurs. Les côtés du logement pas encore décrits sont à part (`manques_enveloppe`)."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return []
        presences = {m.type: m for m in self._manques_presence(PRESENCES_PIECE, piece, self.pieces[piece].absences)}
        manques: list[Manque] = []
        for mur in self.murs_de_la_piece(piece):
            manques += [Manque("mur", piece, mur, c) for c in mur.champs_manquants()]
        for type_element in TOUJOURS_PRESENTS:
            if (element := self.element_de_piece(type_element, piece)) is not None:
                manques += [Manque(type_element, piece, element, c) for c in element.champs_manquants()]
        for type_element in OUVERTURES:  # celles du logement vues dans cette pièce (les radiateurs sont ceux du logement)
            if type_element in presences:
                manques.append(presences[type_element])
            for element in self.enveloppe(type_element):
                if piece in element.pieces:
                    manques += [Manque(element.type, piece, element, c) for c in element.champs_manquants()]
        return manques

    def fenetres_a_confirmer(self, mur: Element) -> bool:
        """Un mur décrit qui donne dehors (ou sur un local non chauffé) : ses fenêtres et portes sont à demander, une fois."""
        return (not mur.champs_manquants() and mur.deperditif and not self.fenetres_du_mur(mur)
                and "fenetre" not in mur.absences and "fenetre" not in self.absences_logement)

    def manques_enveloppe(self) -> list[Manque]:
        """Ce qui manque à l'enveloppe du logement (étape 13), quelle que soit la pièce où l'on est : chaque mur, ses
        fenêtres et portes, puis les côtés du logement dont rien n'est dit, le plafond et le plancher, et les fenêtres
        dont on ne sait pas encore le mur."""
        manques: list[Manque] = []
        for mur in self.enveloppe("mur"):
            manques += [Manque("mur", None, mur, c) for c in mur.champs_manquants()]
            if self.fenetres_a_confirmer(mur):
                manques.append(Manque("fenetre", None, mur=mur))
            for ouverture in self.fenetres_du_mur(mur):
                manques += [Manque(ouverture.type, None, ouverture, c) for c in ouverture.champs_manquants()]
        if "mur" not in self.clos:
            manques += [Manque("mur", None, cote=p) for p in self.orientations_manquantes()]
        for element in self.enveloppe():
            if element.type in TOUJOURS_PRESENTS or self.sans_mur(element):
                manques += [Manque(element.type, None, element, c) for c in element.champs_manquants()]
        return manques

    def emetteurs_deduits(self) -> bool:
        """Chauffage par radiateurs électriques, convecteurs ou panneaux : les émetteurs sont le chauffage lui-même."""
        return any(e.type == "chauffage" and (v := e.valeur("type")) is not None
                   and any(m in cle_texte(v.valeur) for m in CHAUFFAGES_SANS_ANNEE) for e in self.elements)

    def manques_logement(self) -> list[Manque]:
        manques: list[Manque] = []
        for type_element in PRESENCES_LOGEMENT:
            elements = [e for e in self.elements_de(None) if e.type == type_element]
            if type_element == "emetteur" and not elements and self.emetteurs_deduits():
                continue
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
        """Tout ce qui manque au DPE : l'enveloppe du logement, puis ses équipements (aucune pièce : étape 13)."""
        uniques: dict[str, Manque] = {}
        for m in self.manques_enveloppe() + self.manques_logement():
            uniques.setdefault(m.code, m)
        return list(uniques.values())

    def taux_dpe(self) -> float:
        """Part de ce qu'il faut savoir pour le DPE qui est déjà dit (0 à 1) : champs utiles de l'enveloppe et des
        équipements, côtés du logement, fenêtres de chaque mur, présences."""
        remplis = len(POINTS) - len(self.orientations_manquantes())
        for e in self.enveloppe() + self.elements_de(None):
            remplis += sum(c.obligatoire and e.est_utile(c.cle) and e.est_rempli(c.cle) for c in e.type_element.champs)
        remplis += sum(1 for m in self.enveloppe("mur") if m.deperditif and not self.fenetres_a_confirmer(m))
        remplis += sum(1 for t in PRESENCES_LOGEMENT if t in self.absences_logement or any(e.type == t for e in self.elements_de(None)))
        manques = len(self.manques_visite())
        return round(remplis / (remplis + manques), 3) if remplis + manques else 0.0

    def piece_terminee(self, piece: str | None = None) -> bool:
        piece = piece if piece is not None else self.piece_courante
        return piece in self.pieces and not self.manques_piece(piece)

    def taux_remplissage(self, piece: str | None = None) -> float:
        """Part des informations utiles attendues dans la pièce qui sont renseignées (0 à 1)."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return 0.0
        attendus = len(PRESENCES_PIECE)
        parois = self.murs_de_la_piece(piece) + [e for t in TOUJOURS_PRESENTS if (e := self.element_de_piece(t, piece))]
        for e in self.elements_de(piece) + parois:
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
                note += (" (déduit)" if v.note.startswith("déduit") else
                         {"groupe": " (comme son groupe)", "regle": " (règle du logement)"}.get(v.origine, ""))
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
        if element.enveloppe:
            origine += ", vu dans " + (", ".join(self.nom_piece(p) for p in element.pieces) or "aucune pièce encore")
            if element.parent:
                origine = origine.replace(f"séparé de {element.parent}", f"autre partie de {element.parent}")
        if element.interieur:
            origine += ", mur intérieur : ignoré pour le DPE"
        nombre = f" ×{element.nombre}" if element.nombre > 1 else ""
        return f"- {element.id} {element.type_element.nom}{nombre} « {self.nom(element, demonstratif=False)} » ({origine}) : " + ", ".join(champs)

    def lignes_enveloppe(self) -> list[str]:
        """L'enveloppe du logement, par côté (étape 13) : ce que le DPE décrit, chaque mur avec ses fenêtres et portes."""
        lignes = ["Enveloppe du logement (DPE : murs par côté, toutes pièces confondues ; murs entre pièces ignorés) :"]
        murs = self.enveloppe("mur")

        def avec_ouvertures(mur: Element, entete: str) -> None:
            lignes.append(f"- {entete} : " + self._ligne_element(mur)[2:])
            lignes.extend(f"    sur ce mur : {self._ligne_element(o)[2:]}" for o in self.fenetres_du_mur(mur))
            if "fenetre" in mur.absences:
                lignes.append("    sur ce mur : aucune fenêtre (dit)")

        for point in POINTS:
            du_cote = [m for m in murs if m.orientation == point]
            if not du_cote:
                lignes.append(f"- côté {point} : rien encore")
            for mur in du_cote:
                avec_ouvertures(mur, f"côté {point}" + (" (une partie)" if len(du_cote) > 1 else ""))
        for mur in murs:
            if not mur.orientation:
                avec_ouvertures(mur, "côté inconnu (orientation à trouver)")
        for type_element in TOUJOURS_PRESENTS:
            lignes += [f"- {TYPES[type_element].nom} : {self._ligne_element(e)[2:]}" for e in self.enveloppe(type_element)]
        sans_mur = [o for o in self.enveloppe() if self.sans_mur(o)]
        lignes += [f"- fenêtre ou porte dont le mur n'est pas dit : {self._ligne_element(o)[2:]}" for o in sans_mur]
        interieurs = [m for m in self.enveloppe("mur", interieurs=True) if m.interieur]
        if interieurs:
            lignes.append("Murs entre deux pièces (ignorés pour le DPE) : " + ", ".join(m.id for m in interieurs))
        return lignes

    def resume_pour_ia(self, max_manques: int = 12) -> str:
        """État compact envoyé à l'IA à chaque appel (le serveur reste la source de vérité). Étape 13 : tout est décrit
        pour le logement ; la pièce en cours n'est qu'un repère, jamais demandée."""
        lignes: list[str] = []
        if self.piece_courante:
            piece = self.pieces[self.piece_courante]
            lignes.append(f"Pièce en cours (dite par le diagnostiqueur, simple repère : sans effet sur le DPE) : {piece.nom}")
            murs = self.murs_de_la_piece()
            if murs:
                lignes.append("Murs du logement vus dans cette pièce : " + ", ".join(f"{m.id} « {self.nom(m, demonstratif=False)} »" for m in murs))
        else:
            lignes.append("Pièce en cours : aucune (la pièce ne compte pas pour le DPE : ne la demande jamais)")
        lignes += self.lignes_enveloppe()
        cotes = [] if "mur" in self.clos else self.orientations_manquantes()
        lignes.append("Côtés du logement pas encore décrits : " + (", ".join(cotes) or "aucun"))
        equipements = self.elements_de(None)
        lignes.append("Équipements du logement :" if equipements else "Équipements du logement : aucun signalé")
        lignes += [self._ligne_element(e) for e in equipements]
        manques = self.manques_visite()
        codes = ", ".join(f"{m.code} ({self.libelle(m)})" for m in manques[:max_manques])
        lignes.append(f"Manques pour le DPE, par priorité : {codes or 'aucun'}")
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
                "pieces": [self.nom_piece(p) for p in e.pieces] if e.enveloppe else None,
                "interieur": e.interieur if e.type == "mur" else None,
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
            return {"code": m.code, "piece": self.nom_piece(m.piece) if m.piece else None, "libelle": self.libelle(m)}

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
            # Étape 13 : ce que le DPE décrit, pour tout le logement. Un mur par côté (en parties s'il le faut), les pièces
            # où il a été vu ; les murs entre deux pièces à part, ignorés.
            "enveloppe": {
                "murs": [element(e) for e in self.enveloppe("mur")],
                "murs_interieurs": [element(e) for e in self.enveloppe("mur", interieurs=True) if e.interieur],
                "plafonds": [element(e) for e in self.enveloppe("plafond")],
                "planchers": [element(e) for e in self.enveloppe("plancher")],
                "fenetres": [element(e) for e in self.enveloppe() if e.type in OUVERTURES],  # chacune sur son mur (« support »)
                "cotes_manquants": self.orientations_manquantes(),
                "manques": [manque(m) for m in self.manques_enveloppe()],
            },
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
