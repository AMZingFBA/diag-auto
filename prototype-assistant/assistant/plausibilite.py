"""Contrôle de plausibilité des valeurs, avant de les noter (étape 5 de Noah).

Au test réel du 22/10/2026, « il donne sur l'extérieur, il fait 30 mètres » a été noté tel quel : un
mur de 30 m de long dans un séjour. Désormais, une valeur hors des bornes ci-dessous n'est pas
notée : l'assistant propose la lecture la plus probable (« J'ai compris 30 m de long : plutôt 3 m ? »).
Si aucune lecture n'est plausible, la valeur est écartée et la question normale sera posée.

Les bornes sont volontairement larges, pour n'arrêter que l'invraisemblable. Hypothèse, à ajuster
avec les diagnostiqueurs.
"""

from __future__ import annotations

import datetime
import re

# (type, champ) -> (minimum, maximum, unité de la valeur notée)
BORNES: dict[tuple[str, str], tuple[float, float, str]] = {
    ("mur", "longueur"): (0.3, 15.0, "m"),
    ("mur", "epaisseur"): (4.0, 100.0, "cm"),
}
# Épaisseur d'isolant dans la valeur « isolation » (« ITI laine de verre 10 cm »).
ISOLANT_CM: dict[str, tuple[float, float]] = {"mur": (1.0, 40.0), "plafond": (1.0, 60.0), "plancher": (1.0, 40.0)}
DIMENSION_M = (0.2, 6.0)  # côté d'une fenêtre ou d'une porte
ANNEE_MIN = 1850
SUFFIXES = {"longueur": " de long", "epaisseur": " d'épaisseur", "isolation": " d'isolant"}


def _nombre(texte: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)", texte)
    return float(m.group(1).replace(",", ".")) if m else None


def _ecrire(n: float) -> str:
    return f"{n:g}".replace(".", ",")


def _ramener(n: float, minimum: float, maximum: float) -> float | None:
    """« 30 » pour un mur de 3 m, « 2 » pour 20 cm : la puissance de 10 qui rend la valeur plausible."""
    for facteur in (0.1, 0.01, 10.0):
        if minimum <= n * facteur <= maximum:
            return round(n * facteur, 2)
    return None


def verifier(type_element: str, champ: str, valeur: str) -> tuple[bool, str | None]:
    """(plausible, lecture proposée si elle ne l'est pas)."""
    if (type_element, champ) in BORNES:
        minimum, maximum, unite = BORNES[(type_element, champ)]
        n = _nombre(valeur)
        if n is None or minimum <= n <= maximum:
            return True, None
        proposee = _ramener(n, minimum, maximum)
        return False, (f"{_ecrire(proposee)} {unite}" if proposee is not None else None)
    if champ == "isolation" and type_element in ISOLANT_CM and (m := re.search(r"(\d+(?:[.,]\d+)?)\s*cm\b", valeur)):
        minimum, maximum = ISOLANT_CM[type_element]
        n = float(m.group(1).replace(",", "."))
        if minimum <= n <= maximum:
            return True, None
        proposee = _ramener(n, minimum, maximum)
        return False, (valeur[: m.start()] + f"{_ecrire(proposee)} cm" + valeur[m.end():] if proposee is not None else None)
    if champ == "annee" and (n := _nombre(valeur)) is not None:
        return ANNEE_MIN <= n <= datetime.date.today().year, None
    if champ == "dimensions":
        unite_m = valeur.strip().endswith(" m")
        cotes = [float(x.replace(",", ".")) * (1 if unite_m else 0.01) for x in re.findall(r"\d+(?:[.,]\d+)?", valeur)]
        return all(DIMENSION_M[0] <= c <= DIMENSION_M[1] for c in cotes), None
    return True, None


def filtrer(actions: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(actions gardées, propositions à faire confirmer, valeurs écartées) : une valeur invraisemblable n'est
    jamais notée ; si une lecture plausible existe, elle est proposée au diagnostiqueur."""
    gardees, propositions, ecartees = [], [], []
    for action in actions:
        if action.get("outil") != "enregistrer_reponse":
            gardees.append(action)
            continue
        ok, proposee = verifier(str(action.get("type", "")), str(action.get("champ", "")), str(action.get("valeur", "")))
        if ok:
            gardees.append(action)
            continue
        ecartees.append(action)
        if proposee is not None:
            suffixe = SUFFIXES.get(str(action.get("champ")), "")
            propositions.append({**action, "valeur": proposee, "note": f"invraisemblable : « {action.get('valeur')} » ; corrigé, confirmé",
                                 "question": f"J'ai compris {action.get('valeur')}{suffixe} : plutôt {proposee} ?"})
    return gardees, propositions, ecartees
