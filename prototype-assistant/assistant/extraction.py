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

from .checklist import PAROIS, TOUJOURS_PRESENTS, TYPES, VALEUR_INCONNUE, Checklist, Element, cle_texte
from .lexique import corriger

# --- Nombres écrits en lettres ------------------------------------------------------------------

_UNITES = {
    "zero": 0, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}
_NOMBRE_MOTS = set(_UNITES) | {"un", "une", "cent", "cents", "mille", "milles", "et"}


def _valeur_mots(mots: list[str]) -> int:
    total, courant = 0, 0
    for mot in mots:
        if mot in ("mille", "milles"):
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


# Mots d'hésitation, sans contenu (« euh… le… le mur »).
_HESITATIONS = {"euh", "euuh", "euhh", "heu", "heuu", "hum", "humm", "hmm", "mmh", "mh", "bah", "ben", "beh", "hein", "bref"}
# Mots qui ne doivent jamais disparaître comme un faux départ (« pas parpaing » n'est pas un bégaiement).
_JAMAIS_FAUX_DEPART = {"pas", "non", "sans", "ne", "ni"}


def nettoyer_oral(mots: list[str]) -> list[str]:
    """Retire les hésitations, les mots répétés (« le le mur », « roulant roulant ») et les faux départs
    d'un bégaiement (« pa parpaing », « dou double »)."""
    propres: list[str] = []
    for i, mot in enumerate(mots):
        if mot in _HESITATIONS or re.fullmatch(r"e+u+h*|h+e+u+|m{2,}h*|m+h+", mot):
            continue
        suivant = next((m for m in mots[i + 1:] if m not in _HESITATIONS and m != ","), "")
        if (mot.isalpha() and mot not in _JAMAIS_FAUX_DEPART and len(suivant) - len(mot) >= 2
                and suivant.startswith(mot) and len(mot) <= 4):
            continue  # faux départ : « pa… parpaing »
        precedent = next((m for m in reversed(propres) if m != ","), "")
        if mot != "," and mot == precedent and not mot.isdigit():
            while propres and propres[-1] == ",":
                propres.pop()
            continue  # répétition : « le… le mur »
        if mot == "," and propres and propres[-1] == ",":
            continue
        propres.append(mot)
    return propres


def normaliser(texte: str) -> str:
    """Texte comparable : corrections du lexique, minuscules sans accents, ponctuation isolée,
    hésitations et répétitions retirées, nombres en chiffres."""
    texte = cle_texte(corriger(texte))
    texte = re.sub(r"\.{2,}|…", " ", texte)  # « il fait… trente » : une hésitation, pas une fin de phrase
    texte = re.sub(r"[’'`\-]", " ", texte)
    texte = re.sub(r"(\d)\s*[,.]\s*(\d)", r"\1.\2", texte)  # 4,5 → 4.5
    texte = re.sub(r"[;:!?]|\.(?!\d)", " , ", texte)
    texte = re.sub(r",", " , ", texte)
    texte = re.sub(r"[^a-z0-9., ]", " ", texte)
    return chiffres(" ".join(nettoyer_oral(texte.split())))


def phonetique(texte: str) -> str:
    """Clé phonétique française approximative, pour comparer ce qui se prononce pareil :
    « oh est chaude » ≈ « eau chaude », « brik » ≈ « brique », « vie de sanitaire » ≈ « vide sanitaire »."""
    mots = []
    for mot in cle_texte(texte).replace(",", " ").split():
        if mot.isdigit():
            mots.append(mot)
            continue
        m = mot
        for motif, son in (
            (r"^(?:est|et|ai|es)$", "e"), (r"^(?:oh|ho|o|au|aux|eau|eaux)$", "o"),
            (r"eaux?|aux?|au", "o"), (r"ph", "f"), (r"ch", "x"), (r"qu", "k"), (r"gu(?=[eiy])", "g"),
            (r"c(?=[eiy])", "s"), (r"g(?=[eiy])", "j"), (r"c", "k"), (r"x(?!$)", "ks"), (r"ss", "s"),
            (r"(?:ai|ei|er$|ez$|et$)", "e"), (r"ou", "w"), (r"y", "i"), (r"h", ""),
            (r"[ae]n(?=[^aeiouy]|$)|[ae]m(?=[bp])", "a"), (r"(?:ai|ei|i)n(?=[^aeiouy]|$)", "in"),
        ):
            m = re.sub(motif, son, m)
        m = re.sub(r"(.)\1+", r"\1", m)  # lettres doublées
        m = re.sub(r"(?<=.)(?:es|e|s|t|x)$", "", m)  # lettres finales muettes
        mots.append(m)
    return "".join(mots)


# --- Vocabulaire métier par champ -----------------------------------------------------------------
# (formes reconnues, valeur notée). Les formes sont en minuscules sans accents. L'ordre compte :
# la première forme trouvée l'emporte.

VOCABULAIRE: dict[tuple[str, str], list[tuple[tuple[str, ...], str]]] = {
    ("mur", "materiau"): [
        (("parpaing", "parpaings", "agglo", "agglos", "bloc beton", "blocs beton", "parpaing creux", "bloc creux", "blocs creux",
          "bloc", "blocs"), "parpaing"),
        (("brique creuse", "briques creuses"), "brique creuse"),
        (("brique pleine", "briques pleines"), "brique pleine"),
        (("monomur", "brique alveolaire", "briques alveolaires"), "monomur"),
        (("brique", "briques"), "brique"),
        (("beton cellulaire", "siporex"), "béton cellulaire"),
        (("beton banche", "banche"), "béton banché"),
        (("machefer",), "mâchefer"),
        (("beton",), "béton"),
        (("meuliere", "meulieres"), "meulière"),
        (("silex",), "silex"),
        (("gres",), "grès"),
        (("granit", "granite"), "granit"),
        (("calcaire",), "calcaire"),
        (("tuffeau",), "tuffeau"),
        (("pierre de taille",), "pierre de taille"),
        (("pierre", "pierres", "moellon", "moellons"), "pierre"),
        (("ossature bois",), "ossature bois"),
        (("pan de bois", "colombage", "colombages"), "pan de bois"),
        (("placo", "plaque de platre", "carreau de platre", "carreaux de platre", "platre"), "plâtre"),
        (("bois massif", "rondins", "bois"), "bois"),
        (("pise", "terre crue", "torchis", "bauge", "adobe"), "terre"),
    ],
    ("mur", "donne_sur"): [
        (("garage",), "local non chauffé : garage"),
        (("cave", "sous sol"), "local non chauffé : cave"),
        (("cellier",), "local non chauffé : cellier"),
        (("cage d escalier", "cage escalier", "palier", "parties communes", "couloir commun"), "local non chauffé : parties communes"),
        (("combles", "comble", "grenier"), "local non chauffé : combles"),
        (("veranda",), "local non chauffé : véranda"),
        (("local non chauffe", "non chauffe"), "local non chauffé"),
        (("local chauffe", "piece chauffee", "autre piece", "une piece", "interieur du logement", "mur interieur", "interieur", "cloison"),
         "local chauffé"),
        (("voisin", "voisins", "mitoyen", "mitoyenne"), "local chauffé (voisin)"),
        (("exterieur", "dehors", "facade", "rue", "jardin"), "extérieur"),
    ],
    ("plafond", "donne_sur"): [
        (("local non chauffe", "non chauffe"), "local non chauffé"),
        (("combles perdus", "comble perdu", "grenier"), "combles perdus"),
        (("combles amenages", "comble amenage", "combles habitables"), "combles aménagés"),
        (("toit terrasse", "toiture terrasse", "terrasse"), "toiture terrasse"),
        (("rampant", "rampants", "sous toiture", "sous le toit", "toiture", "toit"), "rampants sous toiture"),
        (("combles", "comble"), "combles"),
        (("local chauffe", "chauffe", "logement au dessus", "appartement au dessus", "voisin du dessus", "etage", "logement", "appartement"),
         "local chauffé (logement au-dessus)"),
        (("exterieur", "dehors"), "extérieur"),
    ],
    ("plancher", "donne_sur"): [
        (("local non chauffe", "non chauffe"), "local non chauffé"),
        (("terre plein", "terreplein", "sur terre", "sur le sol", "dalle sur terre"), "terre-plein"),
        (("vide sanitaire",), "vide sanitaire"),
        (("sous sol", "cave"), "sous-sol / cave"),
        (("garage",), "local non chauffé : garage"),
        (("local chauffe", "chauffe", "logement en dessous", "appartement en dessous", "voisin du dessous", "logement", "appartement"),
         "local chauffé (logement en dessous)"),
        (("exterieur", "dehors", "porche", "passage"), "extérieur"),
    ],
    ("porte", "type"): [
        (("vitree",), "vitrée"),
        (("isolee", "isolante", "blindee"), "isolée"),
        (("pvc",), "PVC"),
        (("aluminium", "alu", "metal", "metallique", "acier"), "métal"),
        (("bois",), "bois"),
    ],
    ("porte", "donne_sur"): [
        (("palier", "cage d escalier", "parties communes", "couloir"), "palier (local non chauffé)"),
        (("exterieur", "dehors", "jardin", "rue"), "extérieur"),
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
        (("thermodynamique", "thermo"), "ballon thermodynamique"),
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
    (r"portes? d entree|portes? palieres?|portes? exterieures?|portes? de service|portes? du jardin", "porte", "la porte", "portes"),
    (r"plafonds?|toiture|toit", "plafond", "le plafond", "plafonds"),
    (r"planchers?|(?<!sous )sol|dalle", "plancher", "le plancher", "planchers"),
    (r"murs?|cloisons?|parois?", "mur", "le mur", "murs"),
]
PLURIELS = {"mur": "murs", "fenetre": "fenêtres", "porte": "portes", "emetteur": "radiateurs"}
_MOTS = re.compile("|".join(f"(?P<m{i}>\\b(?:{motif})\\b)" for i, (motif, *_reste) in enumerate(MOTS_ELEMENTS)))
_DESIGNE = re.compile(r"\bcelui (?:ci|la)\b|\bcelle (?:ci|la)\b")  # « celui-ci » : un nouvel élément
_DESIGNATION = "designation"  # type provisoire d'un « celui-ci », fixé d'après les valeurs dites
_NOUVEAU_FORT = {"autre", "deuxieme", "troisieme", "quatrieme", "cinquieme", "second", "seconde", "dernier"}
_NOUVEAU = {"ce", "cet", "cette", "ces", "un", "une"} | _NOUVEAU_FORT

_ISOLANTS = [
    ("laine de verre", "laine de verre"), ("laine de roche", "laine de roche"), ("laine minerale", "laine minérale"),
    ("polystyrene", "polystyrène"), ("polyurethane", "polyuréthane"), ("ouate", "ouate de cellulose"),
    ("fibre de bois", "fibre de bois"), ("liege", "liège"), ("laine", "laine"),
]
_ISOLATION = re.compile(r"\bisol|\biti\b|\bite\b|\bitr\b|\blaine\b|polystyrene|polyurethane|\bouate\b|doublage|fibre de bois|\bliege\b")
# Début de la partie « isolation » d'une clause, négation comprise (« pas isolé », « sans isolation »).
_DEBUT_ISOLATION = re.compile(r"(?:\b(?:pas|non|sans|aucune?)\s+(?:d\s+)?)?(?:" + _ISOLATION.pattern + ")")
_NE_SAIT_PAS = re.compile(
    r"\b(?:je (?:ne )?|j )?(?:sais|sait) (?:pas|plus)\b|\bje (?:ne )?c est pas\b|\b(?:chais|chai|che) pas\b|\bj en sais rien\b"
    r"|\baucune idee\b|\bon (?:ne )?sait pas\b|\binconnu|\bjsp\b")
# « Alu, enfin bois », « brique, non, parpaing » : c'est la dernière version dite qui compte.
_CORRECTION = re.compile(r"\b(?:enfin|plutot|pardon|je veux dire|c est a dire|non)\b(?!\s+(?:isol|chauff|concern))")
# « Je crois que c'est du parpaing » : la valeur est notée, avec le doute, pour l'écran de validation.
_DOUTE = re.compile(r"\bje (?:crois|pense|dirais|suppose)\b|\bpeut etre\b|\bprobablement\b|\bsans doute\b|\bil me semble\b")
_SANS_OBJET = re.compile(r"\bsans objet\b|\bpas concerne\b|\bnon concerne\b")
_ABSENCE = re.compile(r"\b(?:pas de|pas d|aucune?|il n y a pas de|il y a pas de|y a pas de)\s+(fenetres?|radiateurs?|chauffage|emetteurs?|convecteurs?|vmc|ventilation)\b")
_OUI = re.compile(r"^(?:oui|ouais|si|exact|exactement|il y en a|bien sur|tout a fait|absolument|ok|d accord|affirmatif"
                  r"|c est (?:bien )?ca|pareil|meme chose|identique)\b")
_NON = re.compile(r"^(?:non|nan|aucune?|pas du tout|il n y en a pas|y en a pas|c est tout|c est fini|fini|termine|rien)\b")
# « En tout trois fenêtres, toutes pareilles » : le nombre total d'un élément déjà décrit.
_TOTAL = re.compile(r"\ben tout\b|\bau total\b|\btoutes? (?:pareilles?|identiques?|les memes)\b|\btous (?:pareils|identiques|les memes)\b")
_PIECES = {
    "cuisine": "Cuisine", "sejour": "Séjour", "salon": "Salon", "salle a manger": "Salle à manger",
    "salle de bains": "Salle de bains", "salle de bain": "Salle de bains", "salle d eau": "Salle d'eau",
    "wc": "WC", "toilettes": "WC", "entree": "Entrée", "couloir": "Couloir", "degagement": "Dégagement",
    "bureau": "Bureau", "cellier": "Cellier", "buanderie": "Buanderie", "garage": "Garage", "cave": "Cave",
    "grenier": "Grenier", "combles": "Combles", "dressing": "Dressing", "chambre": "Chambre", "mezzanine": "Mezzanine",
}
_NOMS_PIECES = "|".join(sorted(_PIECES, key=len, reverse=True))
# « Ici c'est la cuisine », « on passe au salon ». Pas « c'est les combles » ni « donne dans le garage »,
# qui décrivent un plafond ou un mur.
_PIECE = re.compile(
    r"\b(?:ici c est|ici|on est dans|on entre dans|on passe (?:dans|a|au)|on va (?:dans|a|au)|on arrive dans|nous sommes dans|maintenant)\s+"
    r"(?:la |le |l |les |a la |au )?(" + _NOMS_PIECES + r")(?:\s+(\d+))?\b"
)
_NOM_PIECE = re.compile(r"\b(" + _NOMS_PIECES + r")(?:\s+(\d+))?\b")  # réponse à « Quelle est la pièce suivante ? »
_ANNEE = re.compile(r"\b(19[3-9]\d|20[0-3]\d)\b")


@dataclass
class Cible:
    """La dernière question posée : un champ d'un élément, ou une étape du parcours."""

    genre: str  # « champ », « presence », « suite », « pareil », « piece » ou « secondaire »
    type: str = ""
    champ: str = ""
    element_id: str | None = None
    source: str = ""  # pour « pareil » : la pièce dont on recopie le plafond ou le plancher

    @classmethod
    def depuis_code(cls, code: str, checklist: Checklist) -> "Cible | None":
        """« M1.isolation », « presence:fenetre », « suite:mur », « pareil:plafond:sejour »,
        « piece:suivante », « secondaire:emetteur.temperature » → Cible (None si inconnu)."""
        code = (code or "").strip()
        prefixe, _, reste = code.partition(":")
        if prefixe == "presence" and reste in TYPES:
            return cls("presence", reste, "presence")
        if prefixe == "suite" and reste in TYPES:
            return cls("suite", reste)
        if prefixe == "pareil":
            type_element, _, source = reste.partition(":")
            return cls("pareil", type_element, source=source) if type_element in TYPES and source in checklist.pieces else None
        if prefixe == "piece" and reste in ("suivante", "nom"):
            return cls("piece", champ=reste)
        if prefixe == "confirmer":
            # « J'ai compris eau chaude, c'est bien ça ? » : confirmer:E1.type=radiateur à eau
            designation, _, valeur = reste.partition("=")
            element_id, _, champ = designation.partition(".")
            try:
                element = checklist.trouver_element(element_id)
            except ValueError:
                return None
            if valeur and any(c.cle == champ for c in element.type_element.champs):
                return cls("confirmation", element.type, champ, element.id, source=valeur)
            return None
        if prefixe == "secondaire":
            type_element, _, champ = reste.partition(".")
            if type_element in TYPES and any(c.cle == champ for c in TYPES[type_element].champs):
                return cls("secondaire", type_element, champ)
            return None
        if "." in code and ":" not in code:
            element_id, champ = code.split(".", 1)
            try:
                element = checklist.trouver_element(element_id)
            except ValueError:
                return None
            if any(c.cle == champ for c in element.type_element.champs):
                return cls("champ", element.type, champ, element.id)
        return None

    @property
    def code(self) -> str:
        return {
            "champ": f"{self.element_id}.{self.champ}",
            "presence": f"presence:{self.type}",
            "suite": f"suite:{self.type}",
            "pareil": f"pareil:{self.type}:{self.source}",
            "piece": f"piece:{self.champ}",
            "confirmation": f"confirmer:{self.element_id}.{self.champ}={self.source}",
        }.get(self.genre, f"secondaire:{self.type}.{self.champ}")


@dataclass
class _Segment:
    type: str
    texte: str  # normalisé
    nombre: int | None
    nouveau: bool
    singulier: str
    pluriel: str
    total: bool = False  # « en tout trois fenêtres » : nombre total d'un élément déjà décrit
    nouveau_fort: bool = False  # « un autre mur », « le deuxième », « celui-là » : forcément un autre élément


@dataclass
class Extraction:
    actions: list[dict] = field(default_factory=list)
    devines: list[str] = field(default_factory=list)  # « ictérieur → extérieur »
    # Interprétation probable mais pas sûre : à faire confirmer (« J'ai compris eau chaude, c'est bien ça ? »).
    proposition: dict | None = None


def _motif_formes(formes: tuple[str, ...]) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(re.escape(f) for f in sorted(formes, key=len, reverse=True)) + r")\b")


_MOTIFS = {cle: [(_motif_formes(formes), valeur) for formes, valeur in liste] for cle, liste in VOCABULAIRE.items()}


def _morceaux(texte: str, longueur_max: int = 3) -> list[str]:
    """Groupes de 1 à 3 mots consécutifs (sans ponctuation), pour comparer à des formes de plusieurs mots."""
    mots = [m for m in texte.replace(",", " ").split() if not m.isdigit()]
    return [" ".join(mots[i:i + n]) for n in range(1, longueur_max + 1) for i in range(len(mots) - n + 1)]


def ressemblance(morceau: str, forme: str) -> float:
    """Ressemblance (0 à 1) par l'orthographe ou par le son, mots collés compris
    (« doublevitrage » ≈ « double vitrage », « oh est chaude » ≈ « eau chaude »)."""
    ecrit = SequenceMatcher(None, morceau.replace(" ", ""), forme.replace(" ", ""), autojunk=False).ratio()
    p1, p2 = phonetique(morceau), phonetique(forme)
    if min(len(morceau.replace(" ", "")), len(forme.replace(" ", ""))) <= 5:
        # Mots courts : le son doit être identique (« brik » = « brique »), sinon « allô » ressemblerait à « agglo ».
        son = 1.0 if p1 == p2 and len(p1) >= 2 else 0.0
    else:
        son = SequenceMatcher(None, p1, p2, autojunk=False).ratio() if min(len(p1), len(p2)) >= 2 else 0.0
    return max(ecrit, son)


SEUIL_TOLERANT = 0.9  # forme longue presque identique : comptée comme dite (« condensassion », « doublevitrage »)


def _premiere_valeur(type_element: str, champ: str, texte: str) -> str | None:
    """La première valeur du vocabulaire (de la plus précise à la plus générale) présente dans le texte.
    Si aucune n'y est telle quelle, une forme longue presque identique est acceptée (2e passage seulement :
    « local chauffé » ne doit jamais être pris pour « local non chauffé »)."""
    exacte = next((valeur for motif, valeur in _MOTIFS.get((type_element, champ), []) if motif.search(texte)), None)
    morceaux = _morceaux(texte)
    for formes, valeur in VOCABULAIRE.get((type_element, champ), []):
        if valeur == exacte:
            break  # rien de plus précis avant la valeur dite telle quelle
        longues = [f for f in formes if len(f.replace(" ", "")) >= 9]
        presque = any(ressemblance(m, f) >= SEUIL_TOLERANT for f in longues for m in morceaux if abs(len(m) - len(f)) <= 3)
        # Une valeur plus précise presque dite l'emporte sur une valeur générale dite exactement, si elle l'englobe :
        # « comble perdue » = combles perdus (pas « combles »), « chaudière à condensassion » = à condensation.
        if presque and (exacte is None or cle_texte(exacte) in cle_texte(valeur)):
            return valeur
    return exacte


# Petits mots qui ne portent pas de valeur : un groupe qui commence ou finit par l'un d'eux ne sert pas à
# deviner (« ça c'est » ressemblerait à « calcaire »). « Oh est chaude » reste comparé (« oh » … « chaude »).
_MOTS_VIDES = {
    "c", "ca", "ce", "cet", "cette", "est", "et", "es", "le", "la", "les", "l", "un", "une", "de", "du", "des", "d", "a", "au",
    "aux", "il", "elle", "on", "en", "y", "que", "qui", "se", "sa", "son", "ses", "ok", "oui", "non", "bon", "alors", "donc",
    "mais", "ou", "je", "tu", "j", "t", "m", "s", "n", "ne", "ici", "voila", "celui", "ci", "fait", "dit", "tout", "bien",
    "tres", "plus", "pas", "premier", "mur", "allo", "attends", "entends",
}


def _valeurs_dites(type_element: str, champ: str, texte: str) -> list[str]:
    """Valeurs différentes de ce champ dites telles quelles, dans l'ordre où elles sont dites."""
    trouvees: list[tuple[int, int, str]] = []
    for motif, valeur in _MOTIFS.get((type_element, champ), []):
        if (m := motif.search(texte)) and not any(debut <= m.start() < fin for debut, fin, _ in trouvees):
            trouvees.append((m.start(), m.end(), valeur))
    return list(dict.fromkeys(v for _, _, v in sorted(trouvees)))


def candidats(type_element: str, champ: str, texte: str) -> list[tuple[float, str, str]]:
    """Valeurs possibles du champ, de la plus ressemblante à la moins : (score, valeur, mots entendus)."""
    meilleurs: dict[str, tuple[float, str, str]] = {}
    morceaux = [m for m in _morceaux(texte) if len(m.replace(" ", "")) >= 2
                and m.split()[0] not in _MOTS_VIDES and m.split()[-1] not in _MOTS_VIDES]
    for formes, valeur in VOCABULAIRE.get((type_element, champ), []):
        for forme in formes:
            for morceau in morceaux:
                if len(forme) < 2 or abs(len(morceau) - len(forme)) > 3:
                    continue
                score = ressemblance(morceau, forme)
                if score > meilleurs.get(valeur, (0.0, "", ""))[0]:
                    meilleurs[valeur] = (score, valeur, morceau)
    return sorted(meilleurs.values(), reverse=True)


SEUIL_SUR, ECART_SUR, SEUIL_PROBABLE = 0.74, 0.12, 0.6


def _deviner(type_element: str, champ: str, texte: str) -> tuple[str, str, str] | None:
    """Mot mal entendu, interprété avec le vocabulaire du champ demandé : (« sur » ou « probable »,
    valeur, note). « Sûr » si un seul candidat ressemble nettement ; « probable » s'il y a un doute :
    on propose alors l'interprétation au lieu de faire répéter."""
    liste = candidats(type_element, champ, texte)
    if not liste or liste[0][0] < SEUIL_PROBABLE:
        return None
    score, valeur, entendu = liste[0]
    second = liste[1][0] if len(liste) > 1 else 0.0
    niveau = "sur" if score >= SEUIL_SUR and score - second >= ECART_SUR else "probable"
    return niveau, valeur, f"deviné : « {entendu} » → {valeur}"


# --- Parois : murs, plafonds, planchers --------------------------------------------------------------

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


def _valeurs_paroi(type_element: str, texte: str) -> dict[str, str]:
    valeurs: dict[str, str] = {}
    mur = type_element == "mur"
    materiaux = "|".join(re.escape(f) for formes, _ in VOCABULAIRE[("mur", "materiau")] for f in formes)
    for clause in re.split(r"\s*,\s*|\s+et\s+", texte):
        if not clause:
            continue
        coupure = _DEBUT_ISOLATION.search(clause)
        avant, isolation = (clause[: coupure.start()], clause[coupure.start():]) if coupure else (clause, "")
        if isolation and "isolation" not in valeurs and (v := _valeur_isolation(isolation)):
            valeurs["isolation"] = v
        if mur and "long" in avant and "longueur" not in valeurs:
            if m := re.search(r"\b(\d+(?:\.\d+)?)\s*(?:m|metres?)\b(?:\s*(\d{1,2})\b)?", avant):
                valeurs["longueur"] = f"{m.group(1).replace('.', ',')}{',' + m.group(2) if m.group(2) else ''} m"
            continue
        if mur and "materiau" not in valeurs and (v := _premiere_valeur("mur", "materiau", avant)):
            valeurs["materiau"] = v
        if mur and "epaisseur" not in valeurs:
            m = (re.search(r"\b(\d{1,3}(?:\.\d)?)\s*(?:cm|centimetres?)\b", avant)
                 or re.search(rf"\b(?:{materiaux})\s+(?:de\s+)?(\d{{1,3}})\b(?!\s*(?:m\b|metres?|ans?\b|\.\d))", avant)
                 or re.search(r"\b(\d{1,3})\s*(?:d\s+)?epaisseurs?\b|epaisseur\D{0,12}(\d{1,3})\b", avant)
                 # « le mur il fait trente » (pas « il fait 4 mètres de long », traité plus haut)
                 or re.search(r"\bfait\s+(?:de\s+)?(\d{1,3})\b(?!\s*(?:m\b|metres?|\.\d))", avant))
            if m:
                valeurs["epaisseur"] = f"{next(g for g in m.groups() if g)} cm"
        if "donne_sur" not in valeurs and (v := _premiere_valeur(type_element, "donne_sur", avant)):
            valeurs["donne_sur"] = v
    return valeurs


def _valeurs(type_element: str, texte: str) -> dict[str, str]:
    """Toutes les valeurs reconnues pour un élément de ce type dans ce morceau de phrase."""
    if type_element in PAROIS:
        return _valeurs_paroi(type_element, texte)
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
        total = bool(_TOTAL.search(" ".join(texte[:debut].split()[-5:])))
        nouveau_fort = bool(set(precedent) & _NOUVEAU_FORT) or bool(_DESIGNE.match(texte, debut))
        debuts.append(debut_segment)
        segments.append(_Segment(type_element, "", nombre, nouveau, singulier, pluriel, total, nouveau_fort))
    for k, segment in enumerate(segments):
        segment.texte = texte[debuts[k]: debuts[k + 1] if k + 1 < len(segments) else len(texte)]
        segment.total = segment.total or bool(_TOTAL.search(segment.texte))
        if segment.type == _DESIGNATION:
            # « Celui-là, béton 18 cm » : l'élément que décrivent les valeurs dites (un mur par défaut, ou le
            # type de la dernière question s'il s'agit d'un élément de la pièce).
            candidats = list(dict.fromkeys(
                ([type_courant] if type_courant and TYPES[type_courant].niveau == "piece" else []) + ["mur", "fenetre", "emetteur"]))
            segment.type = max(candidats, key=lambda t: len(_valeurs(t, segment.texte)))
            segment.singulier, segment.pluriel = TYPES[segment.type].designation, PLURIELS.get(segment.type, TYPES[segment.type].nom + "s")
    return (texte[: debuts[0]] if debuts else texte), segments


def _existants(checklist: Checklist, type_element: str) -> list[Element]:
    piece = checklist.piece_courante if TYPES[type_element].niveau == "piece" else None
    return [e for e in checklist.elements_de(piece) if e.type == type_element]


def _element_vise(checklist: Checklist, segment: _Segment, valeurs: dict[str, str]) -> Element | None:
    """L'élément déjà connu que ce morceau de phrase décrit, ou None pour en créer un nouveau."""
    if segment.type in TOUJOURS_PRESENTS:
        return checklist.element_de_piece(segment.type)
    existants = _existants(checklist, segment.type)
    if not existants:
        return None

    def conflit(element: Element) -> bool:
        return any(element.valeur(c) is not None and cle_texte(element.valeur(c).valeur) != cle_texte(v) for c, v in valeurs.items())

    if segment.total and len(existants) == 1 and not conflit(existants[0]):
        return existants[0]  # « en tout trois fenêtres, toutes pareilles » : la fenêtre déjà décrite, ×3
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


def _nouvelle_description(checklist: Checklist, type_element: str, nombre: int | None, singulier: str = "", pluriel: str = "") -> str:
    numero = sum(e.type == type_element for e in checklist.elements) + 1
    singulier = singulier or TYPES[type_element].designation
    pluriel = pluriel or PLURIELS.get(type_element, TYPES[type_element].nom + "s")
    description = f"les {nombre} {pluriel}" if (nombre or 1) > 1 else f"{singulier} {numero}"
    if any(cle_texte(e.description) == cle_texte(description) for e in checklist.elements):
        description += f" n°{numero}"  # deux groupes de « 3 fenêtres » restent distincts
    return description


def extraire(phrase: str, checklist: Checklist, cible: Cible | None = None) -> Extraction:
    """Actions à appliquer pour cette phrase (citation = la phrase entière)."""
    resultat = Extraction()
    texte = normaliser(phrase)
    if not texte.strip(" ,"):
        return resultat

    def action(outil: str, **donnees) -> None:
        resultat.actions.append({"outil": outil, "citation": phrase, **donnees})

    piece = _PIECE.search(texte) or (_NOM_PIECE.search(texte) if cible and cible.genre == "piece" else None)
    if piece:
        action("piece_courante", nom=_PIECES[piece.group(1)] + (f" {piece.group(2)}" if piece.group(2) else ""))
        texte = texte[: piece.start()] + texte[piece.end():]

    # « Je ne sais pas » / « sans objet » : réponse à la dernière question, on passe à la suite. Mais « je sais
    # pas trop, je crois que c'est du parpaing » donne une valeur : elle l'emporte.
    valeur_dite = cible is not None and cible.genre in ("champ", "secondaire", "confirmation") and cible.champ in _valeurs(cible.type, texte)
    if cible and _NE_SAIT_PAS.search(texte) and not valeur_dite:
        if cible.genre in ("champ", "confirmation"):
            action("enregistrer_reponse", element_id=cible.element_id or "", type=cible.type, champ=cible.champ, valeur=VALEUR_INCONNUE)
        elif cible.genre == "secondaire":  # détail secondaire : plus jamais demandé
            for element in checklist.manques_secondaires().get((cible.type, cible.champ), []):
                action("enregistrer_reponse", element_id=element.id, type=cible.type, champ=cible.champ, valeur=VALEUR_INCONNUE)
        return resultat
    if cible and cible.genre == "champ" and _SANS_OBJET.search(texte):
        action("marquer_sans_objet", element_id=cible.element_id or "", type=cible.type, champ=cible.champ)
        return resultat
    for m in _ABSENCE.finditer(texte):
        mot = m.group(1)
        type_element = "fenetre" if mot.startswith("fenetre") else "ventilation" if mot in ("vmc", "ventilation") else "emetteur"
        action("marquer_sans_objet", type=type_element, champ="presence", element_id="")
    texte = _ABSENCE.sub(" ", texte)

    type_courant = cible.type if cible and cible.type in TYPES else None
    debut, segments = _segments(texte, type_courant)
    if type_courant == "ecs":
        # « Par la chaudière », en réponse à une question sur l'eau chaude : c'est l'eau chaude qui est décrite.
        for segment in segments:
            if segment.type == "chauffage":
                segment.type, segment.singulier, segment.pluriel = "ecs", TYPES["ecs"].designation, "eaux chaudes"

    # Réponse courte à la dernière question : le début de phrase (avant tout autre élément cité).
    if cible:
        _reponse_a_la_cible(checklist, cible, debut, segments, resultat, action, phrase)

    cites: set[str] = set()  # types déjà annoncés dans cette phrase
    nouveaux: dict[str, int] = {}  # éléments créés par cette phrase, par type (pour les numéroter)
    for segment in segments:
        if segment.type == "mur":
            segment.nombre = None  # « il y a 4 murs » : chaque mur a ses caractéristiques, jamais de groupe
        valeurs = _valeurs(segment.type, segment.texte)
        simple_mention = not valeurs and not segment.nombre
        # « une fenêtre ici », « et un radiateur ici » : on montre un élément déjà annoncé ; « ce mur » seul :
        # Claude et l'image s'en chargent ; plafond et plancher existent toujours. On ne crée un élément sur une
        # simple mention que s'il n'y en a aucun.
        if simple_mention and (segment.type in ("mur", *TOUJOURS_PRESENTS) or segment.type in cites or _existants(checklist, segment.type)):
            continue
        cites.add(segment.type)
        if cible and cible.genre in ("champ", "confirmation") and segment.type == cible.type and not segment.nouveau_fort:
            # « Le mur 1 donne sur quoi ? » « C'est une cloison » : la réponse décrit l'élément de la question.
            vise = checklist.trouver_element(cible.element_id)
        else:
            vise = _element_vise(checklist, segment, valeurs)
        if vise is None:
            description = _nouvelle_description(checklist, segment.type, segment.nombre, segment.singulier, segment.pluriel)
            if nouveaux.get(segment.type):
                description += f" n°{nouveaux[segment.type] + 1}"
            nouveaux[segment.type] = nouveaux.get(segment.type, 0) + 1
            action("signaler_element", type=segment.type, description=description, nombre=segment.nombre or 1, source="voix")
            reference = {"element_id": "", "description": description}
        else:
            if segment.nombre and segment.nombre != vise.nombre:
                action("signaler_element", type=segment.type, description=vise.description, nombre=segment.nombre, source="voix")
            reference = {"element_id": vise.id, "description": ""}
        for champ, valeur in valeurs.items():
            action("enregistrer_reponse", type=segment.type, champ=champ, valeur=valeur, **reference)
    _energie_de_la_chaudiere(checklist, resultat, action)
    return resultat


def _energie_de_la_chaudiere(checklist: Checklist, resultat: Extraction, action) -> None:
    """Eau chaude faite « par la chaudière » : son énergie est celle de la chaudière déjà décrite
    (déduction notée comme telle, avec sa source, pour l'écran de validation)."""
    systeme = next((a for a in resultat.actions if a["outil"] == "enregistrer_reponse" and a["type"] == "ecs"
                    and a["champ"] == "systeme" and "chaudiere" in cle_texte(a["valeur"])), None)
    if systeme is None or any(a.get("type") == "ecs" and a.get("champ") == "energie" for a in resultat.actions):
        return
    chaudiere = next((e for e in checklist.elements_de(None) if e.type == "chauffage" and e.valeur("energie")
                      and "chaudiere" in cle_texte((e.valeur("type") or e.valeur("energie")).valeur)), None)
    if chaudiere is not None:
        action("enregistrer_reponse", type="ecs", champ="energie", valeur=chaudiere.valeur("energie").valeur,
               element_id=systeme.get("element_id", ""), description=systeme.get("description", ""),
               note=f"déduit : même chaudière que le chauffage ({chaudiere.id})")


def _reponse_a_la_cible(checklist: Checklist, cible: Cible, texte: str, segments: list[_Segment], resultat: Extraction, action,
                        phrase: str) -> None:
    reponse = texte.strip(" ,")
    if cible.genre in ("presence", "suite"):
        # « Oui, trois fenêtres en PVC » : c'est la suite de la phrase qui décrit l'élément.
        if any(s.type == cible.type for s in segments):
            return
        valeurs = _valeurs(cible.type, texte) if reponse else {}
        if _NON.match(reponse) and not valeurs:
            if cible.genre == "suite":
                action("cloturer", type=cible.type)  # « pas d'autre mur »
            elif cible.type != "mur":
                action("marquer_sans_objet", type=cible.type, champ="presence", element_id="")
            return
        nombre = re.match(r"^(?:oui\s*,?\s*)?(\d+)\b", reponse)
        if _OUI.match(reponse) or nombre or valeurs:
            n = int(nombre.group(1)) if nombre and 1 <= int(nombre.group(1)) <= 50 and cible.type != "mur" else None
            description = _nouvelle_description(checklist, cible.type, n)
            action("signaler_element", type=cible.type, description=description, nombre=n or 1, source="voix")
            for champ, valeur in valeurs.items():
                action("enregistrer_reponse", element_id="", type=cible.type, champ=champ, valeur=valeur, description=description)
        return
    if cible.genre == "pareil":
        if _OUI.match(reponse):
            action("copier", type=cible.type, piece_source=cible.source)
        element = checklist.element_de_piece(cible.type)
        if element is not None:
            for champ, valeur in _valeurs(cible.type, texte).items():
                action("enregistrer_reponse", element_id=element.id, type=cible.type, champ=champ, valeur=valeur)
        return
    if cible.genre == "piece" or not reponse:
        return
    # « Alu, enfin bois » : on garde la dernière version dite (si elle contient une valeur).
    corrige = _CORRECTION.split(texte)[-1]
    if corrige.strip(" ,") and corrige != texte and (_valeurs(cible.type, corrige) or candidats(cible.type, cible.champ, corrige)):
        texte = corrige
    doute = f"dit avec un doute : « {phrase} »" if _DOUTE.search(reponse) else ""
    if cible.genre == "secondaire":
        # Une seule réponse pour tout le logement : elle vaut pour tous les éléments concernés.
        valeur = _valeurs(cible.type, texte).get(cible.champ)
        if valeur is None and cible.champ == "annee" and (m := re.search(r"\b(\d{4})\b", texte)):
            valeur = m.group(1)
        if valeur is None and (devine := _deviner(cible.type, cible.champ, texte)) and devine[0] == "sur":
            valeur = devine[1]
            resultat.devines.append(devine[2])
        if valeur is not None:
            for element in checklist.manques_secondaires().get((cible.type, cible.champ), []):
                action("enregistrer_reponse", element_id=element.id, type=cible.type, champ=cible.champ, valeur=valeur)
        return
    if not cible.element_id:
        return
    if cible.genre == "confirmation":
        if _OUI.match(reponse):  # « J'ai compris eau chaude, c'est bien ça ? » « Oui. »
            action("enregistrer_reponse", element_id=cible.element_id, type=cible.type, champ=cible.champ, valeur=cible.source,
                   note=f"confirmé : « {cible.source} »")
            return
        if _NON.match(reponse) and not _valeurs(cible.type, texte) and not candidats(cible.type, cible.champ, _CORRECTION.split(texte)[-1]):
            return  # « Non. » sans autre valeur : on n'insiste pas
    if cible.champ == "isolation":
        # Toute la réponse parle de l'isolation : « 10 cm » est l'épaisseur de l'isolant, pas du mur.
        v = ("non isolé" if _NON.match(reponse) else _valeur_isolation(texte) or ("isolé" if _OUI.match(reponse) else None))
        valeurs = {"isolation": v} if v else {}
    else:
        valeurs = _valeurs(cible.type, texte)
    notes: dict[str, str] = {}
    dites = _valeurs_dites(cible.type, cible.champ, texte)
    if len(dites) > 1 and cible.champ in valeurs:
        # « Bois… ou alu ? » : deux valeurs différentes, sans correction : on propose la dernière dite.
        del valeurs[cible.champ]
        resultat.proposition = {"outil": "enregistrer_reponse", "citation": phrase, "element_id": cible.element_id,
                                "type": cible.type, "champ": cible.champ, "valeur": dites[-1],
                                "note": f"plusieurs valeurs dites ({', '.join(dites)}) : la dernière, confirmée"}
    elif cible.champ not in valeurs:
        if cible.champ == "epaisseur" and (m := re.search(r"\b(\d{1,3}(?:\.\d)?)\b(?!\s*(?:m\b|metres?))", texte)):
            valeurs["epaisseur"] = f"{m.group(1)} cm"
        elif cible.champ == "annee" and (m := re.search(r"\b(\d{4})\b", texte)):
            valeurs["annee"] = m.group(1)
        elif devine := _deviner(cible.type, cible.champ, texte):
            niveau, valeur, note = devine
            resultat.devines.append(note)
            if niveau == "sur":
                valeurs[cible.champ], notes[cible.champ] = valeur, note
            else:  # doute : on propose l'interprétation la plus probable au lieu de faire répéter
                resultat.proposition = {"outil": "enregistrer_reponse", "citation": phrase,
                                        "element_id": cible.element_id, "type": cible.type, "champ": cible.champ,
                                        "valeur": valeur, "note": note}
    for champ, valeur in valeurs.items():
        note = " ; ".join(n for n in (notes.get(champ, ""), doute if champ == cible.champ else "") if n)
        action("enregistrer_reponse", element_id=cible.element_id, type=cible.type, champ=champ, valeur=valeur, **({"note": note} if note else {}))

