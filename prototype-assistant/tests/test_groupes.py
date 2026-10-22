"""Étape 4 de Noah : un assistant qui s'adapte, pas un questionnaire rigide.

Groupes mixtes, exceptions (« dont une », « tous sauf un », « sauf celle de la chambre »), éléments
ajoutés après coup, corrections tardives et contradictions (la dernière valeur est gardée, et c'est
signalé). Rien n'est jamais supposé identique s'il n'a pas été dit.
"""

import asyncio

import pytest

from assistant import parcours
from assistant.actions import appliquer
from assistant.checklist import Checklist
from assistant.extraction import Cible, extraire
from test_dialogue import visite


def dire(c: Checklist, phrase: str, cible: str | None = None, t: float = 10.0):
    """Extrait puis applique comme le serveur ; toutes les actions doivent être acceptées."""
    extraction = extraire(phrase, c, Cible.depuis_code(cible, c) if cible else None)
    resultats = appliquer(c, extraction.actions, t, [phrase])
    refusees = [r for r in resultats if r["statut"] != "accepte" and r["raison"] != "pièce déduite de l'image, à confirmer"]
    assert not refusees, refusees
    return extraction


def groupes(c: Checklist, type_element: str) -> list[tuple[int, str, dict[str, str]]]:
    """(nombre, nom, valeurs) de chaque élément de ce type, dans l'ordre."""
    return [(e.nombre, e.description, {champ: v[-1].valeur for champ, v in e.valeurs.items()})
            for e in c.elements if e.type == type_element]


def sejour() -> Checklist:
    c = Checklist()
    c.definir_piece("Séjour", 0)
    return c


def question(c: Checklist, type_element: str) -> str:
    """La prochaine question du parcours sur ce type d'élément."""
    return next(q.texte for q in parcours.questions(c) if q.code[:2].rstrip("0123456789.") in {
        "fenetre": ("F",), "emetteur": ("E",), "chauffage": ("CH", "C")}[type_element])


# --- 1. Groupes mixtes dans une seule phrase ---------------------------------------------------------------

def test_01_neuf_radiateurs_basse_temperature_et_un_haute_temperature():
    """L'exemple réel de Noah : deux groupes distincts, chacun avec ses attributs."""
    c = sejour()
    dire(c, "Il y a 9 radiateurs électriques basse température et 1 électrique haute température.")
    assert groupes(c, "emetteur") == [
        (9, "les 9 radiateurs basse température", {"type": "radiateur électrique", "temperature": "basse"}),
        (1, "le radiateur haute température", {"type": "radiateur électrique", "temperature": "haute"}),
    ]
    # Rien à demander sur ces radiateurs : leur type est dit ; date et température ne se demandent jamais.
    assert not [m for m in c.manques_piece() if m.type == "emetteur"] and not c.manques_secondaires()


def test_02_deux_groupes_de_fenetres_aux_noms_parlants():
    c = sejour()
    dire(c, "Deux fenêtres PVC double vitrage et une fenêtre bois simple vitrage.")
    assert groupes(c, "fenetre") == [
        (2, "les 2 fenêtres en PVC", {"menuiserie": "PVC", "vitrage": "double"}),
        (1, "la fenêtre en bois", {"menuiserie": "bois", "vitrage": "simple"}),
    ]


def test_03_sous_groupes_qui_reprennent_ce_qui_est_dit_du_groupe():
    """2 + 1 = 3 : ce sont des parties des 3 radiateurs à eau, dont la date diffère."""
    c = sejour()
    dire(c, "3 radiateurs à eau, 2 en fonte de 1975 et 1 en acier de 2010.")
    assert groupes(c, "emetteur") == [
        (2, "les 2 radiateurs de 1975", {"type": "radiateur à eau", "annee": "1975"}),
        (1, "le radiateur de 2010", {"type": "radiateur à eau", "annee": "2010"}),
    ]


def test_04_groupe_distinct_ne_reprend_rien_de_l_autre():
    """9 + 1 ≠ 9 : deux groupes distincts. Le second ne reçoit pas « électrique » par supposition."""
    c = sejour()
    dire(c, "9 radiateurs électriques et 1 haute température.")
    assert groupes(c, "emetteur")[1] == (1, "le radiateur haute température", {"temperature": "haute"})
    assert question(c, "emetteur") == "Le radiateur haute température : à eau ou électrique ?"


# --- 2. Exceptions dans un groupe : « dont », « sauf », « tous sauf un », « un des » ------------------------

def test_05_dont_une_en_simple_vitrage():
    c = sejour()
    dire(c, "Quatre fenêtres en PVC double vitrage, dont une en simple vitrage.")
    assert groupes(c, "fenetre") == [
        (3, "les 3 fenêtres en double vitrage", {"menuiserie": "PVC", "vitrage": "double"}),
        (1, "la fenêtre en simple vitrage", {"menuiserie": "PVC", "vitrage": "simple"}),
    ]


def test_06_reponse_de_groupe_deux_en_pvc_et_une_en_bois():
    c = sejour()
    dire(c, "Trois fenêtres double vitrage.")
    dire(c, "Deux en PVC et une en bois.", cible="F1.menuiserie")
    assert groupes(c, "fenetre") == [
        (2, "les 2 fenêtres en PVC", {"vitrage": "double", "menuiserie": "PVC"}),
        (1, "la fenêtre en bois", {"vitrage": "double", "menuiserie": "bois"}),
    ]
    bois = c.trouver_element("F2")
    assert bois.parent == "F1" and bois.valeur("vitrage").origine == "groupe"  # repris du groupe, visible à la validation
    # Questions construites d'après le logement réel : chaque groupe a la sienne, sous son nom.
    assert [q.texte for q in parcours.questions(c, "F1") if q.code.startswith("F")] == [
        "Les 2 fenêtres en PVC : des volets ?", "La fenêtre en bois : des volets ?"]


def test_07_toutes_sauf_une_dit_apres_coup():
    c = sejour()
    dire(c, "Trois fenêtres PVC double vitrage.")
    dire(c, "Toutes sauf une ont des volets roulants.", cible="F1.volets")
    assert groupes(c, "fenetre") == [
        (2, "les 2 fenêtres à volets roulants", {"menuiserie": "PVC", "vitrage": "double", "volets": "roulants"}),
        (1, "l'autre fenêtre", {"menuiserie": "PVC", "vitrage": "double"}),
    ]
    assert question(c, "fenetre") == "L'autre fenêtre : des volets ?"
    dire(c, "Pareil.", cible="F2.volets")  # finalement elle aussi
    assert c.trouver_element("F2").valeur("volets").note == "pareil que les 2 fenêtres à volets roulants"


def test_08_tous_les_radiateurs_sauf_un_en_basse_temperature():
    """Température jamais demandée, mais notée quand elle est dite, avec son exception."""
    c = sejour()
    dire(c, "Cinq radiateurs à eau.")
    dire(c, "Tous les radiateurs sont en basse température sauf un.")
    assert groupes(c, "emetteur") == [
        (4, "les 4 radiateurs basse température", {"type": "radiateur à eau", "temperature": "basse"}),
        (1, "l'autre radiateur", {"type": "radiateur à eau"}),
    ]
    assert not [m for m in c.manques_piece() if m.type == "emetteur"]  # l'autre : on ne demande pas sa température


def test_09_un_des_radiateurs_est_electrique():
    c = sejour()
    dire(c, "Trois radiateurs à eau.")
    dire(c, "Un des radiateurs est électrique.")
    assert groupes(c, "emetteur") == [
        (2, "les 2 radiateurs à eau", {"type": "radiateur à eau"}),
        (1, "le radiateur électrique", {"type": "radiateur électrique"}),
    ]
    assert not c.signalements and not c.trouver_element("E2").a_verifier("type")  # une exception, pas une contradiction


def test_10_l_une_d_elles_et_l_un_les_autres():
    c = sejour()
    dire(c, "Trois fenêtres en PVC.")
    dire(c, "Double, mais l'une d'elles est en simple vitrage.", cible="F1.vitrage")
    assert [(n, v["vitrage"]) for n, _, v in groupes(c, "fenetre")] == [(2, "double"), (1, "simple")]
    c = sejour()
    dire(c, "Cinq radiateurs.")
    dire(c, "L'un est électrique, les autres à eau.", cible="E1.type")
    assert groupes(c, "emetteur") == [(4, "les 4 radiateurs à eau", {"type": "radiateur à eau"}),
                                      (1, "le radiateur électrique", {"type": "radiateur électrique"})]


def test_11_sauf_une_en_bois_garde_le_reste_du_groupe():
    c = sejour()
    dire(c, "Quatre fenêtres PVC double vitrage, sauf une en bois.")
    assert groupes(c, "fenetre") == [(3, "les 3 fenêtres en PVC", {"menuiserie": "PVC", "vitrage": "double"}),
                                     (1, "la fenêtre en bois", {"menuiserie": "bois", "vitrage": "double"})]


# --- 3. Règles du logement et exceptions par pièce --------------------------------------------------------

def test_12_regle_du_logement_sauf_celle_de_la_chambre():
    """Vaut pour les fenêtres déjà décrites ET celles ajoutées plus tard, avec l'exception de la chambre."""
    c = sejour()
    dire(c, "Deux fenêtres double vitrage.")
    dire(c, "Toutes les fenêtres sont en bois, sauf celle de la chambre qui est en PVC.")
    for phrase in ("On passe dans la chambre.", "Il y a une fenêtre double vitrage.", "On passe dans la cuisine.",
                   "Une fenêtre double vitrage."):
        dire(c, phrase)
    menuiseries = {c.nom_piece(e.piece): e.valeur("menuiserie") for e in c.elements if e.type == "fenetre"}
    assert {piece: v.valeur for piece, v in menuiseries.items()} == {"Séjour": "bois", "Chambre": "PVC", "Cuisine": "bois"}
    assert all(v.origine == "regle" for v in menuiseries.values())
    assert not [m for m in c.manques_visite() if m.champ and m.champ.cle == "menuiserie"]  # rien à redemander


def test_13_exception_dite_apres_la_regle():
    c = sejour()
    dire(c, "Toutes les fenêtres du logement sont en bois.")
    dire(c, "On passe dans la chambre.")
    dire(c, "Une fenêtre double vitrage.")
    assert c.trouver_element("F1").valeur("menuiserie").valeur == "bois"
    dire(c, "Sauf celle de la chambre, qui est en PVC.")
    fenetre = c.trouver_element("F1")
    assert fenetre.valeur("menuiserie").valeur == "PVC" and not fenetre.a_verifier("menuiserie") and not c.signalements
    # Sans valeur : la règle ne vaut plus pour la chambre, la question sera posée.
    c = sejour()
    dire(c, "Toutes les fenêtres du logement sont en bois.")
    dire(c, "On passe dans la chambre.")
    dire(c, "Une fenêtre double vitrage.")
    dire(c, "Sauf celle de la chambre.")
    assert c.trouver_element("F1").valeur("menuiserie") is None
    assert question(c, "fenetre") == "Cette fenêtre : PVC, bois ou alu ?"


def test_14_regle_de_la_piece_pour_les_radiateurs_ajoutes_ensuite():
    c = sejour()
    dire(c, "Tous les radiateurs sont électriques.")
    dire(c, "Oui, trois.", cible="presence:emetteur")
    assert groupes(c, "emetteur") == [(3, "les 3 radiateurs", {"type": "radiateur électrique"})]
    dire(c, "On passe dans la cuisine.")
    dire(c, "Un radiateur.")
    assert c.element_de_piece("emetteur").valeur("type") is None  # règle de la pièce : la cuisine n'est pas concernée


# --- 4. Éléments ajoutés après coup ---------------------------------------------------------------------

def test_15_radiateur_ajoute_dans_une_autre_piece():
    c = sejour()
    dire(c, "On passe dans la chambre.")
    dire(c, "Dans la cuisine, il y a aussi un radiateur électrique.")
    radiateur = next(e for e in c.elements if e.type == "emetteur")
    assert c.nom_piece(radiateur.piece) == "Cuisine" and radiateur.valeur("type").valeur == "radiateur électrique"
    assert c.nom_piece(c.piece_courante) == "Chambre"  # on n'a pas changé de pièce


def test_16_porte_fenetre_ajoutee_apres_la_cloture_des_fenetres():
    c = sejour()
    dire(c, "Deux fenêtres PVC double vitrage, volets roulants.")
    dire(c, "Non.", cible="suite:fenetre")
    dire(c, "Ah, il y a aussi une porte-fenêtre en alu.")
    assert groupes(c, "fenetre")[1] == (1, "la porte-fenêtre 2", {"menuiserie": "alu"})
    assert question(c, "fenetre") == "Cette porte-fenêtre : simple ou double vitrage ?"


def test_17_correction_du_nombre_signalee():
    c = sejour()
    dire(c, "Il y a 2 radiateurs à eau.")
    dire(c, "En fait il y a 3 radiateurs, pas 2.")
    assert groupes(c, "emetteur") == [(3, "les 3 radiateurs", {"type": "radiateur à eau"})]
    assert [s.texte for s in c.signalements] == ["Je corrige : il y en avait 2."]


# --- 5. Corrections tardives et contradictions : la dernière est gardée, et signalée ------------------------

def test_18_correction_tardive_du_premier_mur():
    c = sejour()
    dire(c, "Ce mur donne dehors, brique 30, isolé par l'intérieur.")
    dire(c, "Oui, celui-ci donne sur le garage, parpaing 20, non isolé.", cible="suite:mur")
    dire(c, "Oui, le troisième donne sur une pièce chauffée.", cible="suite:mur")
    dire(c, "Le premier mur, en fait c'est du béton.")
    mur = c.trouver_element("M1")
    assert [v.valeur for v in mur.valeurs["materiau"]] == ["brique", "béton"] and mur.a_verifier("materiau")
    assert c.trouver_element("M2").valeur("materiau").valeur == "parpaing"  # le mur de la dernière question n'a pas bougé
    assert [s.texte for s in c.signalements] == ["Je remplace brique."]


def test_19_correction_par_le_nom_du_mur():
    c = sejour()
    dire(c, "Ce mur donne dehors, brique 30, isolé par l'intérieur.")
    dire(c, "Un autre mur donne dehors, parpaing 20, non isolé.")
    dire(c, "Le mur 2 donne sur le garage, pas dehors.")
    assert c.trouver_element("M2").valeur("donne_sur").valeur == "local non chauffé : garage"
    assert c.trouver_element("M1").valeur("donne_sur").valeur == "extérieur"
    assert c.trouver_element("M2").a_verifier("donne_sur")


def test_20_contradiction_sur_le_plafond():
    c = sejour()
    dire(c, "Le plafond est isolé.")
    dire(c, "Finalement le plafond n'est pas isolé.")
    plafond = c.element_de_piece("plafond")
    assert plafond.valeur("isolation").valeur == "non isolé" and plafond.a_verifier("isolation")
    assert [s.texte for s in c.signalements] == ["Je remplace isolé."]


def test_21_regle_qui_contredit_une_valeur_deja_dite():
    c = sejour()
    dire(c, "Une fenêtre en PVC.")
    dire(c, "Toutes les fenêtres du logement sont en bois.")
    fenetre = c.trouver_element("F1")
    assert fenetre.valeur("menuiserie").valeur == "bois" and fenetre.a_verifier("menuiserie")
    assert [s.texte for s in c.signalements] == ["Je remplace PVC."]


def test_22_exception_a_une_regle_n_est_pas_une_contradiction():
    c = sejour()
    dire(c, "Toutes les fenêtres du logement sont en PVC.")
    dire(c, "On passe dans la chambre.")
    dire(c, "Une fenêtre en bois.")
    fenetre = c.trouver_element("F1")
    assert [(v.valeur, v.origine) for v in fenetre.valeurs["menuiserie"]] == [("PVC", "regle"), ("bois", "dit")]
    assert not fenetre.a_verifier("menuiserie") and not c.signalements


def test_23_pluriel_vaut_pour_toutes_les_fenetres_de_la_piece():
    c = sejour()
    dire(c, "Trois fenêtres double vitrage.")
    dire(c, "Deux en PVC et une en bois.", cible="F1.menuiserie")
    dire(c, "Les fenêtres ont des volets roulants.")
    assert [v["volets"] for _, _, v in groupes(c, "fenetre")] == ["roulants", "roulants"]


# --- 6. Questions construites selon le logement réel -------------------------------------------------------

def test_24_date_et_temperature_toujours_notees_jamais_demandees():
    c = sejour()
    dire(c, "Deux radiateurs à eau de 1975, basse température.")
    assert groupes(c, "emetteur") == [(2, "les 2 radiateurs", {"type": "radiateur à eau", "temperature": "basse", "annee": "1975"})]
    c = sejour()
    dire(c, "Deux radiateurs à eau.")
    textes = [q.texte for q in parcours.questions(c)]
    assert not any("température" in t or "datent" in t for t in textes)


@pytest.mark.parametrize("energie, attendue", [
    ("Gaz.", "Chaudière à condensation, basse température ou standard ?"),
    ("Au bois.", "Poêle, insert ou chaudière ?"),
    ("Pompe à chaleur.", "Pompe à chaleur air/eau ou air/air ?"),
])
def test_25_question_sur_le_chauffage_selon_l_energie_dite(energie, attendue):
    c = sejour()
    dire(c, energie, cible="presence:chauffage")
    assert question(c, "chauffage") == attendue


def test_25b_valeur_trop_generale_precisee_sans_contradiction():
    c = sejour()
    dire(c, "Une pompe à chaleur.", cible="presence:chauffage")
    assert question(c, "chauffage") == "Pompe à chaleur air/eau ou air/air ?"  # « pompe à chaleur » ne suffit pas au DPE
    dire(c, "Air eau.", cible="CH1.type")
    chauffage = c.trouver_element("CH1")
    assert chauffage.valeur("type").valeur == "PAC air/eau" and not chauffage.a_verifier("type") and not c.signalements
    assert question(c, "chauffage") == "La pompe à chaleur date de quand ? Sinon, filmez sa plaque."


def test_26_chauffage_electrique_deduit_des_radiateurs_electriques():
    c = sejour()
    dire(c, "Deux radiateurs électriques.")
    dire(c, "Électrique.", cible="presence:chauffage")
    chauffage = next(e for e in c.elements if e.type == "chauffage")
    assert chauffage.valeur("type").valeur == "radiateurs électriques (effet Joule)"
    assert chauffage.valeur("type").note == "déduit : émetteurs tous électriques (E1)"
    assert not chauffage.champs_manquants()  # ni type, ni date de « chaudière » à demander


@pytest.mark.parametrize("phrase, attendu", [
    ("Il y a deux fenêtres, une en PVC et une en bois.", [(1, "la fenêtre en PVC"), (1, "la fenêtre en bois")]),
    ("Une fenêtre en PVC et une autre en bois.", [(1, "la fenêtre en PVC"), (1, "la fenêtre en bois")]),
    ("Trois fenêtres, deux en PVC, une en bois, toutes en double vitrage.", [(2, "les 2 fenêtres en PVC"), (1, "la fenêtre en bois")]),
    ("La fenêtre fait 1 m 20 par 1 m, double vitrage.", [(1, "la fenêtre 1")]),
])
def test_phrases_courantes_bien_decoupees(phrase, attendu):
    c = sejour()
    dire(c, phrase)
    assert [(n, nom) for n, nom, _ in groupes(c, "fenetre")] == attendu
    if "toutes en double" in phrase:
        assert [v["vitrage"] for _, _, v in groupes(c, "fenetre")] == ["double", "double"]
    if "1 m 20" in phrase:
        assert groupes(c, "fenetre")[0][2]["dimensions"] == "1,20 × 1 m"


def test_ce_qui_situe_un_element_n_en_cree_pas_un_autre():
    c = sejour()
    dire(c, "Le radiateur sous la fenêtre est électrique.")
    assert groupes(c, "emetteur") == [(1, "le radiateur 1", {"type": "radiateur électrique"})] and not groupes(c, "fenetre")
    dire(c, "On passe dans la chambre.")
    dire(c, "Il y a aussi un radiateur électrique.")  # « il y a aussi » : pas un bégaiement (« a… aussi »)
    assert c.nom_piece(c.elements[-1].piece) == "Chambre"


def test_tous_les_deux_ne_deborde_pas_sur_les_autres_radiateurs():
    c = sejour()
    c.signaler_element("emetteur", "les 2 radiateurs", 1, nombre=2)
    c.signaler_element("emetteur", "le radiateur de l'entrée", 1)
    dire(c, "Tous les deux à eau.", cible="E1.type")
    assert c.trouver_element("E1").valeur("type").valeur == "radiateur à eau" and c.trouver_element("E2").valeur("type") is None
    dire(c, "Tous électriques.", cible="E2.type")  # « tous » : vaut aussi pour les autres qui n'ont rien de dit
    assert c.trouver_element("E1").valeur("type").valeur == "radiateur à eau"  # déjà dit : pas touché


def test_au_moins_15_scenarios_d_exceptions():
    scenarios = [nom for nom in globals() if nom.startswith("test_") and nom[5:7].isdigit()]
    assert len(scenarios) >= 15


# --- 7. Dialogue complet : l'assistant s'adapte ------------------------------------------------------------

def test_dialogue_qui_s_adapte(tmp_path):
    echanges = [
        ("Ici c'est le séjour.", "Décrivez le premier mur."),
        ("Ce mur donne dehors, brique 30 cm, isolé par l'intérieur.", "D'autres murs sur l'extérieur ou un local non chauffé ?"),
        # Mur sur une pièce chauffée : rien d'autre à demander, et pas de nouvelle question sur les murs.
        ("Oui, celui-ci donne sur une pièce chauffée.", "Au-dessus du plafond : combles, terrasse ou logement ?"),
        # Correction tardive : gardée, signalée, puis la question restée en attente est reposée.
        ("Le premier mur, en fait c'est du béton.", "Je remplace brique. Au-dessus du plafond : combles, terrasse ou logement ?"),
        ("Logement au-dessus.", "Sous le plancher : terre-plein, vide sanitaire, cave ou logement ?"),
        ("Logement en dessous.", "Des fenêtres dans cette pièce ?"),
        ("Oui, trois, double vitrage.", "Les 3 fenêtres : PVC, bois ou alu ?"),
        ("Deux en PVC et une en bois.", "Les 2 fenêtres en PVC : des volets ?"),
        ("Volets roulants.", "La fenêtre en bois : des volets ?"),
        ("Pareil.", "D'autres fenêtres, ou une porte vers l'extérieur ?"),
        ("Non.", "Des radiateurs dans cette pièce ?"),
        ("Oui, 9 électriques basse température et 1 électrique haute température.", "Quel est le chauffage principal ?"),
        ("Électrique.", "Et l'eau chaude, comment est-elle produite ?"),
    ]
    session, questions_apres, _ = asyncio.run(visite(tmp_path, [phrase for phrase, _ in echanges]))
    for (phrase, attendue), posees in zip(echanges, questions_apres):
        assert posees == [attendue], f"après « {phrase} » : {posees}"
    c = session.checklist
    assert groupes(c, "emetteur") == [
        (9, "les 9 radiateurs basse température", {"type": "radiateur électrique", "temperature": "basse"}),
        (1, "le radiateur haute température", {"type": "radiateur électrique", "temperature": "haute"}),
    ]
    assert [v["volets"] for _, _, v in groupes(c, "fenetre")] == ["roulants", "roulants"]
    assert session.bilan()["contradictions_signalees"] == ["Je remplace brique."]
