"""Croquis du logement en direct (assistant/croquis.py ; demande de Noah du 23/10, plomb et amiante).

Sans mesures ; chaque pièce posée à côté de celle d'où l'on vient, dans la direction où l'on marchait ; murs A à D
(A : la porte par laquelle on entre, puis le sens des aiguilles d'une montre).
"""

from assistant.croquis import Croquis


def tour() -> Croquis:
    c = Croquis()
    c.entrer("entree", "Entrée", "image", 0.0, cap=0.0)
    c.entrer("sejour", "Séjour", "image", 10.0, cap=5.0)  # vers le nord
    c.entrer("cuisine", "Cuisine", "image", 30.0, cap=92.0)  # du séjour, vers l'est
    c.entrer("sejour", "Séjour", "image", 50.0, cap=268.0)  # retour au séjour : rien de nouveau
    c.entrer("chambre", "Chambre", "image", 70.0, cap=275.0)  # du séjour, vers l'ouest
    return c


def test_pieces_posees_dans_la_direction_de_marche():
    d = tour().disposer()
    assert d.positions == {"entree": (0, 0), "sejour": (0, -1), "cuisine": (1, -1), "chambre": (-1, -1)}
    assert d.portes == [("entree", "sejour", "nord"), ("sejour", "cuisine", "est"), ("sejour", "chambre", "ouest")]
    assert d.absolu  # caps de boussole : nord en haut


def test_murs_a_par_la_porte_puis_sens_horaire():
    c = tour()
    d = c.disposer()
    # Entré dans la cuisine en marchant vers l'est : la porte est sur son mur ouest, c'est le mur A.
    assert c.murs("cuisine", d) == {"ouest": "A", "nord": "B", "est": "C", "sud": "D"}
    assert c.murs("sejour", d) == {"sud": "A", "ouest": "B", "nord": "C", "est": "D"}  # entré depuis l'entrée, au sud
    assert c.murs("entree", d)["nord"] == "A"  # pièce de départ : sa première porte connue


def test_gyroscope_sans_nord_puis_nord_connu():
    c = Croquis()
    c.entrer("entree", "Entrée", "image", 0.0, lacet=10.0)
    c.entrer("sejour", "Séjour", "image", 10.0, lacet=10.0)
    c.entrer("cuisine", "Cuisine", "image", 20.0, lacet=100.0)
    relatif = c.disposer()
    assert not relatif.absolu and relatif.positions["cuisine"] == (1, -1)
    oriente = c.disposer(correction=180.0)  # le nord connu : tout tourne d'un demi-tour
    assert oriente.absolu and oriente.positions == {"entree": (0, 0), "sejour": (0, 1), "cuisine": (-1, 1)}


def test_place_prise_pose_plus_loin_sans_porte_dessinee():
    c = Croquis()
    c.entrer("a", "A", "image", 0.0, cap=0.0)
    c.entrer("b", "B", "image", 1.0, cap=90.0)
    c.entrer("a", "A", "image", 2.0, cap=270.0)
    c.entrer("c", "C", "image", 3.0, cap=90.0)  # de A vers l'est, mais B y est déjà
    d = c.disposer()
    assert d.positions["c"] == (2, 0) and ("a", "c", "est") not in d.portes


def test_renommer_la_meme_piece_et_nom_dit_prioritaire():
    c = tour()
    c.renommer("chambre", "bureau", "Bureau", "dit")
    assert c.courante == "bureau" and c.disposer().positions["bureau"] == (-1, -1)
    c.entrer("bureau", "Chambre", "image", 80.0)  # l'image ne remplace pas un nom dit
    assert c.pieces["bureau"].nom == "Bureau"


def test_vers_le_telephone_avec_fenetres_sur_leur_mur():
    dico = tour().vers_dict(ouvertures=[{"piece": "cuisine", "cote": "est", "type": "fenetre", "nombre": 2},
                                        {"piece": "garage", "cote": "sud", "type": "fenetre", "nombre": 1}])
    assert [(p["nom"], p["x"], p["y"]) for p in dico["pieces"]] == [
        ("Entrée", 0, 0), ("Séjour", 0, -1), ("Cuisine", 1, -1), ("Chambre", -1, -1)]
    assert dico["courante"] == "chambre" and dico["oriente"]
    assert dico["ouvertures"] == [{"piece": "cuisine", "cote": "est", "type": "fenetre", "nombre": 2}]  # pièce inconnue : écartée


def test_piece_de_depart_mur_a_par_la_porte_du_logement():
    c = tour()
    pieces = {p["cle"]: p for p in c.vers_dict(ouvertures=[{"piece": "entree", "cote": "sud", "type": "porte", "nombre": 1}])["pieces"]}
    assert pieces["entree"]["murs"]["sud"] == "A"  # la porte palière, pas la porte vers le séjour
    assert pieces["sejour"]["murs"]["sud"] == "A"  # une pièce où l'on est entré : sa porte d'entrée


def test_deplacer_et_fusionner_une_piece():
    c = tour()
    c.deplacer("chambre", "sud")  # de (-1, -1) à (-1, 0) : à côté de l'entrée
    d = c.disposer()
    assert d.positions["chambre"] == (-1, 0) and ("sejour", "chambre", "ouest") not in d.portes  # plus contre le séjour
    c.fusionner("cuisine", "sejour")  # la « cuisine » était un coin du séjour
    d = c.disposer()
    assert "cuisine" not in d.positions and [p.vers for p in c.passages] == ["entree", "sejour", "chambre"]
