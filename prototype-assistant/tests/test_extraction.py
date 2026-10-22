"""Extraction immédiate sur 10 phrases réalistes de diagnostiqueur, avec les fautes de transcription
réellement entendues (test de Noah sur iPhone du 22/10/2026, video-001)."""

import time

import pytest

from assistant.actions import appliquer
from assistant.checklist import VALEUR_INCONNUE, Checklist
from assistant.extraction import Cible, chiffres, extraire, normaliser


def dire(c: Checklist, phrase: str, cible: str | None = None, t: float = 10.0):
    """Extrait puis applique comme le serveur ; toutes les actions doivent être acceptées."""
    extraction = extraire(phrase, c, Cible.depuis_code(cible, c) if cible else None)
    resultats = appliquer(c, extraction.actions, t, [phrase])
    refusees = [r for r in resultats if r["statut"] != "accepte" and r["raison"] != "pièce déduite de l'image, à confirmer"]
    assert not refusees, refusees
    return extraction


def valeurs(c: Checklist, element_id: str) -> dict[str, str]:
    element = c.trouver_element(element_id)
    return {champ: element.valeur(champ).valeur for champ in element.valeurs}


def sejour() -> Checklist:
    c = Checklist()
    c.definir_piece("Séjour", 0)
    return c


def mur_avec(champs: dict[str, str] | None = None) -> Checklist:
    """Séjour avec un mur M1 déjà commencé (comme après quelques échanges)."""
    c = sejour()
    c.signaler_element("mur", "le mur avec la télé", 1)
    for champ, valeur in (champs or {}).items():
        c.enregistrer(type_element="mur", champ=champ, valeur=valeur, citation=valeur, t=2, element_id="M1")
    return c


# --- Les 10 phrases ------------------------------------------------------------------------------------

def test_1_description_libre_complete_en_une_fois():
    c = sejour()
    dire(c, "Ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois "
            "double vitrage, deux radiateurs à eau.")
    assert valeurs(c, "M1") == {"longueur": "4,50 m", "materiau": "brique", "epaisseur": "30 cm", "isolation": "ITI"}
    fenetres, radiateurs = c.trouver_element("F1"), c.trouver_element("E1")
    assert (fenetres.nombre, valeurs(c, "F1")) == (3, {"menuiserie": "bois", "vitrage": "double"})
    assert (radiateurs.nombre, valeurs(c, "E1")) == (2, {"type": "radiateur à eau"})
    # Rien de ce qui a été dit n'est redemandé : il ne reste que ce qui n'a pas été dit (le plafond et le
    # plancher de la pièce existent toujours ; date et température des radiateurs sont secondaires).
    assert [m.code for m in c.manques_piece()] == [
        "M1.donne_sur", "PL1.donne_sur", "PL1.isolation", "PB1.donne_sur", "PB1.isolation", "F1.volets"]
    assert set(c.manques_secondaires()) == {("emetteur", "temperature"), ("emetteur", "annee")}


def test_2_mur_mal_transcrit_parpin_et_isolation_exterieure():
    c = mur_avec({"materiau": "brique"})
    dire(c, "Ça se meurt là, c'est du parpin de 20, isolé par l'extérieur avec 10 cm de polystyrène, il donne dehors.")
    assert valeurs(c, "M2") == {"materiau": "parpaing", "epaisseur": "20 cm", "isolation": "ITE polystyrène 10 cm", "donne_sur": "extérieur"}
    assert valeurs(c, "M1") == {"materiau": "brique"}  # « ce mur-là » est un autre mur que celui déjà décrit


def test_3_celui_la_beton_non_isole_sur_garage():
    c = mur_avec({"materiau": "brique", "epaisseur": "30 cm"})
    dire(c, "Celui-là, béton 18 cm, pas isolé, il donne sur le garage.")
    assert valeurs(c, "M2") == {"materiau": "béton", "epaisseur": "18 cm", "isolation": "non isolé", "donne_sur": "local non chauffé : garage"}


def test_4_porte_fenetre_complete():
    c = sejour()
    dire(c, "La porte-fenêtre en alu, simple vitrage, volets roulants.")
    assert valeurs(c, "F1") == {"menuiserie": "alu", "vitrage": "simple", "volets": "roulants"}
    assert c.trouver_element("F1").description == "la porte-fenêtre 1"


def test_5_reponse_isolation_avec_faute_l_allaine():
    c = mur_avec({"materiau": "brique"})
    dire(c, "C'est l'allaine de verre, 10 centimètres, par l'intérieur.", cible="M1.isolation")
    assert valeurs(c, "M1") == {"materiau": "brique", "isolation": "ITI laine de verre 10 cm"}  # 10 cm = isolant, pas le mur


def test_6_reponse_courte_en_lettres():
    c = mur_avec({"materiau": "brique"})
    dire(c, "Cinq cm.", cible="M1.epaisseur")
    assert valeurs(c, "M1")["epaisseur"] == "5 cm"


def test_7_mot_deforme_ictérieur_devine_avec_le_vocabulaire():
    c = mur_avec({"materiau": "brique"})
    extraction = dire(c, "Ictérieur.", cible="M1.donne_sur")
    assert valeurs(c, "M1")["donne_sur"] == "extérieur"
    assert c.trouver_element("M1").valeur("donne_sur").note == "deviné : « icterieur » → extérieur"
    assert extraction.devines == ["deviné : « icterieur » → extérieur"]


def test_8_reponse_criee_besse():
    c = sejour()
    c.signaler_element("emetteur", "les 2 radiateurs", 1, nombre=2)
    dire(c, "BESSE !", cible="E1.temperature")
    assert valeurs(c, "E1") == {"temperature": "basse"}


def test_9_je_ne_sais_pas_note_et_on_passe_a_la_suite():
    c = sejour()
    c.signaler_element("fenetre", "la fenêtre derrière le rideau", 1)
    dire(c, "Je sais pas.", cible="F1.volets")
    fenetre = c.trouver_element("F1")
    assert fenetre.valeur("volets").valeur == VALEUR_INCONNUE and fenetre.a_verifier("volets")
    assert "F1.volets" not in [m.code for m in c.manques_piece()]  # on ne la redemande pas


def test_10_piece_chaudiere_et_vmc_dans_la_meme_phrase():
    c = Checklist()
    dire(c, "Ici c'est la cuisine, la chaudière gaz à condensation de deux mille douze, et la VMC hygro B.")
    assert c.nom_piece(c.piece_courante) == "Cuisine"
    assert valeurs(c, "CH1") == {"energie": "gaz", "type": "chaudière à condensation", "annee": "2012"}
    assert valeurs(c, "V1") == {"type": "VMC simple flux hygro B"}


# --- Autres comportements ------------------------------------------------------------------------------

@pytest.mark.parametrize("phrase, attendu", [
    ("O, chaudi.", "radiateur à eau"),
    ("Ouh chaud.", "radiateur à eau"),
    ("Tu m'as déjà posé la question, les radiateurs c'est de l'eau chaude.", "radiateur à eau"),
])
def test_eau_chaude_mal_transcrite(phrase, attendu):
    c = sejour()
    c.signaler_element("emetteur", "les radiateurs", 1, nombre=2)
    dire(c, phrase, cible="E1.type")
    assert valeurs(c, "E1")["type"] == attendu


def test_absence_et_presence():
    c = sejour()
    dire(c, "Pas de radiateur dans cette pièce.")
    c2 = sejour()
    dire(c2, "Non.", cible="presence:fenetre")
    dire(c2, "Il y a deux radiateurs ici.")
    assert "presence:emetteur" not in [m.code for m in c.manques_piece()]
    assert "presence:fenetre" not in [m.code for m in c2.manques_piece()]
    assert c2.trouver_element("E1").nombre == 2


def test_phrases_sans_valeur_ne_notent_rien():
    c = mur_avec()
    for phrase in ("Tu m'entends ?", "Allô ?", "Il est...", "OK. Ça, c'est le premier mur."):
        assert [a for a in extraire(phrase, c, Cible.depuis_code("M1.materiau", c)).actions if a["outil"] == "enregistrer_reponse"] == []


def test_nombres_en_lettres():
    assert chiffres("deux mille douze") == "2012"
    assert chiffres("quatre vingt dix") == "90"
    assert chiffres("vingt et un") == "21"
    assert chiffres("un mur de trente") == "un mur de 30"
    assert normaliser("Ce mur fait 4,5 m.") == "ce mur fait 4.5 m ,"


def test_extraction_rapide():
    c = sejour()
    debut = time.perf_counter()
    for _ in range(20):
        extraire("Ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois "
                 "double vitrage, deux radiateurs à eau.", c)
    assert (time.perf_counter() - debut) / 20 < 0.05  # moins de 50 ms par phrase


def test_celui_la_designe_l_element_decrit_et_pas_la_derniere_question():
    c = mur_avec({"materiau": "brique", "epaisseur": "30 cm"})
    dire(c, "Celui-là, béton 18 cm, pas isolé, il donne sur le garage.", cible="presence:ecs")
    assert valeurs(c, "M2")["materiau"] == "béton"
    assert not [e for e in c.elements if e.type == "ecs"]
