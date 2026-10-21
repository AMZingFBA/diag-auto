"""Ligne de commande ``diagauto``.

    diagauto inspect <dossier>      résumé d'un dossier LICIEL (pièces, Carrez, modules)
    diagauto verifier <chemin>...   relit et réécrit en mémoire toutes les tables, vérifie l'identité octet par octet

Les deux commandes sont en lecture seule.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .liciel_xml import DossierLiciel, FormatNonReconnu, FragmentXml, lire_fichier
from .liciel_xml.dossier import COLONNE_CARREZ, COLONNE_HABITABLE, COLONNE_SOL
from .liciel_xml.valeurs import format_fr


def _somme(valeurs) -> float | None:
    valeurs = [v for v in valeurs if v is not None]
    return round(sum(valeurs), 2) if valeurs else None


def _ecart(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) > 0.005


def inspecter(chemin: Path, sortie=None) -> int:
    sortie = sortie or sys.stdout
    dossier = DossierLiciel(chemin)
    p = lambda *args: print(*args, file=sortie)  # noqa: E731

    p(f"Dossier LICIEL : {dossier.chemin}")
    mission = dossier.mission()
    for cle, libelle in (
        ("numero", "N° dossier"),
        ("adresse", "Bien"),
        ("nature", "Nature"),
        ("date_visite", "Visite"),
        ("operateur", "Opérateur"),
    ):
        if mission[cle]:
            p(f"  {libelle:<11}: {mission[cle]}")

    fichiers = dossier.fichiers_tables()
    nb_fragments = 0
    for f in fichiers:
        objet = dossier.lire(f.stem[len("Table_") :])
        nb_fragments += isinstance(objet, FragmentXml)
    nb_illisibles = len(dossier.erreurs)
    p(
        f"  Tables     : {len(fichiers)} fichiers "
        f"({len(fichiers) - nb_fragments - nb_illisibles} au format LiTable, "
        f"{nb_fragments} fragments XML libres, {nb_illisibles} illisibles)"
    )
    for nom, erreur in dossier.erreurs.items():
        p(f"    ILLISIBLE Table_{nom}.xml : {erreur}")

    p("")
    modules = dossier.modules_presents()
    if modules:
        p("Modules présents (tables trouvées, pas forcément remplies) :")
        for module, tables in modules.items():
            p(f"  - {module} ({len(tables)} tables)")
    else:
        p("Aucune table de module (Carrez, DPE, Élec…) dans ce dossier.")

    p("")
    pieces = dossier.pieces()
    p(f"Pièces ({len(pieces)}) :")
    for i, piece in enumerate(pieces, 1):
        etat = "" if piece.visitee else f"   [NON VISITÉE : {piece.justification_non_visite}]"
        p(f"  {i:>2}. {piece.libelle}{etat}")
    if not pieces:
        p("  (aucune liste de pièces : table General_Pieces_Toutes absente)")

    carrez = dossier.carrez()
    totaux = dossier.totaux_carrez()
    if carrez or totaux:
        p("")
        p(f"Métrage Carrez / Boutin ({len(carrez)} pièces) :")
        largeur = max([len(c.localisation) for c in carrez] + [28])
        p(f"  {'Localisation':<{largeur}}  {'Carrez':>8}  {'Habitable':>9}  {'Au sol':>8}  {'HSP':>5}  Calc.  Commentaire")
        for c in carrez:
            p(
                f"  {c.localisation:<{largeur}}  {format_fr(c.carrez):>8}  {format_fr(c.habitable):>9}  "
                f"{format_fr(c.sol):>8}  {format_fr(c.hauteur_sous_plafond):>5}  {c.nb_lignes_calcul:>5}  {c.commentaire}"
            )
        somme = (
            _somme(c.carrez for c in carrez),
            _somme(c.habitable for c in carrez),
            _somme(c.sol for c in carrez),
        )
        p(f"  {'Somme des pièces':<{largeur}}  {format_fr(somme[0]):>8}  {format_fr(somme[1]):>9}  {format_fr(somme[2]):>8}")
        if totaux:
            enregistre = (totaux.carrez, totaux.habitable, totaux.sol)
            p(
                f"  {'Total enregistré par LICIEL':<{largeur}}  {format_fr(enregistre[0]):>8}  "
                f"{format_fr(enregistre[1]):>9}  {format_fr(enregistre[2]):>8}  {format_fr(totaux.hauteur_sous_plafond):>5}"
            )
            for nom, s, t in zip(("Carrez", "habitable", "au sol"), somme, enregistre):
                if _ecart(s, t):
                    p(f"  ATTENTION : la somme {nom} ({format_fr(s)}) diffère du total LICIEL ({format_fr(t)}) — pièce annexe exclue ?")

        libelles = {piece.libelle for piece in pieces}
        if pieces:
            rattachees = sum(c.localisation in libelles for c in carrez)
            p(f"  Rattachement aux pièces par libellé : {rattachees}/{len(carrez)} retrouvées dans la liste des pièces")
        p(
            f"  Note : colonnes {COLONNE_CARREZ}=Carrez, {COLONNE_HABITABLE}=habitable, {COLONNE_SOL}=au sol "
            "(hypothèse, voir docs/01-cadrage.md § 1.5)."
        )
    return 0


def verifier(chemins: list[Path], sortie=None) -> int:
    sortie = sortie or sys.stdout
    fichiers: list[Path] = []
    for chemin in chemins:
        if chemin.is_file():
            fichiers.append(chemin)
        else:
            fichiers += sorted(chemin.rglob("Table_*.xml"))
    nb_ok = nb_fragments = 0
    echecs: list[tuple[Path, str]] = []
    for fichier in fichiers:
        data = fichier.read_bytes()
        try:
            objet = lire_fichier(fichier)
        except FormatNonReconnu as err:
            echecs.append((fichier, f"lecture impossible : {err}"))
            continue
        if objet.en_octets() != data:
            echecs.append((fichier, "la réécriture n'est pas identique à l'original"))
            continue
        nb_ok += 1
        nb_fragments += isinstance(objet, FragmentXml)
    print(
        f"{len(fichiers)} tables vérifiées : {nb_ok} identiques après relecture/réécriture "
        f"(dont {nb_fragments} fragments XML libres conservés tels quels), {len(echecs)} échecs.",
        file=sortie,
    )
    for fichier, raison in echecs:
        print(f"  ÉCHEC {fichier} : {raison}", file=sortie)
    return 1 if echecs or not fichiers else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="diagauto", description="DiagAuto : outils autour des dossiers LICIEL.")
    sous = parser.add_subparsers(dest="commande", required=True)
    p_inspect = sous.add_parser("inspect", help="résumé d'un dossier LICIEL (lecture seule)")
    p_inspect.add_argument("dossier", type=Path, help="dossier LICIEL, ex. C:\\LICIEL_Diagnostics\\Dossiers_2026\\2610210001")
    p_verif = sous.add_parser("verifier", help="vérifie la relecture/réécriture à l'identique des tables (lecture seule)")
    p_verif.add_argument("chemins", type=Path, nargs="+", help="dossiers ou fichiers Table_*.xml")
    args = parser.parse_args(argv)
    try:
        if args.commande == "inspect":
            return inspecter(args.dossier)
        return verifier(args.chemins)
    except FileNotFoundError as err:
        print(f"Erreur : {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
