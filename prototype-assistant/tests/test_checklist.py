import pytest

from assistant.checklist import Checklist, ErreurChecklist
from assistant.citations import citation_trouvee
from assistant.lexique import corriger, est_hallucination


def codes(manques):
    return [m.code for m in manques]


def test_logement_neuf_les_cotes_le_plafond_le_plancher_puis_les_equipements():
    # Étape 13 : le DPE du logement, sans aucune pièce. Le plafond et le plancher du logement existent toujours : on ne
    # demande pas s'ils sont là, mais sur quoi ils donnent ; ce sont les côtés du logement qui manquent, pas des murs par pièce.
    c = Checklist()
    assert codes(c.manques_visite()) == [
        "cote:nord", "cote:est", "cote:sud", "cote:ouest", "PL1.donne_sur", "PL1.isolation", "PB1.donne_sur", "PB1.isolation",
        "presence:chauffage", "presence:emetteur", "presence:ecs", "presence:ventilation"]
    assert c.taux_dpe() == 0.0 and c.piece_courante is None and not c.pieces
    c.definir_piece("cuisine", 40.0)  # une pièce dite : notée, elle n'ajoute rien à demander
    assert [e.id for e in c.enveloppe()] == ["PL1", "PB1"] and len(c.manques_visite()) == 12


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
    assert [code for code in codes(c.manques_piece()) if code.startswith("M")] == ["M1.donne_sur", "M1.isolation"]


def test_valeur_sans_citation_refusee():
    c = Checklist()
    c.definir_piece("séjour", 0)
    with pytest.raises(ErreurChecklist, match="citation"):
        c.enregistrer(type_element="mur", champ="epaisseur", valeur="20 cm", citation=" ", t=1, description="le mur")
    assert not [e for e in c.elements if e.type == "mur"]


def test_champ_ou_type_inconnu_refuse():
    c = Checklist()
    with pytest.raises(ErreurChecklist):
        c.enregistrer(type_element="mur", champ="vitrage", valeur="double", citation="double", t=1)
    with pytest.raises(ErreurChecklist):
        c.signaler_element("toiture", "la toiture", 1)
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
    # Date et température des radiateurs : jamais demandées (étape 4), même pour le logement.
    assert codes(c.manques_piece()) == ["PL1.donne_sur", "PL1.isolation", "PB1.donne_sur", "PB1.isolation"]
    assert list(c.manques_secondaires()) == []
    with pytest.raises(ErreurChecklist):
        c.marquer_sans_objet(type_element="mur", champ="presence", citation="pas de mur", t=6)


def test_equipements_du_logement_hors_piece():
    c = Checklist()
    ch = c.signaler_element("chauffage", "la chaudière", 30)
    assert ch.piece is None and c.piece_courante is None
    c.marquer_sans_objet(type_element="ventilation", champ="presence", citation="pas de VMC", t=31)
    assert codes(c.manques_logement()) == ["CH1.energie", "CH1.type", "CH1.annee", "presence:emetteur", "presence:ecs"]
    c.enregistrer(type_element="chauffage", champ="type", valeur="radiateurs électriques (effet Joule)", citation="grille-pain",
                  t=32, element_id=ch.id)
    assert "presence:emetteur" not in codes(c.manques_logement())  # les radiateurs sont le chauffage lui-même


def test_sans_piece_dite_rien_n_est_range_dans_une_piece():
    # Étape 13 : la pièce ne compte pas pour le DPE ; aucune « Pièce 1 » n'est créée d'office.
    c = Checklist()
    mur = c.signaler_element("mur", "le mur de gauche", 2)
    fenetre = c.signaler_element("fenetre", "la fenêtre", 3, support=mur.id)
    radiateur = c.signaler_element("emetteur", "le radiateur", 4)
    assert c.piece_courante is None and not c.pieces
    assert (mur.piece, mur.pieces, fenetre.piece, fenetre.support, radiateur.piece) == (None, [], None, mur.id, None)
    c.definir_piece("séjour", 5)
    autre = c.signaler_element("fenetre", "la fenêtre du séjour", 6)
    assert autre.pieces == ["sejour"]  # une pièce dite : notée pour le repérage


def test_manques_visite_l_enveloppe_puis_les_equipements():
    c = Checklist()
    c.definir_piece("cuisine", 0)
    c.signaler_element("mur", "le mur de l'évier", 1)
    c.definir_piece("chambre", 50)
    visite = codes(c.manques_visite())
    assert visite[:4] == ["M1.donne_sur", "M1.materiau", "M1.epaisseur", "M1.isolation"]  # le mur, quelle que soit la pièce
    assert visite.index("cote:nord") < visite.index("PL1.donne_sur") < visite.index("presence:chauffage")
    assert len(visite) == len(set(visite))


def test_resume_et_dict():
    c = Checklist()
    c.definir_piece("séjour", 61)
    c.enregistrer(type_element="mur", champ="materiau", valeur="brique", citation="brique", t=70, description="le mur avec la télé")
    resume = c.resume_pour_ia()
    assert "Pièce en cours (dite par le diagnostiqueur, simple repère : sans effet sur le DPE) : Séjour" in resume
    assert ("côté inconnu (orientation à trouver) : M1 mur « le mur avec la télé » (dit, vu dans Séjour) : donne sur = ?, "
            "matériau = brique, épaisseur = ?, isolation = ?") in resume
    assert "Côtés du logement pas encore décrits : nord, est, sud, ouest" in resume
    d = c.vers_dict()
    mur = next(e for e in d["enveloppe"]["murs"] if e["id"] == "M1")
    assert mur["champs"]["materiau"]["valeur"]["citation"] == "brique" and mur["pieces"] == ["Séjour"]
    assert not d["pieces"][0]["elements"]  # le mur est celui du logement, pas de la pièce
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
    assert corriger("Ça se mur-là, brique de 30 cm.") == "ce mur-là, brique de 30 cm."
    assert corriger("ça se meure là, brique") == "ce mur-là, brique"
    assert est_hallucination("Sous-titres réalisés par la communauté d'Amara.org")
    assert not est_hallucination("double vitrage")


def test_paroi_sur_local_chauffe_rien_d_autre_a_demander():
    c = Checklist()
    c.definir_piece("chambre", 0)
    mur = c.signaler_element("mur", "le mur du couloir", 1)
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="local chauffé", citation="il donne sur le couloir chauffé", t=2, element_id=mur.id)
    assert mur.champs_manquants() == []  # hypothèse : paroi non déperditive en 3CL
    plafond = c.element_de_piece("plafond")
    c.enregistrer(type_element="plafond", champ="donne_sur", valeur="local chauffé (logement au-dessus)", citation="logement au-dessus", t=3, element_id=plafond.id)
    assert plafond.champs_manquants() == [] and not plafond.est_utile("isolation")


def test_date_et_temperature_des_radiateurs_jamais_demandees_mais_notees():
    c = Checklist()
    c.definir_piece("séjour", 0)
    eau = c.signaler_element("emetteur", "les radiateurs", 1, nombre=2)
    elec = c.signaler_element("emetteur", "le convecteur", 1)
    assert not eau.est_utile("temperature")  # type pas encore dit
    c.enregistrer(type_element="emetteur", champ="type", valeur="radiateur à eau", citation="à eau", t=2, element_id=eau.id)
    c.enregistrer(type_element="emetteur", champ="type", valeur="convecteur électrique", citation="convecteur", t=2, element_id=elec.id)
    assert eau.est_utile("temperature") and not elec.est_utile("temperature")
    assert not c.manques_secondaires() and not [m for m in c.manques_piece() if m.type == "emetteur"]  # rien à demander
    c.enregistrer(type_element="emetteur", champ="annee", valeur="1985", citation="ils datent de 85", t=3, element_id=elec.id)
    assert elec.valeur("annee").valeur == "1985"  # dit : toujours noté


def test_liste_close_et_plafond_du_logement():
    c = Checklist()
    c.definir_piece("séjour", 0)
    c.cloturer("mur", "pas d'autre mur", 5)
    assert "mur" in c.pieces["sejour"].clos
    c.enregistrer(type_element="plafond", champ="donne_sur", valeur="combles perdus", citation="combles perdus", t=6, element_id="PL1")
    c.enregistrer(type_element="plafond", champ="isolation", valeur="isolé laine de verre 30 cm", citation="laine 30", t=7, element_id="PL1")
    c.definir_piece("cuisine", 20)
    # Étape 13 : le plafond est celui du logement ; dans la cuisine, rien à redemander.
    assert c.element_de_piece("plafond").id == "PL1" and not [m for m in c.manques_piece() if m.type == "plafond"]
    plafond = c.copier("plafond", "sejour", "pareil", 21)  # « pareil que le séjour » : la même partie
    assert plafond.id == "PL1" and plafond.valeur("isolation").valeur == "isolé laine de verre 30 cm"
    assert c.signaler_element("plafond", "un autre plafond", 22) is plafond  # un seul plafond pour la pièce
    with pytest.raises(ErreurChecklist):
        c.copier("plancher", "sejour", "pareil", 23)  # rien à recopier
