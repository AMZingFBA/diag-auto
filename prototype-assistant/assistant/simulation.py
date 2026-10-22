"""Cerveau de simulation : sans Claude, à base de règles simples, pour tester toute la chaîne
gratuitement (page, voix, checklist, journal).

Il reconnaît quelques mots du métier dans la phrase, propose les actions correspondantes (avec
la phrase entière comme citation) et pose la question du premier manque de la checklist. Il ne
voit pas les images.
"""

from __future__ import annotations

import copy
import re

from .actions import appliquer
from .cerveau import Contexte, Decision
from .checklist import TYPES, Checklist, Manque, cle_texte

PIECES = {
    "cuisine": "Cuisine", "sejour": "Séjour", "salon": "Salon", "salle a manger": "Salle à manger",
    "salle de bains": "Salle de bains", "salle de bain": "Salle de bains", "salle d'eau": "Salle d'eau",
    "wc": "WC", "toilettes": "WC", "entree": "Entrée", "couloir": "Couloir", "degagement": "Dégagement",
    "bureau": "Bureau", "cellier": "Cellier", "buanderie": "Buanderie", "garage": "Garage", "cave": "Cave",
    "grenier": "Grenier", "combles": "Combles", "dressing": "Dressing", "chambre": "Chambre",
}
_PIECE = re.compile(
    r"\b(?:ici c ?est|c ?est|on est dans|on entre dans|on passe dans|dans)\s+(?:la |le |l |les )?("
    + "|".join(sorted(PIECES, key=len, reverse=True)) + r")(?:\s+(\d+))?\b"
)

# Mots qui désignent un type d'élément.
TYPES_MOTS = [
    ("fenetre", r"fenetre|porte fenetre|baie"),
    ("emetteur", r"radiateur|convecteur|plancher chauffant|seche serviette|panneau rayonnant"),
    ("chauffage", r"chaudiere|pompe a chaleur|\bpac\b"),
    ("ecs", r"ballon|cumulus|chauffe eau|eau chaude"),
    ("ventilation", r"\bvmc\b|ventilation|bouche"),
    ("mur", r"\bmur\b|celui ci|celui la|cloison|paroi"),
]

# (type, champ, motif, valeur) : la première règle qui correspond donne la valeur.
REGLES = [
    ("mur", "materiau", r"parpaing", "parpaing"), ("mur", "materiau", r"brique", "brique"),
    ("mur", "materiau", r"beton", "béton"), ("mur", "materiau", r"pierre", "pierre"),
    ("mur", "materiau", r"ossature bois|pan de bois|\bbois\b", "bois"), ("mur", "materiau", r"placo", "placo"),
    ("mur", "isolation", r"non isole|pas isole|sans isolation|pas d isolation", "non isolé"),
    ("mur", "isolation", r"\biti\b|par l interieur|isolation interieure|doublage", "ITI"),
    ("mur", "isolation", r"\bite\b|par l exterieur|isolation exterieure", "ITE"),
    ("mur", "donne_sur", r"local non chauffe|garage|cave|cellier|cage d escalier|combles", "local non chauffé"),
    ("mur", "donne_sur", r"local chauffe|piece chauffee|voisin", "local chauffé"),
    ("mur", "donne_sur", r"exterieur|dehors|facade", "extérieur"),
    ("fenetre", "menuiserie", r"\bpvc\b", "PVC"), ("fenetre", "menuiserie", r"\balu(minium)?\b", "alu"),
    ("fenetre", "menuiserie", r"\bbois\b", "bois"),
    ("fenetre", "vitrage", r"simple vitrage|simple", "simple"), ("fenetre", "vitrage", r"double vitrage|double", "double"),
    ("fenetre", "vitrage", r"triple vitrage|triple", "triple"),
    ("fenetre", "volets", r"pas de volets?|sans volets?|aucun volet", "aucun"),
    ("fenetre", "volets", r"volets? roulants?", "roulants"), ("fenetre", "volets", r"battants?", "battants"),
    ("fenetre", "volets", r"persiennes?", "persiennes"),
    ("emetteur", "type", r"plancher chauffant", "plancher chauffant"), ("emetteur", "type", r"convecteur", "convecteur électrique"),
    ("emetteur", "type", r"seche serviettes?", "sèche-serviettes"), ("emetteur", "type", r"radiateur electrique", "radiateur électrique"),
    ("emetteur", "type", r"radiateur", "radiateur à eau"),
    ("emetteur", "temperature", r"basse temperature", "basse"), ("emetteur", "temperature", r"haute temperature", "haute"),
    ("chauffage", "energie", r"\bgaz\b", "gaz"), ("chauffage", "energie", r"fioul|fuel", "fioul"),
    ("chauffage", "energie", r"pompe a chaleur|\bpac\b", "électricité (PAC)"), ("chauffage", "energie", r"electrique", "électricité"),
    ("chauffage", "type", r"condensation", "chaudière à condensation"), ("chauffage", "type", r"chaudiere", "chaudière"),
    ("chauffage", "type", r"pompe a chaleur|\bpac\b", "pompe à chaleur"),
    ("ecs", "systeme", r"thermodynamique", "ballon thermodynamique"), ("ecs", "systeme", r"ballon|cumulus|chauffe eau", "ballon électrique"),
    ("ecs", "systeme", r"chaudiere", "chaudière"), ("ecs", "energie", r"\bgaz\b", "gaz"), ("ecs", "energie", r"electrique", "électricité"),
    ("ventilation", "type", r"double flux", "VMC double flux"), ("ventilation", "type", r"hygro", "VMC simple flux hygro"),
    ("ventilation", "type", r"simple flux|\bvmc\b", "VMC simple flux"), ("ventilation", "type", r"naturelle|grilles?", "naturelle"),
]
_ANNEE = re.compile(r"\b(19[4-9]\d|20[0-3]\d)\b")
_NOMBRE = re.compile(r"\b(\d{1,3}(?:[.,]\d)?)\s*(cm|centimetres?)?\b")
_NE_SAIT_PAS = re.compile(r"je (?:ne )?sais pas|aucune idee|inconnu")
_SANS_OBJET = re.compile(r"sans objet|pas concerne")
_ABSENCE = re.compile(r"\b(?:pas de|aucune?|il n y a pas de)\s+(fenetre|radiateur|chauffage|emetteur|vmc|ventilation)")
_NOUVEAU = re.compile(r"\b(?:celui ci|celui la|l autre|un autre|une autre|deuxieme|troisieme|suivant|pareil)\b")


class CerveauSimulation:
    nom = "simulation (règles simples, sans Claude)"

    def __init__(self) -> None:
        self._dernier: Manque | None = None  # dernière question posée

    async def demarrer(self) -> None:
        pass

    async def fermer(self) -> None:
        pass

    def _valeurs(self, type_element: str, texte: str) -> dict[str, str]:
        valeurs: dict[str, str] = {}
        for t, champ, motif, valeur in REGLES:
            if t == type_element and champ not in valeurs and re.search(motif, texte):
                valeurs[champ] = valeur
        if annee := _ANNEE.search(texte):
            if any(c.cle == "annee" for c in TYPES[type_element].champs):
                valeurs["annee"] = annee.group(1)
        if type_element == "mur":
            sans_annee = _ANNEE.sub(" ", texte)
            for nombre, unite in _NOMBRE.findall(sans_annee):
                n = float(nombre.replace(",", "."))
                if 4 <= n <= 100 or unite:
                    valeurs.setdefault("epaisseur", f"{nombre} cm")
                    break
        return valeurs

    def _type_cite(self, texte: str) -> str | None:
        for type_element, motif in TYPES_MOTS:
            if re.search(motif, texte):
                return type_element
        return None

    def _cible(self, checklist: Checklist, type_element: str, texte: str) -> str:
        """Identifiant de l'élément visé, ou "" pour en créer un nouveau."""
        piece = checklist.piece_courante if TYPES[type_element].niveau == "piece" else None
        dernier = next((e for e in reversed(checklist.elements_de(piece)) if e.type == type_element), None)
        if dernier is None:
            return ""
        if self._dernier and self._dernier.element and self._dernier.element.id == dernier.id and not _NOUVEAU.search(texte):
            return dernier.id
        commence = any(dernier.valeurs.values())
        if _NOUVEAU.search(texte) and commence:
            return ""
        return dernier.id if dernier.champs_manquants() else ""

    def proposer_actions(self, checklist: Checklist, phrase: str) -> list[dict]:
        texte = re.sub(r"[^a-z0-9]+", " ", cle_texte(phrase))
        actions: list[dict] = []
        if m := _PIECE.search(texte):
            nom = PIECES[m.group(1)] + (f" {m.group(2)}" if m.group(2) else "")
            actions.append({"outil": "piece_courante", "nom": nom, "citation": phrase})
            return actions
        if m := _ABSENCE.search(texte):
            mot = m.group(1)
            type_element = {"fenetre": "fenetre", "vmc": "ventilation", "ventilation": "ventilation"}.get(mot, "emetteur")
            actions.append({"outil": "marquer_sans_objet", "type": type_element, "champ": "presence", "citation": phrase})
            return actions
        dernier = self._dernier
        if dernier and dernier.element and dernier.champ and (_NE_SAIT_PAS.search(texte) or _SANS_OBJET.search(texte)):
            outil = "enregistrer_reponse" if _NE_SAIT_PAS.search(texte) else "marquer_sans_objet"
            action = {"outil": outil, "element_id": dernier.element.id, "type": dernier.element.type, "champ": dernier.champ.cle, "citation": phrase}
            if outil == "enregistrer_reponse":
                action["valeur"] = "inconnu"
            return [action]
        type_element = self._type_cite(texte)
        if type_element is None and dernier is not None:
            type_element = dernier.type  # réponse à la dernière question
        if type_element is None:
            return actions
        valeurs = self._valeurs(type_element, texte)
        if not valeurs and type_element != "mur" and self._type_cite(texte):
            return [{"outil": "signaler_element", "type": type_element, "description": TYPES[type_element].designation}]
        cible = self._cible(checklist, type_element, texte)
        description = "" if cible else f"{TYPES[type_element].designation} {self._numero(checklist, type_element)}"
        for champ, valeur in valeurs.items():
            actions.append({"outil": "enregistrer_reponse", "element_id": cible, "type": type_element, "description": description,
                            "champ": champ, "valeur": valeur, "citation": phrase})
        return actions

    @staticmethod
    def _numero(checklist: Checklist, type_element: str) -> int:
        return sum(1 for e in checklist.elements if e.type == type_element) + 1

    async def decider(self, contexte: Contexte, sur_dire=None) -> Decision:
        checklist = contexte.checklist
        actions = self.proposer_actions(checklist, contexte.phrase) if contexte.mode == "reponse" and contexte.phrase else []
        # La question doit porter sur ce qui manque APRÈS ces enregistrements : on les essaie sur une copie.
        apres = copy.deepcopy(checklist)
        appliquer(apres, actions, contexte.t, [contexte.phrase])
        manques = apres.manques_piece() or apres.manques_logement()
        prochain = manques[0] if manques else None
        meme_question = prochain is not None and self._dernier is not None and prochain.code == self._dernier.code
        if prochain is None or (contexte.mode == "veille" and meme_question):
            dire = ""
        else:
            dire = prochain.question
            self._dernier = prochain  # calculé sur la copie : comparé ensuite par identifiant
        if dire and sur_dire:
            await sur_dire(dire)
        return Decision(dire=dire, actions=actions, mesures={"premier_mot_s": 0.0, "total_s": 0.0})
