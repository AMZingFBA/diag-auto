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


def appliquer_action(checklist: Checklist, action: dict, t: float, phrases: list[str]) -> dict:
    outil = _texte(action, "outil")
    resultat = {"action": action, "statut": "accepte", "raison": ""}
    try:
        if outil == "piece_courante":
            citation = _texte(action, "citation")
            confirme = bool(citation) and citation_trouvee(citation, phrases)
            checklist.definir_piece(_texte(action, "nom"), t, citation if confirme else "")
            if not confirme:
                resultat["raison"] = "pièce déduite de l'image, à confirmer"
        elif outil == "signaler_element":
            source = "voix" if _texte(action, "source") == "voix" else "image"
            element = checklist.signaler_element(_texte(action, "type"), _texte(action, "description"), t, source=source, nombre=_nombre(action))
            resultat["element"] = element.id
        elif outil in ("enregistrer_reponse", "marquer_sans_objet"):
            citation = _texte(action, "citation")
            if not citation_trouvee(citation, phrases):
                raise ErreurChecklist("citation introuvable dans ce qui a été dit")
            commun = dict(
                type_element=_texte(action, "type"), champ=_texte(action, "champ"), citation=citation, t=t,
                element_id=_texte(action, "element_id") or None, description=_texte(action, "description"),
            )
            if outil == "enregistrer_reponse":
                element = checklist.enregistrer(valeur=_texte(action, "valeur"), nombre=_nombre(action), note=_texte(action, "note"), **commun)
                resultat["element"] = element.id
            else:
                checklist.marquer_sans_objet(**commun)
        elif outil in ("cloturer", "copier"):
            citation = _texte(action, "citation")
            if not citation_trouvee(citation, phrases):
                raise ErreurChecklist("citation introuvable dans ce qui a été dit")
            if outil == "cloturer":  # « pas d'autre mur » : la liste de la pièce est complète
                checklist.cloturer(_texte(action, "type"), citation, t)
            else:  # « plafond pareil que le séjour »
                source = cle_texte(_texte(action, "piece_source"))
                resultat["element"] = checklist.copier(_texte(action, "type"), source, citation, t).id
        else:
            raise ErreurChecklist(f"outil inconnu : {outil!r}")
    except ErreurChecklist as e:
        resultat.update(statut="refuse", raison=str(e))
    return resultat


def appliquer(checklist: Checklist, actions: list[dict], t: float, phrases: list[str]) -> list[dict]:
    return [appliquer_action(checklist, a, t, phrases) for a in actions]
