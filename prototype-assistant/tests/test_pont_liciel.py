"""Étape 11 : de la visite de l'assistant aux tables LICIEL (pièces + Carrez), avec le vrai format d'export.

L'état est construit par la checklist de l'assistant (comme pendant une visite), écrit en etat.json comme le fait la
session, puis passé au pont diagauto.pont. Le dossier modèle reproduit notre dossier de test LICIEL (4 pièces)."""

import json

from diagauto.liciel_xml import DossierLiciel, Table, ecrire_table, lire_table
from diagauto.pont import generer

from assistant.checklist import Checklist
from test_groupes import dire


def modele(chemin):
    xml = chemin / "XML"
    xml.mkdir(parents=True)
    lignes = [{"id_classement_champs": f"{i:05d}", "Lot": "", "PieceHorsCREP": "", "PieceExterieure": "",
               "ClefComposant": f"2026_10_21_21_58_{39 + i}_1130632007428662{i}", "Batiment": "Appartement", "Local": local,
               "Justification": "", "MoyenAMettreEnOeuvre": ""}
              for i, local in enumerate(("Sejour", "Cuisine", "Chambre 1", "Salle de bains"))]
    ecrire_table(Table("General_Pieces_Toutes", lignes), xml / "Table_General_Pieces_Toutes.xml")
    return chemin


def test_visite_de_l_assistant_vers_le_dossier_liciel(tmp_path):
    c = Checklist()
    c.definir_piece("Séjour", 0.0)
    for phrase in ("Ce mur donne sur l'extérieur, en brique.", "Il y a deux fenêtres en PVC double vitrage.",
                   "Il y a trois radiateurs électriques.", "On passe dans la cuisine.", "Une fenêtre en bois.",
                   "Maintenant le couloir."):
        dire(c, phrase)
    visite = tmp_path / "sessions" / "20261022-150000-abcdef"
    visite.mkdir(parents=True)
    (visite / "etat.json").write_text(json.dumps(c.vers_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    rapport = generer(tmp_path / "sessions", modele(tmp_path / "modele"), tmp_path / "sortie")

    assert rapport.visite == visite  # la visite la plus récente
    assert [(p.libelle, p.statut) for p in rapport.pieces] == [
        ("Appartement - Sejour", "existante"), ("Appartement - Cuisine", "existante"), ("Appartement - Couloir", "ajoutée")]
    assert rapport.pieces[0].elements == {"mur": 1, "fenêtre": 2, "porte": 0, "émetteur": 3}
    assert rapport.a_mesurer == ["Appartement - Sejour", "Appartement - Cuisine", "Appartement - Couloir"]
    dossier = DossierLiciel(tmp_path / "sortie")
    assert [p.libelle for p in dossier.pieces()][-1] == "Appartement - Couloir"
    assert [c.localisation for c in dossier.carrez()] == ["Appartement - Sejour", "Appartement - Cuisine", "Appartement - Couloir"]
    assert all(c.carrez == 0 for c in dossier.carrez())  # aucune surface inventée : rien n'a été mesuré
    assert lire_table(tmp_path / "sortie" / "XML" / "Table_Z_Carrez_Details.xml").lignes == []
