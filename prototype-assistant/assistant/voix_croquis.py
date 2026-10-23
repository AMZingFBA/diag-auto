"""Ce que dit le diagnostiqueur pendant le croquis (amiante, plomb), compris par Claude quand les règles ne suffisent pas.

Test de Noah du 23/10 : il nomme lui-même chaque espace en le filmant, avec ses mots, et souvent sans y entrer (« c'est
la cuisine », « petit couloir », « ici on a un truc », « ici c'est le salon », « au bout du salon on a une chambre »,
« on retourne dans le salon », « ça c'est la cuisine du début », « ici, ça c'est l'entrée », « remplace, t'as mis séjour
à la place de cuisine », « ici il y a l'escalier ») ; la transcription en direct est souvent abîmée. Les règles n'avaient
compris qu'une phrase sur douze, et à contresens. Ici, Claude dit le GESTE de chaque phrase :
- « ici » : il est dans l'espace nommé (ou y entre) ;
- « vue » : il montre un espace voisin sans y entrer (la caméra le filme) ;
- « retour » : il revient dans un espace déjà vu ;
- « correction » : l'espace affiché est faux (« non c'est… », « t'as mis X à la place de Y », « remplace… ») ;
- « inconnu » : une porte vers un local qu'il ne connaît pas (« un truc ») ;
- « question » : il s'adresse au logiciel (« tu m'entends ? », « c'est bon ? ») ;
- « rien » : autre chose.
Son mot est gardé tel quel (« salon » reste « salon »).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

GESTES = ("ici", "vue", "retour", "correction", "inconnu", "question", "rien")

CONSIGNES_VOIX_CROQUIS = (
    "Tu aides un diagnostiqueur immobilier qui filme un logement pour en dessiner le croquis (repérage amiante ou plomb). "
    "Il nomme les espaces en les filmant, avec ses mots, souvent sans y entrer. On te donne la phrase qu'il vient de dire "
    "(la transcription automatique est parfois abîmée : devine les mots probables), l'espace où le logiciel le croit, et les "
    "espaces déjà sur le croquis. Dis le geste de la phrase :\n"
    "- « ici » : il est dans l'espace qu'il nomme, ou y entre (« ici c'est le salon », « c'est la cuisine », « petit couloir ») ;\n"
    "- « vue » : il montre un espace voisin sans y entrer (« au bout du salon on a une chambre », « ça c'est l'entrée ») ;\n"
    "- « retour » : il revient dans un espace déjà vu (« on retourne dans le salon », « la cuisine du début ») ;\n"
    "- « correction » : l'espace affiché est faux (« non c'est la buanderie », « t'as mis séjour à la place de cuisine », "
    "« remplace… ») : donne le bon nom, et le nom faux s'il le dit ;\n"
    "- « inconnu » : une porte vers un local qu'il ne connaît pas (« ici on a un truc ») ;\n"
    "- « question » : il s'adresse au logiciel (« tu m'entends ? », « c'est bon ? ») ;\n"
    "- « rien » : autre chose (un commentaire, du bruit).\n"
    "Garde son mot pour le nom (« salon » reste « salon » ; « petit couloir » devient « Couloir »). Réponds uniquement par un "
    "JSON sur une ligne : {\"geste\": \"…\", \"nom\": \"…\", \"faux\": \"…\", \"reponse\": \"…\"}. « reponse » : 2 à 4 mots à lui "
    "dire seulement pour une question ou une correction (« Oui, je vous entends. », « D'accord, cuisine. »), sinon vide.")


@dataclass
class GesteVoix:
    geste: str
    nom: str = ""
    faux: str = ""
    reponse: str = ""


def contenu_voix(phrase: str, courante: str | None, pieces: list[str]) -> list[dict]:
    texte = (f"Phrase : « {phrase} »\nEspace où le logiciel le croit : « {courante or 'aucun encore'} »\n"
             f"Espaces déjà sur le croquis : {', '.join(f'« {p} »' for p in pieces) or 'aucun'}")
    return [{"type": "text", "text": texte}]


def nom_propre(nom: str) -> str:
    """« petit couloir » → « Couloir » ; « la cuisine » → « Cuisine » : le nom d'un espace, sans article ni qualificatif."""
    nom = " ".join(str(nom or "").split()).strip(" .,;:!?«»\"'")
    nom = re.sub(r"^(?:(?:le|la|les|un|une|des|du|de la)\s+|l['’]\s*)", "", nom, flags=re.IGNORECASE)
    nom = re.sub(r"^(?:petit|petite|grand|grande)\s+", "", nom, flags=re.IGNORECASE)
    return nom[:1].upper() + nom[1:] if nom else ""


def analyser_voix(texte: str) -> GesteVoix | None:
    m = re.search(r"\{.*\}", texte or "", re.DOTALL)
    if not m:
        return None
    try:
        donnees = json.loads(m.group(0))
    except ValueError:
        return None
    geste = str(donnees.get("geste") or "").strip().lower()
    if geste not in GESTES:
        return None
    nom = nom_propre(donnees.get("nom") or "")
    if geste in ("ici", "vue", "retour", "correction") and not nom:
        return None
    reponse = " ".join(str(donnees.get("reponse") or "").split())[:60]
    return GesteVoix(geste, nom, nom_propre(donnees.get("faux") or ""), reponse)
