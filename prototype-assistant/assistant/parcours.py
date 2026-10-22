"""Parcours de la visite : quelle question poser maintenant. Décidé par NOTRE serveur, sans
attendre Claude (retour de Noah, étape 2 du 22/10/2026).

Dans chaque pièce :
1. les murs un par un (« donne sur » d'abord), puis « Un autre mur dans cette pièce ? » jusqu'au non ;
2. le plafond, puis le plancher (« pareil que la pièce précédente ? » s'ils y sont connus) ;
3. les fenêtres et portes restantes, puis « D'autres fenêtres, ou une porte vers l'extérieur ? » ;
4. les émetteurs de chauffage (type seulement) ;
5. une seule fois pour le logement : chauffage, eau chaude, ventilation, puis les détails secondaires
   (date et température des radiateurs…), une seule fois chacun ;
6. « Pièce terminée. Quelle est la pièce suivante ? ».

Les questions sont proposées dans l'ordre ; le serveur pose la première que les garde-fous
acceptent. Chaque question n'est posée qu'une fois (sa clé est retenue) : une question restée sans
réponse n'est pas répétée, elle revient dans le rappel de fin de visite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .checklist import PRESENCES_LOGEMENT, TYPES, Checklist, Element, cle_texte


@dataclass(frozen=True)
class QuestionPlan:
    code: str  # champ ou étape visé : « M1.isolation », « suite:mur », « pareil:plafond:sejour »…
    texte: str
    cle: str  # pour ne jamais poser deux fois la même question


def _capitale(texte: str) -> str:
    return texte[:1].upper() + texte[1:]


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


def texte_champ(element: Element, champ: str, meme_element: bool) -> str:
    """Question courte sur un champ. Si la question précédente portait déjà sur cet élément, on
    ne le renomme pas (« Il est isolé ? » plutôt que « Le mur 2 est isolé ? »)."""
    d = _capitale(element.description)
    t = element.type
    if t == "mur":
        return {
            "donne_sur": f"{d} donne sur quoi ?",
            "materiau": "Il est en quoi ?" if meme_element else f"{d} est en quoi ?",
            "epaisseur": "Quelle épaisseur ?" if meme_element else f"{d}, quelle épaisseur ?",
            "isolation": "Il est isolé ?" if meme_element else f"{d} est isolé ?",
        }[champ]
    if t == "plafond":
        return {"donne_sur": "Au-dessus du plafond : combles, terrasse ou logement ?",
                "isolation": "Le plafond est isolé ?"}[champ]
    if t == "plancher":
        return {"donne_sur": "Sous le plancher : terre-plein, vide sanitaire, cave ou logement ?",
                "isolation": "Le plancher est isolé ?"}[champ]
    if t == "fenetre":
        texte = {"menuiserie": "PVC, bois ou alu ?", "vitrage": "simple ou double vitrage ?", "volets": "des volets ?"}[champ]
        return _capitale(texte) if meme_element else f"{d} : {texte}"
    if t == "porte":
        return {"type": f"{d} est en quoi ?", "donne_sur": f"{d} donne dehors ou sur un palier ?"}[champ]
    if t == "emetteur":
        return {"type": f"{d} : à eau ou électrique ?"}[champ]
    if t == "chauffage":
        return {"energie": "Le chauffage principal, quelle énergie ?",
                "type": "Chaudière, pompe à chaleur ou convecteurs ?",
                "annee": "La chaudière date de quand ? Sinon, filmez sa plaque."}[champ]
    if t == "ecs":
        systeme = element.valeur("systeme")
        ballon = systeme is not None and "ballon" in cle_texte(systeme.valeur)
        return {"systeme": "L'eau chaude : ballon ou chaudière ?",
                "energie": "Le ballon : électrique ou gaz ?" if ballon else "L'eau chaude, quelle énergie ?"}[champ]
    if t == "ventilation":
        return "Ventilation : VMC ou naturelle ?"
    raise KeyError(f"{t}.{champ}")


QUESTIONS_PRESENCE = {
    "mur": "Décrivez le premier mur.",
    "fenetre": "Des fenêtres dans cette pièce ?",
    "emetteur": "Des radiateurs dans cette pièce ?",
    "chauffage": "Quel est le chauffage principal ?",
    "ecs": "Et l'eau chaude, comment est-elle produite ?",
    "ventilation": "Ventilation : VMC ou naturelle ?",
}
QUESTIONS_SUITE = {
    "mur": "Un autre mur dans cette pièce ?",
    "fenetre": "D'autres fenêtres, ou une porte vers l'extérieur ?",
}
QUESTIONS_SECONDAIRES = {
    ("emetteur", "temperature"): "Vos radiateurs à eau sont basse ou haute température ?",
    ("emetteur", "annee"): "Les radiateurs datent de quand, à peu près ?",
    ("ecs", "annee"): "Le ballon d'eau chaude date de quand ?",
}
QUESTION_PIECE_SUIVANTE = "Pièce terminée. Quelle est la pièce suivante ?"
QUESTION_PIECE = "Dans quelle pièce êtes-vous ?"


def _champs(elements: list[Element], dernier_id: str | None) -> Iterator[QuestionPlan]:
    for element in elements:
        for champ in element.champs_manquants():
            code = f"{element.id}.{champ.cle}"
            yield QuestionPlan(code, texte_champ(element, champ.cle, element.id == dernier_id), code)


def _source_pareil(checklist: Checklist, type_element: str) -> str | None:
    """La pièce la plus récente où ce plafond (ou plancher) est déjà décrit."""
    for cle in reversed(list(checklist.pieces)):
        element = checklist.element_de_piece(type_element, cle)
        if cle != checklist.piece_courante and element is not None and element.est_rempli("donne_sur"):
            return cle
    return None


def questions(checklist: Checklist, dernier_id: str | None = None) -> Iterator[QuestionPlan]:
    """Les questions possibles, dans l'ordre du parcours."""
    piece_cle = checklist.piece_courante
    if piece_cle is None:
        yield QuestionPlan("piece:nom", QUESTION_PIECE, "piece:nom")
        return
    piece = checklist.pieces[piece_cle]
    elements = checklist.elements_de(piece_cle)

    def du_type(type_element: str) -> list[Element]:
        return [e for e in elements if e.type == type_element]

    # 1. Les murs, un par un : le mur en cours (le dernier décrit) d'abord.
    murs = du_type("mur")
    if not murs:
        yield QuestionPlan("presence:mur", QUESTIONS_PRESENCE["mur"], f"presence:mur@{piece_cle}")
    yield from _champs(list(reversed(murs)), dernier_id)
    if murs and "mur" not in piece.clos and not any(m.champs_manquants() for m in murs):
        yield QuestionPlan("suite:mur", QUESTIONS_SUITE["mur"], f"suite:mur@{piece_cle}#{len(murs)}")

    # 2-3. Plafond puis plancher, avec « pareil que la pièce précédente ? » s'ils y sont connus.
    for type_element in ("plafond", "plancher"):
        element = checklist.element_de_piece(type_element)
        if element is None:
            continue
        source = _source_pareil(checklist, type_element)
        if source and not element.valeurs and not element.sans_objet:
            texte = f"{_capitale(TYPES[type_element].nom)} pareil que dans {avec_article(checklist.pieces[source].nom)} ?"
            yield QuestionPlan(f"pareil:{type_element}:{source}", texte, f"pareil:{type_element}@{piece_cle}")
        yield from _champs([element], dernier_id)

    # 4. Fenêtres et portes restantes.
    fenetres, portes = du_type("fenetre"), du_type("porte")
    if not fenetres and "fenetre" not in piece.absences and "fenetre" not in piece.clos:
        yield QuestionPlan("presence:fenetre", QUESTIONS_PRESENCE["fenetre"], f"presence:fenetre@{piece_cle}")
    yield from _champs(fenetres + portes, dernier_id)
    if fenetres and "fenetre" not in piece.clos and not any(e.champs_manquants() for e in fenetres + portes):
        yield QuestionPlan("suite:fenetre", QUESTIONS_SUITE["fenetre"], f"suite:fenetre@{piece_cle}#{len(fenetres) + len(portes)}")

    # 5. Émetteurs de chauffage (le type seulement ; le reste est secondaire).
    emetteurs = du_type("emetteur")
    if not emetteurs and "emetteur" not in piece.absences:
        yield QuestionPlan("presence:emetteur", QUESTIONS_PRESENCE["emetteur"], f"presence:emetteur@{piece_cle}")
    yield from _champs(emetteurs, dernier_id)

    # 6. Une seule fois pour le logement : chauffage, eau chaude, ventilation, puis les détails secondaires.
    for type_element in PRESENCES_LOGEMENT:
        existants = [e for e in checklist.elements_de(None) if e.type == type_element]
        if not existants and type_element not in checklist.absences_logement:
            yield QuestionPlan(f"presence:{type_element}", QUESTIONS_PRESENCE[type_element], f"presence:{type_element}")
        yield from _champs(existants, dernier_id)
    for (type_element, champ) in checklist.manques_secondaires():
        if (type_element, champ) in QUESTIONS_SECONDAIRES:
            code = f"secondaire:{type_element}.{champ}"
            yield QuestionPlan(code, QUESTIONS_SECONDAIRES[(type_element, champ)], code)

    # 7. Fin de la pièce.
    yield QuestionPlan("piece:suivante", QUESTION_PIECE_SUIVANTE, f"piece:suivante@{piece_cle}")
