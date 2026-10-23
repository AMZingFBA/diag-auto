"""Chaque bouton de chaque question est compris (retour de Noah du 23/10 : « il faut vérifier que toutes fonctionnent »).

Au test du 23/10 au matin, les boutons de « Et le mur sud, il donne sur quoi ? » ne faisaient rien : la question partait
vers le téléphone avec une mauvaise étiquette (« secondaire:mur.donne_sur » au lieu de « cote:sud »), et la réponse
cochée revenait sans être comprise. Les tests passaient, parce qu'aucun ne faisait l'aller-retour par le téléphone.

Ici, une visite complète est jouée question par question, comme le serveur la pose : à chaque question, l'étiquette
envoyée au téléphone doit redonner la même question, et **chaque** bouton (et « Autre… », avec une valeur tapée) doit
être noté et y répondre (la question ne revient pas). Avec la boussole (côtés demandés mur par mur), et sans (orientation
demandée).
"""

import copy

import pytest

from assistant import parcours
from assistant.checklist import Checklist
from assistant.extraction import Cible
from assistant.garde import Questions, champ_rempli
from assistant.reponses import SAISIES, options_pour, valeur_tapee
from assistant.session import appliquer_coche

# Valeurs tapées après « Autre… », par information (le reste : un texte quelconque).
TAPEES = {"materiau": "pisé", "isolation": "laine de bois 12 cm", "menuiserie": "acier", "volets": "persiennes métalliques"}
# Réponse choisie pour avancer dans la visite (sinon le premier bouton) : un mur en partie sur le voisin, un cinquième mur.
CHOIX = {"cote:sud": "en partie sur le voisin, en partie dehors", "cote:est": "local chauffé (voisin)"}


def valeur_du_bouton(cible: Cible, option: dict) -> str | None:
    if not option.get("saisie"):
        return option["valeur"]
    if option["saisie"] == "nombre":
        unite, mini, maxi = SAISIES[cible.champ]
        return str(round((mini + maxi) / 2))
    return valeur_tapee(cible.champ, TAPEES.get(cible.champ, "autre chose"))


def jouer(boussole: str) -> list[str]:
    c = Checklist()
    c.regler_boussole(0.0 if boussole == "bonne" else None, boussole, True)
    garde = Questions()
    posees, autres_murs = [], 0
    for etape in range(200):
        t = 10.0 + etape
        question = None
        for plan in parcours.questions(c):
            texte, cible, raison, cle = garde.filtrer(plan.texte, plan.code, c, t, cle=plan.cle)
            if not raison:
                question = (texte, cible, cle)
                break
        if question is None:
            break
        texte, cible, cle = question
        if cible is None:  # « C'est complet pour le DPE. » : rien à répondre
            posees.append(texte)
            break
        garde.noter(cle, t, une_fois=True)
        posees.append(texte)
        # Aller-retour par le téléphone : la question part avec son étiquette, le bouton revient avec elle.
        retour = Cible.depuis_code(cible.code, c)
        assert retour == cible, f"« {texte} » : étiquette {cible.code} → {retour}"
        options = options_pour(retour)
        assert options, f"« {texte} » : aucun bouton"
        for option in options:
            essai = copy.deepcopy(c)
            valeur = valeur_du_bouton(retour, option)
            assert valeur, f"« {texte} » / {option['libelle']} : valeur tapée refusée"
            resultats = appliquer_coche(essai, Cible.depuis_code(cible.code, essai), valeur, f"coché : {option['libelle']}", t)
            assert any(r["statut"] == "accepte" for r in resultats), f"« {texte} » / {option['libelle']} : {resultats}"
            if cible.genre == "suite" and valeur == "oui":  # « Oui, un autre » : un mur de plus, la liste reste ouverte
                assert len(essai.enveloppe("mur", interieurs=True)) > len(c.enveloppe("mur", interieurs=True))
            else:
                assert champ_rempli(Cible.depuis_code(cible.code, essai), essai), f"« {texte} » / {option['libelle']} : sans réponse"
        # On avance : la réponse choisie pour la suite de la visite.
        valeurs = [o["valeur"] for o in options if not o.get("saisie")]
        if cible.code == "suite:mur":
            valeur = "oui" if autres_murs == 0 else "non"  # un cinquième mur, puis c'est tout
            autres_murs += 1
        else:
            valeur = CHOIX.get(cible.code) or next(v for v in valeurs if v not in ("inconnu", "non")) if any(
                v not in ("inconnu", "non") for v in valeurs) else valeurs[0]
        appliquer_coche(c, cible, valeur, f"coché : {valeur}", t)
        if cible.code == "presence:mur" or (cible.genre == "suite" and valeur == "oui"):
            if boussole == "bonne":  # il filme le mur : la boussole donne son côté
                from assistant.boussole import Visee

                mur = c.trouver_element(c.dernier["mur"])
                c.mesurer(mur.id, Visee(270.0 if autres_murs == 0 else 200.0, None, True))
    return posees, c


@pytest.mark.parametrize("boussole", ["bonne", "absente"])
def test_chaque_bouton_de_chaque_question_est_compris(boussole):
    posees, c = jouer(boussole)
    assert posees[-1] == "C'est complet pour le DPE.", posees
    assert len(posees) >= 20
    if boussole == "bonne":
        assert "Et le mur sud, il donne sur quoi ?" in posees and "Un autre mur autour du logement, à me montrer ?" in posees
    else:
        assert any("orienté" in q for q in posees)


def test_chaque_bouton_de_la_fiche_est_compris():
    """La fiche (📋) : chaque information de chaque élément de la visite, chaque bouton, et « Autre… »."""
    from assistant.reponses import options_par_champ

    _, c = jouer("bonne")
    options = options_par_champ()
    essais = 0
    for element in c.elements:
        for champ in element.type_element.champs:
            for option in options.get(f"{element.type}.{champ.cle}", []):
                essai = copy.deepcopy(c)
                cible = Cible("champ", element.type, champ.cle, element.id)
                valeur = valeur_du_bouton(cible, option)
                resultats = appliquer_coche(essai, cible, valeur, f"coché : {option['libelle']}", 0.0)
                assert any(r["statut"] == "accepte" for r in resultats), f"{element.id}.{champ.cle} / {option['libelle']} : {resultats}"
                essais += 1
    assert essais > 100
