"""Lecture d'un dossier LICIEL complet (``Dossiers_AAAA\\<n°>\\``) : tables, pièces, Carrez.

Lecture seule. Les correspondances marquées « hypothèse » viennent de
l'observation des dossiers de démonstration (voir docs/01-cadrage.md § 1.5) et
restent à confirmer par des saisies contrôlées dans LICIEL (étape E3).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .table import FormatNonReconnu, FragmentXml, Table, lire_fichier, nom_depuis_fichier
from .valeurs import nombre

# Préfixe de nom de table -> module LICIEL. L'ordre compte : le premier préfixe qui correspond l'emporte.
MODULES = [
    ("Z_Carrez_", "Métrage Carrez / Boutin"),
    ("Z_DPE_ERE", "Audit énergétique"),
    ("Z_DPE_2020_", "DPE 2020"),
    ("DPE_2020_", "DPE 2020"),
    ("Z_Elec", "Électricité"),
    ("Z_Gaz", "Gaz"),
    ("Z_Amiante", "Amiante"),
    ("Z_CREP", "Plomb (CREP)"),
    ("Z_Parasitaire", "Termites / parasites"),
    ("Z_ERNT", "État des risques (ERP)"),
    ("Z_Handicape", "Accessibilité"),
    ("Z_Assainissement", "Assainissement"),
]

# Hypothèse (docs/01-cadrage.md § 1.5) : Surface_2 = au sol est vérifiée par les totaux ;
# Surface_1 = Carrez et Surface_3 = habitable ne sont pas encore départagées (égales dans les démos).
COLONNE_CARREZ = "Surface_1"
COLONNE_SOL = "Surface_2"
COLONNE_HABITABLE = "Surface_3"
COLONNE_REFERENCE = "Surface_4"


@dataclass
class Piece:
    batiment: str
    local: str
    clef: str
    justification_non_visite: str

    @property
    def libelle(self) -> str:
        """Libellé utilisé par LICIEL pour relier les tables : « Bâtiment - Local ».

        Hypothèse quand le bâtiment est vide : le libellé est le seul nom du local.
        """
        return f"{self.batiment} - {self.local}" if self.batiment else self.local

    @property
    def visitee(self) -> bool:
        return not self.justification_non_visite.strip()


@dataclass
class CarrezPiece:
    localisation: str
    lot: str
    carrez: float | None
    habitable: float | None
    sol: float | None
    reference: float | None
    hauteur_sous_plafond: float | None
    commentaire: str
    nb_lignes_calcul: int


@dataclass
class TotauxCarrez:
    carrez: float | None
    habitable: float | None
    sol: float | None
    reference: float | None
    hauteur_sous_plafond: float | None


class DossierLiciel:
    """Un dossier LICIEL sur disque. Les tables sont lues à la demande."""

    def __init__(self, chemin: str | Path):
        self.chemin = Path(chemin)
        if not self.chemin.is_dir():
            raise FileNotFoundError(f"dossier introuvable : {self.chemin}")
        xml = self.chemin / "XML"
        # Certains dossiers de test DPE ont leurs tables à la racine.
        self.dossier_xml = xml if xml.is_dir() else self.chemin
        self._cache: dict[str, Table | FragmentXml] = {}
        self.erreurs: dict[str, str] = {}

    def fichiers_tables(self) -> list[Path]:
        return sorted(self.dossier_xml.glob("Table_*.xml"))

    def noms_tables(self) -> list[str]:
        return [nom_depuis_fichier(f) for f in self.fichiers_tables()]

    def lire(self, nom: str) -> Table | FragmentXml | None:
        """Table par son nom de fichier sans « Table_ » ni « .xml » (ex. « Z_Carrez_Details »)."""
        if nom not in self._cache:
            fichier = self.dossier_xml / f"Table_{nom}.xml"
            if not fichier.is_file():
                return None
            try:
                self._cache[nom] = lire_fichier(fichier)
            except FormatNonReconnu as err:
                self.erreurs[nom] = str(err)
                return None
        return self._cache[nom]

    def table(self, nom: str) -> Table | None:
        objet = self.lire(nom)
        return objet if isinstance(objet, Table) else None

    def modules_presents(self) -> dict[str, list[str]]:
        """Module -> tables présentes. Une table présente ne veut pas dire que le module est rempli."""
        modules: dict[str, list[str]] = {}
        for nom in self.noms_tables():
            for prefixe, module in MODULES:
                if nom.startswith(prefixe):
                    if module == "DPE 2020" and ("_ERE" in nom or "_SR0" in nom):
                        module = "Audit énergétique"
                    modules.setdefault(module, []).append(nom)
                    break
        return modules

    def mission(self) -> dict[str, str]:
        """Informations principales de la mission (copie de la base LICIEL dans le dossier)."""
        admin = self.table("Admin_Donnees_Dossiers")
        bien = self.table("General_Bien")
        a = admin.fiche if admin and not admin.liste else {}
        b = bien.fiche if bien and not bien.liste else {}
        ville = a.get("bien_ville", "").split("#")[0]
        return {
            "numero": a.get("Num_dossier") or b.get("Mission_Num_Dossier", ""),
            "adresse": " ".join(x for x in (a.get("bien_adresse", ""), a.get("bien_cp", ""), ville) if x),
            "nature": a.get("bien_nature") or b.get("Immeuble_Nature_bien", ""),
            "date_visite": a.get("rdv_date") or b.get("Mission_Date_Visite", ""),
            "operateur": b.get("Gen_Nom_operateur") or a.get("operateur_reperage", ""),
        }

    def pieces(self) -> list[Piece]:
        table = self.table("General_Pieces_Toutes")
        if not table:
            return []
        return [
            Piece(
                batiment=ligne.get("Batiment", ""),
                local=ligne.get("Local", ""),
                clef=ligne.get("ClefComposant", ""),
                justification_non_visite=ligne.get("Justification", ""),
            )
            for ligne in table.lignes
        ]

    def carrez(self) -> list[CarrezPiece]:
        resume = self.table("Z_Carrez_Resume")
        if not resume:
            return []
        details = self.table("Z_Carrez_Details")
        nb_lignes: dict[str, int] = {}
        for ligne in details.lignes if details else []:
            cle = ligne.get("ClefComposantPiece", "")
            nb_lignes[cle] = nb_lignes.get(cle, 0) + 1
        return [
            CarrezPiece(
                localisation=ligne.get("Localistion", ""),  # sic : orthographe LICIEL
                lot=ligne.get("NomLot", ""),
                carrez=nombre(ligne.get(COLONNE_CARREZ)),
                habitable=nombre(ligne.get(COLONNE_HABITABLE)),
                sol=nombre(ligne.get(COLONNE_SOL)),
                reference=nombre(ligne.get(COLONNE_REFERENCE)),
                hauteur_sous_plafond=nombre(ligne.get("Data1")),
                commentaire=ligne.get("Commantaires", ""),  # sic
                nb_lignes_calcul=nb_lignes.get(ligne.get("ClefComposantPiece", ""), 0),
            )
            for ligne in resume.lignes
        ]

    def totaux_carrez(self) -> TotauxCarrez | None:
        general = self.table("Z_Carrez_General")
        if not general or general.liste:
            return None
        f = general.fiche
        return TotauxCarrez(
            carrez=nombre(f.get("Surface_Carrez")),
            habitable=nombre(f.get("Surface_Habitable")),
            sol=nombre(f.get("Surface_Sol")),
            reference=nombre(f.get("Surface_Ref")),
            hauteur_sous_plafond=nombre(f.get("HSP")),
        )
