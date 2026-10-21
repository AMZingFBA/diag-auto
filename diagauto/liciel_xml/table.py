"""Lecture et écriture fidèles des tables XML LICIEL (fichiers ``Table_*.xml``).

Les fichiers LICIEL ressemblent à du XML mais n'en sont pas :

- encodage Windows-1252 ;
- caractères ``&`` et ``<`` non échappés dans les valeurs ;
- une seule fin de ligne par fichier : CR (``\\r``) le plus souvent, parfois LF ;
- indentation de 5 espaces par niveau, ligne vide avant la fermeture d'une fiche ;
- les valeurs peuvent contenir des retours à la ligne (souvent CRLF) et du XML imbriqué.

On ne passe donc pas par une bibliothèque XML : on découpe le texte en suivant
la mise en page exacte produite par LICIEL, et on la reproduit à l'identique.
Toute variation de mise en page lève ``FormatNonReconnu`` plutôt que d'être
corrigée en silence.

Deux formes de table existent :

fiche (une seule ligne de valeurs)::

    <LiTable_Z_Carrez_General>
         <LiColonne_Surface_Carrez>284,20</LiColonne_Surface_Carrez>

    </LiTable_Z_Carrez_General>

liste (plusieurs lignes)::

    <LiTable_General_Pieces_Toutes>
         <LiItem_table_General_Pieces_Toutes>
              <LiColonne_Local>Séjour</LiColonne_Local>
         </LiItem_table_General_Pieces_Toutes>
    </LiTable_General_Pieces_Toutes>
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ENCODAGE = "cp1252"
# Les quelques octets non définis en Windows-1252 (0x81, 0x8D…) sont conservés
# tels quels grâce à « surrogateescape ».
_ERREURS = "surrogateescape"

INDENT = " " * 5
PREFIXE_TABLE = "LiTable_"
PREFIXE_ITEM = "LiItem_table_"
PREFIXE_COLONNE = "LiColonne_"
FINS_DE_LIGNE = ("\r", "\n")

# LICIEL écrit parfois deux fois la même colonne dans une ligne (vu dans un
# ancien dossier DPE). La 2e occurrence est exposée sous « Colonne#2 », la 3e
# sous « Colonne#3 »… et réécrite sous son vrai nom, à sa place d'origine.
SEPARATEUR_DOUBLON = "#"

_RE_RACINE = re.compile(r"<(LiTable_[^<>\s/]*)>")
_RE_NOM_COLONNE = re.compile(r"[^<>\s/#]+")
_RE_CLE_COLONNE = re.compile(r"([^<>\s/#]+)(?:#[0-9]+)?")


class FormatNonReconnu(ValueError):
    """Le contenu ne suit pas la mise en page LICIEL attendue."""


def decoder(data: bytes) -> str:
    """Octets d'un fichier LICIEL -> texte (réversible à l'octet près)."""
    return data.decode(ENCODAGE, _ERREURS)


def encoder(texte: str) -> bytes:
    """Texte -> octets Windows-1252. Lève ValueError si un caractère n'existe pas en Windows-1252."""
    try:
        return texte.encode(ENCODAGE, _ERREURS)
    except UnicodeEncodeError as err:
        car = err.object[err.start : err.end]
        raise ValueError(
            f"caractère {car!r} impossible à écrire en Windows-1252 (encodage des fichiers LICIEL)"
        ) from err


@dataclass
class Table:
    """Une table LICIEL : un nom, et une liste de lignes (colonne -> valeur, dans l'ordre du fichier).

    Les valeurs restent du texte brut, exactement comme dans le fichier
    (virgule décimale, « Vrai »/« Faux », XML imbriqué…). Les noms de colonnes
    sont donnés sans le préfixe ``LiColonne_``.
    """

    nom: str
    lignes: list[dict[str, str]] = field(default_factory=list)
    liste: bool = True
    fin_de_ligne: str = "\r"
    balise_item: str | None = None

    @property
    def balise_racine(self) -> str:
        return PREFIXE_TABLE + self.nom

    @property
    def balise_ligne(self) -> str:
        return self.balise_item or PREFIXE_ITEM + self.nom

    @property
    def fiche(self) -> dict[str, str]:
        """Les colonnes d'une table « fiche » (une seule ligne, sans ``LiItem``)."""
        if self.liste:
            raise TypeError(f"la table {self.nom} est une liste, pas une fiche")
        if not self.lignes:
            self.lignes.append({})
        return self.lignes[0]

    def colonnes(self) -> list[str]:
        """Toutes les colonnes rencontrées, dans l'ordre d'apparition."""
        vues: dict[str, None] = {}
        for ligne in self.lignes:
            for colonne in ligne:
                vues.setdefault(colonne, None)
        return list(vues)

    # --- lecture ---------------------------------------------------------

    @classmethod
    def depuis_octets(cls, data: bytes) -> Table:
        return cls.depuis_texte(decoder(data))

    @classmethod
    def depuis_texte(cls, texte: str) -> Table:
        m = _RE_RACINE.match(texte)
        if not m:
            raise FormatNonReconnu("le fichier ne commence pas par <LiTable_…>")
        racine = m.group(1)
        fermeture = f"</{racine}>"
        if not texte.endswith(fermeture) or len(texte) < m.end() + len(fermeture):
            raise FormatNonReconnu(f"le fichier ne se termine pas par {fermeture}")
        cur = _Curseur(texte, m.end(), len(texte) - len(fermeture))
        nl = cur.fin_de_ligne()
        table = cls(nom=racine[len(PREFIXE_TABLE) :], fin_de_ligne=nl)

        if cur.fini():
            # « <LiTable_X>\r</LiTable_X> » : liste vide.
            table.liste = True
        elif cur.reste_egal(nl) or cur.regarde(INDENT + "<" + PREFIXE_COLONNE):
            table.liste = False
            table.lignes = [_lire_colonnes(cur, INDENT, nl)]
            cur.exige(nl, "ligne vide avant la fermeture de la fiche")
        else:
            table.liste = True
            while not cur.fini():
                cur.exige(INDENT + "<", "début de ligne <LiItem…>")
                balise = cur.jusqua(">", "fin de balise de ligne")
                if not balise.startswith("LiItem"):
                    raise FormatNonReconnu(f"balise de ligne inattendue <{balise}> dans {racine}")
                if table.balise_item is None:
                    table.balise_item = balise
                elif balise != table.balise_item:
                    raise FormatNonReconnu(
                        f"balises de ligne différentes dans {racine} : {table.balise_item} / {balise}"
                    )
                cur.exige(nl, "fin de ligne après <LiItem…>")
                table.lignes.append(_lire_colonnes(cur, INDENT * 2, nl, fin=INDENT + f"</{balise}>"))
                cur.exige(nl, "fin de ligne après </LiItem…>")
            if table.balise_item == PREFIXE_ITEM + table.nom:
                table.balise_item = None
        return table

    # --- écriture --------------------------------------------------------

    def en_texte(self) -> str:
        nl = self.fin_de_ligne
        if nl not in FINS_DE_LIGNE:
            raise ValueError(f"fin de ligne invalide : {nl!r}")
        morceaux = [f"<{self.balise_racine}>", nl]
        if self.liste:
            for ligne in self.lignes:
                morceaux += [INDENT, f"<{self.balise_ligne}>", nl]
                _ecrire_colonnes(morceaux, ligne, INDENT * 2, nl)
                morceaux += [INDENT, f"</{self.balise_ligne}>", nl]
        else:
            if len(self.lignes) > 1:
                raise ValueError(f"la fiche {self.nom} contient {len(self.lignes)} lignes (1 attendue)")
            _ecrire_colonnes(morceaux, self.lignes[0] if self.lignes else {}, INDENT, nl)
            morceaux.append(nl)
        morceaux.append(f"</{self.balise_racine}>")
        return "".join(morceaux)

    def en_octets(self) -> bytes:
        return encoder(self.en_texte())


@dataclass
class FragmentXml:
    """Fichier ``Table_*.xml`` qui n'est pas au format LiTable.

    Exemple : ``Table_Z_DPE_2020_Details_simulations_ERE_SR01.xml`` contient une
    suite d'éléments libres (``<Reco1_Presente>True</Reco1_Presente>…``).
    On le conserve tel quel ; seule une lecture des éléments de premier niveau
    est proposée.
    """

    nom: str
    texte: str

    def elements(self) -> list[tuple[str, str]]:
        """Éléments de premier niveau (balise, contenu brut). Lève FormatNonReconnu si le texte n'est pas une simple suite d'éléments."""
        resultat = []
        cur = _Curseur(self.texte, 0, len(self.texte))
        while not cur.fini():
            cur.exige("<", "début d'élément")
            balise = cur.jusqua(">", "fin de balise")
            resultat.append((balise, cur.jusqua(f"</{balise}>", f"fermeture </{balise}>")))
        return resultat

    def en_octets(self) -> bytes:
        return encoder(self.texte)


# --- fonctions de haut niveau --------------------------------------------


def nom_depuis_fichier(chemin: str | os.PathLike) -> str:
    """``Table_Z_Carrez_Details.xml`` -> ``Z_Carrez_Details``."""
    nom = Path(chemin).name
    if nom.startswith("Table_"):
        nom = nom[len("Table_") :]
    if nom.lower().endswith(".xml"):
        nom = nom[: -len(".xml")]
    return nom


def lire_fichier(chemin: str | os.PathLike) -> Table | FragmentXml:
    """Lit un fichier ``Table_*.xml`` : une ``Table``, ou un ``FragmentXml`` s'il n'est pas au format LiTable."""
    texte = decoder(Path(chemin).read_bytes())
    if texte.startswith("<" + PREFIXE_TABLE):
        return Table.depuis_texte(texte)
    return FragmentXml(nom=nom_depuis_fichier(chemin), texte=texte)


def lire_table(chemin: str | os.PathLike) -> Table:
    """Lit un fichier au format LiTable (lève FormatNonReconnu sinon)."""
    return Table.depuis_octets(Path(chemin).read_bytes())


def ecrire_table(table: Table | FragmentXml, chemin: str | os.PathLike) -> None:
    """Écrit une table à l'octet près (via un fichier temporaire, puis remplacement).

    Attention : ne jamais écrire dans un dossier LICIEL ouvert ni sous
    ``C:\\LICIEL_*`` sans sauvegarde ; cette fonction ne fait aucune vérification
    de ce genre.
    """
    chemin = Path(chemin)
    data = table.en_octets()
    temporaire = chemin.with_name(chemin.name + ".tmp")
    temporaire.write_bytes(data)
    os.replace(temporaire, chemin)


# --- mécanique interne ---------------------------------------------------


class _Curseur:
    """Avance dans le texte en vérifiant la mise en page attendue."""

    def __init__(self, texte: str, debut: int, fin: int):
        self.texte = texte
        self.pos = debut
        self.fin = fin

    def fini(self) -> bool:
        return self.pos == self.fin

    def reste_egal(self, attendu: str) -> bool:
        return self.fin - self.pos == len(attendu) and self.regarde(attendu)

    def regarde(self, attendu: str) -> bool:
        return self.pos + len(attendu) <= self.fin and self.texte.startswith(attendu, self.pos)

    def lit(self, attendu: str) -> bool:
        if self.regarde(attendu):
            self.pos += len(attendu)
            return True
        return False

    def exige(self, attendu: str, quoi: str) -> None:
        if not self.lit(attendu):
            raise FormatNonReconnu(
                f"{quoi} attendu à la position {self.pos} : trouvé {self.texte[self.pos : self.pos + 40]!r}"
            )

    def jusqua(self, marqueur: str, quoi: str) -> str:
        i = self.texte.find(marqueur, self.pos, self.fin)
        if i < 0:
            raise FormatNonReconnu(f"{quoi} introuvable après la position {self.pos}")
        morceau = self.texte[self.pos : i]
        self.pos = i + len(marqueur)
        return morceau

    def fin_de_ligne(self) -> str:
        for nl in FINS_DE_LIGNE:
            if self.lit(nl):
                return nl
        raise FormatNonReconnu("fin de ligne (CR ou LF) attendue après la balise <LiTable_…>")


def _lire_colonnes(cur: _Curseur, indent: str, nl: str, fin: str | None = None) -> dict[str, str]:
    """Lit des colonnes jusqu'à la balise ``fin`` (liste) ou jusqu'à la ligne vide finale (fiche)."""
    ligne: dict[str, str] = {}
    ouverture = indent + "<" + PREFIXE_COLONNE
    while True:
        if fin is not None and cur.lit(fin):
            return ligne
        if fin is None and cur.reste_egal(nl):
            return ligne
        cur.exige(ouverture, "colonne <LiColonne_…>")
        colonne = cur.jusqua(">", "fin de balise de colonne")
        if not _RE_NOM_COLONNE.fullmatch(colonne):
            raise FormatNonReconnu(f"nom de colonne invalide : {colonne!r}")
        cle = colonne
        n = 2
        while cle in ligne:
            cle = f"{colonne}{SEPARATEUR_DOUBLON}{n}"
            n += 1
        ligne[cle] = cur.jusqua(f"</{PREFIXE_COLONNE}{colonne}>", f"fermeture de la colonne {colonne}")
        cur.exige(nl, f"fin de ligne après la colonne {colonne}")


def _ecrire_colonnes(morceaux: list[str], ligne: dict[str, str], indent: str, nl: str) -> None:
    for cle, valeur in ligne.items():
        m = _RE_CLE_COLONNE.fullmatch(cle)
        if not m:
            raise ValueError(f"nom de colonne invalide : {cle!r}")
        colonne = m.group(1)
        fermeture = f"</{PREFIXE_COLONNE}{colonne}>"
        if not isinstance(valeur, str):
            raise TypeError(f"la valeur de {cle} doit être du texte (reçu {type(valeur).__name__})")
        if fermeture in valeur:
            raise ValueError(f"la valeur de {cle} contient sa propre balise de fermeture")
        morceaux += [indent, f"<{PREFIXE_COLONNE}{colonne}>", valeur, fermeture, nl]
