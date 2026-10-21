"""Lecture d'un dossier complet (pièces, Carrez, modules) et commandes diagauto."""

import io

from conftest import DEMO, EVAL, FIXTURES
from diagauto.cli import inspecter, main
from diagauto.liciel_xml import DossierLiciel


def test_pieces_demo_0001():
    pieces = DossierLiciel(DEMO / "DEMO_0001").pieces()
    assert len(pieces) == 7
    assert pieces[0].libelle == "Rez de chaussée - Pièce 1"
    assert pieces[2].libelle == "Étage  1 - Pièce  3"  # doubles espaces d'origine conservés
    assert all(p.visitee for p in pieces)


def test_piece_non_visitee_demo_0003():
    pieces = DossierLiciel(DEMO / "DEMO_0003").pieces()
    non_visitees = [p for p in pieces if not p.visitee]
    assert [(p.libelle, p.justification_non_visite) for p in non_visitees] == [
        ("Etage 1 - Buanderie", "Interdiction du propriétaire")
    ]


def test_carrez_demo_0001():
    dossier = DossierLiciel(DEMO / "DEMO_0001")
    carrez = dossier.carrez()
    assert len(carrez) == 8
    comble = next(c for c in carrez if c.localisation == "Étage  2 - Comble non habitable  1")
    assert (comble.carrez, comble.sol, comble.hauteur_sous_plafond) == (22.4, 43.5, 2.6)
    assert comble.nb_lignes_calcul == 2  # +43,5 puis -21,1 (hauteur < 1,80 m)
    totaux = dossier.totaux_carrez()
    assert (totaux.carrez, totaux.habitable, totaux.sol) == (284.2, 284.2, 325.8)
    assert round(sum(c.carrez for c in carrez), 2) == totaux.carrez


def test_modules_presents():
    modules = DossierLiciel(DEMO / "DEMO_0001").modules_presents()
    for module in ("Métrage Carrez / Boutin", "DPE 2020", "Électricité", "Gaz", "Amiante", "Plomb (CREP)"):
        assert module in modules
    assert "Audit énergétique" in DossierLiciel(DEMO / "DEMO_AUDIT_0004").modules_presents()


def test_mission_demo_0001():
    mission = DossierLiciel(DEMO / "DEMO_0001").mission()
    assert mission["numero"] == "DEMO_0001"
    assert "ANNEUX" in mission["adresse"]


def test_inspect_affiche_pieces_et_carrez():
    sortie = io.StringIO()
    assert inspecter(DEMO / "DEMO_0001", sortie) == 0
    texte = sortie.getvalue()
    assert "Pièces (7)" in texte
    assert "Métrage Carrez / Boutin (8 pièces)" in texte
    assert "284,20" in texte and "325,80" in texte
    assert "Rattachement aux pièces par libellé : 6/8" in texte


def test_inspect_signale_un_ecart_de_total():
    sortie = io.StringIO()
    inspecter(DEMO / "DEMO_0003", sortie)
    assert "ATTENTION : la somme au sol (368,87) diffère du total LICIEL (286,87)" in sortie.getvalue()


def test_inspect_dossier_sans_pieces_ni_carrez():
    sortie = io.StringIO()
    assert inspecter(EVAL / "MI1-0", sortie) == 0
    assert "aucune liste de pièces" in sortie.getvalue()


def test_commande_verifier_sur_tous_les_fixtures(capsys):
    assert main(["verifier", str(FIXTURES)]) == 0
    assert "0 échecs" in capsys.readouterr().out


def test_commande_inspect_dossier_introuvable():
    assert main(["inspect", str(FIXTURES / "nexiste_pas")]) == 2
