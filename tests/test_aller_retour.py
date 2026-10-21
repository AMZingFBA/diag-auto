"""Aller-retour octet pour octet sur toutes les tables des dossiers de référence (fixtures)."""

import pytest

from conftest import DEMO, FIXTURES
from diagauto.liciel_xml import FragmentXml, Table, ecrire_table, lire_fichier, lire_table

FICHIERS = sorted(FIXTURES.rglob("Table_*.xml"))


def _id(fichier):
    return fichier.relative_to(FIXTURES).as_posix()


def test_les_fixtures_sont_presentes():
    # 4 dossiers DEMO + 5 dossiers Eval_DPE_2020 = 296 tables au moment de la copie.
    assert len(FICHIERS) >= 290


@pytest.mark.parametrize("fichier", FICHIERS, ids=_id)
def test_relecture_puis_reecriture_identique(fichier):
    data = fichier.read_bytes()
    objet = lire_fichier(fichier)
    assert objet.en_octets() == data


@pytest.mark.parametrize("fichier", FICHIERS, ids=_id)
def test_les_fichiers_litable_sont_bien_analyses(fichier):
    """Un fichier qui commence par <LiTable_ doit être analysé en Table, jamais conservé en vrac."""
    objet = lire_fichier(fichier)
    if fichier.read_bytes().startswith(b"<LiTable_"):
        assert isinstance(objet, Table)
        assert objet.fin_de_ligne in ("\r", "\n")
    else:
        assert isinstance(objet, FragmentXml)


def test_ecriture_sur_disque_identique(tmp_path):
    for fichier in sorted((DEMO / "DEMO_0001" / "XML").glob("Table_*.xml")):
        copie = tmp_path / fichier.name
        ecrire_table(lire_fichier(fichier), copie)
        assert copie.read_bytes() == fichier.read_bytes(), fichier.name
    assert not list(tmp_path.glob("*.tmp"))


def test_modifier_une_valeur_ne_change_que_cette_valeur(tmp_path):
    fichier = DEMO / "DEMO_0001" / "XML" / "Table_Z_Carrez_General.xml"
    table = lire_table(fichier)
    assert table.fiche["Surface_Carrez"] == "284,20"
    table.fiche["Surface_Carrez"] = "123,45"
    copie = tmp_path / fichier.name
    ecrire_table(table, copie)
    attendu = fichier.read_bytes().replace(b">284,20</LiColonne_Surface_Carrez>", b">123,45</LiColonne_Surface_Carrez>")
    assert copie.read_bytes() == attendu
