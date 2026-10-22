"""Noms parlants des éléments, pour les questions dites à l'oral (étape 5 de Noah).

Au test réel du 22/10/2026, « Le mur 3 est en quoi ? » ou « le quatrième mur » : le diagnostiqueur
ne savait pas de quel mur il s'agissait. Un élément est donc nommé par ce qui a été dit ou vu de
lui, jamais par un numéro. Indices, du plus parlant au moins parlant :
0. son orientation d'abord, quand elle est connue (étape 6 : c'est ainsi que LICIEL décrit les parois), avec
   son repère visuel : « le mur nord », « le mur nord, celui avec la télé » ;
1. le repère dit (« le mur avec la télé », « le mur du fond », « le mur de gauche ») ;
2. ses fenêtres (« le mur des 3 fenêtres ») ;
3. ce sur quoi il donne (« le mur côté voisin », « le mur côté garage », « le mur extérieur ») ;
4. son orientation, pour une fenêtre (« la fenêtre sud ») ;
5. son matériau (« le mur en brique »).
Le premier indice qui le distingue des autres éléments de la pièce est retenu (deux au besoin).
L'élément dont on vient de parler est « ce mur ». Sans indice : « le mur affiché » (sa vignette
est montrée à l'écran avec la question), à défaut son rang (« le deuxième mur »).
"""

from __future__ import annotations

import re

from .checklist import TOUJOURS_PRESENTS, Element, cle_texte, description_auto, nom_de

_ORDINAUX = ["premier", "deuxième", "troisième", "quatrième", "cinquième", "sixième", "septième", "huitième"]


def _demonstratif(element: Element) -> str:
    """« ce mur », « cette fenêtre », « ces 3 fenêtres »."""
    if element.type == "mur":
        return "ce mur"
    if trouve := nom_de(element.description):
        pluriel, singulier = trouve
        article, nom = singulier.split(" ", 1)
        if element.nombre > 1:
            return f"ces {element.nombre} {pluriel}"
        return f"{'cette' if article == 'la' else 'ce'} {nom}"
    return {"fenetre": "cette fenêtre", "porte": "cette porte", "emetteur": "ce radiateur"}.get(element.type, element.type_element.designation)


def _cote(valeur: str) -> str:
    """Indice tiré de « donne sur » : « extérieur », « côté voisin », « côté garage »."""
    cle = cle_texte(valeur)
    if cle == "exterieur":
        return "extérieur"
    if "voisin" in cle:
        return "côté voisin"
    if ":" in valeur:
        return "côté " + valeur.split(":", 1)[1].strip()
    if cle.startswith("local chauffe"):
        return "intérieur"
    return "côté local non chauffé" if cle.startswith("local non chauffe") else ""


def _valeur(element: Element, champ: str) -> str:
    v = element.valeur(champ)
    return v.valeur if v is not None and cle_texte(v.valeur) != "inconnu" else ""


def indices(element: Element, fenetres: list[Element]) -> list[str]:
    """Ce qui permet de reconnaître l'élément, du plus parlant au moins parlant."""
    resultat: list[str] = []
    if element.repere:
        resultat.append(element.repere)
    if element.type == "mur":
        portees = [f for f in fenetres if f.support == element.id]
        n = sum(f.nombre for f in portees)
        if n == 1:
            resultat.append("de " + (nom_de(portees[0].description) or ("", "la fenêtre"))[1])
        elif n > 1:
            resultat.append(f"des {n} fenêtres")
        if cote := _cote(_valeur(element, "donne_sur")):
            resultat.append(cote)
    if element.orientation:
        resultat.append(element.orientation)
    if materiau := _valeur(element, "materiau") or _valeur(element, "menuiserie"):
        resultat.append(f"en {materiau}")
    return resultat


def _nom_oriente(element: Element, voisins: list[Element], fenetres: list[Element], numerote: bool) -> str:
    """« le mur nord », « le mur nord, celui avec la télé » : l'orientation d'abord (c'est ainsi que LICIEL décrit les
    parois), puis le repère visuel. Deux murs nord (pièce en L) : ce qui les distingue en plus. Vide si rien ne les
    distingue (le nom habituel est alors utilisé)."""
    nom = f"le mur {element.orientation}"
    # Le repère : dit (« avec la télé ») ou dans le nom donné à l'image (« le mur avec le miroir »).
    repere = element.repere or ("" if numerote or not element.description.startswith("le mur ") else element.description[7:])
    memes = [v for v in voisins if v is not element and v.type == "mur" and v.orientation == element.orientation]
    if not memes:
        return f"{nom}, celui {repere}" if repere else nom
    autres = [set(indices(v, fenetres)) | {v.repere} for v in memes]
    for indice in [repere, *indices(element, fenetres)]:
        if indice and indice != element.orientation and not any(indice in a for a in autres):
            return f"{nom}, celui {indice}" if indice == repere else f"{nom} {indice}"
    return ""


def nom_parlant(element: Element, voisins: list[Element], fenetres: list[Element], courant: bool) -> str:
    """Le nom à dire. `voisins` : les autres éléments du même type dans la pièce ; `courant` : on vient
    d'en parler (« ce mur »)."""
    if element.type in TOUJOURS_PRESENTS or element.piece is None:
        return element.description
    # Seuls les noms numérotés donnés par le serveur (« le mur 3 », « la fenêtre 2 ») sont remplacés ; « les 3
    # fenêtres » ou « le mur avec le miroir » (vu à l'image) sont déjà parlants.
    numerote = description_auto(element.description) and element.nombre == 1 and not element.description.startswith("les ")
    if courant and (element.type == "mur" or numerote):
        return _demonstratif(element)
    if element.type == "mur" and element.orientation and (nom := _nom_oriente(element, voisins, fenetres, numerote)):
        return nom
    if not numerote:
        return element.description
    base = re.sub(r"(?: \d+)?(?: n°\d+)?$", "", element.description)
    siens = indices(element, fenetres)
    autres = [set(indices(v, fenetres)) for v in voisins if v is not element]
    for indice in siens:
        if not any(indice in a for a in autres):
            return f"{base} {indice}"
    for i, premier in enumerate(siens):
        for second in siens[i + 1:]:
            if not any(premier in a and second in a for a in autres):
                return f"{base} {premier} {second}"
    feminin = base.startswith("la ")
    if element.image:
        return f"{base} affichée" if feminin else f"{base} affiché"  # la vignette est à l'écran avec la question
    rang = voisins.index(element) if element in voisins else 0
    if rang < len(_ORDINAUX) and base.startswith(("le ", "la ")):
        article, nom = base.split(" ", 1)
        return f"{article} {'première' if feminin and rang == 0 else _ORDINAUX[rang]} {nom}"
    return base
