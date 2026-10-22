import pytest

from assistant.checklist import Checklist, ErreurChecklist
from assistant.citations import citation_trouvee
from assistant.lexique import corriger, est_hallucination


def codes(manques):
    return [m.code for m in manques]


def test_piece_neuve_demande_d_abord_un_mur_puis_les_presences():
    c = Checklist()
    c.definir_piece("chambre 1", 3.0)
    assert codes(c.manques_piece()) == ["presence:mur", "presence:fenetre", "presence:emetteur"]
    assert c.taux_remplissage() == 0.0


def test_revenir_dans_une_piece_ne_cree_pas_de_doublon():
    c = Checklist()
    c.definir_piece("Chambre 1", 3.0)
    c.definir_piece("cuisine", 40.0)
    c.definir_piece("chambre 1", 95.0)
    assert len(c.pieces) == 2
    assert c.nom_piece(c.piece_courante) == "Chambre 1"


def test_enregistrer_cree_l_element_et_garde_la_citation():
    c = Checklist()
    c.definir_piece("séjour", 0)
    mur = c.enregistrer(
        type_element="mur", champ="materiau", valeur="brique", citation="ce mur-là, brique, 30 cm",
        t=12.4, description="le mur avec la télé",
    )
    c.enregistrer(type_element="mur", champ="epaisseur", valeur="30 cm", citation="brique, 30 cm", t=12.4, element_id=mur.id)
    assert mur.id == "M1"
    assert mur.valeur("materiau").citation == "ce mur-là, brique, 30 cm"
    assert codes(c.manques_piece()) == ["M1.isolation", "M1.donne_sur", "presence:fenetre", "presence:emetteur"]


def test_valeur_sans_citation_refusee():
    c = Checklist()
    c.definir_piece("séjour", 0)
    with pytest.raises(ErreurChecklist, match="citation"):
        c.enregistrer(type_element="mur", champ="epaisseur", valeur="20 cm", citation=" ", t=1, description="le mur")
    assert c.elements == []


def test_champ_ou_type_inconnu_refuse():
    c = Checklist()
    with pytest.raises(ErreurChecklist):
        c.enregistrer(type_element="mur", champ="vitrage", valeur="double", citation="double", t=1)
    with pytest.raises(ErreurChecklist):
        c.signaler_element("plafond", "le plafond", 1)
    c.definir_piece("séjour", 0)
    fenetre = c.signaler_element("fenetre", "la fenêtre", 1)
    with pytest.raises(ErreurChecklist, match="pas un mur"):
        c.enregistrer(type_element="mur", champ="materiau", valeur="brique", citation="brique", t=2, element_id=fenetre.id)


def test_valeurs_differentes_gardees_et_a_verifier():
    c = Checklist()
    c.definir_piece("séjour", 0)
    mur = c.signaler_element("mur", "le mur du fond", 1)
    c.enregistrer(type_element="mur", champ="materiau", valeur="brique", citation="brique", t=2, element_id="m1")
    c.enregistrer(type_element="mur", champ="materiau", valeur="parpaing", citation="non, parpaing", t=9, element_id="M1")
    assert mur.valeur("materiau").valeur == "parpaing"
    assert mur.a_verifier("materiau")
    assert len(mur.valeurs["materiau"]) == 2


def test_sans_objet_et_absences():
    c = Checklist()
    c.definir_piece("salle de bain", 0)
    c.marquer_sans_objet(type_element="fenetre", champ="presence", citation="pas de fenêtre ici", t=3)
    e = c.signaler_element("emetteur", "le sèche-serviettes", 4)
    c.enregistrer(type_element="emetteur", champ="type", valeur="sèche-serviettes électrique", citation="sèche-serviettes électrique", t=5, element_id=e.id)
    c.marquer_sans_objet(type_element="emetteur", champ="temperature", citation="électrique, sans objet", t=5, element_id=e.id)
    assert codes(c.manques_piece()) == ["presence:mur", "E1.annee"]
    with pytest.raises(ErreurChecklist):
        c.marquer_sans_objet(type_element="mur", champ="presence", citation="pas de mur", t=6)


def test_equipements_du_logement_hors_piece():
    c = Checklist()
    ch = c.signaler_element("chauffage", "la chaudière", 30)
    assert ch.piece is None and c.piece_courante is None
    c.marquer_sans_objet(type_element="ventilation", champ="presence", citation="pas de VMC", t=31)
    assert codes(c.manques_logement()) == ["CH1.energie", "CH1.type", "CH1.annee", "presence:ecs"]


def test_element_de_piece_sans_piece_nommee_va_dans_piece_1():
    c = Checklist()
    c.signaler_element("mur", "le mur de gauche", 2)
    assert c.nom_piece(c.piece_courante) == "Pièce 1"


def test_manques_visite_piece_courante_d_abord():
    c = Checklist()
    c.definir_piece("cuisine", 0)
    c.signaler_element("mur", "le mur de l'évier", 1)
    c.definir_piece("chambre", 50)
    assert codes(c.manques_visite())[:3] == ["presence:mur", "presence:fenetre", "presence:emetteur"]
    assert "M1.materiau" in codes(c.manques_visite())


def test_resume_et_dict():
    c = Checklist()
    c.definir_piece("séjour", 61)
    c.enregistrer(type_element="mur", champ="materiau", valeur="brique", citation="brique", t=70, description="le mur avec la télé")
    resume = c.resume_pour_ia()
    assert "Pièce courante : Séjour (entrée à 1:01)" in resume
    assert "M1 mur « le mur avec la télé » (dit) : matériau = brique, épaisseur = ?" in resume
    d = c.vers_dict()
    assert d["pieces"][0]["elements"][0]["champs"]["materiau"]["valeur"]["citation"] == "brique"
    assert 0 < d["pieces"][0]["taux_remplissage"] < 1


def test_citation_retrouvee_ou_pas():
    phrases = ["Voilà, ça c'est la première maison, ce mur-là, brique, 30 cm."]
    assert citation_trouvee("ce mur-là, brique, 30 cm", phrases)
    assert citation_trouvee("Ce mur là brique 30cm", phrases)
    assert not citation_trouvee("brique de 20 cm isolée par l'extérieur", phrases)
    assert not citation_trouvee("", phrases)


def test_lexique_corrige_les_confusions_du_premier_test():
    brut = "ça se meurt là, brique, 30 cm, celui-ci c'est un mur avec VMCE, c'est du parpin de 40 cm"
    assert corriger(brut) == "ce mur-là, brique, 30 cm, celui-ci c'est un mur avec VMC, c'est du parpaing de 40 cm"
    assert est_hallucination("Sous-titres réalisés par la communauté d'Amara.org")
    assert not est_hallucination("double vitrage")
