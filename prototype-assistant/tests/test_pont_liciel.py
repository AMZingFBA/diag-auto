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
    # Étape 13 : le DPE se décrit par côté, pour tout le logement ; les pièces servent au Carrez (et au repérage).
    c = Checklist()
    c.definir_piece("Séjour", 0.0)
    for phrase in ("Au sud la rue, brique 30 cm, isolé par l'intérieur, avec deux fenêtres en PVC double vitrage.",
                   "Au nord le voisin.", "Il y a trois radiateurs électriques.", "On passe dans la cuisine.",
                   "Une fenêtre en bois.", "Maintenant le couloir."):
        dire(c, phrase)
    visite = tmp_path / "sessions" / "20261022-150000-abcdef"
    visite.mkdir(parents=True)
    (visite / "etat.json").write_text(json.dumps(c.vers_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    rapport = generer(tmp_path / "sessions", modele(tmp_path / "modele"), tmp_path / "sortie")

    assert rapport.visite == visite  # la visite la plus récente
    assert [(p.libelle, p.statut) for p in rapport.pieces] == [
        ("Appartement - Sejour", "existante"), ("Appartement - Cuisine", "existante"), ("Appartement - Couloir", "ajoutée")]
    # Ce qui a été vu dans chaque pièce : les murs et fenêtres du logement qui y ont été vus (les radiateurs sont ceux du
    # logement).
    assert rapport.pieces[0].elements == {"mur": 2, "fenêtre": 2, "porte": 0, "émetteur": 0}
    assert rapport.pieces[1].elements == {"mur": 0, "fenêtre": 1, "porte": 0, "émetteur": 0}
    assert rapport.a_mesurer == ["Appartement - Sejour", "Appartement - Cuisine", "Appartement - Couloir"]
    dossier = DossierLiciel(tmp_path / "sortie")
    assert [p.libelle for p in dossier.pieces()][-1] == "Appartement - Couloir"
    assert [c.localisation for c in dossier.carrez()] == ["Appartement - Sejour", "Appartement - Cuisine", "Appartement - Couloir"]
    assert all(c.carrez == 0 for c in dossier.carrez())  # aucune surface inventée : rien n'a été mesuré
    assert lire_table(tmp_path / "sortie" / "XML" / "Table_Z_Carrez_Details.xml").lignes == []

    # Le DPE du logement, par côté : chaque mur avec ses fenêtres ; ce qui n'est pas dit reste à renseigner.
    dpe = rapport.dpe
    sud = dpe["cotes"]["sud"][0]
    assert sud["valeurs"] == {"donne sur": "extérieur", "matériau": "brique", "épaisseur": "30 cm", "isolation": "ITI"}
    assert [(o["nombre"], o["valeurs"]) for o in sud["ouvertures"]] == [(2, {"menuiserie": "PVC", "vitrage": "double"})]
    assert [m["valeurs"] for m in dpe["cotes"]["nord"]] == [{"donne sur": "local chauffé (voisin)"}]
    assert dpe["cotes_non_decrits"] == ["est", "ouest"]
    assert [(o["nom"], o["vu_dans"]) for o in dpe["ouvertures_sans_mur"]] == [("la fenêtre en bois", ["Cuisine"])]
    assert [(e["nom"], e["valeurs"]) for e in dpe["equipements"]] == [("les 3 radiateurs", {"type": "radiateur électrique"})]
    assert "le plafond : donne sur" in dpe["manques"] and not [m for m in dpe["manques"] if "mur 1" in m or "fenêtre 1" in m]
    texte = rapport.en_texte()
    assert ("  - côté sud : le mur sud : donne sur extérieur, matériau brique, épaisseur 30 cm, isolation ITI ; les 2 fenêtres : "
            "menuiserie PVC, vitrage double") in texte
    assert "  - côtés non décrits : est, ouest" in texte
    assert json.loads((tmp_path / "sortie" / "diagauto-pont.json").read_text(encoding="utf-8"))["dpe"] == dpe
