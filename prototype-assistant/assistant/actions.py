"""Application des actions proposées (extraction immédiate, Claude ou simulation) à la checklist.

Le serveur vérifie tout : type et champ connus, élément existant, et surtout citation retrouvée
dans ce que le diagnostiqueur a réellement dit. Une action refusée est journalisée, jamais
appliquée.
"""

from __future__ import annotations

from .checklist import Checklist, ErreurChecklist, cle_texte
from .citations import citation_trouvee


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


def _piece(checklist: Checklist, action: dict, t: float) -> str | None:
    """« Le radiateur de la cuisine » : la pièce nommée (créée si besoin, sans y entrer), sinon la pièce courante."""
    nom = _texte(action, "piece")
    return checklist.piece_pour(nom, t) if nom else None


_AVEC_CITATION = ("enregistrer_reponse", "marquer_sans_objet", "cloturer", "copier", "scinder", "compter", "regle", "exception", "murs",
                  "orienter")


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
            checklist.definir_piece(_texte(action, "nom"), t, citation if confirme else "")
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
            ident = _texte(action, "element_id")
            if not ident:  # élément créé par la même phrase : retrouvé par son nom dans la pièce
                piece = _piece(checklist, action, t) or checklist.piece_courante
                nom = cle_texte(_texte(action, "description"))
                element = next((e for e in reversed(checklist.elements_de(piece)) if e.type == _texte(action, "type")
                                and cle_texte(e.description) == nom), None)
                if element is None:
                    raise ErreurChecklist("élément à orienter introuvable")
                ident = element.id
            resultat["element"] = checklist.orienter(ident, _texte(action, "orientation"), citation, t).id
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
            else:
                checklist.marquer_sans_objet(**commun)
        elif outil == "cloturer":  # « pas d'autre mur » : la liste de la pièce est complète
            checklist.cloturer(_texte(action, "type"), citation, t)
        elif outil == "copier":  # « plafond pareil que le séjour »
            source = cle_texte(_texte(action, "piece_source"))
            resultat["element"] = checklist.copier(_texte(action, "type"), source, citation, t).id
        elif outil == "scinder":  # « dont une en bois », « tous sauf un »
            element = checklist.scinder(_texte(action, "element_id"), _nombre(action) or 1, _texte(action, "description"), t, citation,
                                        _valeurs(action))
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
