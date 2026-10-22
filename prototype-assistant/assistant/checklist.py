"""État « checklist DPE » d'une visite, tenu par NOTRE serveur (docs/02-capture-video.md § 3.6).

C'est ce module, et non l'IA, qui sait ce qui manque : il calcule les champs manquants par
priorité à partir des éléments signalés (vus à l'image ou dits) et des valeurs enregistrées.

Règles :
- une valeur n'existe que si le diagnostiqueur l'a dite : elle est toujours stockée avec sa
  citation et son horodatage (instant dans la vidéo, en secondes) ;
- une valeur redite différemment n'écrase rien : l'historique est gardé et le champ passe
  « à vérifier » (orange à l'écran de validation) ;
- les champs viennent de docs/checklist-dpe.md, réduits au périmètre du prototype ;
- seuls les champs UTILES au DPE sont réclamés (retour de Noah du 22/10/2026) :
  - « principal » : réclamé pour chaque élément (isolation, matériau, vitrage…) ;
  - « secondaire » : demandé une seule fois pour tout le logement (date et température des
    radiateurs, date du ballon), et plus du tout après « je ne sais pas » ;
  - « facultatif » : noté s'il est dit, jamais réclamé (longueur d'un mur, dimensions d'une fenêtre) ;
- hypothèse (à faire valider) : une paroi qui donne sur un local chauffé n'est pas déperditive en
  3CL-2021 ; son matériau, son épaisseur et son isolation ne sont donc pas réclamés.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


class ErreurChecklist(ValueError):
    """Demande invalide (type ou champ inconnu, élément introuvable…)."""


@dataclass(frozen=True)
class Champ:
    cle: str
    libelle: str
    importance: str = "principal"  # « principal », « secondaire » ou « facultatif »

    @property
    def obligatoire(self) -> bool:
        return self.importance == "principal"


@dataclass(frozen=True)
class TypeElement:
    cle: str
    nom: str  # nom affiché : « mur », « fenêtre »…
    prefixe: str  # préfixe des identifiants : M1, F2…
    niveau: str  # « piece » ou « logement »
    champs: tuple[Champ, ...]
    designation: str  # avec article, pour les descriptions par défaut : « la fenêtre »


TYPES: dict[str, TypeElement] = {
    t.cle: t
    for t in (
        # « donne sur » d'abord : sur un local chauffé, le reste de la paroi n'est pas réclamé.
        TypeElement("mur", "mur", "M", "piece", (
            Champ("donne_sur", "donne sur"),
            Champ("materiau", "matériau"),
            Champ("epaisseur", "épaisseur"),
            Champ("isolation", "isolation"),
            Champ("longueur", "longueur", "facultatif"),
        ), "le mur"),
        TypeElement("plafond", "plafond", "PL", "piece", (
            Champ("donne_sur", "donne sur"),
            Champ("isolation", "isolation"),
            Champ("structure", "structure", "facultatif"),
        ), "le plafond"),
        TypeElement("plancher", "plancher", "PB", "piece", (
            Champ("donne_sur", "donne sur"),
            Champ("isolation", "isolation"),
            Champ("structure", "structure", "facultatif"),
        ), "le plancher"),
        TypeElement("fenetre", "fenêtre", "F", "piece", (
            Champ("menuiserie", "menuiserie"),
            Champ("vitrage", "vitrage"),
            Champ("volets", "volets"),
            Champ("dimensions", "dimensions", "facultatif"),
        ), "la fenêtre"),
        TypeElement("porte", "porte extérieure", "PO", "piece", (
            Champ("type", "type"),
            Champ("donne_sur", "donne sur"),
        ), "la porte"),
        TypeElement("emetteur", "émetteur de chauffage", "E", "piece", (
            Champ("type", "type"),
            Champ("temperature", "température", "secondaire"),
            Champ("annee", "année", "secondaire"),
        ), "le radiateur"),
        TypeElement("chauffage", "générateur de chauffage", "CH", "logement", (
            Champ("energie", "énergie"),
            Champ("type", "type"),
            Champ("annee", "année"),
        ), "le chauffage"),
        TypeElement("ecs", "eau chaude sanitaire", "ECS", "logement", (
            Champ("systeme", "système"),
            Champ("energie", "énergie"),
            Champ("annee", "année", "secondaire"),
        ), "l'eau chaude"),
        TypeElement("ventilation", "ventilation", "V", "logement", (
            Champ("type", "type"),
        ), "la ventilation"),
    )
}

PAROIS = ("mur", "plafond", "plancher")
# Présent dans toute pièce, créé automatiquement : on ne demande pas s'il existe.
TOUJOURS_PRESENTS = ("plafond", "plancher")
# Présences à confirmer dans une pièce (le mur est forcément là), puis dans le logement.
PRESENCES_PIECE = ("mur", "fenetre", "emetteur")
PRESENCES_LOGEMENT = ("chauffage", "ecs", "ventilation")
# Pièce par défaut quand un élément de pièce arrive avant qu'une pièce soit nommée.
PIECE_PAR_DEFAUT = "Pièce 1"
VALEUR_INCONNUE = "inconnu"  # « je ne sais pas » : champ rempli (on n'y revient pas) mais à vérifier


def cle_texte(texte: str) -> str:
    """Forme comparable d'un texte : minuscules, sans accents ni espaces superflus."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(sans_accents.lower().split())


def horodatage(t: float) -> str:
    """Instant dans la vidéo au format m:ss."""
    t = max(0, int(round(t)))
    return f"{t // 60}:{t % 60:02d}"


@dataclass
class Valeur:
    valeur: str
    citation: str
    t: float
    note: str = ""  # ex. « deviné : ictérieur → extérieur », montré à la validation


@dataclass
class Element:
    id: str
    type: str
    description: str
    piece: str | None  # None pour un équipement du logement
    t: float
    source: str  # « image » (signalé par l'IA), « voix » (cité par le diagnostiqueur), « auto » (plafond, plancher)
    nombre: int = 1  # éléments identiques décrits ensemble : « trois fenêtres en bois »
    valeurs: dict[str, list[Valeur]] = field(default_factory=dict)
    sans_objet: dict[str, Valeur] = field(default_factory=dict)

    @property
    def type_element(self) -> TypeElement:
        return TYPES[self.type]

    def valeur(self, champ: str) -> Valeur | None:
        historique = self.valeurs.get(champ)
        return historique[-1] if historique else None

    def a_verifier(self, champ: str) -> bool:
        """Vrai si le champ a reçu plusieurs valeurs différentes (correction ou contradiction),
        ou si le diagnostiqueur a dit ne pas savoir."""
        historique = self.valeurs.get(champ, [])
        return len({cle_texte(v.valeur) for v in historique}) > 1 or bool(historique and historique[-1].valeur == VALEUR_INCONNUE)

    def est_rempli(self, champ: str) -> bool:
        return champ in self.sans_objet or bool(self.valeurs.get(champ))

    @property
    def sur_local_chauffe(self) -> bool:
        """Paroi qui donne sur un local chauffé (hypothèse : non déperditive en 3CL-2021)."""
        v = self.valeur("donne_sur")
        return self.type in PAROIS and v is not None and cle_texte(v.valeur).startswith("local chauffe")

    def est_utile(self, champ: str) -> bool:
        """Faut-il connaître ce champ pour le DPE, vu ce qu'on sait déjà de l'élément ?"""
        if self.sur_local_chauffe and champ != "donne_sur":
            return False
        if self.type == "emetteur" and champ == "temperature":
            # Basse / haute température : n'a de sens que pour des émetteurs à eau.
            type_dit = self.valeur("type")
            return type_dit is not None and any(m in cle_texte(type_dit.valeur) for m in ("eau", "plancher chauffant"))
        if self.type == "ecs" and champ == "annee":
            # Date d'un ballon ; une eau chaude faite par la chaudière a la date de la chaudière.
            systeme = self.valeur("systeme")
            return systeme is not None and "chaudiere" not in cle_texte(systeme.valeur)
        return True

    def champs_manquants(self) -> list[Champ]:
        """Champs principaux encore à demander pour cet élément, dans l'ordre."""
        return [c for c in self.type_element.champs if c.obligatoire and self.est_utile(c.cle) and not self.est_rempli(c.cle)]

    def champs_secondaires_manquants(self) -> list[Champ]:
        return [c for c in self.type_element.champs if c.importance == "secondaire" and self.est_utile(c.cle) and not self.est_rempli(c.cle)]


@dataclass
class Piece:
    nom: str
    t: float
    citation: str = ""
    absences: dict[str, Valeur] = field(default_factory=dict)  # type -> « pas de fenêtre » cité
    clos: dict[str, Valeur] = field(default_factory=dict)  # type -> « pas d'autre mur » cité


@dataclass
class Manque:
    """Une information manquante : un champ d'un élément, ou la présence d'un type d'élément."""

    type: str
    piece: str | None
    element: Element | None = None
    champ: Champ | None = None

    @property
    def code(self) -> str:
        if self.element and self.champ:
            return f"{self.element.id}.{self.champ.cle}"
        return f"presence:{self.type}"

    @property
    def libelle(self) -> str:
        if self.element and self.champ:
            return f"{self.element.description} : {self.champ.libelle}"
        if self.type == "mur":
            return "aucun mur décrit"
        return f"{TYPES[self.type].nom} : présence à confirmer"


class Checklist:
    def __init__(self) -> None:
        self.pieces: dict[str, Piece] = {}
        self.elements: list[Element] = []
        self.piece_courante: str | None = None
        self.absences_logement: dict[str, Valeur] = {}  # type -> « pas de VMC » cité
        self._compteurs: dict[str, int] = {}

    # --- Pièces ---------------------------------------------------------------------------

    def definir_piece(self, nom: str, t: float, citation: str = "") -> Piece:
        """Change de pièce. Revenir dans une pièce déjà vue la reprend, sans doublon. Une pièce
        neuve reçoit son plafond et son plancher, toujours présents."""
        nom = " ".join(nom.split())
        if not nom:
            raise ErreurChecklist("nom de pièce vide")
        cle = cle_texte(nom)
        neuve = cle not in self.pieces
        if neuve:
            self.pieces[cle] = Piece(nom=nom[0].upper() + nom[1:], t=t, citation=citation)
        self.piece_courante = cle
        if neuve:
            for type_element in TOUJOURS_PRESENTS:
                self.signaler_element(type_element, TYPES[type_element].designation, t, source="auto")
        return self.pieces[cle]

    def _piece_pour_element(self) -> str:
        if self.piece_courante is None:
            self.definir_piece(PIECE_PAR_DEFAUT, 0.0)
        return self.piece_courante  # type: ignore[return-value]

    def nom_piece(self, cle: str | None) -> str:
        return self.pieces[cle].nom if cle in self.pieces else "Logement"

    def cloturer(self, type_element: str, citation: str, t: float) -> None:
        """« Pas d'autre mur » : la liste de ce type est complète dans la pièce courante."""
        self._type(type_element)
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("clôture refusée : aucune citation du diagnostiqueur")
        self.pieces[self._piece_pour_element()].clos[type_element] = Valeur("complet", citation, t)

    def copier(self, type_element: str, piece_source: str, citation: str, t: float) -> Element:
        """« Plafond pareil que le séjour » : recopie les valeurs de l'élément de l'autre pièce."""
        source = next((e for e in self.elements_de(piece_source) if e.type == type_element), None)
        if source is None or not source.valeurs:
            raise ErreurChecklist(f"rien à recopier : pas de {TYPES[type_element].nom} décrit dans {self.nom_piece(piece_source)}")
        cible = next((e for e in self.elements_de(self._piece_pour_element()) if e.type == type_element), None)
        if cible is None:
            cible = self.signaler_element(type_element, TYPES[type_element].designation, t, source="voix")
        for champ, historique in source.valeurs.items():
            note = f"pareil que {self.nom_piece(piece_source)}"
            self.enregistrer(type_element=type_element, champ=champ, valeur=historique[-1].valeur, citation=citation, t=t,
                             element_id=cible.id, note=note)
        return cible

    # --- Éléments -------------------------------------------------------------------------

    def _type(self, type_element: str) -> TypeElement:
        if type_element not in TYPES:
            raise ErreurChecklist(f"type d'élément inconnu : {type_element!r}")
        return TYPES[type_element]

    def trouver_element(self, element_id: str) -> Element:
        for element in self.elements:
            if element.id == element_id.strip().upper():
                return element
        raise ErreurChecklist(f"élément inconnu : {element_id!r}")

    def elements_de(self, piece: str | None) -> list[Element]:
        return [e for e in self.elements if e.piece == piece]

    def element_de_piece(self, type_element: str, piece: str | None = None) -> Element | None:
        """Le (dernier) élément de ce type dans la pièce, par exemple son plafond."""
        piece = piece if piece is not None else self.piece_courante
        return next((e for e in reversed(self.elements_de(piece)) if e.type == type_element), None)

    @staticmethod
    def _verifier_nombre(nombre: int | None) -> int | None:
        if nombre is None:
            return None
        if not isinstance(nombre, int) or not 1 <= nombre <= 50:
            raise ErreurChecklist(f"nombre d'éléments invalide : {nombre!r}")
        return nombre

    def signaler_element(self, type_element: str, description: str, t: float, source: str = "image", nombre: int | None = None) -> Element:
        """Ajoute un élément à décrire (ex. « le mur avec la télé »), éventuellement en plusieurs
        exemplaires identiques (« trois fenêtres »). Une description déjà connue dans la même pièce
        renvoie l'élément existant ; le plafond et le plancher sont uniques dans une pièce."""
        te = self._type(type_element)
        nombre = self._verifier_nombre(nombre)
        description = " ".join(description.split()) or te.designation
        piece = self._piece_pour_element() if te.niveau == "piece" else None
        for element in self.elements_de(piece):
            if element.type == te.cle and (te.cle in TOUJOURS_PRESENTS or cle_texte(element.description) == cle_texte(description)):
                if nombre:
                    element.nombre = nombre
                return element
        self._compteurs[te.prefixe] = self._compteurs.get(te.prefixe, 0) + 1
        element = Element(
            id=f"{te.prefixe}{self._compteurs[te.prefixe]}",
            type=te.cle,
            description=description,
            piece=piece,
            t=t,
            source=source,
            nombre=nombre or 1,
        )
        self.elements.append(element)
        return element

    def _element_cible(self, type_element: str, element_id: str | None, description: str, t: float, nombre: int | None = None) -> Element:
        if element_id:
            element = self.trouver_element(element_id)
            if element.type != type_element:
                raise ErreurChecklist(f"{element.id} est un {element.type_element.nom}, pas un {TYPES[type_element].nom}")
            if self._verifier_nombre(nombre):
                element.nombre = nombre
            return element
        return self.signaler_element(type_element, description, t, source="voix", nombre=nombre)

    def _champ(self, type_element: str, champ: str) -> Champ:
        for c in self._type(type_element).champs:
            if c.cle == champ:
                return c
        raise ErreurChecklist(f"champ {champ!r} inconnu pour un {TYPES[type_element].nom}")

    def enregistrer(
        self,
        *,
        type_element: str,
        champ: str,
        valeur: str,
        citation: str,
        t: float,
        element_id: str | None = None,
        description: str = "",
        nombre: int | None = None,
        note: str = "",
    ) -> Element:
        """Enregistre une valeur dite par le diagnostiqueur. Sans citation, elle est refusée.
        La même valeur redite n'est pas ajoutée une 2e fois à l'historique."""
        self._champ(type_element, champ)
        valeur = " ".join(valeur.split())
        citation = " ".join(citation.split())
        if not valeur:
            raise ErreurChecklist("valeur vide")
        if not citation:
            raise ErreurChecklist("valeur refusée : aucune citation du diagnostiqueur")
        element = self._element_cible(type_element, element_id, description, t, nombre)
        derniere = element.valeur(champ)
        if derniere is None or cle_texte(derniere.valeur) != cle_texte(valeur):
            element.valeurs.setdefault(champ, []).append(Valeur(valeur, citation, t, note))
        element.sans_objet.pop(champ, None)
        return element

    def marquer_sans_objet(
        self,
        *,
        type_element: str,
        champ: str,
        citation: str,
        t: float,
        element_id: str | None = None,
        description: str = "",
    ) -> None:
        """Champ sans objet pour un élément, ou absence d'un type d'élément (champ « presence »),
        par exemple « pas de fenêtre ici ». Toujours avec citation."""
        te = self._type(type_element)
        citation = " ".join(citation.split())
        if not citation:
            raise ErreurChecklist("« sans objet » refusé : aucune citation du diagnostiqueur")
        if champ == "presence":
            if te.cle == "mur" or te.cle in TOUJOURS_PRESENTS:
                raise ErreurChecklist(f"une pièce a toujours un {te.nom}")
            if te.niveau == "piece":
                self.pieces[self._piece_pour_element()].absences[te.cle] = Valeur("absent", citation, t)
            else:
                self.absences_logement[te.cle] = Valeur("absent", citation, t)
            return
        self._champ(te.cle, champ)
        element = self._element_cible(te.cle, element_id, description, t)
        element.sans_objet[champ] = Valeur("sans objet", citation, t)

    # --- Ce qui manque ---------------------------------------------------------------------

    def _manques_presence(self, types: tuple[str, ...], piece: str | None, absences: dict[str, Valeur]) -> list[Manque]:
        presents = {e.type for e in self.elements_de(piece)}
        return [Manque(type=t, piece=piece) for t in types if t not in presents and t not in absences]

    def manques_piece(self, piece: str | None = None) -> list[Manque]:
        """Manques principaux d'une pièce (la pièce courante par défaut), dans l'ordre du parcours :
        murs, plafond, plancher, fenêtres et portes, émetteurs."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return []
        presences = {m.type: m for m in self._manques_presence(PRESENCES_PIECE, piece, self.pieces[piece].absences)}
        manques: list[Manque] = []
        for type_element in ("mur", "plafond", "plancher", "fenetre", "porte", "emetteur"):
            if type_element in presences:
                manques.append(presences[type_element])
            for element in self.elements_de(piece):
                if element.type == type_element:
                    manques += [Manque(element.type, piece, element, c) for c in element.champs_manquants()]
        return manques

    def manques_logement(self) -> list[Manque]:
        manques: list[Manque] = []
        for type_element in PRESENCES_LOGEMENT:
            elements = [e for e in self.elements_de(None) if e.type == type_element]
            if not elements and type_element not in self.absences_logement:
                manques.append(Manque(type=type_element, piece=None))
            for element in elements:
                manques += [Manque(element.type, None, element, c) for c in element.champs_manquants()]
        return manques

    def manques_secondaires(self) -> dict[tuple[str, str], list[Element]]:
        """Détails secondaires manquants, regroupés pour être demandés une seule fois pour le
        logement : (type, champ) -> éléments concernés."""
        groupes: dict[tuple[str, str], list[Element]] = {}
        for element in self.elements:
            for champ in element.champs_secondaires_manquants():
                groupes.setdefault((element.type, champ.cle), []).append(element)
        return groupes

    def manques_visite(self) -> list[Manque]:
        """Tout ce qui manque : pièce courante d'abord, puis les autres pièces, puis le logement."""
        ordre = [self.piece_courante] if self.piece_courante else []
        ordre += [cle for cle in self.pieces if cle != self.piece_courante]
        manques: list[Manque] = []
        for cle in ordre:
            manques += self.manques_piece(cle)
        return manques + self.manques_logement()

    def piece_terminee(self, piece: str | None = None) -> bool:
        piece = piece if piece is not None else self.piece_courante
        return piece in self.pieces and not self.manques_piece(piece)

    def taux_remplissage(self, piece: str | None = None) -> float:
        """Part des informations utiles attendues dans la pièce qui sont renseignées (0 à 1)."""
        piece = piece if piece is not None else self.piece_courante
        if piece is None or piece not in self.pieces:
            return 0.0
        attendus = len(PRESENCES_PIECE)
        for e in self.elements_de(piece):
            attendus += sum(c.obligatoire and e.est_utile(c.cle) for c in e.type_element.champs)
        return round(1 - len(self.manques_piece(piece)) / attendus, 3) if attendus else 0.0

    # --- Restitution -----------------------------------------------------------------------

    def _ligne_element(self, element: Element) -> str:
        champs = []
        for c in element.type_element.champs:
            v = element.valeur(c.cle)
            if c.cle in element.sans_objet:
                champs.append(f"{c.libelle} = sans objet")
            elif v:
                note = " (déjà demandé, à vérifier plus tard : ne pas redemander)" if element.a_verifier(c.cle) else ""
                champs.append(f"{c.libelle} = {v.valeur}{note}")
            elif not element.est_utile(c.cle):
                champs.append(f"{c.libelle} = inutile pour le DPE")
            elif c.importance == "principal":
                champs.append(f"{c.libelle} = ?")
            elif c.importance == "secondaire":
                champs.append(f"{c.libelle} = ? (secondaire)")
        origine = {"image": "vu à l'image", "auto": "toujours présent"}.get(element.source, "dit")
        nombre = f" ×{element.nombre}" if element.nombre > 1 else ""
        return f"- {element.id} {element.type_element.nom}{nombre} « {element.description} » ({origine}) : " + ", ".join(champs)

    def resume_pour_ia(self, max_manques: int = 12) -> str:
        """État compact envoyé à l'IA à chaque appel (le serveur reste la source de vérité)."""
        lignes: list[str] = []
        if self.piece_courante:
            piece = self.pieces[self.piece_courante]
            lignes.append(f"Pièce courante : {piece.nom} (entrée à {horodatage(piece.t)})")
            elements = self.elements_de(self.piece_courante)
            lignes.append("Éléments de la pièce :" if elements else "Éléments de la pièce : aucun signalé")
            lignes += [self._ligne_element(e) for e in elements]
            absents = ", ".join(TYPES[t].nom for t in piece.absences)
            if absents:
                lignes.append(f"Absents (dit) : {absents}")
            clos = ", ".join(TYPES[t].nom + "s" for t in piece.clos)
            if clos:
                lignes.append(f"Listes complètes (dit) : {clos}")
            manques = self.manques_piece()
            codes = ", ".join(f"{m.code} ({m.libelle})" for m in manques[:max_manques])
            lignes.append(f"Manques de la pièce, par priorité : {codes or 'aucun'}")
        else:
            lignes.append("Pièce courante : pas encore nommée")
        autres = [cle for cle in self.pieces if cle != self.piece_courante]
        for cle in autres:
            manques = self.manques_piece(cle)
            detail = ", ".join(m.code for m in manques[:5]) or "rien"
            lignes.append(f"Autre pièce : {self.pieces[cle].nom} ({round(100 * self.taux_remplissage(cle))} % rempli, manque : {detail})")
        equipements = self.elements_de(None)
        lignes.append("Équipements du logement :" if equipements else "Équipements du logement : aucun signalé")
        lignes += [self._ligne_element(e) for e in equipements]
        manques = self.manques_logement()
        lignes.append("Manques du logement : " + (", ".join(f"{m.code} ({m.libelle})" for m in manques) or "aucun"))
        return "\n".join(lignes)

    def vers_dict(self) -> dict:
        def valeur(v: Valeur) -> dict:
            return {"valeur": v.valeur, "citation": v.citation, "t": round(v.t, 2), "note": v.note}

        def element(e: Element) -> dict:
            return {
                "id": e.id,
                "type": e.type,
                "description": e.description,
                "piece": self.nom_piece(e.piece) if e.piece else None,
                "t": round(e.t, 2),
                "source": e.source,
                "nombre": e.nombre,
                "champs": {
                    c.cle: {
                        "libelle": c.libelle,
                        "importance": c.importance,
                        "utile": e.est_utile(c.cle),
                        "valeur": valeur(e.valeur(c.cle)) if e.valeur(c.cle) else None,
                        "historique": [valeur(v) for v in e.valeurs.get(c.cle, [])],
                        "sans_objet": valeur(e.sans_objet[c.cle]) if c.cle in e.sans_objet else None,
                        "a_verifier": e.a_verifier(c.cle),
                    }
                    for c in e.type_element.champs
                },
            }

        def manque(m: Manque) -> dict:
            return {"code": m.code, "piece": self.nom_piece(m.piece) if m.piece else None, "libelle": m.libelle}

        return {
            "piece_courante": self.nom_piece(self.piece_courante) if self.piece_courante else None,
            "pieces": [
                {
                    "nom": p.nom,
                    "t": round(p.t, 2),
                    "taux_remplissage": self.taux_remplissage(cle),
                    "absences": {t: valeur(v) for t, v in p.absences.items()},
                    "clos": {t: valeur(v) for t, v in p.clos.items()},
                    "elements": [element(e) for e in self.elements_de(cle)],
                    "manques": [manque(m) for m in self.manques_piece(cle)],
                }
                for cle, p in self.pieces.items()
            ],
            "logement": {
                "elements": [element(e) for e in self.elements_de(None)],
                "absences": {t: valeur(v) for t, v in self.absences_logement.items()},
                "manques": [manque(m) for m in self.manques_logement()],
            },
        }
