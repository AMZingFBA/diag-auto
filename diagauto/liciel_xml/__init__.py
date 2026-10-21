"""Lecture et écriture des tables XML d'un dossier LICIEL (``XML\\Table_*.xml``)."""

from .dossier import CarrezPiece, DossierLiciel, Piece, TotauxCarrez
from .table import (
    ENCODAGE,
    FormatNonReconnu,
    FragmentXml,
    Table,
    ecrire_table,
    lire_fichier,
    lire_table,
    nom_depuis_fichier,
)

__all__ = [
    "CarrezPiece",
    "DossierLiciel",
    "Piece",
    "TotauxCarrez",
    "ENCODAGE",
    "FormatNonReconnu",
    "FragmentXml",
    "Table",
    "ecrire_table",
    "lire_fichier",
    "lire_table",
    "nom_depuis_fichier",
]
