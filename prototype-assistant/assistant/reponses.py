"""Réponses attendues à une question, à l'écran du téléphone comme à l'oral (test de Noah du 22/10, après-midi).

1. **Questionnaire en direct** : chaque question de l'assistant arrive sur le téléphone avec ses réponses en boutons ;
   un appui vaut une réponse dite, en plus rapide et sans risque d'être mal entendu. La fiche de la pièce montre aussi
   chaque information, à compléter ou corriger d'un appui.
2. **Réponses courtes à l'oral** : la transcription rapide rate souvent les mots isolés (« VMC » → « Vaime s. »,
   « non » → « Na. »), et un bruit (téléphone manipulé, pas) donne des lettres (« A. », « F. »). Une phrase courte qui
   ne ressemble à rien de connu est réécoutée par Whisper avant d'être prise pour une réponse : bruit, ou vraie réponse.

Les valeurs des boutons sont celles du vocabulaire des règles (``extraction.VOCABULAIRE``) : une réponse cochée est
rangée exactement comme la même réponse dite.
"""

from __future__ import annotations

import re
import unicodedata

from .checklist import TYPES, VALEUR_INCONNUE
from .extraction import VOCABULAIRE, Cible

NE_SAIT_PAS = ("Je ne sais pas", VALEUR_INCONNUE)
ISOLATION = [("Non isolé", "non isolé"), ("Isolé par l'intérieur", "ITI"), ("Isolé par l'extérieur", "ITE"),
             ("Isolé (sans précision)", "isolé"), NE_SAIT_PAS]
ANNEES = [("Avant 1990", "avant 1990"), ("1990 à 2000", "1990-2000"), ("2000 à 2010", "2000-2010"),
          ("2010 à 2015", "2010-2015"), ("Après 2015", "après 2015"), NE_SAIT_PAS]

# Boutons par information (libellé, valeur) : les réponses les plus fréquentes d'abord ; le reste se dit à l'oral.
OPTIONS: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("mur", "donne_sur"): [("Extérieur", "extérieur"), ("Voisin chauffé", "local chauffé (voisin)"),
                           ("Pièce du logement", "local chauffé"), ("Garage", "local non chauffé : garage"),
                           ("Cave", "local non chauffé : cave"), ("Parties communes", "local non chauffé : parties communes"),
                           ("Combles", "local non chauffé : combles"), ("Autre local non chauffé", "local non chauffé")],
    ("mur", "materiau"): [("Brique", "brique"), ("Parpaing", "parpaing"), ("Béton", "béton"), ("Pierre", "pierre"),
                          ("Brique creuse", "brique creuse"), ("Brique pleine", "brique pleine"),
                          ("Béton cellulaire", "béton cellulaire"), ("Monomur", "monomur"), ("Bois", "bois"),
                          ("Meulière", "meulière"), NE_SAIT_PAS],
    ("mur", "epaisseur"): [(f"{n} cm", f"{n} cm") for n in (15, 20, 25, 30, 35, 40, 50, 60)] + [NE_SAIT_PAS],
    ("mur", "isolation"): ISOLATION,
    ("plafond", "donne_sur"): [("Combles perdus", "combles perdus"), ("Combles aménagés", "combles aménagés"),
                               ("Logement au-dessus", "local chauffé (logement au-dessus)"),
                               ("Toiture terrasse", "toiture terrasse"), ("Rampants (sous toit)", "rampants sous toiture"),
                               ("Local non chauffé", "local non chauffé")],
    ("plafond", "isolation"): ISOLATION,
    ("plancher", "donne_sur"): [("Terre-plein", "terre-plein"), ("Vide sanitaire", "vide sanitaire"),
                                ("Cave / sous-sol", "sous-sol / cave"), ("Garage", "local non chauffé : garage"),
                                ("Logement en dessous", "local chauffé (logement en dessous)"),
                                ("Local non chauffé", "local non chauffé"), ("Extérieur", "extérieur")],
    ("plancher", "isolation"): ISOLATION,
    ("fenetre", "menuiserie"): [("PVC", "PVC"), ("Bois", "bois"), ("Alu", "alu"), ("Bois-alu", "mixte bois-alu"),
                                ("Métal", "métal")],
    ("fenetre", "vitrage"): [("Simple", "simple"), ("Double", "double"), ("Triple", "triple"), ("Survitrage", "survitrage")],
    ("fenetre", "volets"): [("Aucun", "aucun"), ("Roulants", "roulants"), ("Battants", "battants"),
                            ("Persiennes", "persiennes")],
    ("porte", "type"): [("Bois", "bois"), ("PVC", "PVC"), ("Métal", "métal"), ("Vitrée", "vitrée"), ("Isolée", "isolée")],
    ("porte", "donne_sur"): [("Extérieur", "extérieur"), ("Palier (non chauffé)", "palier (local non chauffé)")],
    ("emetteur", "type"): [("Radiateur à eau", "radiateur à eau"), ("Radiateur électrique", "radiateur électrique"),
                           ("Convecteur", "convecteur électrique"), ("Panneau rayonnant", "panneau rayonnant électrique"),
                           ("Plancher chauffant", "plancher chauffant"), ("Sèche-serviettes", "sèche-serviettes")],
    ("emetteur", "temperature"): [("Basse", "basse"), ("Moyenne", "moyenne"), ("Haute", "haute"), NE_SAIT_PAS],
    ("emetteur", "annee"): ANNEES,
    ("chauffage", "energie"): [("Gaz", "gaz"), ("Électricité", "électricité"), ("Fioul", "fioul"), ("Bois", "bois"),
                               ("Granulés", "bois (granulés)"), ("Pompe à chaleur", "électricité (PAC)"),
                               ("Réseau de chaleur", "réseau de chaleur")],
    ("chauffage", "type"): [("Chaudière à condensation", "chaudière à condensation"),
                            ("Chaudière basse température", "chaudière basse température"),
                            ("Chaudière standard", "chaudière standard"), ("PAC air/eau", "PAC air/eau"),
                            ("PAC air/air", "PAC air/air"), ("Radiateurs électriques", "radiateurs électriques (effet Joule)"),
                            ("Poêle", "poêle"), ("Insert", "insert"), NE_SAIT_PAS],
    ("chauffage", "annee"): ANNEES,
    ("ecs", "systeme"): [("Chaudière", "chaudière"), ("Ballon électrique", "ballon électrique"),
                         ("Ballon thermodynamique", "ballon thermodynamique"),
                         ("Chauffe-eau instantané", "chauffe-eau instantané"), ("Solaire", "chauffe-eau solaire")],
    ("ecs", "energie"): [("Gaz", "gaz"), ("Électricité", "électricité"), ("Fioul", "fioul")],
    ("ecs", "annee"): ANNEES,
    ("ventilation", "type"): [("VMC simple flux", "VMC simple flux"), ("VMC hygro B", "VMC simple flux hygro B"),
                              ("VMC hygro A", "VMC simple flux hygro A"), ("VMC double flux", "VMC double flux"),
                              ("Naturelle (grilles)", "naturelle")],
}

OUI_NON = [("Oui", "oui"), ("Non", "non")]
# Questions du parcours qui ne portent pas sur une information précise : réponses en mots que les règles comprennent
# (le bouton envoie ce mot, comme s'il avait été dit).
PRESENCES = {
    "fenetre": OUI_NON,
    "emetteur": [(libelle, valeur) for libelle, valeur in OPTIONS[("emetteur", "type")]] + [("Aucun", "non")],
    "chauffage": OPTIONS[("chauffage", "energie")],
    "ecs": OPTIONS[("ecs", "systeme")],
    "ventilation": OPTIONS[("ventilation", "type")] + [("Aucune", "non")],
}
PIECES = ["Séjour", "Cuisine", "Chambre 1", "Chambre 2", "Salle de bains", "WC", "Entrée", "Couloir", "Bureau",
          "Buanderie", "Cellier"]


def options_pour(cible: Cible | None) -> list[dict]:
    """Boutons de réponse à la question posée (vide : réponse libre, à l'oral)."""
    if cible is None:
        return []
    paires: list[tuple[str, str]] = []
    if cible.genre in ("champ", "secondaire", "confirmation") and cible.type and cible.champ:
        paires = list(OPTIONS.get((cible.type, cible.champ), []))
        if cible.genre == "confirmation":
            paires = [("Oui, c'est ça", "oui"), ("Non", "non")]
    elif cible.genre == "presence":
        paires = PRESENCES.get(cible.type, [])
    elif cible.genre == "suite":
        paires = [("Oui, un autre", "oui"), ("Non, c'est tout", "non")]
    elif cible.genre == "pareil":
        paires = [("Oui, pareil", "oui"), ("Non", "non")]
    elif cible.genre == "doublon":
        paires = [("Oui, le même", "oui"), ("Non, un autre", "non")]
    elif cible.genre == "piece" and cible.champ == "proposee":
        paires = [("Oui", "oui"), ("Non", "non")]
    elif cible.genre == "piece":
        paires = [(nom, nom) for nom in PIECES]
    elif cible.genre == "orientation":
        paires = [("Nord", "nord"), ("Est", "est"), ("Sud", "sud"), ("Ouest", "ouest")]
    return [{"libelle": libelle, "valeur": valeur} for libelle, valeur in paires]


def options_par_champ() -> dict[str, list[dict]]:
    """Toutes les réponses en boutons, par « type.champ » : la fiche de la pièce, sur le téléphone, s'en sert."""
    return {f"{t}.{c}": [{"libelle": l, "valeur": v} for l, v in paires] for (t, c), paires in OPTIONS.items()
            if t in TYPES and any(ch.cle == c for ch in TYPES[t].champs)}


# --- Réponses courtes à l'oral -----------------------------------------------------------------------------------


def _mots(texte: str) -> list[str]:
    sans_accent = "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", sans_accent)


# Mots d'une vraie réponse courte : oui, non, nombres, mots du métier (vocabulaire des règles), pièces, appels.
_COURANTS = """oui ouais si non nan ok voila d accord exact exactement pareil idem meme rien aucun aucune tout fini termine
attends attendez pause stop allo salut pardon quoi comment hein ici la dehors dedans exterieur interieur nord sud est ouest
mur murs fenetre fenetres porte portes plafond plancher sol radiateur radiateurs chaudiere ballon vmc gaz fioul bois pvc alu
simple double triple isole isolee isoles non isolee laine verre roche polystyrene voisin voisins cave garage combles
un une deux trois quatre cinq six sept huit neuf dix onze douze quinze vingt trente quarante cinquante soixante cent mille
cm centimetres centimetre metre metres m premier premiere deuxieme second autre autres celui celle ceux ca je sais pas""".split()
MOTS_CONNUS: set[str] = set(_COURANTS)
for _paires in VOCABULAIRE.values():
    for _formes, _valeur in _paires:
        for _forme in (*_formes, _valeur):
            MOTS_CONNUS.update(m for m in _mots(_forme) if len(m) >= 3)
for _paires in OPTIONS.values():
    for _libelle, _valeur in _paires:
        MOTS_CONNUS.update(m for m in _mots(f"{_libelle} {_valeur}") if len(m) >= 3)
for _nom in PIECES + ["salon", "salle", "bains", "entree", "chambre", "dressing", "grenier"]:
    MOTS_CONNUS.update(_mots(_nom))
# Petits mots de liaison : présents partout, ils ne prouvent pas qu'une réponse a été dite (« Elle par su. »).
MOTS_CONNUS -= {"les", "des", "par", "sur", "sous", "dans", "avec", "pour", "qui", "que", "est", "son", "ses", "aux", "une",
                "elle", "elles", "ils", "cet", "cette", "ces", "leur", "mon", "ton", "votre", "vos", "nos", "pas"}


def suspecte(texte: str) -> bool:
    """Phrase trop courte et sans aucun mot connu (« A. », « Il ré. », « Elle par su. ») : peut-être un bruit, ou une
    réponse mal transcrite. À réécouter avant d'y répondre."""
    mots = _mots(texte)
    if not mots:
        return True
    if sum(len(m) for m in mots) <= 2:
        return True  # « A. », « F. », « Il. », « Na. »
    return len(mots) <= 3 and not any(m in MOTS_CONNUS or m.isdigit() for m in mots)
