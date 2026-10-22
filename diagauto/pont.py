"""Pont assistant -> LICIEL : la liste des pièces et le métrage Carrez d'une visite, écrits en tables LICIEL.

Entrées :

- l'état d'une visite de l'assistant vocal (``prototype-assistant/sessions/<visite>/etat.json`` : pièces, murs,
  ouvertures, émetteurs), ou mieux, s'il existe, ``etat-consolide.json`` : le même état vu par la carte des pièces de
  la vidéo (``python -m assistant.carte``) : une seule pièce par endroit, pièces revisitées fusionnées ;
- s'il existe, ``mesures.json`` dans le dossier de la visite : les mesures laser ou dictées, validées par le
  diagnostiqueur (pour le Carrez, la mesure laser fait foi) ;
- un dossier LICIEL modèle, lu seulement (le nôtre : 2610210001, créé dans LICIEL par Hermes).

Sortie : un NOUVEAU dossier, jamais sous ``C:\\LICIEL_*`` :

- les tables du modèle, copiées à l'octet près ;
- ``General_Pieces_Toutes`` complétée : les pièces de la visite déjà présentes gardent leur ligne (et leur clé), les
  nouvelles sont ajoutées à la fin ; une pièce du dossier non vue pendant la visite reste telle quelle (signalée) ;
- ``Z_Carrez_Details`` (une ligne par mesure), ``Z_Carrez_Resume`` (une ligne par pièce), ``Z_Carrez_General``
  (totaux) ;
- ``diagauto-pont.json`` : ce qui a été fait, ce qui reste à mesurer, les hypothèses.

Aucune surface n'est inventée : une pièce sans mesure est écrite à 0 m² et signalée « à mesurer ». Le sens des
colonnes Carrez vient des dossiers de démonstration (docs/01-cadrage.md § 1.5) ; les points incertains sont listés
comme hypothèses dans le rapport.
"""

from __future__ import annotations

import json
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .liciel_xml import Table, ecrire_table, lire_fichier, lire_table
from .liciel_xml.valeurs import format_fr

FICHIER_RAPPORT = "diagauto-pont.json"
FICHIER_CONSOLIDE = "etat-consolide.json"  # écrit par la carte des pièces (python -m assistant.carte)
FICHIER_MESURES = "mesures.json"

# Ordre des colonnes relevé dans les dossiers de démonstration LICIEL 4.28 (DEMO_0001 à 0003).
COLONNES_PIECE = ["id_classement_champs", "Lot", "PieceHorsCREP", "PieceExterieure", "ClefComposant", "Batiment",
                  "Local", "Justification", "MoyenAMettreEnOeuvre"]
COLONNES_DETAILS = (["id_classement_champs", "ClefComposantPiece", "ClefComposant", "Localistion",
                     "Surface_1", "Surface_2", "Surface_3", "Surface_4", "Commantaires"]
                    + [f"Data{i}" for i in range(1, 13)]
                    + ["Code_Chk_Habitable", "Code_Outil_Mesure_Type", "Code_Outil_Mesure_Forme", "Code_Outil_Mesure_XML"])
COLONNES_RESUME = ["id_classement_champs", "ClefComposantPiece", "Localistion", "NomLot", "Surface_1", "Surface_2",
                   "Surface_3", "Surface_4", "Commantaires", "Data1", "Data2"]
COLONNES_GENERAL = ["Doc_Remis", "Surface_Carrez", "Surface_Habitable", "Surface_Sol", "Surface_Ref", "HSP"]

HYPOTHESES = {
    "lien": "Tables Carrez reliées à la pièce par le libellé « Bâtiment - Local » (comme dans les démos) et par "
            "ClefComposantPiece = clé de la pièce dans la liste des pièces (hypothèse : les démos, converties d'anciennes "
            "versions, ont des clés différentes).",
    "colonnes": "Surface_1 = Carrez et Surface_3 = habitable (confiance moyenne) : la même valeur est écrite dans les "
                "deux, comme dans toutes les démos ; Surface_2 = au sol (confiance forte) ; Surface_4 = 0.",
    "a_mesurer": "Pièce sans mesure : écrite à 0 m² et hauteur 0 (LICIEL écrit 0 pour une hauteur non saisie). "
                 "À mesurer au laser avant d'éditer le rapport.",
    "hsp": "Hauteur générale = moyenne des hauteurs des pièces pondérée par la surface au sol (pièces sans hauteur et "
           "annexes exclues), 0 si aucune : règle retrouvée sur les 3 démos, à confirmer.",
    "code_chk": "Code_Chk_Habitable = 0 (sens inconnu ; valeur la plus fréquente dans les démos).",
    "doc_remis": "Documents remis (Doc_Remis) laissé vide : à renseigner dans LICIEL (les démos ont « Néant »).",
    "batiment": "Nouvelles pièces rattachées au bâtiment « {batiment} ».",
}


class ErreurPont(ValueError):
    """Entrée refusée : sortie interdite, mesure illisible, pièce inconnue ou ambiguë…"""


# --- petites fonctions -----------------------------------------------------


def nombre_liciel(valeur: float) -> str:
    """Nombre au format des lignes Carrez de LICIEL : 50 -> « 50 », 43.3 -> « 43,3 », -21.1 -> « -21,1 »."""
    valeur = round(valeur, 2)
    if abs(valeur) < 0.005:
        return "0"
    return f"{valeur:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def cle_composant(maintenant: datetime, alea: random.Random) -> str:
    """Clé de composant LICIEL : « AAAA_MM_JJ_hh_mm_ss_ » + 17 chiffres (ex. 2026_10_21_21_58_39_11306320074286620)."""
    return maintenant.strftime("%Y_%m_%d_%H_%M_%S_") + "".join(str(alea.randrange(10)) for _ in range(17))


def _normaliser(nom: str) -> str:
    """« Séjour » et « Sejour », « Chambre  1 » et « chambre 1 » désignent la même pièce."""
    sans_accent = "".join(c for c in unicodedata.normalize("NFD", nom) if unicodedata.category(c) != "Mn")
    return " ".join(sans_accent.lower().split())


def _libelle(batiment: str, local: str) -> str:
    """Libellé LICIEL d'une pièce (voir liciel_xml.dossier.Piece.libelle)."""
    return f"{batiment} - {local}" if batiment else local


def sous_liciel(chemin: Path) -> bool:
    """Vrai si le chemin est dans un dossier « LICIEL_* » (installation ou données de LICIEL : lecture seule)."""
    return any(partie.upper().startswith("LICIEL_") for partie in Path(chemin).resolve().parts)


def derniere_visite(chemin: Path) -> Path:
    """Le dossier d'une visite (contient etat.json), ou la plus récente d'un dossier de sessions."""
    chemin = Path(chemin)
    if (chemin / "etat.json").is_file():
        return chemin
    if not chemin.is_dir():
        raise FileNotFoundError(f"dossier de visite introuvable : {chemin}")
    visites = sorted(d for d in chemin.iterdir() if (d / "etat.json").is_file())
    if not visites:
        raise FileNotFoundError(f"aucune visite (etat.json) dans {chemin}")
    return visites[-1]


# --- mesures ---------------------------------------------------------------


@dataclass
class MesurePiece:
    """Mesures d'une pièce, validées par le diagnostiqueur (laser ou dictées).

    ``surfaces`` : surfaces mesurées (m²), comptées en Carrez et au sol ; ``moins_1m80`` : parties de hauteur inférieure
    à 1,80 m, retirées du Carrez mais gardées au sol ; ``hors_carrez`` : pièce comptée au sol seulement (cave, garage,
    escalier…) ; ``annexe`` : pièce hors des totaux du lot.
    """

    surfaces: list[float] = field(default_factory=list)
    moins_1m80: list[float] = field(default_factory=list)
    hors_carrez: bool = False
    annexe: bool = False
    hsp: float | None = None
    commentaire: str = ""
    source: str = ""

    @property
    def carrez(self) -> float:
        if self.hors_carrez:
            return 0.0
        return round(sum(self.surfaces) - sum(self.moins_1m80), 2)

    @property
    def sol(self) -> float:
        return round(sum(self.surfaces), 2)


def _surface(valeur, quoi: str) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not 0 < valeur < 10000:
        raise ErreurPont(f"{quoi} : surface invalide {valeur!r} (nombre de m² attendu, positif)")
    return float(valeur)


def lire_mesures(donnees: dict) -> dict[str, MesurePiece]:
    """``{"Séjour": {"surfaces": [18.42], "hsp": 2.5, "source": "laser"}, …}`` -> mesures par nom de pièce."""
    mesures: dict[str, MesurePiece] = {}
    for nom, d in donnees.items():
        if not isinstance(d, dict):
            raise ErreurPont(f"mesures de « {nom} » : objet attendu")
        inconnues = set(d) - {"surfaces", "moins_1m80", "hors_carrez", "annexe", "hsp", "commentaire", "source", "citation"}
        if inconnues:
            raise ErreurPont(f"mesures de « {nom} » : champs inconnus {sorted(inconnues)}")
        m = MesurePiece(
            surfaces=[_surface(s, f"« {nom} »") for s in d.get("surfaces", [])],
            moins_1m80=[_surface(s, f"« {nom} », partie < 1,80 m") for s in d.get("moins_1m80", [])],
            hors_carrez=bool(d.get("hors_carrez", False)),
            annexe=bool(d.get("annexe", False)),
            hsp=d.get("hsp"),
            commentaire=str(d.get("commentaire", "")),
            source=str(d.get("source", "")),
        )
        if m.hsp is not None and (isinstance(m.hsp, bool) or not isinstance(m.hsp, (int, float)) or not 1 <= m.hsp <= 15):
            raise ErreurPont(f"« {nom} » : hauteur sous plafond invalide {m.hsp!r} (en mètres)")
        if sum(m.moins_1m80) > sum(m.surfaces) + 0.005:
            raise ErreurPont(f"« {nom} » : la partie de moins de 1,80 m dépasse la surface mesurée")
        mesures[nom] = m
    return mesures


# --- génération -------------------------------------------------------------


@dataclass
class PieceGeneree:
    nom_visite: str  # nom dit pendant la visite (ou dans mesures.json)
    batiment: str
    local: str
    clef: str
    statut: str  # « existante » (déjà dans le dossier) ou « ajoutée »
    vue: bool  # vue pendant la visite
    mesure: MesurePiece | None = None
    elements: dict[str, int] = field(default_factory=dict)
    passages: int = 0  # fois où l'on est entré dans la pièce, d'après la carte (2 ou plus : revisitée)

    @property
    def libelle(self) -> str:
        return _libelle(self.batiment, self.local)


@dataclass
class Rapport:
    visite: Path
    modele: Path
    sortie: Path
    pieces: list[PieceGeneree]
    non_vues: list[str]
    tables_copiees: list[str]
    tables_ecrites: list[str]
    totaux: dict[str, str]
    hypotheses: list[str]
    etat: str = "etat.json"  # fichier d'état lu
    questions: list[str] = field(default_factory=list)  # questions de la carte des pièces, pour le diagnostiqueur

    @property
    def a_mesurer(self) -> list[str]:
        return [p.libelle for p in self.pieces if p.vue and not (p.mesure and p.mesure.surfaces)]

    def en_dict(self) -> dict:
        return {
            "visite": str(self.visite),
            "etat": self.etat,
            "modele": str(self.modele),
            "sortie": str(self.sortie),
            "pieces": [
                {"nom_visite": p.nom_visite, "libelle": p.libelle, "clef": p.clef, "statut": p.statut, "vue": p.vue,
                 "carrez": None if not (p.mesure and p.mesure.surfaces) else p.mesure.carrez,
                 "sol": None if not (p.mesure and p.mesure.surfaces) else p.mesure.sol,
                 "hsp": p.mesure.hsp if p.mesure else None,
                 "source_mesure": p.mesure.source if p.mesure else "",
                 "elements": p.elements, "passages": p.passages}
                for p in self.pieces
            ],
            "a_mesurer": self.a_mesurer,
            "non_vues": self.non_vues,
            "tables_copiees": self.tables_copiees,
            "tables_ecrites": self.tables_ecrites,
            "totaux": self.totaux,
            "hypotheses": self.hypotheses,
            "questions": self.questions,
        }

    def en_texte(self) -> str:
        etat = ("état consolidé par la carte des pièces de la vidéo" if self.etat == FICHIER_CONSOLIDE
                else "état de l'assistant (carte des pièces non calculée)")
        lignes = [f"Visite : {self.visite} ({etat})", f"Modèle : {self.modele} (lu seulement)", f"Sortie : {self.sortie}", ""]
        lignes.append(f"Pièces ({len(self.pieces)}) :")
        for p in self.pieces:
            m = p.mesure
            if m and m.surfaces:
                carrez = f"Carrez {format_fr(m.carrez)} m², sol {format_fr(m.sol)} m²"
            else:
                carrez = "À MESURER" if p.vue else "non vue pendant la visite"
            elements = ", ".join(f"{n} {_PLURIELS.get(t, t) if n > 1 else t}" for t, n in p.elements.items() if n)
            revisite = f" ; revisitée ({p.passages} passages)" if p.passages > 1 else ""
            lignes.append(f"  - {p.libelle} [{p.statut}] : {carrez}" + (f" ; vu : {elements}" if elements else "") + revisite)
        if self.non_vues:
            lignes.append(f"Pièces du dossier non vues pendant la visite (laissées telles quelles) : {', '.join(self.non_vues)}")
        hauteur = f"{self.totaux['HSP']} m" if self.totaux["HSP"] != "0" else "non renseignée"
        lignes.append(f"Totaux Carrez : Carrez {self.totaux['Surface_Carrez']} m², habitable {self.totaux['Surface_Habitable']} m², "
                      f"au sol {self.totaux['Surface_Sol']} m², hauteur {hauteur}")
        lignes.append(f"Tables écrites : {', '.join(self.tables_ecrites)} ; copiées telles quelles : {len(self.tables_copiees)}")
        lignes.append("Hypothèses :")
        lignes += [f"  - {h}" for h in self.hypotheses]
        if self.questions:
            lignes.append("Questions de la carte des pièces (à trancher par le diagnostiqueur) :")
            lignes += [f"  - {q}" for q in self.questions]
        return "\n".join(lignes)


_TYPES_RAPPORT = {"mur": "mur", "fenetre": "fenêtre", "porte": "porte", "emetteur": "émetteur"}
_PLURIELS = {"mur": "murs", "fenêtre": "fenêtres", "porte": "portes", "émetteur": "émetteurs"}


def _elements(piece: dict) -> dict[str, int]:
    """Murs, ouvertures et émetteurs vus dans la pièce (pour le rapport ; le DPE est l'étape suivante)."""
    compte = {nom: 0 for nom in _TYPES_RAPPORT.values()}
    for e in piece.get("elements", []):
        nom = _TYPES_RAPPORT.get(e.get("type"))
        if nom:
            compte[nom] += e.get("nombre") or 1
    return compte


def _preparer_sortie(sortie: Path, modele: Path) -> Path:
    """Vérifie que la sortie est permise et la vide de nos anciennes tables. Renvoie le dossier XML de sortie."""
    if sous_liciel(sortie):
        raise ErreurPont(f"écriture refusée sous un dossier LICIEL_* : {sortie} (lecture seule ; les essais dans LICIEL "
                         "sont faits par Hermes sur un dossier jetable)")
    sortie_r, modele_r = sortie.resolve(), modele.resolve()
    if sortie_r == modele_r or modele_r in sortie_r.parents or sortie_r in modele_r.parents:
        raise ErreurPont(f"la sortie {sortie} ne doit ni contenir le modèle ni être dedans")
    xml = sortie / "XML"
    if sortie.exists() and any(sortie.iterdir()):
        if not (sortie / FICHIER_RAPPORT).is_file():
            raise ErreurPont(f"le dossier de sortie {sortie} existe déjà et n'a pas été créé par « diagauto generer »")
        for ancien in xml.glob("Table_*.xml"):
            ancien.unlink()
    xml.mkdir(parents=True, exist_ok=True)
    return xml


def _trouver(nom: str, lignes: list[dict[str, str]]) -> int | None:
    """Ligne de la liste des pièces qui porte ce nom (« Séjour » ou « Appartement - Séjour »), ou None."""
    cle = _normaliser(nom)
    complets = [i for i, l in enumerate(lignes) if _normaliser(_libelle(l.get("Batiment", ""), l.get("Local", ""))) == cle]
    if complets:
        return complets[0]
    locaux = [i for i, l in enumerate(lignes) if _normaliser(l.get("Local", "")) == cle]
    if len(locaux) > 1:
        candidats = ", ".join(_libelle(lignes[i].get("Batiment", ""), lignes[i]["Local"]) for i in locaux)
        raise ErreurPont(f"« {nom} » est ambigu dans le dossier ({candidats}) : préciser « Bâtiment - Pièce »")
    return locaux[0] if locaux else None


def generer(visite: Path, modele: Path, sortie: Path, mesures: Path | None = None, batiment: str | None = None,
            maintenant: datetime | None = None, alea: random.Random | None = None) -> Rapport:
    """Écrit dans ``sortie`` le dossier LICIEL de la visite, à partir du dossier ``modele`` (lu seulement)."""
    visite, modele, sortie = derniere_visite(Path(visite)), Path(modele), Path(sortie)
    maintenant = maintenant or datetime.now()
    alea = alea or random.Random()
    xml_modele = modele / "XML" if (modele / "XML").is_dir() else modele
    if not xml_modele.is_dir():
        raise FileNotFoundError(f"dossier LICIEL modèle introuvable : {modele}")
    fichier_etat = FICHIER_CONSOLIDE if (visite / FICHIER_CONSOLIDE).is_file() else "etat.json"
    etat = _lire_json(visite / fichier_etat)
    chemin_mesures = Path(mesures) if mesures else visite / FICHIER_MESURES
    if mesures and not chemin_mesures.is_file():
        raise FileNotFoundError(f"fichier de mesures introuvable : {chemin_mesures}")
    toutes_mesures = lire_mesures(_lire_json(chemin_mesures) if chemin_mesures.is_file() else {})

    # Liste des pièces : celle du modèle, complétée.
    fichier_pieces = xml_modele / "Table_General_Pieces_Toutes.xml"
    pieces = lire_table(fichier_pieces) if fichier_pieces.is_file() else Table("General_Pieces_Toutes")
    lignes = [dict(l) for l in pieces.lignes]
    colonnes = list(lignes[0]) if lignes else COLONNES_PIECE
    batiments = sorted({l.get("Batiment", "") for l in lignes})
    hypotheses = [HYPOTHESES["lien"], HYPOTHESES["colonnes"]]
    cles = {l.get("ClefComposant", "") for l in lignes}

    def batiment_des_nouvelles() -> str:
        """Bâtiment d'une pièce ajoutée : celui demandé, sinon le seul du dossier."""
        if batiment is not None:
            return batiment
        if len(batiments) > 1:
            raise ErreurPont(f"le dossier a plusieurs bâtiments ({', '.join(batiments)}) : préciser --batiment")
        return batiments[0] if batiments else ""

    def nouvelle_cle() -> str:
        while (cle := cle_composant(maintenant, alea)) in cles:
            pass
        cles.add(cle)
        return cle

    generees: dict[int, PieceGeneree] = {}
    for p in etat.get("pieces", []):
        nom = p["nom"]
        i = _trouver(nom, lignes)
        if i is None:
            ligne = {c: "" for c in colonnes}
            ligne.update(ClefComposant=nouvelle_cle(), Batiment=batiment_des_nouvelles(), Local=nom)
            lignes.append(ligne)
            i = len(lignes) - 1
            statut = "ajoutée"
        else:
            statut = "existante"
        if i in generees:  # deux noms de la visite pour la même pièce du dossier
            generees[i].elements = {t: n + _elements(p)[t] for t, n in generees[i].elements.items()}
            continue
        generees[i] = PieceGeneree(nom, lignes[i].get("Batiment", ""), lignes[i]["Local"], lignes[i]["ClefComposant"],
                                   statut, vue=True, elements=_elements(p),
                                   passages=(p.get("carte") or {}).get("sejours") or 0)
    if any(g.statut == "ajoutée" for g in generees.values()) and batiment_des_nouvelles():
        hypotheses.append(HYPOTHESES["batiment"].format(batiment=batiment_des_nouvelles()))
    for nom, mesure in toutes_mesures.items():
        i = _trouver(nom, lignes)
        if i is None:
            raise ErreurPont(f"mesures pour « {nom} » : pièce ni vue pendant la visite ni présente dans le dossier")
        if i not in generees:
            generees[i] = PieceGeneree(nom, lignes[i].get("Batiment", ""), lignes[i]["Local"], lignes[i]["ClefComposant"],
                                       "existante", vue=False)
        generees[i].mesure = mesure
    for n, ligne in enumerate(lignes):
        if "id_classement_champs" in ligne:
            ligne["id_classement_champs"] = f"{n:05d}"
    pieces_sortie = Table("General_Pieces_Toutes", lignes, liste=True, fin_de_ligne=pieces.fin_de_ligne,
                          balise_item=pieces.balise_item)
    ordre = [generees[i] for i in sorted(generees)]  # ordre de la liste des pièces
    non_vues = [_libelle(l.get("Batiment", ""), l.get("Local", "")) for i, l in enumerate(lignes) if i not in generees]

    # Carrez.
    nl = pieces.fin_de_ligne
    details, resume = [], []
    for p in ordre:
        m = p.mesure or MesurePiece()
        for s in m.surfaces:
            carrez = "0" if m.hors_carrez else nombre_liciel(s)
            details.append(_ligne_details(p, len(details), nouvelle_cle(), carrez, nombre_liciel(s), "Vrai", "Faux",
                                          "0" if m.hors_carrez else "1", "1", s))
        if not m.hors_carrez:
            for r in m.moins_1m80:
                details.append(_ligne_details(p, len(details), nouvelle_cle(), nombre_liciel(-r), "0", "Faux", "Vrai",
                                              "1", "0", r))
        resume.append(dict(zip(COLONNES_RESUME, [
            f"{len(resume):05d}", p.clef, p.libelle, "", nombre_liciel(m.carrez), nombre_liciel(m.sol),
            nombre_liciel(m.carrez), "0", m.commentaire, nombre_liciel(m.hsp or 0), "OUI" if m.annexe else "",
        ])))
    comptees = [p.mesure for p in ordre if p.mesure and not p.mesure.annexe]
    carrez_total = sum(m.carrez for m in comptees)
    sol_total = sum(m.sol for m in comptees)
    avec_hauteur = [m for m in comptees if m.hsp and m.sol]
    poids = sum(m.sol for m in avec_hauteur)
    hsp = sum(m.hsp * m.sol for m in avec_hauteur) / poids if poids else 0
    totaux = dict(zip(COLONNES_GENERAL, ["", format_fr(carrez_total), format_fr(carrez_total), format_fr(sol_total),
                                         format_fr(0), format_fr(hsp) if hsp else "0"]))
    if any(p.vue and not (p.mesure and p.mesure.surfaces) for p in ordre):
        hypotheses.append(HYPOTHESES["a_mesurer"])
    hypotheses += [HYPOTHESES["hsp"], HYPOTHESES["code_chk"], HYPOTHESES["doc_remis"]]
    nouvelles = [
        pieces_sortie,
        Table("Z_Carrez_Details", details, liste=True, fin_de_ligne=nl),
        Table("Z_Carrez_Resume", resume, liste=True, fin_de_ligne=nl),
        Table("Z_Carrez_General", [totaux], liste=False, fin_de_ligne=nl),
    ]
    # Liste des pièces visitées : complétée seulement si le modèle l'a (notre dossier de test ne l'a pas ; LICIEL la
    # remplit-il seul ? question E2 de docs/01-cadrage.md § 3).
    fichier_visites = xml_modele / "Table_General_Pieces_Visites.xml"
    ajoutees = [p.libelle for p in ordre if p.statut == "ajoutée"]
    if ajoutees and fichier_visites.is_file():
        visites = lire_table(fichier_visites)
        nouvelles.append(Table(visites.nom, visites.lignes + [{"Pieces": libelle} for libelle in ajoutees], liste=True,
                               fin_de_ligne=visites.fin_de_ligne, balise_item=visites.balise_item))

    # Écriture : tables du modèle copiées à l'octet près, puis les nôtres. Tout est encodé avant de toucher au disque.
    for table in nouvelles:
        try:
            table.en_octets()
        except ValueError as err:  # ex. un nom de pièce avec un caractère absent de Windows-1252
            raise ErreurPont(f"Table_{table.nom}.xml : {err}") from err
    xml = _preparer_sortie(sortie, modele)
    ecrites = {t.nom for t in nouvelles}
    copiees = []
    for fichier in sorted(xml_modele.glob("Table_*.xml")):
        nom = fichier.stem[len("Table_"):]
        if nom not in ecrites:
            (xml / fichier.name).write_bytes(fichier.read_bytes())
            copiees.append(nom)
    for table in nouvelles:
        ecrire_table(table, xml / f"Table_{table.nom}.xml")
        relue = lire_fichier(xml / f"Table_{table.nom}.xml")
        if relue.en_octets() != table.en_octets():  # garde-fou : l'écrivain doit relire ce qu'il a écrit
            raise ErreurPont(f"Table_{table.nom}.xml : relecture différente de l'écriture")
    # Questions de la carte, et éléments notés dans une pièce mais filmés dans une autre (comptés là où ils ont été notés).
    questions = list((etat.get("carte") or {}).get("questions") or [])
    for p in etat.get("pieces") or []:
        for e in p.get("elements") or []:
            if (e.get("carte") or {}).get("a_verifier"):
                questions.append(f"{e.get('description') or e['id']} ({e['id']}) : {e['carte']['a_verifier']} : "
                                 "dans quelle pièce ?")
    rapport = Rapport(visite, modele, sortie, ordre, non_vues, copiees, [t.nom for t in nouvelles], totaux, hypotheses,
                      fichier_etat, questions)
    (sortie / FICHIER_RAPPORT).write_text(json.dumps(rapport.en_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return rapport


def _lire_json(chemin: Path):
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except ValueError as err:
        raise ErreurPont(f"{chemin} illisible : {err}") from err


def _ligne_details(piece: PieceGeneree, n: int, cle: str, carrez: str, sol: str, ajouter: str, retrancher: str,
                   compte_carrez: str, compte_sol: str, saisie: float) -> dict[str, str]:
    """Une opération de mesure (docs/01-cadrage.md § 1.5) : Data1/Data2 ajouter/retrancher, Data3/Data4 compte en
    Carrez/au sol, Data5 valeur saisie (positive)."""
    valeurs = [f"{n:05d}", piece.clef, cle, piece.libelle, carrez, sol, carrez, "0", "",
               ajouter, retrancher, compte_carrez, compte_sol, nombre_liciel(saisie), "", "0", "0", "0", "", "", "",
               "0", "", "", ""]
    return dict(zip(COLONNES_DETAILS, valeurs))

