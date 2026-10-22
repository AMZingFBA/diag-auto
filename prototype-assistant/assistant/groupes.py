"""Groupes, quantités et exceptions dans une phrase (retour de Noah, étape 4 du 22/10/2026).

« Il y a 9 radiateurs électriques basse température et 1 électrique haute température » décrit deux
groupes distincts ; « 2 en PVC et une en bois », « toutes sauf une ont des volets roulants », « dont
une en simple vitrage », « l'une d'elles est en bois », « sauf celle de la chambre qui est en PVC »
découpent ou corrigent un groupe.

Ce module ne fait que découper le texte (déjà normalisé : minuscules, sans accents, nombres en
chiffres). extraction.py lit ensuite les valeurs de chaque morceau et décide quels éléments créer,
séparer ou compléter. Rien n'est supposé identique s'il n'a pas été dit :
- « 3 radiateurs à eau, 2 en fonte et 1 en acier » : 2 + 1 = 3, ce sont des sous-groupes du groupe
  annoncé, ils en reprennent les valeurs (« à eau ») ;
- « 9 radiateurs électriques et 1 haute température » : 9 + 1 ≠ 9, ce sont deux groupes distincts, le
  second ne reprend rien du premier (on demandera s'il est électrique) ;
- « dont une », « sauf une », « à part une » : une exception, séparée du groupe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_EXCEPTION = r"sauf|a part|excepte|hormis|dont|mis a part"
# Après un nombre, ces mots en font une mesure et non une quantité : « 30 cm », « 2 m par 1 », « 15 ans ».
_UNITES = r"(?:cm|mm|m|metres?|centimetres?|ans?|fois|kw|litres?|degres?|par|x|sur|heures?|h|%)\b"
_Q = (r"(?P<q>les autres|le reste|l autre|les (?P<n_autres>\d{1,2}) autres|(?P<n_autres2>\d{1,2}) autres"
      r"|celui|celle|ceux|celles|l une|l un|une|un|(?P<n>\d{1,2}))\b(?!\s*(?:" + _UNITES + r"|\.\d))")
# « … sauf une en bois », « dont 2 en simple vitrage », « sauf dans la chambre » (quantité facultative).
_DEBUT_EXCEPTION = re.compile(r"\b(?P<sep>" + _EXCEPTION + r")\b\s*(?:" + _Q + r")?")
# « 2 en PVC et 1 en bois », « l'un est électrique, les autres à eau » (quantité obligatoire).
_DEBUT_PARTIE = re.compile(r"(?:^|(?<=,)|\b(?P<sep>et|mais|puis)\b)\s*(?:(?:oui|il y en a|y en a|il y a)\s+)?" + _Q)
# « un des radiateurs », « l'une d'elles », « 2 d'entre eux » : une partie d'un groupe déjà décrit.
_PARTIE_DE = re.compile(r"^\s*(?:des|d entre (?:eux|elles)|d elles|d eux|de ces|parmi (?:les|ces|eux|elles))\b")
# « Toutes sauf une ONT des volets roulants » : ce qui suit la quantité revient au groupe principal.
_VERBE_PLURIEL = re.compile(r"^\s*(?:,\s*)?(?:ont|sont|font|possedent)\b")
_TOUS = re.compile(r"\b(?:tous|toutes)\b")
# « …, une en bois, toutes en double vitrage » : ce qui suit vaut pour toutes les parties.
_COMMUN = re.compile(r"(?:^|,|\bet\b)\s*(?:tous|toutes)\b(?!\s+sauf)(?:\s+(?:les|ont|sont))?")


@dataclass
class Partie:
    """Un morceau de groupe dit dans la phrase : « 2 en PVC », « une en bois », « les autres à eau »."""

    texte: str  # ce qui est dit de cette partie (ses valeurs à lire)
    nombre: int | None  # None : « les autres », « le reste », « celle de la chambre », « sauf » seul
    position: int = 0  # début de la partie dans le texte découpé (mot « sauf », « et »… compris)
    exception: bool = False  # après « sauf », « dont », « à part »… : une exception au groupe
    reste: bool = False  # « les autres », « le reste », « l'autre » : ce qui reste du groupe
    designe: bool = False  # « celui », « celle » (de la chambre)
    un: bool = False  # quantité « un » ou « une » : ambiguë avec l'article, à confirmer par le contexte
    partie_de: bool = False  # « un des radiateurs », « l'une d'elles »
    dont: bool = False  # « dont une » : sous-ensemble qui partage les valeurs du groupe


@dataclass
class Decoupage:
    tete: str  # avant la première partie : « 9 radiateurs électriques basse température », « toutes »
    parties: list[Partie] = field(default_factory=list)
    tous: bool = False  # « tous », « toutes » : la tête vaut pour tout le groupe, sauf les exceptions
    au_principal: str = ""  # « toutes sauf une ont des volets roulants » : « des volets roulants »
    commun: str = ""  # « …, une en bois, toutes en double vitrage » : vaut pour toutes les parties


def _nombre(m: re.Match) -> tuple[int | None, bool, bool, bool]:
    """(nombre, reste, designe, un) d'une quantité reconnue."""
    q = m.group("q")
    if q is None:
        return None, False, False, False
    for nom in ("n", "n_autres", "n_autres2"):
        if m.group(nom):
            return int(m.group(nom)), nom != "n", False, False
    if q in ("un", "une", "l un", "l une"):
        return 1, False, False, True
    if q == "l autre":
        return 1, True, False, False
    if q in ("les autres", "le reste"):
        return None, True, False, False
    return (1 if q in ("celui", "celle") else None), False, True, False


def decouper(texte: str) -> Decoupage:
    """Découpe un morceau de phrase en tête + parties (sous-groupes, exceptions)."""
    debuts: list[tuple[int, int, re.Match, bool]] = []
    for motif, exception in ((_DEBUT_EXCEPTION, True), (_DEBUT_PARTIE, False)):
        for m in motif.finditer(texte):
            if m.end() > m.start() and not any(a <= m.start() < b or m.start() <= a < m.end() for a, b, _, _ in debuts):
                debuts.append((m.start(), m.end(), m, exception))
    debuts.sort(key=lambda d: d[0])
    resultat = Decoupage(tete=texte[: debuts[0][0]] if debuts else texte)
    exception = False
    for k, (debut, fin, m, est_exception) in enumerate(debuts):
        exception = exception or est_exception  # « sauf un électrique et un en fonte » : deux exceptions
        suite = texte[fin: debuts[k + 1][0] if k + 1 < len(debuts) else len(texte)]
        nombre, reste, designe, un = _nombre(m)
        if m.group("q") is None and not est_exception:
            continue
        partie = Partie(suite.strip(" ,"), nombre, debut, exception, reste, designe, un, dont=m.groupdict().get("sep") == "dont")
        if (pd := _PARTIE_DE.match(suite)) and nombre:
            partie.partie_de, partie.exception, partie.dont = True, True, True
            partie.texte = suite[pd.end():].strip(" ,")
        if exception and (v := _VERBE_PLURIEL.match(partie.texte)):
            resultat.au_principal += " " + partie.texte[v.end():]
            partie.texte = ""
        if commun := _COMMUN.search(partie.texte):
            resultat.commun += " " + partie.texte[commun.end():]
            partie.texte = partie.texte[: commun.start()]
        resultat.parties.append(partie)
    resultat.tous = bool(_TOUS.search(resultat.tete))
    return resultat
