"""Parcours de la visite : quelle question poser maintenant. Décidé par NOTRE serveur, sans
attendre Claude (retour de Noah, étape 2 du 22/10/2026).

Dans chaque pièce :
1. les murs un par un (« donne sur » d'abord), puis « D'autres murs sur l'extérieur ou un local non chauffé ? »,
   une fois, et de nouveau seulement après un tel mur ajouté (test de Noah du 22/10 après-midi) ; si la
   boussole est absente ou perturbée, l'orientation d'un mur extérieur est demandée une fois (étape 6) ;
2. le plafond, puis le plancher (« pareil que la pièce précédente ? » s'ils y sont connus) ;
3. les fenêtres et portes restantes, puis « D'autres fenêtres, ou une porte vers l'extérieur ? » ;
4. les émetteurs de chauffage (type seulement : leur date et leur température ne sont jamais demandées,
   mais notées si elles sont dites) ;
5. une seule fois pour le logement : chauffage, eau chaude, ventilation, puis la date du ballon ;
6. « Pièce terminée. Quelle est la pièce suivante ? ».

Les questions ne sont pas une liste figée (étape 4 de Noah) : elles suivent le logement réel et ce qui
a été dit. Un groupe séparé (« dont une en bois ») a ses propres questions, sous un nom parlant (« La
fenêtre en bois : des volets ? ») ; ce qui est déjà connu par une règle (« toutes les fenêtres sont en
PVC ») ou se déduit (chauffage électrique et radiateurs électriques) n'est pas demandé ; les réponses
proposées dépendent de ce qui est dit (gaz : « condensation, basse température ou standard ? »).

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


def texte_champ(element: Element, champ: str, meme_element: bool, nom: str = "") -> str:
    """Question courte sur un champ. Si la question précédente portait déjà sur cet élément, on
    ne le renomme pas (« Il est isolé ? »). Sinon, il est désigné par son nom parlant (`nom` :
    « ce mur », « le mur côté voisin »), jamais par un numéro (étape 5 de Noah)."""
    d = _capitale(nom or element.description)
    sujet = f"{d}," if "," in d else d  # « Le mur nord, celui avec la télé, est en quoi ? »
    t = element.type
    if t == "mur":
        return {
            "donne_sur": f"{sujet} donne sur quoi ?",
            "materiau": "Il est en quoi ?" if meme_element else f"{sujet} est en quoi ?",
            "epaisseur": "Quelle épaisseur ?" if meme_element else f"{d}, quelle épaisseur ?",
            "isolation": "Il est isolé ?" if meme_element else f"{sujet} est isolé ?",
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
        # La question dépend de ce qui est déjà dit : on ne propose que les réponses possibles (étape 4 de Noah).
        energie = cle_texte(element.valeur("energie").valeur) if element.valeur("energie") else ""
        type_dit = cle_texte(element.valeur("type").valeur) if element.valeur("type") else ""
        if champ == "type":
            if energie.startswith(("gaz", "fioul")):
                return "Chaudière à condensation, basse température ou standard ?"
            if energie.startswith("bois"):
                return "Poêle, insert ou chaudière ?"
            if "pac" in energie:
                return "Pompe à chaleur air/eau ou air/air ?"
            if energie.startswith("electricite"):
                return "Radiateurs électriques ou pompe à chaleur ?"
            return "Chaudière, pompe à chaleur ou convecteurs ?"
        if champ == "annee":
            appareil = ("La pompe à chaleur" if "pac" in type_dit or "pompe" in type_dit or "pac" in energie
                        else "Le poêle" if "poele" in type_dit else "L'insert" if "insert" in type_dit else "La chaudière")
            return f"{appareil} date de quand ? Sinon, filmez sa plaque."
        return "Le chauffage principal, quelle énergie ?"
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
    # Test de Noah du 22/10 après-midi : « Un autre mur dans cette pièce ? » posé 10 fois. Pour le DPE, seuls comptent les
    # murs qui donnent dehors ou sur un local non chauffé : la question les vise, une fois par pièce.
    "mur": "D'autres murs sur l'extérieur ou un local non chauffé ?",
    "fenetre": "D'autres fenêtres, ou une porte vers l'extérieur ?",
}
# Date et température des radiateurs : jamais demandées (Noah, étape 4), mais notées dès qu'elles sont dites.
QUESTIONS_SECONDAIRES = {
    ("ecs", "annee"): "Le ballon d'eau chaude date de quand ?",
}
QUESTION_PIECE_SUIVANTE = "Pièce terminée. Quelle est la pièce suivante ?"
QUESTION_PIECE = "Dans quelle pièce êtes-vous ?"


def _champs(checklist: Checklist, elements: list[Element], dernier_id: str | None, separes: set[str] = frozenset()
            ) -> Iterator[QuestionPlan]:
    for element in elements:
        for champ in element.champs_manquants():
            code = f"{element.id}.{champ.cle}"
            # Un groupe qui vient d'être séparé (« deux en PVC et une en bois ») est nommé : « Des volets ? » serait ambigu ;
            # de même si le diagnostiqueur vient de parler d'un autre mur (« Il est isolé ? » : lequel ?).
            meme = (element.id == dernier_id and element.id not in separes
                    and checklist.dernier.get(element.type, element.id) == element.id)
            yield QuestionPlan(code, texte_champ(element, champ.cle, meme, checklist.nom(element)), code)


def _source_pareil(checklist: Checklist, type_element: str) -> str | None:
    """La pièce la plus récente où ce plafond (ou plancher) est déjà décrit."""
    for cle in reversed(list(checklist.pieces)):
        element = checklist.element_de_piece(type_element, cle)
        if cle != checklist.piece_courante and element is not None and element.est_rempli("donne_sur"):
            return cle
    return None


def cle_suite(checklist: Checklist, type_element: str) -> str:
    """Clé de « D'autres murs… ? » / « D'autres fenêtres… ? » dans la pièce en cours : la même pour le parcours et pour
    les questions de Claude (test de Noah du 22/10 après-midi : Claude reposait « Un autre mur ? » sous une autre clé,
    10 fois). Elle ne change, et la question ne peut revenir, qu'avec un nouveau mur dehors ou sur un local non chauffé
    (ou une fenêtre de plus)."""
    piece_cle = checklist.piece_courante
    elements = checklist.elements_de(piece_cle)
    if type_element == "mur":
        murs = [e for e in elements if e.type == "mur"]
        piece = checklist.pieces.get(piece_cle) if piece_cle else None
        reste = int(piece.nombre_murs.valeur) - sum(m.nombre for m in murs) if piece and piece.nombre_murs else 0
        compte = sum(m.nombre for m in murs if not m.sur_local_chauffe) if reste <= 0 else len(murs)
    else:
        compte = len([e for e in elements if e.type in ("fenetre", "porte")])
    return f"suite:{type_element}@{piece_cle}#{compte}"


def questions(checklist: Checklist, dernier_id: str | None = None) -> Iterator[QuestionPlan]:
    """Les questions possibles, dans l'ordre du parcours."""
    piece_cle = checklist.piece_courante
    if piece_cle is None:
        yield QuestionPlan("piece:nom", QUESTION_PIECE, "piece:nom")
        return
    piece = checklist.pieces[piece_cle]
    elements = checklist.elements_de(piece_cle)
    separes = {e.parent for e in checklist.elements if e.parent}

    def du_type(type_element: str) -> list[Element]:
        return [e for e in elements if e.type == type_element]

    # 1. Les murs, un par un : le mur en cours (le dernier décrit) d'abord.
    murs = du_type("mur")
    if not murs:
        yield QuestionPlan("presence:mur", QUESTIONS_PRESENCE["mur"], f"presence:mur@{piece_cle}")
    yield from _champs(checklist, list(reversed(murs)), dernier_id, separes)
    if (mur := checklist.orientation_a_demander()) is not None:
        # Boussole absente ou perturbée : l'orientation d'un mur extérieur, demandée une seule fois ; avec le gyroscope,
        # les autres murs s'en déduisent (sinon, une fois par pièce).
        cle = "orientation@visite" if checklist.boussole_gyroscope else f"orientation@{piece_cle}"
        nom = _capitale(checklist.nom(mur))
        yield QuestionPlan(f"orientation:{mur.id}", f"{nom}{',' if ',' in nom else ''} est orienté nord, sud, est ou ouest ?", cle)
    if murs and not checklist.murs_complets() and not any(m.champs_manquants() for m in murs):
        # « Cette pièce fait 4 murs » : on sait combien il en reste.
        reste = int(piece.nombre_murs.valeur) - sum(m.nombre for m in murs) if piece.nombre_murs else 0
        texte = (QUESTIONS_SUITE["mur"] if reste <= 0 else "Il reste un mur : il donne sur quoi ?" if reste == 1
                 else f"Il reste {reste} murs : le suivant donne sur quoi ?")
        # Reposée seulement après un nouveau mur qui donne dehors ou sur un local non chauffé (pas après un mur sur un
        # voisin ou une pièce chauffée).
        yield QuestionPlan("suite:mur", texte, cle_suite(checklist, "mur"))

    # 2-3. Plafond puis plancher, avec « pareil que la pièce précédente ? » s'ils y sont connus.
    for type_element in ("plafond", "plancher"):
        element = checklist.element_de_piece(type_element)
        if element is None:
            continue
        source = _source_pareil(checklist, type_element)
        if source and not element.valeurs and not element.sans_objet:
            texte = f"{_capitale(TYPES[type_element].nom)} pareil que dans {avec_article(checklist.pieces[source].nom)} ?"
            yield QuestionPlan(f"pareil:{type_element}:{source}", texte, f"pareil:{type_element}@{piece_cle}")
        yield from _champs(checklist, [element], dernier_id, separes)

    # 4. Fenêtres et portes restantes.
    fenetres, portes = du_type("fenetre"), du_type("porte")
    if not fenetres and "fenetre" not in piece.absences and "fenetre" not in piece.clos:
        yield QuestionPlan("presence:fenetre", QUESTIONS_PRESENCE["fenetre"], f"presence:fenetre@{piece_cle}")
    yield from _champs(checklist, fenetres + portes, dernier_id, separes)
    if fenetres and "fenetre" not in piece.clos and not any(e.champs_manquants() for e in fenetres + portes):
        yield QuestionPlan("suite:fenetre", QUESTIONS_SUITE["fenetre"], cle_suite(checklist, "fenetre"))

    # 5. Émetteurs de chauffage (le type seulement ; le reste est secondaire).
    emetteurs = du_type("emetteur")
    if not emetteurs and "emetteur" not in piece.absences:
        yield QuestionPlan("presence:emetteur", QUESTIONS_PRESENCE["emetteur"], f"presence:emetteur@{piece_cle}")
    yield from _champs(checklist, emetteurs, dernier_id, separes)

    # 6. Une seule fois pour le logement : chauffage, eau chaude, ventilation, puis les détails secondaires.
    for type_element in PRESENCES_LOGEMENT:
        existants = [e for e in checklist.elements_de(None) if e.type == type_element]
        if not existants and type_element not in checklist.absences_logement:
            yield QuestionPlan(f"presence:{type_element}", QUESTIONS_PRESENCE[type_element], f"presence:{type_element}")
        yield from _champs(checklist, existants, dernier_id, separes)
    for (type_element, champ) in checklist.manques_secondaires():
        if (type_element, champ) in QUESTIONS_SECONDAIRES:
            code = f"secondaire:{type_element}.{champ}"
            yield QuestionPlan(code, QUESTIONS_SECONDAIRES[(type_element, champ)], code)

    # 7. Fin de la pièce.
    yield QuestionPlan("piece:suivante", QUESTION_PIECE_SUIVANTE, f"piece:suivante@{piece_cle}")
