"""Étape 13 : l'enveloppe du logement par côté, cas limites relevés à la relecture.

Un pronom pris pour le côté est, les parties d'un même mur (orientation, longueur, « le reste »), les fenêtres rangées
d'après la pièce où elles ont été vues, une porte dont la déduction suit son mur, un mur réuni d'office puis dit autre.
"""

from assistant.boussole import Visee
from assistant.checklist import Checklist
from test_groupes import dire


def murs(c: Checklist) -> list[tuple[str, str, str, dict[str, str]]]:
    return [(e.id, e.orientation, e.parent, {k: v[-1].valeur for k, v in e.valeurs.items()}) for e in c.enveloppe("mur", interieurs=True)]


def test_il_l_est_n_est_pas_le_cote_est():
    c = Checklist()
    dire(c, "Ce mur donne dehors, en brique de 30.", cible="presence:mur")
    dire(c, "Oui, il l'est, laine de verre 10 cm.", cible="M1.isolation")
    assert [m[0] for m in murs(c)] == ["M1"] and "est" in c.orientations_manquantes()
    c = Checklist()
    dire(c, "Ce mur donne dehors, en brique de 30.", cible="presence:mur")
    dire(c, "Oui il l'est, par l'intérieur.", cible="M1.isolation")  # une isolation, pas un mur sur l'intérieur
    assert murs(c) == [("M1", "", "", {"donne_sur": "extérieur", "materiau": "brique", "epaisseur": "30 cm", "isolation": "ITI"})]


def test_parties_d_un_mur_chacune_de_son_cote_sans_la_longueur_de_l_autre():
    c = Checklist()
    dire(c, "Mur ouest : 60 % sur le voisin, 40 % dehors.")
    assert murs(c) == [("M1", "ouest", "", {"donne_sur": "local chauffé (voisin)", "part": "60 %"}),
                       ("M2", "ouest", "M1", {"donne_sur": "extérieur", "part": "40 %"})]
    c = Checklist()
    dire(c, "Le mur ouest, la moitié sur le voisin, le reste sur la rue.")  # « le reste » : de ce mur, pas des autres murs
    assert [(m[1], m[3]["donne_sur"]) for m in murs(c)] == [("ouest", "local chauffé (voisin)"), ("ouest", "extérieur")]
    assert "mur" not in c.clos
    c = Checklist()
    dire(c, "À l'ouest, 3 mètres sur le voisin, le reste dehors.")
    assert [m[3].get("longueur") for m in murs(c) if m[1] == "ouest"] == ["3 m", None]


def test_fenetre_rangee_sur_la_partie_vue_dans_sa_piece():
    c = Checklist()
    c.definir_piece("Séjour", 0)
    m = c.signaler_element("mur", "le mur 1", 1, source="voix")
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="extérieur", citation="dehors", t=2, element_id=m.id)
    c.definir_piece("Chambre", 3)
    fenetre = c.signaler_element("fenetre", "la fenêtre", 4, source="voix", support=m.id)
    # Dans la chambre, ce mur donne sur le garage : une autre partie du mur, et la fenêtre de la chambre est sur elle.
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="local non chauffé : garage", citation="sur le garage", t=5,
                  element_id=m.id)
    partie = next(e for e in c.enveloppe("mur") if e.parent == m.id)
    assert partie.pieces == ["chambre"] and fenetre.support == partie.id


def test_porte_deduite_d_apres_son_mur_meme_corrige():
    c = Checklist()
    m = c.signaler_element("mur", "le mur 1", 1, source="voix")
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="extérieur", citation="dehors", t=2, element_id=m.id)
    porte = c.signaler_element("porte", "la porte", 3, source="voix", support=m.id)
    assert (porte.valeur("donne_sur").valeur, porte.valeur("donne_sur").note) == ("extérieur", "déduit : sur le mur de la porte")
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="local non chauffé : parties communes", citation="non, le palier",
                  t=4, element_id=m.id)
    assert porte.valeur("donne_sur").valeur == "palier (local non chauffé)"
    assert "(déduit)" in "\n".join(c.lignes_enveloppe())  # montré comme déduit, pas comme dit


def test_mur_reuni_d_office_puis_dit_autre_redevient_un_mur_a_part():
    c = Checklist()
    c.regler_boussole(0.0, "bonne", True)
    m1 = c.signaler_element("mur", "le mur 1", 1, source="voix")
    c.mesurer(m1.id, Visee(270.0, 270.0, True))
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="extérieur", citation="dehors", t=2, element_id=m1.id)
    fenetre = c.signaler_element("fenetre", "la fenêtre", 3, source="voix", support=m1.id)
    m2 = c.signaler_element("mur", "le mur 2", 10, source="voix")
    assert c.mesurer(m2.id, Visee(268.0, 268.0, True)) is m1  # rien ne les distingue : le même mur ouest
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="local chauffé : cuisine", citation="celui-là donne sur la cuisine",
                  t=11, element_id=m2.id)
    assert [(m[0], m[3]["donne_sur"]) for m in murs(c)] == [("M1", "extérieur"), ("M2", "local chauffé : cuisine")]
    assert fenetre.support == "M1" and not c.signalements and c.orientations_manquantes() == ["nord", "est", "sud"]


def test_fenetre_d_un_mur_devenu_mur_entre_deux_pieces_reste_a_decrire():
    c = Checklist()
    m = c.signaler_element("mur", "le mur 1", 1, source="voix")
    fenetre = c.signaler_element("fenetre", "la fenêtre", 2, source="voix", support=m.id)
    c.enregistrer(type_element="mur", champ="donne_sur", valeur="local chauffé : cuisine", citation="sur la cuisine", t=3, element_id=m.id)
    assert c.sans_mur(fenetre) and f"{fenetre.id}.menuiserie" in [x.code for x in c.manques_visite()]
