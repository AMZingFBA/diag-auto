"""Pont assistant -> LICIEL (étape 11) : liste des pièces et Carrez d'une visite, écrits en tables LICIEL.

Le modèle est une reproduction du dossier de test 2610210001 (4 pièces créées dans LICIEL par Hermes) ; les dossiers de
démonstration LICIEL servent à vérifier que nos tables Carrez reprennent exactement les colonnes et les calculs de
LICIEL. Rien n'est jamais écrit sous un dossier LICIEL_*.
"""

import io
import json
import random
import re
from datetime import datetime

import pytest

from conftest import DEMO
from diagauto.cli import main, verifier
from diagauto.liciel_xml import DossierLiciel, Table, ecrire_table, lire_table
from diagauto.pont import ErreurPont, cle_composant, derniere_visite, generer, nombre_liciel

CLE = re.compile(r"\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}_\d{17}")
MAINTENANT = datetime(2026, 10, 22, 15, 0, 0)

# Les 4 pièces du dossier de test 2610210001, telles que LICIEL les a enregistrées (bâtiment « Appartement »).
PIECES_TEST = [("2026_10_21_21_58_39_11306320074286620", "Sejour"), ("2026_10_21_21_58_44_10114220016113791", "Cuisine"),
               ("2026_10_21_21_58_49_12772730013311412", "Chambre 1"), ("2026_10_21_21_58_54_26104460099016523", "Salle de bains")]


def dossier_test(chemin):
    """Reproduction du dossier de test : la liste des 4 pièces et une autre table (copiée telle quelle)."""
    xml = chemin / "XML"
    xml.mkdir(parents=True)
    lignes = [{"id_classement_champs": f"{i:05d}", "Lot": "", "PieceHorsCREP": "", "PieceExterieure": "", "ClefComposant": cle,
               "Batiment": "Appartement", "Local": local, "Justification": "", "MoyenAMettreEnOeuvre": ""}
              for i, (cle, local) in enumerate(PIECES_TEST)]
    ecrire_table(Table("General_Pieces_Toutes", lignes), xml / "Table_General_Pieces_Toutes.xml")
    bien = Table("General_Bien", [{"Mission_Num_Dossier": "2610210001", "Immeuble_Nature_bien": "Habitation (partie privative d'immeuble)"}],
                 liste=False)
    ecrire_table(bien, xml / "Table_General_Bien.xml")
    return chemin


def element(id_, type_, nombre=1):
    return {"id": id_, "type": type_, "description": "", "nombre": nombre, "champs": {}}


def piece(nom, *elements):
    """Une pièce telle que l'assistant l'exporte dans etat.json (Checklist.vers_dict)."""
    return {"nom": nom, "t": 0.0, "taux_remplissage": 0.5, "absences": {}, "clos": {}, "nombre_murs": None,
            "elements": [element("PL1", "plafond"), element("PB1", "plancher"), *elements], "manques": []}


def visite(chemin, pieces, mesures=None):
    chemin.mkdir(parents=True)
    etat = {"piece_courante": pieces[-1]["nom"] if pieces else None, "pieces": pieces,
            "logement": {"elements": [], "absences": {}, "manques": []}, "regles": [], "boussole": {}, "signalements": []}
    (chemin / "etat.json").write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
    if mesures is not None:
        (chemin / "mesures.json").write_text(json.dumps(mesures, ensure_ascii=False), encoding="utf-8")
    return chemin


def visite_de_noah(chemin, mesures=None):
    """Comme la visite rejouée de Noah : séjour (murs, fenêtres, radiateurs), couloir, cuisine."""
    return visite(chemin, [
        piece("Séjour", element("M1", "mur"), element("M2", "mur"), element("F1", "fenetre", 2), element("E1", "emetteur", 2)),
        piece("Couloir"),
        piece("Cuisine", element("M1", "mur"), element("F1", "fenetre")),
    ], mesures)


def lancer(tmp_path, mesures=None, **options):
    return generer(visite_de_noah(tmp_path / "visite", mesures), dossier_test(tmp_path / "modele"), tmp_path / "sortie",
                   maintenant=MAINTENANT, alea=random.Random(1), **options)


def lignes(sortie, nom):
    return lire_table(sortie / "XML" / f"Table_{nom}.xml").lignes


# --- liste des pièces ---------------------------------------------------------------------------------------------


def test_pieces_de_la_visite_dans_le_dossier_de_test(tmp_path):
    rapport = lancer(tmp_path)
    pieces = lignes(tmp_path / "sortie", "General_Pieces_Toutes")
    modele = lignes(tmp_path / "modele", "General_Pieces_Toutes")
    assert pieces[:4] == modele  # pièces existantes : lignes et clés inchangées (« Séjour » = « Sejour »)
    nouvelle = pieces[4]
    assert (nouvelle["Batiment"], nouvelle["Local"], nouvelle["id_classement_champs"]) == ("Appartement", "Couloir", "00004")
    assert CLE.fullmatch(nouvelle["ClefComposant"]) and nouvelle["ClefComposant"].startswith("2026_10_22_15_00_00_")
    assert list(nouvelle) == list(modele[0])  # mêmes colonnes, même ordre
    assert all(nouvelle[c] == "" for c in ("Lot", "PieceHorsCREP", "PieceExterieure", "Justification", "MoyenAMettreEnOeuvre"))
    assert [(p.libelle, p.statut) for p in rapport.pieces] == [
        ("Appartement - Sejour", "existante"), ("Appartement - Cuisine", "existante"), ("Appartement - Couloir", "ajoutée")]
    # Pièces du dossier non vues : laissées telles quelles (jamais déclarées « non visitées » à la place du diagnostiqueur).
    assert rapport.non_vues == ["Appartement - Chambre 1", "Appartement - Salle de bains"]


def test_pieces_deja_toutes_dans_le_dossier_liste_identique_a_l_octet(tmp_path):
    vue = visite(tmp_path / "visite", [piece("sejour"), piece("CUISINE")])
    generer(vue, dossier_test(tmp_path / "modele"), tmp_path / "sortie", maintenant=MAINTENANT)
    nom = "XML/Table_General_Pieces_Toutes.xml"
    assert (tmp_path / "sortie" / nom).read_bytes() == (tmp_path / "modele" / nom).read_bytes()


def test_murs_ouvertures_emetteurs_au_rapport(tmp_path):
    lancer(tmp_path)
    rapport = json.loads((tmp_path / "sortie" / "diagauto-pont.json").read_text(encoding="utf-8"))
    sejour = rapport["pieces"][0]
    assert sejour["nom_visite"] == "Séjour" and sejour["elements"] == {"mur": 2, "fenêtre": 2, "porte": 0, "émetteur": 2}
    assert rapport["a_mesurer"] == ["Appartement - Sejour", "Appartement - Cuisine", "Appartement - Couloir"]
    assert any("hypothèse" in h for h in rapport["hypotheses"])


def test_etat_consolide_par_la_carte_des_pieces(tmp_path):
    """Étape 12 : la carte des pièces (python -m assistant.carte) écrit etat-consolide.json, lu de préférence."""
    vue = visite_de_noah(tmp_path / "visite")
    etat = json.loads((vue / "etat.json").read_text(encoding="utf-8"))
    # Le « couloir » de l'assistant était le séjour (même endroit, fusionné par la carte) ; on est revenu au séjour.
    etat["pieces"] = [etat["pieces"][0], etat["pieces"][2]]
    etat["pieces"][0]["carte"] = {"reconnue": True, "passages": [[0.0, 120.0], [300.0, 340.0]], "sejours": 2,
                                  "revisitee": True, "corrections": []}
    etat["pieces"][1]["carte"] = {"reconnue": True, "passages": [[125.0, 295.0]], "sejours": 1, "revisitee": False,
                                  "corrections": []}
    etat["pieces"][1]["elements"][-1]["description"] = "la fenêtre de l'évier"
    etat["pieces"][1]["elements"][-1]["carte"] = {"piece_vue": "Séjour", "mur": None, "cap": None,
                                                  "a_verifier": "noté dans « Cuisine », mais filmé dans « Séjour »"}
    question = "de 2:59 à 3:02 : Claude voit une autre pièce (couloir), rangé dans « Séjour » : pièce à ajouter ?"
    etat["carte"] = {"source": "vidéo continue (video.mp4)", "cap": "boussole", "pieces": [], "questions": [question],
                     "fusions": ["« Couloir » est le même endroit que « Séjour » : fusionnées."]}
    (vue / "etat-consolide.json").write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
    rapport = generer(vue, dossier_test(tmp_path / "modele"), tmp_path / "sortie", maintenant=MAINTENANT,
                      alea=random.Random(1))
    fenetre = "la fenêtre de l'évier (F1) : noté dans « Cuisine », mais filmé dans « Séjour » : dans quelle pièce ?"
    assert rapport.etat == "etat-consolide.json" and rapport.questions == [question, fenetre]
    assert [(p.libelle, p.passages) for p in rapport.pieces] == [("Appartement - Sejour", 2), ("Appartement - Cuisine", 1)]
    assert lignes(tmp_path / "sortie", "General_Pieces_Toutes") == lignes(tmp_path / "modele", "General_Pieces_Toutes")
    texte = rapport.en_texte()
    assert "(état consolidé par la carte des pièces de la vidéo)" in texte
    assert "Appartement - Sejour [existante] : À MESURER ; vu : 2 murs, 2 fenêtres, 2 émetteurs ; revisitée (2 passages)" in texte
    assert texte.endswith(f"Questions de la carte des pièces (à trancher par le diagnostiqueur) :\n  - {question}\n"
                          f"  - {fenetre}")


# --- Carrez -------------------------------------------------------------------------------------------------------


def test_carrez_sans_mesure_pieces_a_mesurer_rien_d_invente(tmp_path):
    lancer(tmp_path)
    sortie = tmp_path / "sortie"
    pieces = {l["Local"]: l["ClefComposant"] for l in lignes(sortie, "General_Pieces_Toutes")}
    resume = lignes(sortie, "Z_Carrez_Resume")
    assert [l["Localistion"] for l in resume] == ["Appartement - Sejour", "Appartement - Cuisine", "Appartement - Couloir"]
    assert [l["ClefComposantPiece"] for l in resume] == [pieces["Sejour"], pieces["Cuisine"], pieces["Couloir"]]
    for l in resume:  # aucune surface ni hauteur inventée : 0, comme LICIEL pour une valeur non saisie
        assert [l[c] for c in ("Surface_1", "Surface_2", "Surface_3", "Surface_4", "Data1", "Data2", "Commantaires")] == \
            ["0", "0", "0", "0", "0", "", ""]
    assert lignes(sortie, "Z_Carrez_Details") == []  # aucune mesure
    general = lire_table(sortie / "XML" / "Table_Z_Carrez_General.xml")
    assert not general.liste and general.fiche == {"Doc_Remis": "", "Surface_Carrez": "0,00", "Surface_Habitable": "0,00",
                                                   "Surface_Sol": "0,00", "Surface_Ref": "0,00", "HSP": "0"}


def test_carrez_rattache_aux_pieces_comme_diagauto_inspect(tmp_path):
    lancer(tmp_path)
    dossier = DossierLiciel(tmp_path / "sortie")
    libelles = {p.libelle for p in dossier.pieces()}
    assert [c.localisation in libelles for c in dossier.carrez()] == [True, True, True]


def test_carrez_avec_mesures_validees(tmp_path):
    mesures = {"Séjour": {"surfaces": [18.42], "hsp": 2.5, "source": "laser"},
               "Cuisine": {"surfaces": [7.1, 1.25], "hsp": 2.5, "source": "laser"}}
    rapport = lancer(tmp_path, mesures)
    sortie = tmp_path / "sortie"
    details = lignes(sortie, "Z_Carrez_Details")
    assert [(d["Localistion"], d["Surface_1"], d["Data5"]) for d in details] == [
        ("Appartement - Sejour", "18,42", "18,42"), ("Appartement - Cuisine", "7,1", "7,1"), ("Appartement - Cuisine", "1,25", "1,25")]
    assert len({d["ClefComposant"] for d in details}) == 3 and all(CLE.fullmatch(d["ClefComposant"]) for d in details)
    resume = {l["Localistion"]: (l["Surface_1"], l["Surface_2"], l["Surface_3"], l["Data1"]) for l in lignes(sortie, "Z_Carrez_Resume")}
    assert resume == {"Appartement - Sejour": ("18,42", "18,42", "18,42", "2,5"),
                      "Appartement - Cuisine": ("8,35", "8,35", "8,35", "2,5"),
                      "Appartement - Couloir": ("0", "0", "0", "0")}
    general = lire_table(sortie / "XML" / "Table_Z_Carrez_General.xml").fiche
    assert (general["Surface_Carrez"], general["Surface_Sol"], general["HSP"]) == ("26,77", "26,77", "2,50")
    assert rapport.a_mesurer == ["Appartement - Couloir"]
    assert DossierLiciel(sortie).totaux_carrez().carrez == 26.77


def test_comble_de_moins_de_1m80_comme_la_demo_0001(tmp_path):
    """Les lignes de calcul du comble de DEMO_0001 (+43,5 puis -21,1) sont reproduites colonne par colonne."""
    mesures = {"Étage 2 - Comble non habitable 1": {"surfaces": [43.5], "moins_1m80": [21.1], "hsp": 2.6,
                                                    "commentaire": "Hauteur inférieure à 1,80 m"}}
    generer(visite(tmp_path / "visite", [], mesures), DEMO / "DEMO_0001", tmp_path / "sortie")
    colonnes = ["Localistion", "Surface_1", "Surface_2", "Surface_3", "Surface_4"] + [f"Data{i}" for i in range(1, 13)]
    nos_lignes = [[d[c] for c in colonnes] for d in lignes(tmp_path / "sortie", "Z_Carrez_Details")]
    demo = [[d[c] for c in colonnes] for d in lignes(DEMO / "DEMO_0001", "Z_Carrez_Details")
            if d["Localistion"] == "Étage  2 - Comble non habitable  1"]
    assert sorted(nos_lignes) == sorted(demo)
    resume = lignes(tmp_path / "sortie", "Z_Carrez_Resume")[0]
    demo_resume = next(l for l in lignes(DEMO / "DEMO_0001", "Z_Carrez_Resume") if l["Localistion"] == resume["Localistion"])
    for c in ("Surface_1", "Surface_2", "Surface_3", "Surface_4", "Commantaires", "Data1", "Data2"):
        assert resume[c] == demo_resume[c], c


@pytest.mark.parametrize("demo", ["DEMO_0002", "DEMO_0003"])
def test_carrez_des_demos_reconstruit_a_l_identique(tmp_path, demo):
    """À partir des surfaces de chaque pièce d'une démo (pièces exclues, annexes, parties < 1,80 m), nos tables
    redonnent les lignes et les totaux calculés par LICIEL."""
    mesures = {}
    for l in lignes(DEMO / demo, "Z_Carrez_Resume"):
        carrez, sol = float(l["Surface_1"].replace(",", ".")), float(l["Surface_2"].replace(",", "."))
        m = {"surfaces": [sol], "commentaire": l["Commantaires"], "annexe": l["Data2"] == "OUI"}
        if carrez == 0:
            m["hors_carrez"] = True
        elif carrez < sol:
            m["moins_1m80"] = [round(sol - carrez, 2)]
        if float(l["Data1"].replace(",", ".")):
            m["hsp"] = float(l["Data1"].replace(",", "."))
        mesures[l["Localistion"]] = m
    generer(visite(tmp_path / "visite", [], mesures), DEMO / demo, tmp_path / "sortie")
    colonnes = ("Surface_1", "Surface_2", "Surface_3", "Surface_4", "Commantaires", "Data1", "Data2")
    attendu = {l["Localistion"]: [l[c] for c in colonnes] for l in lignes(DEMO / demo, "Z_Carrez_Resume")}
    obtenu = {l["Localistion"]: [l[c] for c in colonnes] for l in lignes(tmp_path / "sortie", "Z_Carrez_Resume")}
    assert obtenu == attendu
    general, general_demo = (lire_table(d / "XML" / "Table_Z_Carrez_General.xml").fiche for d in (tmp_path / "sortie", DEMO / demo))
    for c in ("Surface_Carrez", "Surface_Habitable", "Surface_Sol", "Surface_Ref", "HSP"):
        assert general[c] == general_demo[c], c


def test_colonnes_carrez_dans_l_ordre_de_licel(tmp_path):
    lancer(tmp_path, {"Séjour": {"surfaces": [18.42]}})
    for nom in ("Z_Carrez_Details", "Z_Carrez_Resume", "Z_Carrez_General"):
        assert lire_table(tmp_path / "sortie" / "XML" / f"Table_{nom}.xml").colonnes() == \
            lire_table(DEMO / "DEMO_0001" / "XML" / f"Table_{nom}.xml").colonnes(), nom


# --- format et sécurité ----------------------------------------------------------------------------------------------


def test_toutes_les_tables_relues_a_l_octet_pres(tmp_path):
    lancer(tmp_path, {"Séjour": {"surfaces": [18.42], "hsp": 2.5}})
    flux = io.StringIO()
    assert verifier([tmp_path / "sortie"], flux) == 0
    assert "5 tables vérifiées : 5 identiques" in flux.getvalue()
    for nom in ("Table_General_Bien.xml",):  # tables du modèle : copiées telles quelles
        assert (tmp_path / "sortie" / "XML" / nom).read_bytes() == (tmp_path / "modele" / "XML" / nom).read_bytes()
    brut = (tmp_path / "sortie" / "XML" / "Table_Z_Carrez_Resume.xml").read_bytes()
    assert b"\n" not in brut and b"\r     <LiItem_table_Z_Carrez_Resume>\r" in brut  # fins de ligne CR, indentation de 5
    assert "Appartement - Sejour".encode("cp1252") in brut


def test_demo_0003_pieces_hors_visite_non_touchees(tmp_path):
    generer(visite(tmp_path / "visite", [piece("Rez de chaussée - Véranda")]), DEMO / "DEMO_0003", tmp_path / "sortie")
    nom = "XML/Table_General_Pieces_Toutes.xml"
    assert (tmp_path / "sortie" / nom).read_bytes() == (DEMO / "DEMO_0003" / nom).read_bytes()  # dont la pièce non visitée
    for nom in ("Table_Z_Amiante.xml", "Table_General_Pieces_Visites.xml", "Table_General_Pieces_Non_Visites.xml"):
        assert (tmp_path / "sortie" / "XML" / nom).read_bytes() == (DEMO / "DEMO_0003" / "XML" / nom).read_bytes()
    assert not list((tmp_path / "sortie" / "XML").glob("*.signed.xml"))  # jamais de fichier signé recopié ou fabriqué


def test_piece_ajoutee_aussi_dans_les_pieces_visitees_si_le_dossier_les_liste(tmp_path):
    generer(visite(tmp_path / "visite", [piece("Rez de chaussée - Véranda"), piece("Cellier")]), DEMO / "DEMO_0003",
            tmp_path / "sortie", batiment="Rez de chaussée")
    visites = [l["Pieces"] for l in lignes(tmp_path / "sortie", "General_Pieces_Visites")]
    assert visites == [l["Pieces"] for l in lignes(DEMO / "DEMO_0003", "General_Pieces_Visites")] + ["Rez de chaussée - Cellier"]
    lancer(tmp_path / "test")  # notre dossier de test n'a pas cette liste : elle n'est pas créée
    assert not (tmp_path / "test" / "sortie" / "XML" / "Table_General_Pieces_Visites.xml").exists()


def test_ecriture_refusee_sous_un_dossier_liciel(tmp_path):
    sortie = tmp_path / "LICIEL_Diagnostics" / "Dossiers_2026" / "2610210001"
    with pytest.raises(ErreurPont, match="LICIEL_"):
        generer(visite_de_noah(tmp_path / "visite"), dossier_test(tmp_path / "modele"), sortie)
    assert not (tmp_path / "LICIEL_Diagnostics").exists()


def test_sortie_dans_le_modele_refusee(tmp_path):
    modele = dossier_test(tmp_path / "modele")
    with pytest.raises(ErreurPont, match="modèle"):
        generer(visite_de_noah(tmp_path / "visite"), modele, modele / "sortie")


def test_dossier_de_sortie_etranger_jamais_ecrase(tmp_path):
    (tmp_path / "sortie").mkdir()
    (tmp_path / "sortie" / "notes.txt").write_text("à garder", encoding="utf-8")
    with pytest.raises(ErreurPont, match="existe déjà"):
        lancer(tmp_path)
    assert (tmp_path / "sortie" / "notes.txt").read_text(encoding="utf-8") == "à garder"


def test_regeneration_remplace_nos_anciennes_tables(tmp_path):
    lancer(tmp_path)
    (tmp_path / "sortie" / "XML" / "Table_Z_Ancienne.xml").write_bytes(b"<LiTable_Z_Ancienne>\r</LiTable_Z_Ancienne>")
    generer(tmp_path / "visite", tmp_path / "modele", tmp_path / "sortie", maintenant=MAINTENANT)
    assert not (tmp_path / "sortie" / "XML" / "Table_Z_Ancienne.xml").exists()
    assert len(lignes(tmp_path / "sortie", "General_Pieces_Toutes")) == 5


# --- entrées refusées -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mesures, message", [
    ({"Garage": {"surfaces": [15]}}, "ni vue"),
    ({"Séjour": {"surfaces": [-3]}}, "surface invalide"),
    ({"Séjour": {"surfaces": ["18"]}}, "surface invalide"),
    ({"Séjour": {"surfaces": [10], "moins_1m80": [12]}}, "dépasse"),
    ({"Séjour": {"surfaces": [10], "hsp": 25}}, "hauteur"),
    ({"Séjour": {"surface": [10]}}, "champs inconnus"),
])
def test_mesures_refusees(tmp_path, mesures, message):
    with pytest.raises(ErreurPont, match=message):
        lancer(tmp_path, mesures)
    assert not (tmp_path / "sortie").exists()  # rien n'est écrit


def test_fichiers_illisibles_ou_nom_impossible_en_windows_1252(tmp_path):
    vue = visite_de_noah(tmp_path / "visite")
    (vue / "mesures.json").write_text("{pas du json", encoding="utf-8")
    with pytest.raises(ErreurPont, match="illisible"):
        generer(vue, dossier_test(tmp_path / "modele"), tmp_path / "sortie")
    with pytest.raises(FileNotFoundError):
        generer(vue, tmp_path / "modele", tmp_path / "sortie", mesures=tmp_path / "absent.json")
    autre = visite(tmp_path / "visite2", [piece("Séjour 🏠")])
    with pytest.raises(ErreurPont, match="Windows-1252"):
        generer(autre, tmp_path / "modele", tmp_path / "sortie")
    assert not (tmp_path / "sortie").exists()  # rien n'est écrit


def test_piece_ambigue_et_batiment_a_preciser(tmp_path):
    with pytest.raises(ErreurPont, match="ambigu"):  # « Pièce 1 » : au rez-de-chaussée, au garage et à l'étage
        generer(visite(tmp_path / "v1", [piece("Pièce 1")]), DEMO / "DEMO_0003", tmp_path / "s1")
    with pytest.raises(ErreurPont, match="--batiment"):
        generer(visite(tmp_path / "v2", [piece("Cellier")]), DEMO / "DEMO_0003", tmp_path / "s2")
    generer(tmp_path / "v2", DEMO / "DEMO_0003", tmp_path / "s3", batiment="Rez de chaussée")
    assert lignes(tmp_path / "s3", "General_Pieces_Toutes")[-1]["Batiment"] == "Rez de chaussée"
    generer(visite(tmp_path / "v4", [piece("Garage - Pièce 1")]), DEMO / "DEMO_0003", tmp_path / "s4")
    assert [l["Localistion"] for l in lignes(tmp_path / "s4", "Z_Carrez_Resume")] == ["Garage - Pièce 1"]


# --- utilitaires et commande --------------------------------------------------------------------------------------------


def test_nombres_et_cles_au_format_liciel():
    assert [nombre_liciel(x) for x in (50, 43.3, 10.36, -21.1, 0, 0.829, -0.001, 2.5)] == \
        ["50", "43,3", "10,36", "-21,1", "0", "0,83", "0", "2,5"]
    assert all(CLE.fullmatch(cle) for cle, _ in PIECES_TEST)  # le format des clés écrites par LICIEL
    assert CLE.fullmatch(cle_composant(MAINTENANT, random.Random(0)))


def test_derniere_visite_avec_etat(tmp_path):
    for nom, avec_etat in (("20261022-100000-aaaaaa", True), ("20261022-110000-bbbbbb", True), ("20261022-120000-cccccc", False)):
        (tmp_path / nom).mkdir()
        if avec_etat:
            (tmp_path / nom / "etat.json").write_text("{}", encoding="utf-8")
    assert derniere_visite(tmp_path).name == "20261022-110000-bbbbbb"
    assert derniere_visite(tmp_path / "20261022-100000-aaaaaa").name == "20261022-100000-aaaaaa"
    with pytest.raises(FileNotFoundError):
        derniere_visite(tmp_path / "20261022-120000-cccccc")


def test_commande_generer(tmp_path, capsys):
    vue, modele = visite_de_noah(tmp_path / "visite"), dossier_test(tmp_path / "modele")
    code = main(["generer", "--visite", str(tmp_path), "--modele", str(modele), "--sortie", str(tmp_path / "sortie")])
    sortie = capsys.readouterr().out
    assert code == 0, sortie
    assert "Appartement - Couloir [ajoutée] : À MESURER" in sortie and "2 murs, 2 fenêtres, 2 émetteurs" in sortie
    assert "0 échecs" in sortie and vue.name in sortie
    code = main(["generer", "--visite", str(vue), "--modele", str(modele), "--sortie", str(tmp_path / "LICIEL_Diagnostics")])
    assert code == 2 and "LICIEL_" in capsys.readouterr().err
