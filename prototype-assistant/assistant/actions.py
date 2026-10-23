"""Application des actions proposées (extraction immédiate, Claude ou simulation) à la checklist.

Le serveur vérifie tout : type et champ connus, élément existant, et surtout citation retrouvée
dans ce que le diagnostiqueur a réellement dit. Une action refusée est journalisée, jamais
appliquée.
"""

from __future__ import annotations

import re

from .checklist import Checklist, ErreurChecklist, cle_texte
from .citations import citation_trouvee

# « C'est la première pièce » : Claude l'avait appelée « U » (test de Noah du 22/10 après-midi : « la pièce U »).
# « On passe dans la cuisine », « je vais dans la chambre » : un déplacement, pas un nouveau nom pour la pièce où l'on est.
_DEPLACEMENT = re.compile(r"\b(?:pass\w*|va|vais|allons|allez|aller|entr\w*|rentr\w*|sor\w*|arriv\w*|mainten\w*|ensuite|apres)\b")
_PREMIERE_PIECE = re.compile(r"^(?:la\s+)?(?:pi[eè]ce\s+)?(?:u|un|une|1|premi[eè]re)(?:\s+pi[eè]ce)?$", re.IGNORECASE)


def _nom_piece(checklist: Checklist, nom: str) -> str:
    """Un vrai nom de pièce : « U », « une », « première pièce » → « Pièce 1 » ; une ou deux lettres (sauf WC) →
    « Pièce n »."""
    nom = " ".join(nom.split())
    if _PREMIERE_PIECE.match(nom):
        return "Pièce 1"
    if len(nom.replace(" ", "")) <= 2 and nom.upper() != "WC":
        return f"Pièce {len(checklist.pieces) + 1}"
    return nom


def _texte(action: dict, cle: str) -> str:
    valeur = action.get(cle)
    return valeur.strip() if isinstance(valeur, str) else ""


def _nombre(action: dict) -> int | None:
    valeur = action.get("nombre")
    if valeur is None or valeur == "":
        return None
    try:
        return int(valeur)
    except (TypeError, ValueError):
        raise ErreurChecklist(f"nombre d'éléments invalide : {valeur!r}") from None


def _valeurs(action: dict, cle: str = "valeurs") -> dict[str, str]:
    valeurs = action.get(cle) or {}
    if not isinstance(valeurs, dict) or not all(isinstance(c, str) and isinstance(v, str) and v.strip() for c, v in valeurs.items()):
        raise ErreurChecklist(f"{cle} invalides : {valeurs!r}")
    return {c.strip(): v.strip() for c, v in valeurs.items()}


def _par_description(checklist: Checklist, type_element: str, description: str, piece: str | None) -> str:
    """Un élément créé par la même phrase, retrouvé par son nom : dans la pièce, ou parmi les murs du logement (étape 13)."""
    nom = cle_texte(description)
    candidats = checklist.enveloppe(type_element, interieurs=True) + list(reversed(checklist.elements_de(piece)))
    element = next((e for e in candidats if e.type == type_element and cle_texte(e.description) == nom), None)
    if element is None:
        raise ErreurChecklist("élément introuvable")
    return element.id


def _piece(checklist: Checklist, action: dict, t: float) -> str | None:
    """« Le radiateur de la cuisine » : la pièce nommée (créée si besoin, sans y entrer), sinon la pièce courante."""
    nom = _texte(action, "piece")
    return checklist.piece_pour(nom, t) if nom else None


_AVEC_CITATION = ("enregistrer_reponse", "marquer_sans_objet", "cloturer", "copier", "scinder", "compter", "regle", "exception", "murs",
                  "orienter", "fusionner")


def appliquer_action(checklist: Checklist, action: dict, t: float, phrases: list[str]) -> dict:
    outil = _texte(action, "outil")
    resultat = {"action": action, "statut": "accepte", "raison": ""}
    try:
        if _texte(action, "element_id") and not _texte(action, "type"):
            # Claude omet souvent le type d'un élément qu'il désigne par son identifiant : c'est celui de l'élément.
            action = {**action, "type": checklist.trouver_element(_texte(action, "element_id")).type}
            resultat["action"] = action
        citation = _texte(action, "citation")
        if outil in _AVEC_CITATION and not citation_trouvee(citation, phrases):
            raise ErreurChecklist("citation introuvable dans ce qui a été dit")
        if outil == "piece_courante":
            confirme = bool(citation) and citation_trouvee(citation, phrases)
            nom = _nom_piece(checklist, _texte(action, "nom"))
            actuelle = checklist.pieces.get(checklist.piece_courante or "")
            correction = (confirme and _texte(action, "correction") == "oui" and actuelle is not None and actuelle.source == "image"
                          and not _DEPLACEMENT.search(cle_texte(citation)))
            existante = checklist.trouver_piece(nom)
            if _texte(action, "nouvelle") == "oui":
                # « C'est une autre chambre » : jamais la chambre déjà vue, une nouvelle (« Chambre 2 »).
                checklist.definir_piece(checklist.nom_libre(_texte(action, "nom")), t, citation if confirme else "")
            elif correction and existante is None:
                # « Non, c'est la chambre » dans une pièce reconnue sur l'image : la même pièce, mal nommée (croquis).
                checklist.renommer_piece(checklist.piece_courante, nom)
            elif correction and existante != checklist.piece_courante:
                # « Non, c'est le séjour » : pas une autre pièce, un coin du séjour reconnu à tort (essai du 22/10).
                checklist.fusionner_pieces(checklist.piece_courante, existante)
            else:
                # Une pièce déjà vue sous ce nom ou un autre (« le salon » quand Claude l'a appelée « Séjour », « la
                # chambre » quand il n'y a que « Chambre 1 ») : on y revient, jamais deux pièces pour un même espace.
                checklist.definir_piece(checklist.nom_piece(existante) if existante else nom, t, citation if confirme else "")
            if not confirme:
                resultat["raison"] = "pièce déduite de l'image, à confirmer"
        elif outil == "signaler_element":
            source = "voix" if _texte(action, "source") == "voix" else "image"
            if _texte(action, "element_id"):  # élément déjà connu : son repère ou son mur (« il y a 3 fenêtres dessus »)
                element = checklist.completer(_texte(action, "element_id"), _texte(action, "repere"), _texte(action, "support"))
            else:
                element = checklist.signaler_element(_texte(action, "type"), _texte(action, "description"), t, source=source,
                                                     nombre=_nombre(action), piece=_piece(checklist, action, t),
                                                     repere=_texte(action, "repere"), support=_texte(action, "support"))
            resultat["element"] = element.id
        elif outil == "orienter":  # « non, c'est le mur ouest » (étape 6)
            ident = _texte(action, "element_id") or _par_description(  # élément créé par la même phrase
                checklist, _texte(action, "type"), _texte(action, "description"), _piece(checklist, action, t) or checklist.piece_courante)
            resultat["element"] = checklist.orienter(ident, _texte(action, "orientation"), citation, t).id
        elif outil == "fusionner":  # « C'est le même mur ? » « Oui. » : doublon confirmé par le diagnostiqueur (étape 9)
            resultat["element"] = checklist.fusionner(_texte(action, "element_id"), _texte(action, "meme_que")).id
        elif outil == "murs":  # « cette pièce fait 4 murs »
            checklist.compter_murs(_nombre(action) or 0, citation, t)
        elif outil in ("enregistrer_reponse", "marquer_sans_objet"):
            commun = dict(
                type_element=_texte(action, "type"), champ=_texte(action, "champ"), citation=citation, t=t,
                element_id=_texte(action, "element_id") or None, description=_texte(action, "description"),
            )
            if outil == "enregistrer_reponse":
                element = checklist.enregistrer(valeur=_texte(action, "valeur"), nombre=_nombre(action), note=_texte(action, "note"),
                                                piece=_piece(checklist, action, t), **commun)
                resultat["element"] = element.id
            else:  # « pas de fenêtre sur ce mur » : `support` (étape 13)
                checklist.marquer_sans_objet(support=_texte(action, "support"), **commun)
        elif outil == "cloturer":  # « pas d'autre mur » : la liste de la pièce est complète
            checklist.cloturer(_texte(action, "type"), citation, t)
        elif outil == "copier":  # « plafond pareil que le séjour »
            source = cle_texte(_texte(action, "piece_source"))
            resultat["element"] = checklist.copier(_texte(action, "type"), source, citation, t).id
        elif outil == "scinder":  # « dont une en bois », « tous sauf un » ; « mur est : 60 % voisin, 40 % dehors » (étape 13)
            ident = _texte(action, "element_id") or _par_description(
                checklist, _texte(action, "type"), _texte(action, "de"), _piece(checklist, action, t) or checklist.piece_courante)
            element = checklist.scinder(ident, _nombre(action) or 1, _texte(action, "description"), t, citation, _valeurs(action))
            resultat["element"] = element.id
        elif outil == "compter":  # nouveau nombre d'un groupe
            if not _nombre(action):
                raise ErreurChecklist("nombre manquant")
            element = checklist.changer_nombre(_texte(action, "element_id"), _nombre(action), citation, t, _texte(action, "description"),
                                               correction=action.get("correction") is True)
            resultat["element"] = element.id
        elif outil == "regle":  # « toutes les fenêtres sont en bois, sauf celle de la chambre »
            exceptions = action.get("exceptions") or {}
            if not isinstance(exceptions, dict):
                raise ErreurChecklist(f"exceptions invalides : {exceptions!r}")
            piece = _texte(action, "piece")
            checklist.ajouter_regle(_texte(action, "type"), _valeurs(action), citation, t,
                                    piece=checklist.piece_pour(piece, t) if piece else None,
                                    exceptions={p: _valeurs(exceptions, p) for p in exceptions})
        elif outil == "exception":  # « sauf celle de la chambre, qui est en PVC », dit après la règle
            if checklist.ajouter_exception(_texte(action, "type"), _texte(action, "piece"), _valeurs(action), citation, t) is None:
                raise ErreurChecklist("aucune règle du logement à laquelle rattacher cette exception")
        else:
            raise ErreurChecklist(f"outil inconnu : {outil!r}")
    except ErreurChecklist as e:
        resultat.update(statut="refuse", raison=str(e))
    return resultat


def appliquer(checklist: Checklist, actions: list[dict], t: float, phrases: list[str]) -> list[dict]:
    return [appliquer_action(checklist, a, t, phrases) for a in actions]
