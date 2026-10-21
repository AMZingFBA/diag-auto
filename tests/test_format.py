"""Cas de format LICIEL construits à la main (voir diagauto/liciel_xml/table.py)."""

import pytest

from diagauto.liciel_xml import FormatNonReconnu, FragmentXml, Table

FICHE = (
    "<LiTable_Z_Carrez_General>\r"
    "     <LiColonne_Doc_Remis>Néant</LiColonne_Doc_Remis>\r"
    "     <LiColonne_Surface_Carrez>284,20</LiColonne_Surface_Carrez>\r"
    "\r"
    "</LiTable_Z_Carrez_General>"
).encode("cp1252")

LISTE = (
    "<LiTable_General_Pieces_Toutes>\r"
    "     <LiItem_table_General_Pieces_Toutes>\r"
    "          <LiColonne_Batiment>Rez de chaussée</LiColonne_Batiment>\r"
    "          <LiColonne_Local>Pièce 1</LiColonne_Local>\r"
    "     </LiItem_table_General_Pieces_Toutes>\r"
    "     <LiItem_table_General_Pieces_Toutes>\r"
    "          <LiColonne_Batiment>Étage  1</LiColonne_Batiment>\r"
    "          <LiColonne_Local>Séjour</LiColonne_Local>\r"
    "     </LiItem_table_General_Pieces_Toutes>\r"
    "</LiTable_General_Pieces_Toutes>"
).encode("cp1252")


def test_fiche():
    table = Table.depuis_octets(FICHE)
    assert table.nom == "Z_Carrez_General"
    assert not table.liste
    assert table.fiche == {"Doc_Remis": "Néant", "Surface_Carrez": "284,20"}
    assert table.en_octets() == FICHE


def test_liste():
    table = Table.depuis_octets(LISTE)
    assert table.liste
    assert table.balise_item is None  # balise standard LiItem_table_<nom>
    assert [l["Local"] for l in table.lignes] == ["Pièce 1", "Séjour"]
    assert table.colonnes() == ["Batiment", "Local"]
    assert table.en_octets() == LISTE


def test_encodage_windows_1252():
    assert b"Pi\xe8ce 1" in LISTE
    assert Table.depuis_octets(LISTE).lignes[0]["Local"] == "Pièce 1"


def test_generer_une_table_from_scratch_au_format_liciel():
    table = Table(nom="General_Pieces_Toutes")
    table.lignes.append({"Batiment": "Rez de chaussée", "Local": "Pièce 1"})
    table.lignes.append({"Batiment": "Étage  1", "Local": "Séjour"})
    assert table.en_octets() == LISTE
    fiche = Table(nom="Z_Carrez_General", liste=False)
    fiche.fiche["Doc_Remis"] = "Néant"
    fiche.fiche["Surface_Carrez"] = "284,20"
    assert fiche.en_octets() == FICHE


def test_esperluette_et_chevron_non_echappes_et_xml_imbrique():
    valeur = "1780 & 1830 <5 m²> <Paroies_ITE>11</Paroies_ITE>"
    data = (f"<LiTable_T>\r     <LiColonne_A>{valeur}</LiColonne_A>\r\r</LiTable_T>").encode("cp1252")
    table = Table.depuis_octets(data)
    assert table.fiche["A"] == valeur
    assert table.en_octets() == data


def test_valeur_sur_plusieurs_lignes_avec_crlf():
    valeur = "DPE : \r\nOpérateur: TEST\r\nClasse A"
    data = (f"<LiTable_T>\r     <LiColonne_conclusion>{valeur}</LiColonne_conclusion>\r\r</LiTable_T>").encode("cp1252")
    table = Table.depuis_octets(data)
    assert table.fiche["conclusion"] == valeur
    assert table.en_octets() == data


def test_fichier_en_fins_de_ligne_lf():
    data = FICHE.replace(b"\r", b"\n")
    table = Table.depuis_octets(data)
    assert table.fin_de_ligne == "\n"
    assert table.en_octets() == data


def test_octet_non_defini_en_windows_1252_conserve():
    data = b"<LiTable_T>\r     <LiColonne_A>x\x81y</LiColonne_A>\r\r</LiTable_T>"
    assert Table.depuis_octets(data).en_octets() == data


def test_colonne_en_double_conservee_a_sa_place():
    data = (
        b"<LiTable_T>\r     <LiItem_table_T>\r"
        b"          <LiColonne_A>1</LiColonne_A>\r"
        b"          <LiColonne_B>2</LiColonne_B>\r"
        b"          <LiColonne_A>3</LiColonne_A>\r"
        b"     </LiItem_table_T>\r</LiTable_T>"
    )
    table = Table.depuis_octets(data)
    assert table.lignes[0] == {"A": "1", "B": "2", "A#2": "3"}
    assert table.en_octets() == data


def test_tables_vides():
    liste_vide = b"<LiTable_T>\r</LiTable_T>"
    fiche_vide = b"<LiTable_T>\r\r</LiTable_T>"
    assert Table.depuis_octets(liste_vide).liste
    assert Table.depuis_octets(liste_vide).lignes == []
    assert not Table.depuis_octets(fiche_vide).liste
    for data in (liste_vide, fiche_vide):
        assert Table.depuis_octets(data).en_octets() == data


def test_balise_de_ligne_atypique_conservee():
    data = b"<LiTable_T>\r     <LiItem_table_Autre>\r          <LiColonne_A>1</LiColonne_A>\r     </LiItem_table_Autre>\r</LiTable_T>"
    table = Table.depuis_octets(data)
    assert table.balise_item == "LiItem_table_Autre"
    assert table.en_octets() == data


@pytest.mark.parametrize(
    "data",
    [
        b"<Autre>\r</Autre>",  # pas une table LiTable
        b"<LiTable_T>\r     <LiColonne_A>1</LiColonne_A>\r\r",  # fermeture absente
        b"<LiTable_T>\r    <LiColonne_A>1</LiColonne_A>\r\r</LiTable_T>",  # indentation de 4 espaces
        b"<LiTable_T>\r     <LiColonne_A>1</LiColonne_A>\r</LiTable_T>",  # fiche sans ligne vide finale
        b"<LiTable_T>\r     <LiColonne_A>1\r\r</LiTable_T>",  # colonne non fermée
        b"<LiTable_T>     <LiColonne_A>1</LiColonne_A>\r\r</LiTable_T>",  # pas de fin de ligne après la racine
    ],
)
def test_mise_en_page_inattendue_refusee(data):
    with pytest.raises(FormatNonReconnu):
        Table.depuis_octets(data)


def test_ecriture_refuse_les_valeurs_dangereuses():
    table = Table(nom="T", liste=False)
    table.fiche["A"] = "texte</LiColonne_A>suite"
    with pytest.raises(ValueError):
        table.en_octets()
    table.fiche["A"] = "coche ✓"  # absent de Windows-1252
    with pytest.raises(ValueError):
        table.en_octets()
    table.fiche["A"] = 12
    with pytest.raises(TypeError):
        table.en_octets()


def test_fragment_xml_libre():
    texte = "<Reco1_Presente>True</Reco1_Presente><Reco1_Analyse><Valeur_EP>9065</Valeur_EP></Reco1_Analyse>"
    fragment = FragmentXml(nom="Z_DPE_2020_Details_simulations_ERE_SR01", texte=texte)
    assert fragment.elements() == [
        ("Reco1_Presente", "True"),
        ("Reco1_Analyse", "<Valeur_EP>9065</Valeur_EP>"),
    ]
    assert fragment.en_octets() == texte.encode("cp1252")
