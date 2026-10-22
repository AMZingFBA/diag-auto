"""Compréhension orale robuste (étape 3 de Noah) : 30 transcriptions bruitées réalistes, chacune
interprétée par rapport à la dernière question posée. Fautes de transcription, accent, débit rapide,
hésitations, bégaiements, répétitions, corrections, doute.

Chaque cas : (dernière question posée, transcription, interprétation attendue). L'interprétation est :
- ("note", valeur) : la valeur est notée tout de suite ;
- ("confirmer", valeur) : doute, l'assistant propose « J'ai compris <valeur>, c'est bien ça ? » ;
- ("inconnu", None) : « je ne sais pas », noté et on passe à la suite ;
- ("rien", None) : rien à noter, et surtout rien d'inventé.
"""

import asyncio

import pytest

from assistant.actions import appliquer
from assistant.cerveau import Decision
from assistant.checklist import VALEUR_INCONNUE, Checklist
from assistant.extraction import Cible, extraire
from assistant.reglages import Reglages
from assistant.session import Session
from assistant.transcription import TranscripteurSimulation


def sejour() -> Checklist:
    """Un séjour en cours de description : M1, F1 (×3), E1 (×2, type inconnu), E2 (radiateur à eau), CH1, ECS1."""
    c = Checklist()
    c.definir_piece("Séjour", 0)  # PL1, PB1 créés d'office
    c.signaler_element("mur", "le mur avec la télé", 1)
    c.signaler_element("fenetre", "les 3 fenêtres", 1, nombre=3)
    c.signaler_element("emetteur", "les 2 radiateurs", 1, nombre=2)
    e2 = c.signaler_element("emetteur", "le radiateur de l'entrée", 1)
    c.enregistrer(type_element="emetteur", champ="type", valeur="radiateur à eau", citation="à eau", t=1, element_id=e2.id)
    c.signaler_element("chauffage", "le chauffage", 1)
    c.signaler_element("ecs", "l'eau chaude", 1)
    return c


CAS = [
    # Fautes de transcription et accent : interprétées avec les valeurs possibles de la question posée
    ("E1.type", "Oh ! est chaude.", ("note", "radiateur à eau")),  # le cas réel de Noah
    ("E1.type", "O, chaudi.", ("note", "radiateur à eau")),
    ("E2.temperature", "Besse.", ("note", "basse")),
    ("M1.donne_sur", "Ictérieur.", ("note", "extérieur")),
    ("M1.donne_sur", "Le gara…", ("note", "local non chauffé : garage")),
    ("M1.materiau", "Du parpin.", ("note", "parpaing")),
    ("M1.materiau", "Brik.", ("note", "brique")),
    ("F1.menuiserie", "Pévécé.", ("note", "PVC")),
    ("PL1.donne_sur", "Comble perdue.", ("note", "combles perdus")),
    ("PB1.donne_sur", "Terre pleine.", ("note", "terre-plein")),
    ("PB1.donne_sur", "Vie de sanitaire.", ("note", "vide sanitaire")),
    ("CH1.type", "Une chaudière à condensassion.", ("note", "chaudière à condensation")),
    ("ECS1.systeme", "Un ballon thermo.", ("note", "ballon thermodynamique")),
    ("M1.donne_sur", "Intérieur, c'est une cloison.", ("note", "local chauffé")),
    ("M1.materiau", "C'est du, euh, comment on dit, du bloc creux.", ("note", "parpaing")),
    # Débit rapide : mots collés
    ("F1.vitrage", "Doublevitrage.", ("note", "double")),
    # Hésitations, répétitions, bégaiements, phrases coupées
    ("E1.type", "Les, les… électriques.", ("note", "radiateur électrique")),
    ("M1.donne_sur", "Euh… dehors, dehors.", ("note", "extérieur")),
    ("M1.materiau", "Pa… parpaing.", ("note", "parpaing")),
    ("M1.epaisseur", "Euh le… le mur il fait… trente.", ("note", "30 cm")),
    ("M1.epaisseur", "Vingt-cinq centimètres.", ("note", "25 cm")),
    ("M1.isolation", "Isolé par l'intérieur, euh, laine de roche dix.", ("note", "ITI laine de roche 10 cm")),
    ("F1.volets", "Roulant, roulant.", ("note", "roulants")),
    # Corrections et doute
    ("M1.materiau", "Brique, non, parpaing.", ("note", "parpaing")),
    ("F1.menuiserie", "Alu… enfin bois.", ("note", "bois")),
    ("M1.materiau", "Je sais pas trop, je crois que c'est du béton.", ("note", "béton")),
    ("M1.isolation", "Chais pas.", ("inconnu", None)),
    # Doute qui persiste : on propose l'interprétation la plus probable, on ne fait jamais répéter
    ("F1.vitrage", "Doux.", ("confirmer", "double")),
    ("F1.menuiserie", "Bois… ou alu ?", ("confirmer", "alu")),
    # Rien d'utile : rien n'est inventé
    ("M1.materiau", "Allô ? Tu m'entends ?", ("rien", None)),
    ("E1.type", "Attends, je regarde.", ("rien", None)),
]


@pytest.mark.parametrize("code, transcription, attendu", CAS, ids=[f"{i + 1:02d}-{c[1]}" for i, c in enumerate(CAS)])
def test_interpretation_selon_la_question_posee(code, transcription, attendu):
    c = sejour()
    cible = Cible.depuis_code(code, c)
    extraction = extraire(transcription, c, cible)
    resultats = appliquer(c, extraction.actions, 10.0, [transcription])
    assert all(r["statut"] == "accepte" for r in resultats), resultats
    element = c.trouver_element(cible.element_id)
    valeur = element.valeur(cible.champ)
    genre, attendue = attendu
    if genre == "note":
        assert valeur is not None and valeur.valeur == attendue, (valeur, extraction.proposition)
        assert extraction.proposition is None
    elif genre == "confirmer":
        assert valeur is None
        assert extraction.proposition is not None and extraction.proposition["valeur"] == attendue
    elif genre == "inconnu":
        assert valeur is not None and valeur.valeur == VALEUR_INCONNUE and element.a_verifier(cible.champ)
    else:
        assert valeur is None and extraction.proposition is None


def test_au_moins_20_transcriptions_bruitees():
    assert len(CAS) >= 20


def test_correction_et_doute_gardes_pour_la_validation():
    c = sejour()
    extraire_et_appliquer = lambda texte, code: appliquer(c, extraire(texte, c, Cible.depuis_code(code, c)).actions, 10.0, [texte])
    extraire_et_appliquer("Dehor.", "M1.donne_sur")
    assert c.trouver_element("M1").valeur("donne_sur").note == "deviné : « dehor » → extérieur"
    extraire_et_appliquer("Je sais pas trop, je crois que c'est du béton.", "M1.materiau")
    assert c.trouver_element("M1").valeur("materiau").note.startswith("dit avec un doute")


def test_reponse_a_la_confirmation():
    for reponse, attendu in (("Oui, c'est ça.", "double"), ("Non, triple.", "triple"), ("Non.", None)):
        c = sejour()
        cible = Cible.depuis_code("confirmer:F1.vitrage=double", c)
        assert cible.genre == "confirmation" and cible.code == "confirmer:F1.vitrage=double"
        appliquer(c, extraire(reponse, c, cible).actions, 12.0, [reponse])
        valeur = c.trouver_element("F1").valeur("vitrage")
        assert (valeur.valeur if valeur else None) == attendu


class CerveauProbable:
    """Claude qui comprend « Oh ! » comme « eau chaude », mais sans en être sûr."""

    nom = "probable"

    def __init__(self):
        self.contextes = []

    async def demarrer(self):
        pass

    async def fermer(self):
        pass

    async def decider(self, contexte, sur_dire=None):
        self.contextes.append(contexte)
        if contexte.mode != "reponse":
            return Decision()
        return Decision(actions=[{"outil": "enregistrer_reponse", "element_id": "E1", "type": "emetteur", "champ": "type",
                                  "valeur": "radiateur à eau", "citation": contexte.phrase, "certitude": "probable"}])


def test_claude_probable_donne_une_confirmation_et_pas_une_valeur(tmp_path):
    async def scenario():
        cerveau = CerveauProbable()
        reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=tmp_path, veille_s=1000,
                            questions_par_minute=60)
        session = Session("essai", tmp_path, cerveau, cerveau, TranscripteurSimulation(), reglages)
        dits = []

        async def envoyer(m):
            if m["type"] == "dire":
                dits.append(m["texte"])

        session.envoyer = envoyer
        await session.demarrer()
        for phrase in ("Ici c'est le séjour.", "Ce mur donne dehors, brique 30, non isolé.", "Non.", "Comble perdue, isolé 30 cm.",
                       "Terre plein non isolé.", "Non.", "Oui, deux.", "Oh !", "Oui."):
            await session.recevoir_controle({"type": "texte", "texte": phrase})
            await asyncio.sleep(0.02)
            while session.occupe:
                await asyncio.sleep(0.02)
        await session.terminer()
        return session, dits, cerveau

    session, dits, cerveau = asyncio.run(scenario())
    assert dits[-3:] == ["Les 2 radiateurs : à eau ou électrique ?", "J'ai compris radiateur à eau, c'est bien ça ?",
                         "Quel est le chauffage principal ?"]
    assert session.checklist.trouver_element("E1").valeur("type").note == "confirmé : « radiateur à eau »"
    contexte = cerveau.contextes[-1]
    assert "radiateur à eau" in contexte.valeurs_attendues and contexte.derniere_question.startswith("E1.type")


def test_transcription_inventee_sur_du_silence_ecartee():
    from types import SimpleNamespace as S

    from assistant.extraction import chiffres
    from assistant.lexique import est_recopie_du_contexte
    from assistant.transcription import transcription_douteuse

    # Mesures réelles (enregistrement de Noah) : « Laine de verre. » inventé, puis de vraies réponses.
    assert transcription_douteuse("Laine de verre.", [S(no_speech_prob=0.40, avg_logprob=-1.25)])
    assert transcription_douteuse("Merci d'avoir regardé cette vidéo.", [S(no_speech_prob=0.50, avg_logprob=-0.84)])
    assert not transcription_douteuse("Eau chaude.", [S(no_speech_prob=0.01, avg_logprob=-0.14)])
    assert not transcription_douteuse("BASSE.", [S(no_speech_prob=0.01, avg_logprob=-0.71)])
    assert not transcription_douteuse("C'est la laine de verre.", [S(no_speech_prob=0.00, avg_logprob=-0.21)])
    assert est_recopie_du_contexte("Laine de verre.") and not est_recopie_du_contexte("C'est la laine de verre.")
    assert chiffres("deux milles") == "2000"
