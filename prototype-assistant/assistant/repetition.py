"""Ne pas répéter ce que dit le diagnostiqueur (étape 9 de Noah).

« Laine de verre 30 cm » → pas de « OK, c'est noté laine de verre 30 cm » : un bip, puis directement la question suivante.
Ce module mesure ce qu'une réponse de l'assistant reprend de la phrase du diagnostiqueur (mots porteurs de sens communs aux
deux), et reconnaît une phrase qui n'est qu'une reformulation, pour que le serveur ne la dise pas.
"""

from __future__ import annotations

import re

from .checklist import cle_texte

# Mots sans contenu propre (articles, prépositions, pronoms, verbes de liaison, accusés de réception).
MOTS_VIDES = set("""
a ai as au aux avec avez avoir bien c ca ce ceci cela celle celles celui cet cette ces chez comme d dans de des deja
dessus donc du e elle elles en encore enfin est et etait etre eu fait faire fais il ils j je l la le les leur leurs lui
m ma mais me meme mes moi mon n ne ni non nos notre nous o on ont ou oui ok par parce pas peu plus pour pres qu que quel
quelle quels quelles qui quoi s sa sans se ses si son sont sous sur t ta te tes toi ton tous tout toute toutes tres tu
un une va vers voila vos votre vous y alors bon note notee notes accord daccord compris parfait voici ici la la-bas aussi
puis apres ensuite donne donnent
""".split())
# Noms des éléments : la question suivante doit pouvoir nommer l'élément (« ce mur, il est en quoi ? »).
NOMS_ELEMENTS = set("""
mur murs cloison cloisons fenetre fenetres porte portes baie baies plafond plafonds plancher planchers sol piece pieces
radiateur radiateurs emetteur emetteurs convecteur convecteurs chauffage chaudiere eau chaude ventilation vmc ballon
logement maison appartement premier deuxieme troisieme quatrieme autre autres
""".split())
NOMBRES = {
    "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7", "huit": "8",
    "neuf": "9", "dix": "10", "onze": "11", "douze": "12", "quinze": "15", "vingt": "20", "trente": "30",
    "quarante": "40", "cinquante": "50", "soixante": "60", "cent": "100",
}
UNITES = {"cm": "centimetres", "centimetre": "centimetres", "m": "metres", "metre": "metres"}


def mots_porteurs(texte: str) -> list[str]:
    """Les mots porteurs de sens d'un texte, sous une forme comparable (« trente centimètres » = « 30 cm »). Le nombre
    d'un groupe fait partie de son nom (« les 2 fenêtres : des volets ? ») : il n'est pas compté."""
    mots = []
    tous = [UNITES.get(m, NOMBRES.get(m, m)) for m in re.findall(r"[a-z0-9]+", cle_texte(texte).replace("'", " "))]
    for k, mot in enumerate(tous):
        if mot.isdigit() and k + 1 < len(tous) and tous[k + 1] in NOMS_ELEMENTS:
            continue
        if mot in MOTS_VIDES or mot in NOMS_ELEMENTS or (len(mot) < 2 and not mot.isdigit()):
            continue
        mots.append(mot[:-1] if len(mot) > 3 and mot.endswith("s") and not mot.isdigit() else mot)  # pluriel simple
    return mots


def mots_repetes(phrase: str, reponse: str) -> list[str]:
    """Mots porteurs de la réponse déjà présents dans la phrase du diagnostiqueur (objectif : aucun)."""
    dits = set(mots_porteurs(phrase))
    return list(dict.fromkeys(m for m in mots_porteurs(reponse) if m in dits))


def reformulation(phrase: str, reponse: str) -> bool:
    """La réponse ne fait-elle que reprendre ce qu'il vient de dire (« Laine de verre 30 centimètres. ») ?"""
    porteurs = mots_porteurs(reponse)
    if not porteurs:
        return False
    repetes = mots_repetes(phrase, reponse)
    return len(repetes) >= 1 and len(repetes) >= 0.5 * len(set(porteurs))
