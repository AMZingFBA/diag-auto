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

from .checklist import (ORIENTABLES, PAROIS, TOUJOURS_PRESENTS, TYPES, VALEUR_INCONNUE, Checklist, Element, cle_texte, description_auto, nom_de,
                        nom_groupe)
from .groupes import Decoupage, Partie, decouper
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
# Mots qui ne doivent jamais disparaître comme un faux départ : « pas parpaing » n'est pas un bégaiement, ni
# « il y a aussi » (« a » n'est pas le début raté de « aussi »).
_JAMAIS_FAUX_DEPART = {"pas", "non", "sans", "ne", "ni", "a", "y", "l", "d", "de", "du", "des", "la", "le", "les", "un", "une",
                       "en", "il", "on", "ce", "ces", "se", "sa", "son", "et", "est", "sur", "par", "au", "aux", "ou", "dans"}


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
        # (pièces voisines du logement, ajoutées plus bas : « il donne derrière sur des toilettes »)
        (("local chauffe", "piece chauffee", "autre piece", "une piece", "interieur du logement", "interieur de la maison",
          "mur interieur", "interieur", "cloison"), "local chauffé"),
        (("voisin", "voisins", "mitoyen", "mitoyenne", "autre maison", "maison d a cote", "maison voisine"), "local chauffé (voisin)"),
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
        (("chaudiere basse temperature", "basse temperature"), "chaudière basse température"),
        (("chaudiere standard", "standard", "classique"), "chaudière standard"),
        (("pompe a chaleur air eau", "pac air eau", "air eau"), "PAC air/eau"),
        (("pompe a chaleur air air", "pac air air", "air air", "climatisation reversible"), "PAC air/air"),
        (("pompe a chaleur", "pac"), "pompe à chaleur"),
        (("insert", "foyer ferme"), "insert"),
        (("poele",), "poêle"),
        (("chaudiere",), "chaudière"),
        (("convecteur", "convecteurs"), "convecteurs électriques"),
        (("panneau rayonnant", "panneaux rayonnants"), "panneaux rayonnants électriques"),
        (("radiateur electrique", "radiateurs electriques", "effet joule", "joule", "electrique direct"),
         "radiateurs électriques (effet Joule)"),
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

# Une autre pièce du logement est un local chauffé (test réel de Noah : « il donne derrière sur des toilettes »).
# « Sur les toilettes », « côté cuisine » passent avant les autres valeurs ; le nom seul (réponse courte « Les
# toilettes. ») passe en dernier : « le mur de la chambre donne dehors » donne sur l'extérieur.
_PIECES_VOISINES = [
    (("toilettes", "wc"), "WC"), (("salle de bains", "salle de bain", "salle d eau"), "salle de bains"), (("cuisine",), "cuisine"),
    (("chambre", "chambres"), "chambre"), (("sejour", "salon", "salle a manger"), "séjour"), (("couloir", "degagement"), "couloir"),
    (("entree",), "entrée"), (("bureau",), "bureau"),
]
_avant_le_local_chauffe = next(i for i, (formes, _) in enumerate(VOCABULAIRE[("mur", "donne_sur")]) if "local chauffe" in formes)
VOCABULAIRE[("mur", "donne_sur")][_avant_le_local_chauffe:_avant_le_local_chauffe] = [
    (tuple(f"{p} {a}{m}" for m in mots for p in ("sur", "vers", "cote", "derriere") for a in ("", "la ", "le ", "les ", "l ", "des ", "une ")),
     f"local chauffé : {nom}") for mots, nom in _PIECES_VOISINES]
VOCABULAIRE[("mur", "donne_sur")] += [(mots, f"local chauffé : {nom}") for mots, nom in _PIECES_VOISINES]

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

# --- Groupes, exceptions, références (étape 4 de Noah) ---
# « Le deuxième mur », « la fenêtre 2 » : un élément déjà décrit (s'il existe), sinon un nouveau.
# (« le dernier mur » reste un nouveau mur : c'est le dernier qu'on décrit.)
_ORDINAUX = {"premier": 1, "premiere": 1, "1er": 1, "1ere": 1, "deuxieme": 2, "second": 2, "seconde": 2, "troisieme": 3,
             "quatrieme": 4, "cinquieme": 5, "sixieme": 6, "septieme": 7, "huitieme": 8}
_NUMERO = re.compile(r"\s+(\d{1,2})\b(?!\s*(?:cm|mm|m\b|metres?|centimetres?|ans?\b|par\b|x\b|sur\b|\.\d))")
# « Un des radiateurs est électrique », « 2 d'entre elles sont en bois » : une partie d'un groupe déjà décrit.
_UN_DES = re.compile(r"\b(l un|l une|un|une|\d{1,2})\s+(?:des|d entre (?:eux|elles)|de ces|parmi (?:les|ces))\s*$")
# « En fait il y a 3 radiateurs, pas 2 » : le nombre d'un groupe déjà décrit est corrigé (et signalé).
_CORRECTION_NOMBRE = re.compile(r"\ben fait\b|\bfinalement\b|\bpas (\d{1,2})\b|\bplutot\b|\bje me suis trompe\b|\bje corrige\b")
# « Le radiateur de la salle de bains », « dans la cuisine, il y a aussi un radiateur » : un élément d'une autre pièce.
_LIEU = re.compile(r"\b(?:de|du|dans|des)\s+(?:la |le |l |les )?(" + _NOMS_PIECES + r")(?:\s+(\d+))?\b")
_ENTRE_LIEU_ET_ELEMENT = re.compile(r"[\s,]*(?:(?:et|il y a|y a|aussi|on a|il y en a|encore|egalement|1|un|une|\d{1,2})[\s,]*)*")
# « Toutes les fenêtres du logement… » : une règle pour tout le logement, et pas seulement pour la pièce.
_LOGEMENT = re.compile(r"\b(?:du logement|de la maison|de l appartement|partout|dans tout(?:e)? (?:le logement|la maison|l appartement)"
                       r"|(?:dans|de) toutes les pieces|de tout le logement)\b")
# « Pareil », « comme les autres » : la même valeur que l'élément du même type décrit juste avant.
_PAREIL = re.compile(r"^(?:(?:oui|c est|ce sont|elles? sont|ils? sont|elles? ont|ils? ont|il a|elle a)\s*,?\s*)?"
                     r"(?:pareil(?:le)?s?|idem|(?:la )?meme chose|les memes|la meme|le meme|aussi"
                     r"|comme (?:les |la |le |l )?(?:autres?|precedente?s?|d avant))\b")
_TOUS = re.compile(r"\b(?:tous|toutes)\b")
# « Toutes, des volets roulants » (et pas « tous les deux », qui ne parle que du groupe de la question).
_TOUS_LES_AUTRES = re.compile(r"\b(?:tous|toutes)\b(?!\s+les\s+\d)")
# « Le radiateur sous la fenêtre » : la fenêtre situe le radiateur, ce n'est pas un élément décrit.
_SITUE = re.compile(r"\b(?:sous|pres d[eu]?|a cote d[eu]?|au dessus d[eu]?|en dessous d[eu]?|devant|derriere|entre|contre"
                    r"|le long d[eu]?|face a|en face d[eu]?|a gauche d[eu]?|a droite d[eu]?)\s+(?:la |le |les |l |un |une |des |chaque )?$"
                    r"|\b(?:mur|cloison)\s+(?:avec|de|du)\s+(?:la |le |l )?$")  # « le mur avec la fenêtre » : un repère du mur

# --- Murs : repères et phrases globales (test réel de Noah, étape 5) ---
# « Le mur avec la télé », « le mur du fond » : ce qui permet au diagnostiqueur de savoir de quel mur on parle.
_REPERES = {
    "tele": "avec la télé", "television": "avec la télé", "canape": "avec le canapé", "cheminee": "avec la cheminée",
    "bibliotheque": "avec la bibliothèque", "lit": "avec le lit", "evier": "avec l'évier", "placard": "avec le placard",
    "placards": "avec les placards", "armoire": "avec l'armoire", "frigo": "avec le frigo", "buffet": "avec le buffet",
    "miroir": "avec le miroir", "tableau": "avec le tableau", "lavabo": "avec le lavabo", "douche": "de la douche",
    "baignoire": "de la baignoire", "cuisiniere": "avec la cuisinière", "four": "avec le four", "escalier": "de l'escalier",
    "porte": "de la porte", "fenetre": "de la fenêtre", "baie vitree": "de la baie vitrée", "baie": "de la baie vitrée",
    "porte fenetre": "de la porte-fenêtre", "radiateur": "du radiateur",
}
_POSITIONS = {"du fond": "du fond", "de gauche": "de gauche", "de droite": "de droite", "d en face": "d'en face",
              "en face": "d'en face", "cote rue": "côté rue", "cote jardin": "côté jardin", "cote cour": "côté cour"}
_REPERE = re.compile(
    r"^\s*(?:qui est |qu on voit |ici )?(?:(?:avec|ou il y a|ou est|de|du|derriere)\s+(?:la |le |l |les |un |une )?("
    + "|".join(sorted(_REPERES, key=len, reverse=True)) + r")\b|(" + "|".join(sorted(_POSITIONS, key=len, reverse=True)) + r")\b)")
# « Cette pièce fait 4 murs », « il y a 4 murs », « 4 murs en tout ».
_NOMBRE_MURS = re.compile(r"\bpiece\b[^,]{0,25}?\b(\d{1,2})\s+murs\b|\bil y a\s+(\d{1,2})\s+murs\b"
                          r"|\b(\d{1,2})\s+murs\s+(?:en tout|au total|dans (?:la|cette) piece)\b")
# « Il y a juste un mur qui donne sur l'extérieur » : pas un mur de plus, mais le seul mur de ce genre.
_UN_SEUL_MUR = re.compile(r"\b(?:il y a\s+)?(?:juste|seulement|uniquement|qu|que)\s+(?:un|1)\s+(?:seul\s+)?mur\b.*?"
                          r"(?=,|\ble reste\b|\btous les autres\b|\bles autres\b|$)")
# « Le reste donne sur l'intérieur ou les voisins » : tous les autres murs, d'un coup.
_RESTE_MURS = re.compile(r"\b(?:le reste(?: des murs)?|tous les autres(?: murs)?|les autres murs|les murs restants|les autres)\b")
# « Pareil pour celui-là » : un nouvel élément qui a les mêmes valeurs que le précédent.
_PAREIL_POUR = re.compile(r"\b(?:c est )?(?:pareil|idem|(?:la )?meme chose)\s+pour\s+(celui (?:ci|la)|ce mur|cet autre mur|l autre"
                          r"|le suivant|le mur suivant|celle (?:ci|la)|cette fenetre|la suivante|l autre fenetre)\b")
# Le diagnostiqueur pose une question à l'assistant.
_DEMANDE_MANQUES = re.compile(r"\bil (?:te|vous) faut quoi\b|\bqu est ce qu il (?:te |vous )?faut\b|\bqu est ce qui (?:te |vous )?manque\b"
                              r"|\bil (?:te |vous )?manque quoi\b|\bquoi d autre\b|\bde quoi (?:tu as|as tu|vous avez) besoin\b"
                              r"|\btu as besoin de quoi\b|\btu veux savoir quoi\b")
_DEMANDE_LEQUEL = re.compile(r"^\s*(?:c est |mais )?(?:quel|lequel|laquelle|quelle|de quel|c est lequel)(?:\s+(?:mur|fenetre|radiateur|porte))?"
                             r"\s*,?\s*$|\bc est quel (?:mur|fenetre|radiateur)\b|\bde quel (?:mur|radiateur)\b")
# --- Orientation dite (étape 6) ---
# « est » n'est l'orientation que si rien ne le suit qui en ferait le verbe : « le mur est donne dehors », mais pas
# « le mur est en brique ».
_EST = r"est(?=\s*(?:,|$|donne(?:nt)?\b|qui\b|il\b|celui\b|celle\b|avec\b|c\b|est\b|et\b|aussi\b|lui\b))"
# « le mur nord », « la baie plein sud », « le mur côté est » (juste après le nom de l'élément).
_ORIENTATION_APRES_MOT = re.compile(r"^\s*(?:(?:cote|plein|au|a l|oriente|orientee|expose|exposee)\s+)?(nord|sud|ouest|" + _EST + r")")
# « ce mur est au nord », « il donne plein sud », « elle est orientée à l'est ».
_EST_ORIENTE = re.compile(r"\b(?:est|donne(?:nt)?|se trouve|regarde|fait face)\s+(?:(?:oriente|orientee|expose|exposee|plein|vers|face)\s+)*"
                          r"(?:au |a l |le |l )?(nord|sud|ouest|est)\b")
# Réponse à « Ce mur est orienté nord, sud, est ou ouest ? » : « Sud. », « plein sud », « à l'est », « Est. ».
_POINT_REPONDU = re.compile(r"\b(nord|sud|ouest)\b|(?:^|\b(?:plein|a l|vers l|cote|l)\s+)(est)\b")
# « C'est le mur ouest », « non, c'est le mur ouest » : l'orientation du mur dont on parle.
_C_EST = re.compile(r"(?:^|\b)(?:non\s*,?\s*)?(?:en fait\s*,?\s*)?(?:c est|ca c est|ici c est|voila)\s+(?:le|la)?\s*$")
# « En fait », « non », « pas » : le diagnostiqueur corrige l'élément dont on parle, il n'en décrit pas un autre.
_SE_CORRIGE = re.compile(r"\ben fait\b|\bfinalement\b|\bplutot\b|\bpardon\b|\bje me suis trompe\b|\bje corrige\b|\bnon\b|\bpas\b")
# Question ou longue phrase : on ne devine pas un mot mal entendu (« il te faut quoi d'être… » n'est pas « tuffeau »).
MOTS_POUR_DEVINER = 4


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
        if prefixe == "orientation":  # « Ce mur est orienté nord, sud, est ou ouest ? »
            try:
                element = checklist.trouver_element(reste)
            except ValueError:
                return None
            return cls("orientation", element.type, "orientation", element.id)
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
            "orientation": f"orientation:{self.element_id}",
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
    debut: int = 0  # position dans la phrase
    fin_mot: int = 0  # fin du mot de l'élément, dans le texte du segment (« 9 radiateurs| électriques… »)
    rang: tuple[str, int] | None = None  # (« ordinal », 2) pour « le deuxième mur », (« numero », 5) pour « le mur 5 »
    partie_de: int | None = None  # « un des radiateurs » : 1
    tous: bool = False  # « tous les radiateurs », « toutes les fenêtres »
    correction: bool = False  # « en fait », « finalement », « pas 2 » : un nombre corrigé
    ancien_nombre: int | None = None  # « …, pas 2 »


@dataclass
class Extraction:
    actions: list[dict] = field(default_factory=list)
    devines: list[str] = field(default_factory=list)  # « ictérieur → extérieur »
    # Interprétation probable mais pas sûre : à faire confirmer (« J'ai compris eau chaude, c'est bien ça ? »).
    proposition: dict | None = None
    # Le diagnostiqueur demande quelque chose : « manques » (« il te faut quoi d'autre ? »), « lequel » (« quel mur ? »).
    demande: str = ""


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


def valeur_normalisee(type_element: str, champ: str, valeur: str) -> str:
    """Valeur libre (proposée par Claude) ramenée au vocabulaire du champ quand elle y correspond : « toilettes »
    → « local chauffé : WC ». Sans correspondance, elle reste telle quelle."""
    liste = VOCABULAIRE.get((type_element, champ))
    if not liste or cle_texte(valeur) in {cle_texte(v) for _, v in liste}:
        return valeur
    return _premiere_valeur(type_element, champ, normaliser(valeur)) or valeur


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
            mesures = re.sub(r"\b(\d+)\s*m\s*(\d{1,2})\b(?!\s*(?:cm|m)\b)", r"\1.\2 m", texte)  # « 1 m 20 » → 1.20 m
            m = re.search(r"\b(\d+(?:\.\d+)?)\s*(m|cm)?\s*(?:par|sur|x|fois)\s*(\d+(?:\.\d+)?)\s*(m|cm)?\b", mesures)
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
        if reperes and _SITUE.search(texte[: m.start()]):
            continue  # « le radiateur sous la fenêtre est électrique » : la phrase parle encore du radiateur
        reperes.append((m.start(), m.end(), type_element, singulier, pluriel))
    for m in _DESIGNE.finditer(texte):
        if not any(a <= m.start() < b for a, b, *_ in reperes):
            reperes.append((m.start(), m.end(), _DESIGNATION, "", ""))  # type choisi ensuite, d'après les valeurs dites
    reperes.sort()
    segments: list[_Segment] = []
    debuts = []
    fins = []
    lu = list(texte)  # texte où les numéros de référence (« le mur 5 ») sont effacés avant de lire les valeurs
    for debut, fin, type_element, singulier, pluriel in reperes:
        avant = texte[:debut]
        precedent = avant.split()[-3:]
        nombre = None
        debut_segment = debut
        partie_de = None
        if m := _UN_DES.search(avant):  # « un des radiateurs » : une partie d'un groupe, pas un nouveau
            partie_de = int(m.group(1)) if m.group(1).isdigit() else 1
            debut_segment = m.start()
        elif precedent and precedent[-1].isdigit() and 1 <= int(precedent[-1]) <= 50:
            nombre = int(precedent[-1])
            debut_segment = texte.rfind(precedent[-1], 0, debut)
        rang = None
        if precedent and precedent[-1] in _ORDINAUX:
            rang = ("ordinal", _ORDINAUX[precedent[-1]])
        elif not texte[debut:fin].endswith(("s", "x")) and (m := _NUMERO.match(texte, fin)):
            rang = ("numero", int(m.group(1)))
            lu[m.start(1):m.end(1)] = " " * (m.end(1) - m.start(1))
        nouveau = (bool(set(precedent) & _NOUVEAU) or bool(_DESIGNE.match(texte, debut)) or (nombre or 0) > 1) and not partie_de
        total = bool(_TOTAL.search(" ".join(avant.split()[-5:])))
        nouveau_fort = (bool(set(precedent) & _NOUVEAU_FORT) or bool(_DESIGNE.match(texte, debut))) and not partie_de
        debuts.append(debut_segment)
        fins.append(fin)
        segments.append(_Segment(type_element, "", nombre, nouveau, singulier, pluriel, total, nouveau_fort, debut_segment,
                                 rang=rang, partie_de=partie_de, tous=bool(_TOUS.search(" ".join(avant.split()[-3:])))))
    lu = "".join(lu)
    for k, segment in enumerate(segments):
        segment.texte = lu[debuts[k]: debuts[k + 1] if k + 1 < len(segments) else len(texte)]
        segment.fin_mot = fins[k] - debuts[k]
        segment.total = segment.total or bool(_TOTAL.search(segment.texte))
        correction = _CORRECTION_NOMBRE.search(" ".join(texte[:debuts[k]].split()[-4:]) + " " + segment.texte)
        segment.correction = correction is not None and segment.nombre is not None
        segment.ancien_nombre = int(correction.group(1)) if segment.correction and correction.group(1) else None
        if segment.type == _DESIGNATION:
            # « Celui-là, béton 18 cm » : l'élément que décrivent les valeurs dites (un mur par défaut, ou le
            # type de la dernière question s'il s'agit d'un élément de la pièce).
            candidats = list(dict.fromkeys(
                ([type_courant] if type_courant and TYPES[type_courant].niveau == "piece" else []) + ["mur", "fenetre", "emetteur"]))
            segment.type = max(candidats, key=lambda t: len(_valeurs(t, segment.texte)))
            segment.singulier, segment.pluriel = TYPES[segment.type].designation, PLURIELS.get(segment.type, TYPES[segment.type].nom + "s")
    return (texte[: debuts[0]] if debuts else texte), segments


def _existants(checklist: Checklist, type_element: str, piece: str | None = None) -> list[Element]:
    if TYPES[type_element].niveau == "piece":
        piece = piece or checklist.piece_courante
    else:
        piece = None
    return [e for e in checklist.elements_de(piece) if e.type == type_element]


def _par_rang(checklist: Checklist, segment: _Segment, existants: list[Element]) -> Element | None:
    """« Le deuxième mur », « le mur 5 » : l'élément déjà décrit qui porte ce rang ou ce nom, sinon None
    (un nouveau : « le quatrième mur » quand il n'y en a que trois)."""
    genre, k = segment.rang  # type: ignore[misc]
    if genre == "numero":
        noms = {cle_texte(f"{segment.singulier} {k}"), cle_texte(f"{TYPES[segment.type].designation} {k}")}
        autres = [e for e in checklist.elements if e.type == segment.type and e not in existants]
        for element in existants + autres:
            if cle_texte(element.description) in noms:
                return element
    return existants[k - 1] if 1 <= k <= len(existants) else None


def _element_vise(checklist: Checklist, segment: _Segment, valeurs: dict[str, str], piece: str | None = None) -> Element | None:
    """L'élément déjà connu que ce morceau de phrase décrit, ou None pour en créer un nouveau."""
    if segment.type in TOUJOURS_PRESENTS:
        return checklist.element_de_piece(segment.type, piece)
    existants = _existants(checklist, segment.type, piece)
    if segment.rang:
        return _par_rang(checklist, segment, existants)
    if not existants:
        return None

    def conflit(element: Element) -> bool:
        # Seule une valeur dite pour cet élément compte : une valeur reprise d'une règle ou d'un groupe admet des exceptions.
        return any((v := element.valeur(c)) is not None and v.origine == "dit" and cle_texte(v.valeur) != cle_texte(nouvelle)
                   for c, nouvelle in valeurs.items())

    if segment.correction:  # « en fait il y a 3 radiateurs, pas 2 » : le groupe déjà décrit
        for element in reversed(existants):
            if element.nombre == segment.ancien_nombre:
                return element
        return ([e for e in existants if e.nombre > 1] or existants)[-1]
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
    # Un élément complet qui reçoit de nouveau un champ déjà dit, c'est un autre élément (un autre mur) ; un champ
    # jamais demandé (température d'un radiateur) le complète.
    redit = any(dernier.est_rempli(c) for c in valeurs)
    if conflit(dernier) or (TYPES[segment.type].niveau == "piece" and not dernier.champs_manquants() and redit):
        return None
    return dernier


def _nouvelle_description(checklist: Checklist, type_element: str, nombre: int | None, singulier: str = "", pluriel: str = "",
                          deja: int = 0) -> str:
    numero = sum(e.type == type_element for e in checklist.elements) + 1 + deja  # deja : créés par la même phrase
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
    # Phrases globales sur les murs (test réel de Noah, étape 5) : « cette pièce fait 4 murs », « il y a juste un mur
    # qui donne sur l'extérieur, le reste donne sur l'intérieur ou les voisins », « pareil pour celui-là ».
    texte = _pareil_pour(checklist, _phrases_globales(checklist, cible, texte, action), action)
    resultat.demande = _demande(texte)

    type_courant = cible.type if cible and cible.type in TYPES else None
    debut, segments = _segments(texte, type_courant)
    if type_courant == "ecs":
        # « Par la chaudière », en réponse à une question sur l'eau chaude : c'est l'eau chaude qui est décrite.
        for segment in segments:
            if segment.type == "chauffage":
                segment.type, segment.singulier, segment.pluriel = "ecs", TYPES["ecs"].designation, "eaux chaudes"
    if type_courant == "chauffage" and len(segments) == 1 and segments[0].type == "emetteur" and not segments[0].nombre:
        # « Quel est le chauffage principal ? » « Les radiateurs électriques » : c'est le chauffage qui est décrit.
        segments[0].type, segments[0].singulier, segments[0].pluriel = "chauffage", TYPES["chauffage"].designation, "générateurs"

    # « Sauf celle de la chambre, qui est en PVC », sans nommer l'élément : une exception de pièce, traitée à part.
    debut = _exceptions_sans_element(checklist, cible, debut, action)
    # Réponse courte à la dernière question : le début de phrase (avant tout autre élément cité).
    if cible:
        _reponse_a_la_cible(checklist, cible, debut, segments, resultat, action, phrase)

    cites: set[str] = set()  # types déjà annoncés dans cette phrase
    nouveaux: dict[str, int] = {}  # éléments créés par cette phrase, par type (pour les numéroter)
    pris: set[str] = set()  # noms donnés dans cette phrase
    crees: list[dict] = []  # éléments créés un par un par cette phrase
    lieux = _lieux(texte, segments, checklist)
    mur_de_la_phrase: dict = {}
    if cible is not None and cible.type == "mur" and cible.element_id:
        mur_de_la_phrase["ref"] = cible.element_id  # « Il y a 3 fenêtres dessus », en réponse à une question sur ce mur
    for k, segment in enumerate(segments):
        _decrire_segment(checklist, cible, segment, lieux.get(k), texte, action, cites, nouveaux, pris, crees, mur_de_la_phrase)
    _distinguer(checklist, crees, resultat)
    if (not any(a["outil"] == "orienter" for a in resultat.actions) and (m := _EST_ORIENTE.search(debut))
            and "facade" not in debut and not (cible and cible.genre == "orientation")):
        # « Il est orienté plein sud » : le mur (ou la fenêtre) de la question, sinon le dernier mur décrit.
        sujet = cible.element_id if cible and cible.element_id and cible.type in ORIENTABLES else checklist.dernier.get("mur")
        if sujet:
            action("orienter", element_id=sujet, orientation=m.group(1))
    _energie_de_la_chaudiere(checklist, resultat, action)
    _chauffage_par_les_emetteurs(checklist, resultat, action)
    resultat.actions = _derniere_valeur_dite(resultat.actions)
    return resultat


def _derniere_valeur_dite(actions: list[dict]) -> list[dict]:
    """« Le plafond est isolé… le plafond est pas isolé » dans une même phrase : le diagnostiqueur se reprend ; seule
    la dernière valeur dite pour un champ est notée (ce n'est pas une contradiction à signaler)."""
    def cle(a: dict) -> tuple:
        return a.get("element_id") or a.get("description"), a.get("piece"), a.get("type"), a.get("champ")

    derniere = {cle(a): i for i, a in enumerate(actions) if a["outil"] == "enregistrer_reponse"}
    return [a for i, a in enumerate(actions) if a["outil"] != "enregistrer_reponse" or derniere[cle(a)] == i]


def _distinguer(checklist: Checklist, crees: list[dict], resultat: Extraction) -> None:
    """« Deux fenêtres PVC double vitrage et une fenêtre bois simple vitrage » : des éléments du même genre
    décrits dans la même phrase reçoivent des noms qui les distinguent (« les 2 fenêtres en PVC », « la
    fenêtre en bois ») plutôt que des numéros."""
    familles: dict[tuple[str, str, str | None], list[dict]] = {}
    for cree in crees:
        familles.setdefault((cree["type"], cree["singulier"], cree["piece"]), []).append(cree)
    for (type_element, _singulier, piece), liste in familles.items():
        if len(liste) < 2 or type_element not in ("fenetre", "porte", "emetteur"):
            continue
        groupes = [_Groupe(c["nombre"], c["valeurs"], principal=(i == 0)) for i, c in enumerate(liste)]
        noms = _noms(type_element, groupes, None, liste[0]["singulier"] or TYPES[type_element].designation,
                     liste[0]["pluriel"] or PLURIELS.get(type_element, TYPES[type_element].nom + "s"))
        if len(set(noms)) < len(noms):
            continue  # rien ne les distingue : les numéros restent
        pris: set[str] = set()
        for cree, nom in zip(liste, noms):
            nom = _unique(checklist, nom, piece, pris)
            for a in resultat.actions:
                if a.get("type") == type_element and a.get("description") == cree["description"]:
                    a["description"] = nom


def _decrire_segment(checklist: Checklist, cible: Cible | None, segment: _Segment, lieu: str | None, texte: str, action,
                     cites: set[str], nouveaux: dict[str, int], pris: set[str], crees: list[dict], mur_de_la_phrase: dict) -> None:
    """Un élément cité dans la phrase : le créer, le compléter, le séparer en groupes, ou en tirer une règle.
    `mur_de_la_phrase` : le dernier mur cité dans la phrase ; une fenêtre citée ensuite est sur ce mur (« ce mur donne
    dehors, il y a 3 fenêtres dessus »)."""
    repere, point, apres_mot = "", "", segment.texte[segment.fin_mot:]
    if segment.type in ORIENTABLES:
        if o := _ORIENTATION_APRES_MOT.match(apres_mot):  # « le mur nord », « la baie plein sud »
            point, apres_mot = o.group(1), apres_mot[o.end():]
        elif o := _EST_ORIENTE.search(apres_mot):  # « ce mur est au nord »
            point = o.group(1)
    if segment.type == "mur":
        segment.nombre = None  # « il y a 4 murs » : chaque mur a ses caractéristiques, jamais de groupe
        if r := _REPERE.match(apres_mot):  # « le mur avec la télé », « le mur (nord) du fond »
            repere = _REPERES.get(r.group(1) or "") or _POSITIONS.get(r.group(2) or "", "")
    support = mur_de_la_phrase.get("ref", "") if segment.type in ("fenetre", "porte") else ""
    piece = checklist.trouver_piece(lieu) if lieu else None  # None si la pièce nommée n'est pas encore visitée
    groupes_possibles = segment.type not in PAROIS  # murs, plafonds, planchers : un par un (étape 5)
    apres = segment.texte[segment.fin_mot:]
    decoupage = decouper(apres) if groupes_possibles else Decoupage(apres)
    decoupage.tete = segment.texte[: segment.fin_mot] + " " + decoupage.tete
    valeurs = _valeurs(segment.type, decoupage.tete)
    tous = segment.tous or decoupage.tous
    parties = _parties_valables(segment.type, decoupage, (segment.nombre or 0) > 1 or tous) if groupes_possibles else []
    exceptions_pieces = _exceptions_de_piece(segment.type, decoupage, checklist) if groupes_possibles else {}
    simple_mention = (not valeurs and not segment.nombre and not parties and not exceptions_pieces and not segment.partie_de
                      and not repere and not point)
    # « une fenêtre ici », « et un radiateur ici » : on montre un élément déjà annoncé ; « ce mur » seul :
    # Claude et l'image s'en chargent ; plafond et plancher existent toujours. On ne crée un élément sur une
    # simple mention que s'il n'y en a aucun.
    if simple_mention and (segment.type in ("mur", *TOUJOURS_PRESENTS) or segment.type in cites or lieu
                           or _existants(checklist, segment.type)):
        if support and (existants := _existants(checklist, segment.type)) and not existants[-1].support:
            action("signaler_element", element_id=existants[-1].id, type=segment.type, support=support)  # « 3 fenêtres dessus »
        return
    cites.add(segment.type)
    dans_lieu = {"piece": lieu} if lieu else {}

    # « Non, c'est le mur ouest » : l'orientation du mur dont on parle (celui de la question, sinon le dernier décrit).
    if point and not valeurs and not parties and _C_EST.search(texte[: segment.debut]):
        courant = (cible.element_id if cible and cible.element_id and cible.type == segment.type
                   else checklist.dernier.get(segment.type))
        if courant:
            action("orienter", element_id=courant, type=segment.type, orientation=point)
            return
    # « Le mur nord est en brique » : le mur déjà orienté nord (par la boussole ou dit), s'il y en a un dans la pièce.
    par_orientation = None
    if point and not segment.nouveau_fort:
        par_orientation = next((e for e in _existants(checklist, segment.type, piece) if e.orientation == point), None)

    # 1. « Tous les radiateurs sont électriques », « toutes les fenêtres sont en bois, sauf celle de la chambre qui
    # est en PVC » : une règle, pour les éléments déjà décrits et ceux qui viendront (pour la pièce, ou pour tout le
    # logement si c'est dit ou si une autre pièce est exceptée).
    if ((tous or exceptions_pieces) and not segment.nombre and not segment.partie_de and not parties and groupes_possibles
            and TYPES[segment.type].niveau == "piece" and (valeurs or exceptions_pieces)):
        logement = bool(exceptions_pieces) or bool(_LOGEMENT.search(texte)) or (checklist.piece_courante is None and not lieu)
        action("regle", type=segment.type, valeurs=valeurs, exceptions=exceptions_pieces,
               piece="" if logement else (lieu or checklist.nom_piece(checklist.piece_courante)))
        return

    # 2. « Un des radiateurs est électrique » : une partie d'un groupe déjà décrit, séparée du groupe.
    if segment.partie_de:
        groupe = _groupe_pour_partie(checklist, segment.type, segment.partie_de, cible, piece)
        if groupe is not None:
            k = segment.partie_de
            _emettre(checklist, segment.type, groupe, [_Groupe(groupe.nombre - k, {}, principal=True),
                                                        _Groupe(k, valeurs, herite=True, autre=not valeurs)], action, pris)
            return

    # 3. L'élément décrit.
    if par_orientation is not None:
        vise = par_orientation
    elif (cible and cible.genre in ("champ", "confirmation") and segment.type == cible.type and not segment.nouveau_fort
            and not segment.rang and not lieu):
        # « Le mur 1 donne sur quoi ? » « C'est une cloison » : la réponse décrit l'élément de la question.
        vise = checklist.trouver_element(cible.element_id)
        # Sauf « c'est un mur qui donne vers un voisin » quand celui de la question donne sur le garage : un autre mur
        # (rejeu du test de Noah), à moins que le diagnostiqueur ne se corrige (« en fait », « non », « pas »).
        if any((v := vise.valeur(c)) is not None and v.origine == "dit" and c != cible.champ and cle_texte(v.valeur) != cle_texte(n)
               for c, n in valeurs.items()) and (segment.nouveau or not _SE_CORRIGE.search(segment.texte)):
            vise = _element_vise(checklist, segment, valeurs, piece)
    elif lieu and piece is None:
        vise = None  # pièce pas encore visitée : un élément nouveau, qui y sera rangé
    else:
        vise = _element_vise(checklist, segment, valeurs, piece)
    if repere and vise is not None and (vise.repere and vise.repere != repere or (
            not vise.repere and vise.valeurs and not vise.champs_manquants())):
        vise = None  # « le mur avec la télé » : un autre mur que celui, complet ou nommé autrement, dont on parlait

    # 4. Plusieurs groupes ou des exceptions : « 9 radiateurs électriques basse température et 1 électrique haute
    # température », « 3 fenêtres en PVC dont une en simple vitrage », « 2 en fonte et 1 en acier ».
    if parties:
        existant = vise is not None and not segment.nombre
        total = segment.nombre or (vise.nombre if vise is not None else None)
        if groupes := _repartir(segment.type, decoupage, parties, total, existant):
            _emettre(checklist, segment.type, vise, groupes, action, pris, segment.singulier, segment.pluriel, lieu, support)
            return

    # 5. Un seul groupe : le cas courant.
    if vise is None:
        description = _nouvelle_description(checklist, segment.type, segment.nombre, segment.singulier, segment.pluriel,
                                            deja=nouveaux.get(segment.type, 0))
        nouveaux[segment.type] = nouveaux.get(segment.type, 0) + 1
        description = _unique(checklist, description, piece if lieu else checklist.piece_courante, pris)
        crees.append({"type": segment.type, "description": description, "nombre": segment.nombre or 1, "valeurs": valeurs,
                      "singulier": segment.singulier, "pluriel": segment.pluriel, "piece": piece if lieu else checklist.piece_courante})
        action("signaler_element", type=segment.type, description=description, nombre=segment.nombre or 1, source="voix",
               **dans_lieu, **({"repere": repere} if repere else {}), **({"support": support} if support else {}))
        reference = {"element_id": "", "description": description, **dans_lieu}
    else:
        if segment.nombre and segment.nombre != vise.nombre:
            # « En tout trois fenêtres » ; « en fait il y en a 3, pas 2 » : un nombre déjà dit qui change est signalé.
            action("compter", element_id=vise.id, nombre=segment.nombre, correction=vise.nombre > 1 or segment.correction)
        if (repere and not vise.repere) or (support and not vise.support):
            action("signaler_element", element_id=vise.id, type=segment.type, repere=repere, support=support)
        reference = {"element_id": vise.id, "description": ""}
    if segment.type == "mur":
        mur_de_la_phrase["ref"] = reference["element_id"] or reference["description"]
    for champ, valeur in valeurs.items():
        action("enregistrer_reponse", type=segment.type, champ=champ, valeur=valeur, **reference)
    if point and par_orientation is None:  # « le mur sud donne dehors » : un mur dont l'orientation est dite
        action("orienter", type=segment.type, orientation=point, **reference)
    mot = segment.texte[: segment.fin_mot].split()
    if vise is not None and valeurs and not segment.nombre and mot and mot[-1].endswith(("s", "x")):
        # « Les fenêtres ont des volets roulants » (au pluriel) : vaut aussi pour les autres fenêtres de la pièce
        # qui n'en ont rien dit.
        for autre in _existants(checklist, segment.type, vise.piece):
            for champ, valeur in valeurs.items():
                if autre is not vise and not autre.est_rempli(champ):
                    action("enregistrer_reponse", element_id=autre.id, type=segment.type, champ=champ, valeur=valeur)


# --- Groupes et exceptions ------------------------------------------------------------------------------

@dataclass
class _Groupe:
    nombre: int | None
    valeurs: dict[str, str]  # dites pour ce groupe (avec ce qui est dit pour tout le groupe, s'il en fait partie)
    herite: bool = False  # sous-groupe ou exception d'un groupe : reprend aussi les valeurs déjà dites du groupe
    principal: bool = False  # reste dans l'élément d'origine
    autre: bool = False  # « l'autre », « les autres » : rien qui le distingue n'a été dit


def _nom_de_piece(m: re.Match, checklist: Checklist, sans_numero: bool = False) -> str:
    nom = _PIECES[m.group(1)] + (f" {m.group(2)}" if m.group(2) and not sans_numero else "")
    cle = checklist.trouver_piece(nom)
    return checklist.nom_piece(cle) if cle else nom


def _lieux(texte: str, segments: list[_Segment], checklist: Checklist) -> dict[int, str]:
    """Pièce nommée pour un élément d'une autre pièce : « le radiateur de la salle de bains est électrique »,
    « dans la cuisine, il y a aussi un radiateur ». Renvoie {indice du segment : nom de la pièce}."""
    lieux: dict[int, str] = {}
    for m in _LIEU.finditer(texte):
        contenant = next((k for k in range(len(segments) - 1, -1, -1) if segments[k].debut <= m.start()), None)
        suivant = next((k for k, s in enumerate(segments) if s.debut > m.start()), None)
        numero_du_segment = m.group(2) is not None and suivant is not None and segments[suivant].debut == m.start(2)
        fin = m.start(2) if numero_du_segment else m.end()  # « dans la chambre 2 convecteurs » : 2 est leur nombre
        # Un lieu qui ouvre une proposition et précède un élément est le sien (« et dans la chambre, 2 convecteurs ») ;
        # sinon il complète l'élément en cours (« un radiateur électrique dans la cuisine »).
        vers_suivant = suivant is not None and _ENTRE_LIEU_ET_ELEMENT.fullmatch(texte[fin: segments[suivant].debut]) is not None
        debut_de_proposition = re.search(r"(?:^|,|\bet|\bpuis|\bmais)\s*$", texte[: m.start()]) is not None
        k = suivant if vers_suivant and (contenant is None or debut_de_proposition) else contenant
        if k is None or k in lieux or segments[k].type in PAROIS or TYPES[segments[k].type].niveau != "piece":
            continue
        nom = _nom_de_piece(m, checklist, sans_numero=numero_du_segment)
        if checklist.trouver_piece(nom) != checklist.piece_courante:
            lieux[k] = nom
    return lieux


def _parties_valables(type_element: str, decoupage: Decoupage, groupe: bool) -> list[Partie]:
    """Les parties qui décrivent vraiment un groupe (pas « et un isolant », pas « et 2 ici »). Les exceptions de
    pièce (« sauf celle de la chambre ») sont traitées à part."""
    valables = []
    for p in decoupage.parties:
        if _LIEU.search(p.texte) and (p.exception or p.designe):
            continue
        a_valeurs = bool(_valeurs(type_element, p.texte))
        if p.exception and (p.nombre or a_valeurs or p.designe):
            valables.append(p)
        elif p.reste and (a_valeurs or groupe):
            valables.append(p)
        elif a_valeurs:
            valables.append(p)
    return valables


def _exceptions_de_piece(type_element: str, decoupage: Decoupage, checklist: Checklist) -> dict[str, dict[str, str]]:
    """« Sauf celle de la chambre, qui est en PVC » → {« Chambre » : {menuiserie : PVC}}."""
    exceptions: dict[str, dict[str, str]] = {}
    for p in decoupage.parties:
        if (p.exception or p.designe) and (m := _LIEU.search(p.texte)):
            exceptions[_nom_de_piece(m, checklist)] = _valeurs(type_element, p.texte[: m.start()] + " " + p.texte[m.end():])
    return exceptions


def _repartir(type_element: str, decoupage: Decoupage, parties: list[Partie], total: int | None, existant: bool) -> list[_Groupe]:
    """Les groupes décrits, le principal en premier. `total` : nombre annoncé (« 9 radiateurs ») ou nombre du
    groupe déjà décrit ; `existant` : la phrase redécoupe un groupe déjà décrit (« 2 en PVC et 1 en bois »)."""
    groupes = _repartir_parties(type_element, decoupage, parties, total, existant)
    commun = _valeurs(type_element, decoupage.commun)  # « …, toutes en double vitrage »
    for g in groupes:
        g.valeurs = {**commun, **g.valeurs}
    return groupes


def _repartir_parties(type_element: str, decoupage: Decoupage, parties: list[Partie], total: int | None, existant: bool) -> list[_Groupe]:
    tete = _valeurs(type_element, decoupage.tete)
    principal = {**tete, **_valeurs(type_element, decoupage.au_principal)}
    exceptions = [p for p in parties if p.exception]
    if exceptions:
        # « Dont une en simple vitrage », « tous à eau sauf un électrique », « toutes sauf une ont des volets roulants ».
        retires = sum(p.nombre or 1 for p in exceptions)
        if total and total <= retires:
            return []  # « sauf un » dans un groupe d'un seul : rien à séparer
        groupes = [_Groupe(total - retires if total else None, principal, principal=True)]
        for p in exceptions:
            propres = _valeurs(type_element, p.texte)
            # « Dont » : un sous-ensemble, qui partage ce qui est dit du groupe. « Sauf une » sans rien de plus : elle
            # diffère sur ce qui vient d'être dit, on ne lui reprend rien de la phrase (on demandera).
            commun = tete if (p.dont or propres) else {}
            groupes.append(_Groupe(p.nombre or 1, {**commun, **propres}, herite=True, autre=not propres))
        return groupes
    explicites = sum(p.nombre or 0 for p in parties)
    restes = [p for p in parties if p.reste and not p.nombre]
    if existant or (total and (explicites == total or restes)):
        # Sous-groupes d'un même groupe (2 + 1 = 3, ou « l'un… les autres… ») : chacun reprend ce qui est dit du groupe.
        groupes = []
        for p in parties:
            n = p.nombre or (total - explicites if total and total > explicites else None)
            propres = _valeurs(type_element, p.texte)
            groupes.append(_Groupe(n, {**tete, **propres}, herite=True, autre=p.reste and not propres))
        if total and explicites < total and not restes:
            groupes.append(_Groupe(total - explicites, dict(tete), herite=True, autre=True))  # « 2 roulants » sur 3 : il en reste 1
        principal_groupe = max(groupes, key=lambda g: g.nombre or 0)
        principal_groupe.principal = True
        groupes.remove(principal_groupe)
        return [principal_groupe, *groupes]
    # Groupes distincts (9 + 1 ≠ 9) : rien n'est repris de l'un à l'autre.
    groupes = [_Groupe(total, principal, principal=True)] if (principal or total or existant) else []
    groupes += [_Groupe(p.nombre, _valeurs(type_element, p.texte)) for p in parties]
    groupes[0].principal = True
    return groupes


def _qualificatif(type_element: str, champ: str, valeur: str, nombre: int) -> str:
    """Ce qui distingue un groupe dans son nom : « en bois », « haute température », « à volets roulants »."""
    v, cle = valeur, cle_texte(valeur)
    if champ in ("menuiserie", "materiau") or (type_element == "porte" and champ == "type"):
        return f"en {v}"
    if champ == "vitrage":
        return f"en {v} vitrage" if v in ("simple", "double", "triple") else f"en {v}"
    if champ == "volets":
        return "sans volets" if v == "aucun" else f"à volets {v}"
    if type_element == "emetteur" and champ == "type":
        if "eau" in cle:
            return "à eau"
        return ("électriques" if nombre > 1 else "électrique") if "electrique" in cle else f"({v})"
    if champ == "temperature":
        return f"{v} température"
    if champ == "annee":
        return f"de {v}"
    libelle = next(c.libelle for c in TYPES[type_element].champs if c.cle == champ)
    return f"({libelle} : {v})"


def _noms_de(element: Element, singulier: str = "", pluriel: str = "") -> tuple[str, str]:
    """(singulier, pluriel) du nom d'un élément : « les 3 fenêtres » → (« la fenêtre », « fenêtres »)."""
    if trouve := nom_de(element.description):
        return trouve[1], trouve[0]
    return singulier or element.type_element.designation, pluriel or PLURIELS.get(element.type, element.type_element.nom + "s")


def _noms(type_element: str, groupes: list[_Groupe], vise: Element | None, singulier: str, pluriel: str) -> list[str]:
    """Un nom parlant par groupe, d'après le premier champ qui les distingue : « les 9 radiateurs basse
    température » et « le radiateur haute température » ; « l'autre fenêtre » si rien ne la distingue."""
    def valeur(g: _Groupe, champ: str) -> str:
        if champ in g.valeurs:
            return g.valeurs[champ]
        dite = vise.valeur(champ) if vise is not None and (g.principal or g.herite) else None
        return dite.valeur if dite is not None else ""

    # Champs qui distinguent les groupes ; chacun est nommé par le premier de ces champs qu'on connaît pour lui.
    distinctifs = [c.cle for c in TYPES[type_element].champs if len({cle_texte(valeur(g, c.cle)) for g in groupes}) > 1]
    noms = []
    for g in groupes:
        champ = next((c for c in distinctifs if valeur(g, c) and valeur(g, c) != VALEUR_INCONNUE), None)
        qualificatif = _qualificatif(type_element, champ, valeur(g, champ), g.nombre or 1) if champ else ""
        autre = not qualificatif and not g.principal and (g.autre or bool(distinctifs))
        noms.append(nom_groupe(singulier, pluriel, g.nombre or 1, qualificatif, autre))
    return noms


def _unique(checklist: Checklist, nom: str, piece: str | None, pris: set[str], sauf: Element | None = None) -> str:
    """Deux éléments d'une même pièce ne portent jamais le même nom (il sert à les retrouver)."""
    base, k = nom, 2
    while cle_texte(nom) in pris or any(e is not sauf and cle_texte(e.description) == cle_texte(nom) for e in checklist.elements_de(piece)):
        nom, k = f"{base} n°{k}", k + 1
    pris.add(cle_texte(nom))
    return nom


def _emettre(checklist: Checklist, type_element: str, vise: Element | None, groupes: list[_Groupe], action, pris: set[str],
             singulier: str = "", pluriel: str = "", lieu: str | None = None, support: str = "") -> None:
    """Crée, sépare ou complète les éléments décrits par ces groupes (le principal en premier)."""
    if vise is not None:
        singulier, pluriel = _noms_de(vise, singulier, pluriel)
        noms = _noms(type_element, groupes, vise, singulier, pluriel)
        principal = groupes[0]
        ailleurs = {"piece": checklist.nom_piece(vise.piece)} if vise.piece and vise.piece != checklist.piece_courante else {}
        # 1. Les parties séparées d'abord : elles reprennent les valeurs du groupe telles qu'elles avaient été dites.
        for g, nom in zip(groupes[1:], noms[1:]):
            nom = _unique(checklist, nom, vise.piece, pris)
            if g.herite:
                action("scinder", element_id=vise.id, nombre=g.nombre or 1, description=nom, valeurs=g.valeurs)
            else:
                _nouvel_element(action, type_element, nom, g.nombre, g.valeurs, ailleurs)
        # 2. Le groupe d'origine : son nouveau nombre et son nom parlant, puis ses valeurs.
        nom = _unique(checklist, noms[0], vise.piece, pris, sauf=vise) if description_auto(vise.description) else ""
        if (principal.nombre and principal.nombre != vise.nombre) or (nom and nom != vise.description):
            action("compter", element_id=vise.id, nombre=principal.nombre or vise.nombre, description=nom)
        for champ, valeur in principal.valeurs.items():
            action("enregistrer_reponse", element_id=vise.id, type=type_element, champ=champ, valeur=valeur)
        return
    singulier = singulier or TYPES[type_element].designation
    pluriel = pluriel or PLURIELS.get(type_element, TYPES[type_element].nom + "s")
    piece = checklist.trouver_piece(lieu) if lieu else checklist.piece_courante
    for g, nom in zip(groupes, _noms(type_element, groupes, None, singulier, pluriel)):
        _nouvel_element(action, type_element, _unique(checklist, nom, piece, pris), g.nombre, g.valeurs, {"piece": lieu} if lieu else {},
                        support)


def _nouvel_element(action, type_element: str, description: str, nombre: int | None, valeurs: dict[str, str], ailleurs: dict,
                    support: str = "") -> None:
    action("signaler_element", type=type_element, description=description, nombre=nombre or 1, source="voix", **ailleurs,
           **({"support": support} if support else {}))
    for champ, valeur in valeurs.items():
        action("enregistrer_reponse", element_id="", type=type_element, champ=champ, valeur=valeur, description=description, **ailleurs)


def _groupe_pour_partie(checklist: Checklist, type_element: str, k: int, cible: Cible | None, piece: str | None) -> Element | None:
    """« Un des radiateurs » : le groupe de la dernière question s'il en a plus de k, sinon le dernier de la pièce."""
    if cible and cible.element_id and cible.type == type_element:
        element = checklist.trouver_element(cible.element_id)
        if element.nombre > k:
            return element
    groupes = [e for e in _existants(checklist, type_element, piece) if e.nombre > k]
    return groupes[-1] if groupes else None


def _exceptions_sans_element(checklist: Checklist, cible: Cible | None, texte: str, action) -> str:
    """« Sauf celle de la chambre, qui est en PVC », dit sans nommer l'élément : exception à la dernière règle
    du logement, ou à défaut correction des éléments de cette pièce. Renvoie le texte sans cette exception."""
    exceptions = [(p, m) for p in decouper(texte).parties if (p.exception or p.designe) and (m := _LIEU.search(p.texte))]
    if not exceptions:
        return texte
    if checklist.regles:
        type_element = checklist.regles[-1].type
    elif cible and cible.type in TYPES and TYPES[cible.type].niveau == "piece" and cible.type not in PAROIS:
        type_element = cible.type
    else:
        return texte
    debut = texte[: exceptions[0][0].position]
    tete = _valeurs(type_element, debut)
    if tete and not any(r.type == type_element and r.piece is None for r in checklist.regles):
        # « Bois, sauf celle de la chambre qui est en PVC » : une règle pour tout le logement, avec son exception.
        action("regle", type=type_element, valeurs=tete, piece="", exceptions={
            _nom_de_piece(m, checklist): _valeurs(type_element, p.texte[: m.start()] + " " + p.texte[m.end():]) for p, m in exceptions})
        return debut
    for partie, m in exceptions:
        nom = _nom_de_piece(m, checklist)
        valeurs = _valeurs(type_element, partie.texte[: m.start()] + " " + partie.texte[m.end():])
        if any(r.type == type_element and r.piece is None for r in checklist.regles):
            action("exception", type=type_element, piece=nom, valeurs=valeurs)
        elif valeurs:
            cle = checklist.trouver_piece(nom)
            elements = _existants(checklist, type_element, cle) if cle else []
            for element in elements:
                for champ, valeur in valeurs.items():
                    action("enregistrer_reponse", element_id=element.id, type=type_element, champ=champ, valeur=valeur)
            if not elements:
                _nouvel_element(action, type_element, _nouvelle_description(checklist, type_element, None), None, valeurs, {"piece": nom})
    return debut


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


def _phrases_globales(checklist: Checklist, cible: Cible | None, texte: str, action) -> str:
    """Ce qui est dit de l'ensemble des murs de la pièce (test réel de Noah). Renvoie le texte sans ce qui a été traité.
    - « Cette pièce fait 4 murs » : on ne demande plus « un autre mur ? » une fois les 4 décrits ;
    - « il y a juste un mur qui donne sur l'extérieur » : c'est le mur déjà décrit, pas un mur de plus ;
    - « le reste donne sur l'intérieur ou les voisins » : tous les autres murs, d'un coup, et la liste est close.
    (« Pareil pour celui-là » : voir _pareil_pour.)"""
    if (m := _NOMBRE_MURS.search(texte)) and 3 <= int(next(g for g in m.groups() if g)) <= 12:
        action("murs", nombre=int(next(g for g in m.groups() if g)))
        texte = texte[: m.start()] + " , " + texte[m.end():]
    if not (re.search(r"\bmurs?\b", texte) or (cible is not None and cible.type == "mur")):
        return texte
    murs = _existants(checklist, "mur")
    if (m := _UN_SEUL_MUR.search(texte)) and (dites := _valeurs_dites("mur", "donne_sur", m.group(0))):
        valeur = dites[0]
        if not any((v := e.valeur("donne_sur")) is not None and cle_texte(v.valeur) == cle_texte(valeur) for e in murs):
            description = _nouvelle_description(checklist, "mur", None)
            action("signaler_element", type="mur", description=description, nombre=1, source="voix")
            action("enregistrer_reponse", element_id="", type="mur", champ="donne_sur", valeur=valeur, description=description)
        texte = texte[: m.start()] + " , " + texte[m.end():]
    if (m := _RESTE_MURS.search(texte)) and (dites := _valeurs_dites("mur", "donne_sur", texte[m.end():])):
        # « l'intérieur de la maison ou un voisin » : tous chauffés, donc aucune question de plus sur ces murs.
        tous_chauffes = all(cle_texte(v).startswith("local chauffe") for v in dites)
        valeur = dites[0] if len(dites) == 1 or not tous_chauffes else "local chauffé"
        note = "tous les autres murs" + (f" : {' ou '.join(dites)}" if len(dites) > 1 else "")
        for mur in murs:
            if not mur.est_rempli("donne_sur"):
                action("enregistrer_reponse", element_id=mur.id, type="mur", champ="donne_sur", valeur=valeur, note=note)
        if not checklist.murs_complets():
            action("signaler_element", type="mur", description="les autres murs", nombre=1, source="voix")
            action("enregistrer_reponse", element_id="", type="mur", champ="donne_sur", valeur=valeur, description="les autres murs",
                   note=note)
        action("cloturer", type="mur")
        texte = texte[: m.start()]
    return texte


def _pareil_pour(checklist: Checklist, texte: str, action) -> str:
    """« Pareil pour celui-là » : un nouveau mur (ou une fenêtre, « celle-là ») avec les valeurs du dernier décrit."""
    if not (m := _PAREIL_POUR.search(texte)):
        return texte
    type_element = "fenetre" if m.group(1).startswith(("celle", "cette", "la suivante", "l autre fenetre")) else "mur"
    existants = _existants(checklist, type_element)
    modele = (next((e for e in existants if e.id == checklist.dernier.get(type_element) and e.valeurs), None)
              or next((e for e in reversed(existants) if e.valeurs), None))
    if modele is None:
        return texte
    description = _nouvelle_description(checklist, type_element, None)
    action("signaler_element", type=type_element, description=description, nombre=1, source="voix")
    for champ, historique in modele.valeurs.items():
        if historique[-1].valeur != VALEUR_INCONNUE and champ not in ("longueur", "dimensions"):
            action("enregistrer_reponse", element_id="", type=type_element, champ=champ, valeur=historique[-1].valeur,
                   description=description, note=f"pareil que {checklist.nom(modele, demonstratif=False)}")
    return texte[: m.start()] + " , " + texte[m.end():]


def _demande(texte: str) -> str:
    """« Il te faut quoi d'autre ? » → « manques » ; « Quel mur ? » → « lequel »."""
    if _DEMANDE_MANQUES.search(texte):
        return "manques"
    return "lequel" if _DEMANDE_LEQUEL.search(texte.strip(" ,")) else ""


def _chauffage_par_les_emetteurs(checklist: Checklist, resultat: Extraction, action) -> None:
    """Chauffage à l'électricité et tous les émetteurs du logement électriques : ce sont des radiateurs
    électriques (effet Joule). Déduction notée comme telle, avec sa source, pour l'écran de validation ;
    elle évite une question inutile."""
    notees = [a for a in resultat.actions if a["outil"] == "enregistrer_reponse" and a["type"] == "chauffage"]
    energie = next((a for a in notees if a["champ"] == "energie"), None)
    if energie is None or cle_texte(energie["valeur"]) != "electricite" or any(a["champ"] == "type" for a in notees):
        return
    if energie.get("element_id") and checklist.trouver_element(energie["element_id"]).valeur("type") is not None:
        return
    emetteurs = [e for e in checklist.elements if e.type == "emetteur"]
    if emetteurs and all((v := e.valeur("type")) is not None and "electrique" in cle_texte(v.valeur) for e in emetteurs):
        action("enregistrer_reponse", type="chauffage", champ="type", valeur="radiateurs électriques (effet Joule)",
               element_id=energie.get("element_id", ""), description=energie.get("description", ""),
               note=f"déduit : émetteurs tous électriques ({', '.join(e.id for e in emetteurs)})")


def _peut_deviner(phrase: str, reponse: str, autres_valeurs: dict) -> bool:
    """Un mot mal entendu n'est deviné que dans une réponse courte, qui ne dit rien d'autre et n'est pas une question
    (rejeu du test de Noah : « Laine de verre de 30 cm » n'est pas « pierre », « Il te faut quoi d'être comme
    information ? » n'est pas « tuffeau ») ; sinon c'est Claude qui interprète."""
    mots = [m for m in reponse.replace(",", " ").split() if m not in _MOTS_VIDES]
    return len(mots) <= MOTS_POUR_DEVINER and not autres_valeurs and not phrase.strip().endswith("?") and not _demande(reponse)


def _modele_pareil(checklist: Checklist, element: Element, champ: str) -> Element | None:
    """« Pareil » : le dernier élément du même type, dans la même pièce, dont ce champ a été dit."""
    autres = [e for e in _existants(checklist, element.type, element.piece) if e is not element]
    return next((e for e in reversed(autres) if (v := e.valeur(champ)) is not None and v.valeur != VALEUR_INCONNUE), None)


def _reponse_a_la_cible(checklist: Checklist, cible: Cible, texte: str, segments: list[_Segment], resultat: Extraction, action,
                        phrase: str) -> None:
    reponse = texte.strip(" ,")
    if cible.genre in ("presence", "suite"):
        # « Oui, trois fenêtres en PVC » : c'est la suite de la phrase qui décrit l'élément.
        if any(s.type == cible.type for s in segments):
            return
        if cible.type not in PAROIS and reponse:
            # « Oui, deux en PVC et une en bois » : plusieurs groupes d'un coup.
            decoupage = decouper(texte)
            parties = _parties_valables(cible.type, decoupage, True)
            if (len(parties) > 1 or any(p.exception for p in parties)) and (groupes := _repartir(cible.type, decoupage, parties, None, False)):
                _emettre(checklist, cible.type, None, groupes, action, set())
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
    if cible.genre == "orientation":
        # « Ce mur est orienté nord, sud, est ou ouest ? » « Plein sud. » / « À l'est. » / « La façade est au sud. »
        if not any(s.type in ORIENTABLES for s in segments) and (m := _POINT_REPONDU.search(reponse)):
            action("orienter", element_id=cible.element_id, type=cible.type, orientation=m.group(1) or m.group(2))
        return
    if cible.genre == "piece" or not reponse:
        return
    if cible.genre == "champ" and cible.element_id:
        element = checklist.trouver_element(cible.element_id)
        if element.type not in PAROIS:
            # Question sur un groupe : « 2 en PVC et une en bois », « tous à eau sauf un », « l'une d'elles est en bois ».
            decoupage = decouper(texte)
            parties = _parties_valables(cible.type, decoupage, element.nombre > 1 or decoupage.tous)
            if parties and (groupes := _repartir(cible.type, decoupage, parties, element.nombre, existant=True)):
                _emettre(checklist, cible.type, element, groupes, action, set())
                return
        if (_PAREIL.match(reponse) and cible.champ not in _valeurs(cible.type, texte)
                and (modele := _modele_pareil(checklist, element, cible.champ)) is not None):
            # « Pareil » : la même valeur que l'élément du même type décrit juste avant.
            action("enregistrer_reponse", element_id=element.id, type=cible.type, champ=cible.champ,
                   valeur=modele.valeur(cible.champ).valeur, note=f"pareil que {modele.description}")
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
        # Ce qui est dit d'autre est gardé (« Le plancher est isolé ? » « Un sous-sol. ») ; mais si la réponse parle
        # d'isolant, « par l'intérieur » est le côté de l'isolation, pas ce sur quoi la paroi donne.
        autres = {} if _ISOLATION.search(texte) else _valeurs(cible.type, texte)
        valeurs = {c: val for c, val in autres.items() if c not in ("isolation", "epaisseur")}
        if v:
            valeurs["isolation"] = v
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
        elif _peut_deviner(phrase, reponse, valeurs) and (devine := _deviner(cible.type, cible.champ, texte)):
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
    if cible.genre == "champ" and valeurs and _TOUS_LES_AUTRES.search(reponse):
        # « Toutes, des volets roulants » : vaut aussi pour les autres éléments de ce type de la pièce qui n'en ont rien dit.
        element = checklist.trouver_element(cible.element_id)
        for autre in _existants(checklist, cible.type, element.piece):
            for champ, valeur in valeurs.items():
                if autre is not element and not autre.est_rempli(champ):
                    action("enregistrer_reponse", element_id=autre.id, type=cible.type, champ=champ, valeur=valeur)

