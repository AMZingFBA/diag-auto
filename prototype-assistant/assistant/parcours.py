"""Parcours de la visite : quelle question poser maintenant. Décidé par NOTRE serveur, sans
attendre Claude (retour de Noah, étape 2 du 22/10/2026).

Étape 13 (Noah) : le DPE décrit l'enveloppe du logement, par côté, pas chaque pièce. On ne demande jamais dans quelle
pièce on est (« qu'on soit dans le séjour ou la chambre, pour le DPE on s'en fiche »), ni « quels murs dans cette
pièce ? », mais « ce mur donne sur quoi ? ». Un mur déjà décrit d'un côté ne l'est pas une seconde fois, un mur entre
deux pièces ne demande rien.

Ordre :
1. « Ce mur donne sur quoi ? » tant qu'aucun mur n'est décrit ; chaque mur du logement (le dernier dont il a parlé
   d'abord) : « donne sur », puis matériau, épaisseur, isolation s'il donne dehors ou sur un local non chauffé, puis
   « Des fenêtres ou une porte sur ce mur ? » et leurs menuiserie, vitrage, volets ;
2. si la boussole est absente ou perturbée, l'orientation d'un mur, une fois (étape 6) : c'est elle qui le range du bon
   côté ; puis, mur par mur, les côtés du logement dont rien n'est dit : « Et le mur sud, il donne sur quoi ? » (nord,
   sud, est, ouest : chacun fini avant le suivant) ; enfin « Un autre mur autour du logement, à me montrer ? » (une maison
   peut en avoir plus de quatre) ;
3. le plafond, puis le plancher du logement (une partie différente, dite dans une pièce, a ses propres questions) ;
4. une seule fois pour le logement : chauffage, émetteurs (leur type), eau chaude, ventilation, puis la date du ballon ;
5. « C'est complet pour le DPE. »

Les questions ne sont pas une liste figée (étape 4 de Noah) : elles suivent le logement réel et ce qui a été dit. Un
groupe séparé (« dont une en bois ») a ses propres questions, sous un nom parlant ; ce qui est déjà connu par une règle
(« toutes les fenêtres sont en PVC ») ou se déduit (chauffage électrique et radiateurs électriques) n'est pas demandé ;
les réponses proposées dépendent de ce qui est dit (gaz : « condensation, basse température ou standard ? »).

Les questions sont proposées dans l'ordre ; le serveur pose la première que les garde-fous acceptent. Chaque question
n'est posée qu'une fois (sa clé est retenue) : une question restée sans réponse n'est pas répétée, elle revient dans le
rappel de fin de visite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .checklist import OUVERTURES, PRESENCES_LOGEMENT, TOUJOURS_PRESENTS, TYPES, Checklist, Element, avec_article, cle_texte  # noqa: F401


@dataclass(frozen=True)
class QuestionPlan:
    code: str  # champ ou étape visé : « M1.isolation », « suite:mur », « presence:fenetre »…
    texte: str
    cle: str  # pour ne jamais poser deux fois la même question


def _capitale(texte: str) -> str:
    return texte[:1].upper() + texte[1:]


ORDRE_COTES = ("nord", "sud", "est", "ouest")  # Noah : « le mur nord, puis le sud, puis l'est et l'ouest »


def texte_cote(cote: str) -> str:
    """« Et le mur sud, il donne sur quoi ? » : un côté à la fois (retour de Noah du 22/10 au soir : une question pour
    trois côtés, avec « des voisins » ou « non », ne convenait pas à deux murs sur le voisin et un sur la rue)."""
    return f"Et le mur {cote}, il donne sur quoi ?"


def texte_champ(element: Element, champ: str, meme_element: bool, nom: str = "") -> str:
    """Question courte sur un champ. Si la question précédente portait déjà sur cet élément, on
    ne le renomme pas (« Il est isolé ? »). Sinon, il est désigné par son nom parlant (`nom` :
    « ce mur », « le mur côté voisin »), jamais par un numéro (étape 5 de Noah)."""
    d = _capitale(nom or element.description)
    sujet = f"{d}," if "," in d else d  # « Le mur nord, celui avec la télé, est en quoi ? »
    t = element.type
    if t == "mur":
        if d.endswith(" est"):  # « Le mur est, il est en quoi ? » plutôt que « Le mur est est en quoi ? » (étape 13)
            sujet = f"{d}, il"
        return {
            "donne_sur": f"{d} donne sur quoi ?" if d.endswith(" est") else f"{sujet} donne sur quoi ?",
            "materiau": "Il est en quoi ?" if meme_element else f"{sujet} est en quoi ?",
            "epaisseur": "Quelle épaisseur ?" if meme_element else f"{d}, quelle épaisseur ?",
            "isolation": "Il est isolé ?" if meme_element else f"{sujet} est isolé ?",
        }[champ]
    if t in ("plafond", "plancher") and element.description != element.type_element.designation:
        # Une partie propre à une pièce (« le plafond de la cuisine ») : on la nomme (étape 13).
        texte = {"donne_sur": "au-dessus : combles, terrasse ou logement ?" if t == "plafond"
                 else "en dessous : terre-plein, vide sanitaire, cave ou logement ?", "isolation": "isolé ?"}[champ]
        return f"{d}, {texte}"
    if t == "plafond":  # celui du logement : demandé une seule fois (étape 13)
        return {"donne_sur": "Au-dessus du logement : combles, terrasse ou un autre logement ?",
                "isolation": "Le plafond est isolé ?"}[champ]
    if t == "plancher":
        return {"donne_sur": "Sous le logement : terre-plein, vide sanitaire, cave ou un autre logement ?",
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
    # Étape 13 : « ce mur donne sur quoi ? », et non « décrivez le premier mur » ou « quels murs dans cette pièce ? ».
    "mur": "Ce mur donne sur quoi ?",
    "fenetre": "Des fenêtres ou une porte sur ce mur ?",  # mur par mur, pas pièce par pièce
    "emetteur": "Et les radiateurs : à eau ou électriques ?",  # ceux du logement
    "chauffage": "Quel est le chauffage principal ?",
    "ecs": "Et l'eau chaude, comment est-elle produite ?",
    "ventilation": "Ventilation : VMC ou naturelle ?",
}
QUESTIONS_SUITE = {
    # Les côtés manquants sont demandés un par un (`texte_cote`) ; ensuite, ou sans boussole, un mur de plus : une maison
    # peut avoir plus de quatre murs autour d'elle. Il le montre à la caméra, qui donne son côté.
    "mur": "Un autre mur autour du logement, à me montrer ?",
    "fenetre": "D'autres fenêtres, ou une porte vers l'extérieur ?",
}
# Date et température des radiateurs : jamais demandées (Noah, étape 4), mais notées dès qu'elles sont dites.
QUESTIONS_SECONDAIRES = {
    ("ecs", "annee"): "Le ballon d'eau chaude date de quand ?",
}
QUESTION_FIN = "C'est complet pour le DPE."  # étape 13 : plus de « pièce suivante ? »


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


def cle_suite(checklist: Checklist, type_element: str) -> str:
    """Clé de « Et côtés nord et sud… ? » / « D'autres fenêtres… ? » dans la pièce en cours : la même pour le parcours
    et pour les questions de Claude (test de Noah du 22/10 après-midi : Claude reposait « Un autre mur ? » sous une
    autre clé, 10 fois). Pour les murs, elle ne change qu'avec les côtés du logement qui restent à décrire (étape 13) ;
    pour les fenêtres, avec une fenêtre de plus."""
    if type_element == "mur":
        return f"suite:mur#{len(checklist.enveloppe('mur', interieurs=True))}"  # reposée après chaque mur de plus
    return f"suite:{type_element}#{len([e for e in checklist.elements if e.type in OUVERTURES])}"


def texte_fenetres(checklist: Checklist, mur: Element) -> str:
    """« Des fenêtres ou une porte sur ce mur ? », ou, si on a parlé d'autre chose depuis, « Le mur est : des fenêtres
    ou une porte ? »."""
    nom = checklist.nom(mur)
    return QUESTIONS_PRESENCE["fenetre"] if nom.startswith("ce mur") else f"{_capitale(nom)} : des fenêtres ou une porte ?"


def questions(checklist: Checklist, dernier_id: str | None = None) -> Iterator[QuestionPlan]:
    """Les questions possibles, dans l'ordre du parcours DPE : l'enveloppe du logement par côté, puis ses équipements. La
    pièce où l'on est n'y joue aucun rôle (étape 13)."""
    separes = {e.parent for e in checklist.elements if e.parent}
    murs = checklist.enveloppe("mur")

    # 1. Les murs du logement : le mur en cours (le dernier dont il a parlé) d'abord, puis les plus récents ; chacun avec
    # ses fenêtres et portes. Un mur filmé du même côté qu'un mur déjà décrit l'a rejoint : rien n'est redemandé.
    if not murs and "mur" not in checklist.clos:
        yield QuestionPlan("presence:mur", QUESTIONS_PRESENCE["mur"], "presence:mur")
    courant = next((m for m in murs if m.id == checklist.dernier.get("mur")), None)
    for mur in ([courant] if courant else []) + [m for m in reversed(murs) if m is not courant]:
        yield from _champs(checklist, [mur], dernier_id, separes)
        if checklist.fenetres_a_confirmer(mur):
            yield QuestionPlan(f"fenetres:{mur.id}", texte_fenetres(checklist, mur), f"fenetres:{mur.id}")
        yield from _champs(checklist, checklist.fenetres_du_mur(mur), dernier_id, separes)

    # 2. L'orientation d'un mur si la boussole manque (une fois ; avec le gyroscope, les autres s'en déduisent), puis les
    # côtés du logement dont rien n'est dit (la question ne revient que si ces côtés changent).
    if (mur := checklist.orientation_a_demander()) is not None:
        cle = "orientation@visite" if checklist.boussole_gyroscope else f"orientation:{mur.id}"
        nom = _capitale(checklist.nom(mur))
        yield QuestionPlan(f"orientation:{mur.id}", f"{nom}{',' if ',' in nom else ''} est orienté nord, sud, est ou ouest ?", cle)
    if "mur" not in checklist.clos and murs:  # aucun mur encore : « Ce mur donne sur quoi ? » suffit
        if any(m.orientation for m in murs):  # avec un côté connu : les autres, un par un
            for cote in (c for c in ORDRE_COTES if c in checklist.orientations_manquantes()):
                yield QuestionPlan(f"cote:{cote}", texte_cote(cote), f"cote:{cote}")
        yield QuestionPlan("suite:mur", QUESTIONS_SUITE["mur"], cle_suite(checklist, "mur"))

    # 3. Le plafond, puis le plancher du logement (et une partie propre à une pièce, si elle a été dite).
    for type_element in TOUJOURS_PRESENTS:
        yield from _champs(checklist, checklist.enveloppe(type_element), dernier_id, separes)
    # Les fenêtres dont on ne sait pas encore le mur.
    yield from _champs(checklist, [o for o in checklist.enveloppe() if checklist.sans_mur(o)], dernier_id, separes)

    # 4. Une seule fois pour le logement : chauffage, émetteurs, eau chaude, ventilation, puis les détails secondaires.
    for type_element in PRESENCES_LOGEMENT:
        existants = [e for e in checklist.elements_de(None) if e.type == type_element]
        deduit = type_element == "emetteur" and checklist.emetteurs_deduits()  # radiateurs électriques : c'est le chauffage
        if not existants and type_element not in checklist.absences_logement and not deduit:
            yield QuestionPlan(f"presence:{type_element}", QUESTIONS_PRESENCE[type_element], f"presence:{type_element}")
        yield from _champs(checklist, existants, dernier_id, separes)
    for (type_element, champ) in checklist.manques_secondaires():
        if (type_element, champ) in QUESTIONS_SECONDAIRES:
            code = f"secondaire:{type_element}.{champ}"
            yield QuestionPlan(code, QUESTIONS_SECONDAIRES[(type_element, champ)], code)

    # 5. Tout est dit pour le DPE.
    if not checklist.manques_visite():
        yield QuestionPlan("fin", QUESTION_FIN, "fin")
