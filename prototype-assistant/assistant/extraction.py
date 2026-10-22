"""Extraction immédiate, sans IA, des valeurs dites par le diagnostiqueur.

Retour de Noah (test sur téléphone du 22/10/2026) : le diagnostiqueur doit pouvoir tout décrire
d'un coup (« ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois
fenêtres en bois double vitrage, deux radiateurs à eau »), sans jamais avoir à répéter.

Ce module lit chaque phrase transcrite en quelques millisecondes :
- description libre : la phrase est découpée élément par élément (mur, fenêtres, radiateurs…),
  avec le nombre d'éléments identiques (« trois fenêtres ») et tous leurs attributs ;
- réponse courte à la dernière question (« Ictérieur. », « BESSE ! ») : le mot est deviné avec le
  vocabulaire du champ demandé, et la correction est notée pour l'écran de validation ;
- « je ne sais pas » : le champ demandé vaut « inconnu » (à vérifier) et on passe à la suite.

Il produit des actions au même format que le cerveau (Claude) : elles passent par les mêmes
contrôles (citation, type, champ). Claude vient ensuite compléter ce que ces règles n'ont pas
compris et choisir la question suivante.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .checklist import TYPES, VALEUR_INCONNUE, Checklist, Element, cle_texte
from .lexique import corriger

# --- Nombres écrits en lettres ------------------------------------------------------------------

_UNITES = {
    "zero": 0, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}
_NOMBRE_MOTS = set(_UNITES) | {"un", "une", "cent", "cents", "mille", "et"}


def _valeur_mots(mots: list[str]) -> int:
    total, courant = 0, 0
    for mot in mots:
        if mot == "mille":
            total += (courant or 1) * 1000
            courant = 0
        elif mot in ("cent", "cents"):
            courant = (courant or 1) * 100
        elif mot in ("vingt", "vingts") and courant % 100 == 4:
            courant += 76  # quatre-vingt
        elif mot in ("un", "une"):
            courant += 1
        elif mot != "et":
            courant += _UNITES[mot]
    return total + courant


def chiffres(texte: str) -> str:
    """Remplace les nombres écrits en lettres par des chiffres (« deux mille douze » → 2012).
        « un » ou « une » seuls restent des mots (articles)."""
    mots, sortie, i = texte.split(), [], 0
    while i < len(mots):
        j = i
        while j < len(mots) and mots[j] in _NOMBRE_MOTS:
            j += 1
        groupe = mots[i:j]
        while groupe and groupe[-1] == "et":
            groupe.pop()
            j -= 1
        if groupe and groupe[0] != "et" and not (len(groupe) == 1 and groupe[0] in ("un", "une")):
            sortie.append(str(_valeur_mots(groupe)))
            i = j
        else:
            sortie.append(mots[i])
            i += 1
    return " ".join(sortie)


def normaliser(texte: str) -> str:
    """Texte comparable : corrections du lexique, minuscules sans accents, ponctuation isolée,
    nombres en chiffres."""
    texte = cle_texte(corriger(texte))
    texte = re.sub(r"[’'`\-]", " ", texte)
    texte = re.sub(r"(\d)\s*[,.]\s*(\d)", r"\1.\2", texte)  # 4,5 → 4.5
    texte = re.sub(r"[;:!?…]|\.(?!\d)", " , ", texte)
    texte = re.sub(r",", " , ", texte)
    texte = re.sub(r"[^a-z0-9., ]", " ", texte)
    return chiffres(" ".join(texte.split()))


# --- Vocabulaire métier par champ -----------------------------------------------------------------
# (formes reconnues, valeur notée). Les formes sont en minuscules sans accents. L'ordre compte :
# la première forme trouvée l'emporte.

VOCABULAIRE: dict[tuple[str, str], list[tuple[tuple[str, ...], str]]] = {
    ("mur", "materiau"): [
        (("parpaing", "parpaings", "agglo", "agglos"), "parpaing"),
        (("brique", "briques"), "brique"),
        (("beton cellulaire", "siporex"), "béton cellulaire"),
        (("beton", "banche"), "béton"),
        (("pierre", "pierres", "moellon", "moellons"), "pierre"),
        (("ossature bois",), "ossature bois"),
        (("pan de bois", "colombage", "colombages"), "pan de bois"),
        (("monomur",), "monomur"),
        (("placo", "plaque de platre", "carreau de platre", "carreaux de platre"), "plâtre"),
        (("bois",), "bois"),
        (("pise", "terre crue", "torchis"), "terre"),
    ],
    ("mur", "donne_sur"): [
        (("garage",), "local non chauffé : garage"),
        (("cave", "sous sol"), "local non chauffé : cave"),
        (("cellier",), "local non chauffé : cellier"),
        (("cage d escalier", "cage escalier", "palier", "parties communes", "couloir commun"), "local non chauffé : parties communes"),
        (("combles", "comble", "grenier"), "local non chauffé : combles"),
        (("veranda",), "local non chauffé : véranda"),
        (("local non chauffe", "non chauffe"), "local non chauffé"),
        (("local chauffe", "piece chauffee", "autre piece", "une piece", "interieur du logement"), "local chauffé"),
        (("voisin", "voisins", "mitoyen", "mitoyenne"), "local chauffé (voisin)"),
        (("exterieur", "dehors", "facade", "rue", "jardin"), "extérieur"),
    ],
    ("fenetre", "menuiserie"): [
        (("bois alu", "bois aluminium", "mixte"), "mixte bois-alu"),
        (("pvc", "p v c"), "PVC"),
        (("aluminium", "alu"), "alu"),
        (("metal", "metallique", "acier", "fer"), "métal"),
        (("bois",), "bois"),
    ],
    ("fenetre", "vitrage"): [
        (("triple vitrage", "triple"), "triple"),
        (("double vitrage", "double"), "double"),
        (("survitrage",), "survitrage"),
        (("simple vitrage", "simple"), "simple"),
    ],
    ("fenetre", "volets"): [
        (("pas de volet", "pas de volets", "sans volet", "sans volets", "aucun volet", "aucun"), "aucun"),
        (("roulant", "roulants"), "roulants"),
        (("battant", "battants"), "battants"),
        (("persienne", "persiennes"), "persiennes"),
    ],
    ("emetteur", "type"): [
        (("plancher chauffant",), "plancher chauffant"),
        (("seche serviette", "seche serviettes"), "sèche-serviettes"),
        (("radiateur electrique", "radiateurs electriques"), "radiateur électrique"),
        (("convecteur", "convecteurs", "grille pain"), "convecteur électrique"),
        (("panneau rayonnant", "panneaux rayonnants"), "panneau rayonnant électrique"),
        (("a eau", "eau chaude", "fonte", "chauffage central", "radiateur acier"), "radiateur à eau"),
        (("electrique", "electriques"), "radiateur électrique"),
    ],
    ("emetteur", "temperature"): [
        (("basse temperature", "basse", "bas"), "basse"),
        (("moyenne temperature", "moyenne"), "moyenne"),
        (("haute temperature", "haute", "haut"), "haute"),
    ],
    ("chauffage", "energie"): [
        (("gaz",), "gaz"),
        (("fioul", "fuel", "mazout"), "fioul"),
        (("granule", "granules", "pellet", "pellets"), "bois (granulés)"),
        (("pompe a chaleur", "pac"), "électricité (PAC)"),
        (("electrique", "electricite"), "électricité"),
        (("bois",), "bois"),
        (("reseau de chaleur", "chauffage urbain"), "réseau de chaleur"),
    ],
    ("chauffage", "type"): [
        (("condensation",), "chaudière à condensation"),
        (("chaudiere basse temperature",), "chaudière basse température"),
        (("pompe a chaleur air eau", "pac air eau"), "PAC air/eau"),
        (("pompe a chaleur air air", "pac air air", "climatisation reversible"), "PAC air/air"),
        (("pompe a chaleur", "pac"), "pompe à chaleur"),
        (("poele",), "poêle"),
        (("chaudiere",), "chaudière"),
        (("convecteur", "convecteurs"), "convecteurs électriques"),
    ],
    ("ecs", "systeme"): [
        (("thermodynamique",), "ballon thermodynamique"),
        (("solaire",), "chauffe-eau solaire"),
        (("instantane",), "chauffe-eau instantané"),
        (("ballon", "cumulus", "chauffe eau"), "ballon électrique"),
        (("chaudiere",), "chaudière"),
    ],
    ("ecs", "energie"): [
        (("gaz",), "gaz"),
        (("electrique", "electricite"), "électricité"),
        (("fioul", "fuel"), "fioul"),
    ],
    ("ventilation", "type"): [
        (("double flux",), "VMC double flux"),
        (("hygro b", "hygroreglable b"), "VMC simple flux hygro B"),
        (("hygro a", "hygroreglable a"), "VMC simple flux hygro A"),
        (("hygro", "hygroreglable"), "VMC simple flux hygro"),
        (("autoreglable", "auto reglable", "simple flux"), "VMC simple flux autoréglable"),
        (("naturelle", "grille", "grilles", "conduit", "conduits"), "naturelle"),
        (("vmc",), "VMC simple flux"),
    ],
}

# Mots qui annoncent un élément, et noms affichés (singulier, pluriel) pour les descriptions.
MOTS_ELEMENTS: list[tuple[str, str, str, str]] = [
    # (motif, type, singulier, pluriel)
    (r"portes? fenetres?", "fenetre", "la porte-fenêtre", "portes-fenêtres"),
    (r"baies? vitrees?|baies?", "fenetre", "la baie vitrée", "baies vitrées"),
    (r"fenetres?|velux|chassis", "fenetre", "la fenêtre", "fenêtres"),
    (r"plancher chauffant", "emetteur", "le plancher chauffant", "planchers chauffants"),
    (r"seche serviettes?", "emetteur", "le sèche-serviettes", "sèche-serviettes"),
    (r"radiateurs?", "emetteur", "le radiateur", "radiateurs"),
    (r"convecteurs?", "emetteur", "le convecteur", "convecteurs"),
    (r"panneaux? rayonnants?", "emetteur", "le panneau rayonnant", "panneaux rayonnants"),
    (r"chaudieres?|pompe a chaleur|\bpac\b|poele", "chauffage", "le chauffage", "générateurs"),
    (r"ballon(?: d eau chaude)?|cumulus|chauffe eau|eau chaude sanitaire|\becs\b", "ecs", "l'eau chaude", "ballons"),
    (r"\bvmc\b|ventilation|bouches? d aeration|grilles? d aeration", "ventilation", "la ventilation", "ventilations"),
    (r"murs?|cloisons?|parois?", "mur", "le mur", "murs"),
]
_MOTS = re.compile("|".join(f"(?P<m{i}>\\b(?:{motif})\\b)" for i, (motif, *_reste) in enumerate(MOTS_ELEMENTS)))
_DESIGNE = re.compile(r"\bcelui (?:ci|la)\b|\bcelle (?:ci|la)\b")  # « celui-ci » : un nouvel élément
_DESIGNATION = "designation"  # type provisoire d'un « celui-ci », fixé d'après les valeurs dites
_NOUVEAU = {"ce", "cet", "cette", "ces", "un", "une", "autre", "deuxieme", "troisieme", "quatrieme", "second", "seconde", "dernier"}

_ISOLANTS = [
    ("laine de verre", "laine de verre"), ("laine de roche", "laine de roche"), ("laine minerale", "laine minérale"),
    ("polystyrene", "polystyrène"), ("polyurethane", "polyuréthane"), ("ouate", "ouate de cellulose"),
    ("fibre de bois", "fibre de bois"), ("liege", "liège"), ("laine", "laine"),
]
_ISOLATION = re.compile(r"\bisol|\biti\b|\bite\b|\bitr\b|\blaine\b|polystyrene|polyurethane|\bouate\b|doublage|fibre de bois|\bliege\b")
# Début de la partie « isolation » d'une clause, négation comprise (« pas isolé », « sans isolation »).
_DEBUT_ISOLATION = re.compile(r"(?:\b(?:pas|non|sans|aucune?)\s+(?:d\s+)?)?(?:" + _ISOLATION.pattern + ")")
_NE_SAIT_PAS = re.compile(r"\bje (?:ne )?(?:sais|sait|c est) pas\b|\bj en sais rien\b|\baucune idee\b|\bon (?:ne )?sait pas\b|\binconnu")
_SANS_OBJET = re.compile(r"\bsans objet\b|\bpas concerne\b|\bnon concerne\b")
_ABSENCE = re.compile(r"\b(?:pas de|pas d|aucune?|il n y a pas de|il y a pas de|y a pas de)\s+(fenetres?|radiateurs?|chauffage|emetteurs?|convecteurs?|vmc|ventilation)\b")
_OUI = re.compile(r"^(?:oui|ouais|si|exact|voila|il y en a)\b")
_NON = re.compile(r"^(?:non|nan|aucune?|pas du tout|il n y en a pas|y en a pas)\b")
_PIECES = {
    "cuisine": "Cuisine", "sejour": "Séjour", "salon": "Salon", "salle a manger": "Salle à manger",
    "salle de bains": "Salle de bains", "salle de bain": "Salle de bains", "salle d eau": "Salle d'eau",
    "wc": "WC", "toilettes": "WC", "entree": "Entrée", "couloir": "Couloir", "degagement": "Dégagement",
    "bureau": "Bureau", "cellier": "Cellier", "buanderie": "Buanderie", "garage": "Garage", "cave": "Cave",
    "grenier": "Grenier", "combles": "Combles", "dressing": "Dressing", "chambre": "Chambre", "mezzanine": "Mezzanine",
}
_PIECE = re.compile(
    r"\b(?:ici c est|ici|c est|on est dans|on entre dans|on passe dans|on arrive dans|nous sommes dans)\s+(?:la |le |l |les )?("
    + "|".join(sorted(_PIECES, key=len, reverse=True)) + r")(?:\s+(\d+))?\b"
)
_ANNEE = re.compile(r"\b(19[3-9]\d|20[0-3]\d)\b")


@dataclass
class Cible:
    """La dernière question posée : quel champ de quel élément (ou quelle présence)."""

    type: str
    champ: str  # « presence » pour « Y a-t-il une fenêtre ? »
    element_id: str | None = None

    @classmethod
    def depuis_code(cls, code: str, checklist: Checklist) -> "Cible | None":
        """« M1.isolation » ou « presence:fenetre » → Cible (None si le code est inconnu)."""
        code = (code or "").strip()
        if code.startswith("presence:"):
            type_element = code.split(":", 1)[1]
            return cls(type_element, "presence") if type_element in TYPES else None
        if "." in code:
            element_id, champ = code.split(".", 1)
            try:
                element = checklist.trouver_element(element_id)
            except ValueError:
                return None
            if any(c.cle == champ for c in element.type_element.champs):
                return cls(element.type, champ, element.id)
        return None

    @property
    def code(self) -> str:
        return f"{self.element_id}.{self.champ}" if self.element_id else f"presence:{self.type}"


@dataclass
class _Segment:
    type: str
    texte: str  # normalisé
    nombre: int | None
    nouveau: bool
    singulier: str
    pluriel: str


@dataclass
class Extraction:
    actions: list[dict] = field(default_factory=list)
    devines: list[str] = field(default_factory=list)  # « ictérieur → extérieur »


def _motif_formes(formes: tuple[str, ...]) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(re.escape(f) for f in sorted(formes, key=len, reverse=True)) + r")\b")


_MOTIFS = {cle: [(_motif_formes(formes), valeur) for formes, valeur in liste] for cle, liste in VOCABULAIRE.items()}


def _premiere_valeur(type_element: str, champ: str, texte: str) -> str | None:
    for motif, valeur in _MOTIFS.get((type_element, champ), []):
        if motif.search(texte):
            return valeur
    return None


def _deviner(type_element: str, champ: str, texte: str, seuil: float = 0.74) -> tuple[str, str] | None:
    """Mot mal transcrit : le plus proche du vocabulaire du champ demandé (« ictérieur » → extérieur)."""
    mots = [m for m in texte.replace(",", " ").split() if len(m) >= 3 and not m.isdigit()]
    morceaux = mots + [f"{a} {b}" for a, b in zip(mots, mots[1:])]
    meilleur: tuple[float, str, str] | None = None
    for formes, valeur in VOCABULAIRE.get((type_element, champ), []):
        for forme in formes:
            for morceau in morceaux:
                if (forme.count(" ") == morceau.count(" ")) and len(forme) >= 3:
                    ratio = SequenceMatcher(None, morceau, forme).ratio()
                    if ratio >= seuil and (meilleur is None or ratio > meilleur[0]):
                        meilleur = (ratio, valeur, morceau)
    return (meilleur[1], f"deviné : « {meilleur[2]} » → {meilleur[1]}") if meilleur else None


# --- Champs particuliers du mur ----------------------------------------------------------------------

def _valeur_isolation(partie: str) -> str | None:
    if re.search(r"\bnon isole|\bpas isole|\bpas d isolation|\bsans isolation|\baucune isolation|\bpas d isolant", partie):
        return "non isolé"
    cote = None
    if re.search(r"\biti\b|par l interieur|isolation interieure|isole (?:a l |par l |de l )?interieur|doublage|\binterieur\b", partie):
        cote = "ITI"
    elif re.search(r"\bite\b|par l exterieur|isolation exterieure|isole (?:a l |par l |de l )?exterieur|\bexterieur\b", partie):
        cote = "ITE"
    elif re.search(r"\bitr\b|repartie", partie):
        cote = "ITR"
    isolant = next((nom for forme, nom in _ISOLANTS if re.search(rf"\b{forme}\b", partie)), None)
    epaisseur = re.search(r"\b(\d{1,3}(?:\.\d)?)\s*(?:cm|centimetres?)?\b(?!\s*(?:m\b|metres?))", partie)
    morceaux = [cote or ("isolé" if isolant or epaisseur or "isol" in partie else "")]
    morceaux += [isolant or "", f"{epaisseur.group(1)} cm" if epaisseur else ""]
    valeur = " ".join(m for m in morceaux if m)
    return valeur or None


def _valeurs_mur(texte: str) -> dict[str, str]:
    valeurs: dict[str, str] = {}
    materiaux = "|".join(re.escape(f) for formes, _ in VOCABULAIRE[("mur", "materiau")] for f in formes)
    for clause in re.split(r"\s*,\s*|\s+et\s+", texte):
        if not clause:
            continue
        coupure = _DEBUT_ISOLATION.search(clause)
        avant, isolation = (clause[: coupure.start()], clause[coupure.start():]) if coupure else (clause, "")
        if isolation and "isolation" not in valeurs and (v := _valeur_isolation(isolation)):
            valeurs["isolation"] = v
        if "long" in avant and "longueur" not in valeurs:
            if m := re.search(r"\b(\d+(?:\.\d+)?)\s*(?:m|metres?)\b(?:\s*(\d{1,2})\b)?", avant):
                valeurs["longueur"] = f"{m.group(1).replace('.', ',')}{',' + m.group(2) if m.group(2) else ''} m"
            continue
        if "materiau" not in valeurs and (v := _premiere_valeur("mur", "materiau", avant)):
            valeurs["materiau"] = v
        if "epaisseur" not in valeurs:
            m = (re.search(r"\b(\d{1,3}(?:\.\d)?)\s*(?:cm|centimetres?)\b", avant)
                 or re.search(rf"\b(?:{materiaux})\s+(?:de\s+)?(\d{{1,3}})\b(?!\s*(?:m\b|metres?|ans?\b|\.\d))", avant)
                 or re.search(r"\b(\d{1,3})\s*(?:d\s+)?epaisseurs?\b|epaisseur\D{0,12}(\d{1,3})\b", avant))
            if m:
                valeurs["epaisseur"] = f"{next(g for g in m.groups() if g)} cm"
        if "donne_sur" not in valeurs and (v := _premiere_valeur("mur", "donne_sur", avant)):
            valeurs["donne_sur"] = v
    return valeurs


def _valeurs(type_element: str, texte: str) -> dict[str, str]:
    """Toutes les valeurs reconnues pour un élément de ce type dans ce morceau de phrase."""
    if type_element == "mur":
        return _valeurs_mur(texte)
    valeurs: dict[str, str] = {}
    for champ in (c.cle for c in TYPES[type_element].champs):
        if champ == "annee":
            if m := _ANNEE.search(texte):
                valeurs[champ] = m.group(1)
        elif champ == "dimensions":
            m = re.search(r"\b(\d+(?:\.\d+)?)\s*(m|cm)?\s*(?:par|sur|x|fois)\s*(\d+(?:\.\d+)?)\s*(m|cm)?\b", texte)
            if m:
                unite = m.group(4) or m.group(2) or ("m" if "." in m.group(1) else "cm")
                valeurs[champ] = f"{m.group(1).replace('.', ',')} × {m.group(3).replace('.', ',')} {unite}"
        elif v := _premiere_valeur(type_element, champ, texte):
            valeurs[champ] = v
    return valeurs


# --- Découpage d'une phrase en éléments ---------------------------------------------------------------

def _segments(texte: str, type_courant: str | None) -> tuple[str, list[_Segment]]:
    """Coupe la phrase aux mots qui annoncent un élément. Renvoie (début sans élément, segments)."""
    reperes = []
    for m in _MOTS.finditer(texte):
        i = int(next(k for k, v in m.groupdict().items() if v)[1:])
        _motif, type_element, singulier, pluriel = MOTS_ELEMENTS[i]
        reperes.append((m.start(), m.end(), type_element, singulier, pluriel))
    for m in _DESIGNE.finditer(texte):
        if not any(a <= m.start() < b for a, b, *_ in reperes):
            reperes.append((m.start(), m.end(), _DESIGNATION, "", ""))  # type choisi ensuite, d'après les valeurs dites
    reperes.sort()
    segments: list[_Segment] = []
    debuts = []
    for debut, fin, type_element, singulier, pluriel in reperes:
        precedent = texte[:debut].split()[-3:]
        nombre = None
        debut_segment = debut
        if precedent and precedent[-1].isdigit() and 1 <= int(precedent[-1]) <= 50:
            nombre = int(precedent[-1])
            debut_segment = texte.rfind(precedent[-1], 0, debut)
        nouveau = bool(set(precedent) & _NOUVEAU) or bool(_DESIGNE.match(texte, debut)) or (nombre or 0) > 1
        debuts.append(debut_segment)
        segments.append(_Segment(type_element, "", nombre, nouveau, singulier, pluriel))
    for k, segment in enumerate(segments):
        segment.texte = texte[debuts[k]: debuts[k + 1] if k + 1 < len(segments) else len(texte)]
        if segment.type == _DESIGNATION:
            # « Celui-là, béton 18 cm » : l'élément que décrivent les valeurs dites (un mur par défaut, ou le
            # type de la dernière question s'il s'agit d'un élément de la pièce).
            candidats = list(dict.fromkeys(
                ([type_courant] if type_courant and TYPES[type_courant].niveau == "piece" else []) + ["mur", "fenetre", "emetteur"]))
            segment.type = max(candidats, key=lambda t: len(_valeurs(t, segment.texte)))
            segment.singulier, segment.pluriel = TYPES[segment.type].designation, TYPES[segment.type].nom + "s"
    return (texte[: debuts[0]] if debuts else texte), segments


def _element_vise(checklist: Checklist, segment: _Segment, valeurs: dict[str, str]) -> Element | None:
    """L'élément déjà connu que ce morceau de phrase décrit, ou None pour en créer un nouveau."""
    existants = _existants(checklist, segment.type)
    if not existants:
        return None

    def conflit(element: Element) -> bool:
        return any(element.valeur(c) is not None and cle_texte(element.valeur(c).valeur) != cle_texte(v) for c, v in valeurs.items())

    if segment.nombre:  # « les trois fenêtres » redit plus tard : le même groupe
        for element in reversed(existants):
            if element.nombre == segment.nombre and not conflit(element):
                return element
    dernier = existants[-1]
    deja_decrit = any(dernier.valeurs.values())
    if segment.nouveau:
        return None if (deja_decrit or segment.nombre and dernier.nombre != segment.nombre) else dernier
    if conflit(dernier) or (TYPES[segment.type].niveau == "piece" and not dernier.champs_manquants() and valeurs):
        return None
    return dernier


def _existants(checklist: Checklist, type_element: str) -> list[Element]:
    piece = checklist.piece_courante if TYPES[type_element].niveau == "piece" else None
    return [e for e in checklist.elements_de(piece) if e.type == type_element]


def extraire(phrase: str, checklist: Checklist, cible: Cible | None = None) -> Extraction:
    """Actions à appliquer pour cette phrase (citation = la phrase entière)."""
    resultat = Extraction()
    texte = normaliser(phrase)
    if not texte.strip(" ,"):
        return resultat

    def action(outil: str, **donnees) -> None:
        resultat.actions.append({"outil": outil, "citation": phrase, **donnees})

    if m := _PIECE.search(texte):
        nom = _PIECES[m.group(1)] + (f" {m.group(2)}" if m.group(2) else "")
        action("piece_courante", nom=nom)
        texte = texte[: m.start()] + texte[m.end():]

    # « Je ne sais pas » / « sans objet » : réponse à la dernière question, on passe à la suite.
    if cible and _NE_SAIT_PAS.search(texte):
        if cible.champ == "presence":
            action("marquer_sans_objet", type=cible.type, champ="presence", element_id="", note="ne sait pas")
        else:
            action("enregistrer_reponse", element_id=cible.element_id or "", type=cible.type, champ=cible.champ, valeur=VALEUR_INCONNUE)
        return resultat
    if cible and cible.champ != "presence" and _SANS_OBJET.search(texte):
        action("marquer_sans_objet", element_id=cible.element_id or "", type=cible.type, champ=cible.champ)
        return resultat
    for m in _ABSENCE.finditer(texte):
        mot = m.group(1)
        type_element = "fenetre" if mot.startswith("fenetre") else "ventilation" if mot in ("vmc", "ventilation") else "emetteur"
        action("marquer_sans_objet", type=type_element, champ="presence", element_id="")
    texte = _ABSENCE.sub(" ", texte)

    type_courant = cible.type if cible else None
    debut, segments = _segments(texte, type_courant)

    # Réponse courte à la dernière question : le début de phrase (avant tout autre élément cité).
    # « Oui, trois fenêtres en PVC » à « Y a-t-il une fenêtre ? » : c'est la suite de la phrase qui la décrit.
    if cible and not (cible.champ == "presence" and any(s.type == cible.type for s in segments)):
        _reponse_a_la_cible(checklist, cible, debut, resultat, action)

    numeros: dict[str, int] = {}
    cites: set[str] = set()  # types déjà annoncés dans cette phrase
    for segment in segments:
        if segment.type == "mur":
            segment.nombre = None  # « il y a 4 murs » : chaque mur a ses caractéristiques, jamais de groupe
        valeurs = _valeurs(segment.type, segment.texte)
        simple_mention = not valeurs and not segment.nombre
        # « une fenêtre ici », « et un radiateur ici » : on montre un élément déjà annoncé ; « ce mur » seul :
        # Claude et l'image s'en chargent. On ne crée un élément sur une simple mention que s'il n'y en a aucun.
        if simple_mention and (segment.type == "mur" or segment.type in cites or _existants(checklist, segment.type)):
            continue
        cites.add(segment.type)
        vise = _element_vise(checklist, segment, valeurs)
        if vise is None:
            numeros[segment.type] = numeros.get(segment.type, sum(e.type == segment.type for e in checklist.elements))
            numeros[segment.type] += 1
            description = (f"les {segment.nombre} {segment.pluriel}" if (segment.nombre or 1) > 1
                           else f"{segment.singulier} {numeros[segment.type]}")
            if any(cle_texte(e.description) == cle_texte(description) for e in checklist.elements):
                description += f" n°{numeros[segment.type]}"  # deux groupes de « 3 fenêtres » restent distincts
            action("signaler_element", type=segment.type, description=description, nombre=segment.nombre or 1, source="voix")
            reference = {"element_id": "", "description": description}
        else:
            if segment.nombre and segment.nombre != vise.nombre:
                action("signaler_element", type=segment.type, description=vise.description, nombre=segment.nombre, source="voix")
            reference = {"element_id": vise.id, "description": ""}
        for champ, valeur in valeurs.items():
            action("enregistrer_reponse", type=segment.type, champ=champ, valeur=valeur, **reference)
    return resultat


def _reponse_a_la_cible(checklist: Checklist, cible: Cible, texte: str, resultat: Extraction, action) -> None:
    if cible.champ == "presence":
        if _NON.match(texte.strip(" ,")):
            action("marquer_sans_objet", type=cible.type, champ="presence", element_id="")
        elif _OUI.match(texte.strip(" ,")) or re.match(r"^\s*(\d+)\b", texte):
            nombre = re.match(r"^\s*(?:oui\s*,?\s*)?(\d+)\b", texte)
            n = int(nombre.group(1)) if nombre and 1 <= int(nombre.group(1)) <= 50 else 1
            action("signaler_element", type=cible.type, description=TYPES[cible.type].designation, nombre=n, source="voix")
        return
    if not texte.strip(" ,") or not cible.element_id:
        return
    if cible.champ == "isolation":
        # Toute la réponse parle de l'isolation : « 10 cm » est l'épaisseur de l'isolant, pas du mur.
        reponse = texte.strip(" ,")
        v = ("non isolé" if _NON.match(reponse) else _valeur_isolation(texte) or ("isolé" if _OUI.match(reponse) else None))
        valeurs = {"isolation": v} if v else {}
    else:
        valeurs = _valeurs(cible.type, texte)
    if cible.champ not in valeurs:
        if cible.champ == "epaisseur" and (m := re.search(r"\b(\d{1,3}(?:\.\d)?)\b(?!\s*(?:m\b|metres?))", texte)):
            valeurs["epaisseur"] = f"{m.group(1)} cm"
        elif cible.champ == "isolation" and (v := _valeur_isolation(texte)):
            valeurs["isolation"] = v
        elif cible.champ in ("annee",) and (m := re.search(r"\b(\d{4})\b", texte)):
            valeurs["annee"] = m.group(1)
        elif devine := _deviner(cible.type, cible.champ, texte):
            valeurs[cible.champ] = devine[0]
            resultat.devines.append(devine[1])
    for champ, valeur in valeurs.items():
        note = next((d for d in resultat.devines if d.endswith(f"→ {valeur}")), "") if champ == cible.champ else ""
        action("enregistrer_reponse", element_id=cible.element_id, type=cible.type, champ=champ, valeur=valeur, **({"note": note} if note else {}))
