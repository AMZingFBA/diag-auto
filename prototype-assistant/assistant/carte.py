"""Carte des pièces d'une visite filmée (étape 12) : pièces revisitées et phrases rattachées au mur visé.

À partir de la vidéo continue (ou, à défaut, des images envoyées pendant la visite, une par seconde), sur le serveur,
sans GPU, pour tout téléphone :

1. **Suivi continu du mouvement** : les points de l'image sont suivis d'une image à la suivante (pas une photo toutes
   les n secondes). On sait ainsi quand la caméra tourne sur place, quand elle avance, quand le suivi décroche.
2. **Images clés** choisies par le mouvement : une nouvelle dès que la vue a assez glissé ou avancé.
3. **Stations** : suites d'images clés où le diagnostiqueur tourne sur place, suivi tenu. Une station est forcément
   dans une seule pièce.
4. **Reconnaissance de lieu** : chaque image clé est comparée aux images qui lui ressemblent le plus (mots visuels),
   puis la ressemblance est **vérifiée par la géométrie** (mêmes points, même déplacement de caméra).
5. **Pièces** : dans l'ordre du temps, chaque station rejoint la pièce qu'elle reconnaît nettement, sinon la pièce
   annoncée par le diagnostiqueur, sinon reste dans la pièce en cours, **sauf s'il a marché** (on ne change pas de pièce
   en tournant sur place). Une pièce est un ensemble d'endroits, pas un morceau de vidéo : une revisite rejoint la pièce
   déjà vue, même quand l'assistant se croyait ailleurs. Jamais deux pièces pour le même endroit reconnu.
   Une image clé n'est **ancrée** (sûre) que si l'image la relie, de proche en proche, au début de sa pièce. Les autres
   ne tiennent leur pièce que du nom dit, qui retarde sur la porte (la pièce est annoncée jusqu'à ~15 s après y être
   entré) et peut être faux pendant des minutes (retour non annoncé).
6. **Arbitrage par Claude** (le seul cerveau du projet) : les passages non ancrés sont montrés à Claude (une image
   toutes les 8 s, toutes les 2 s juste avant l'annonce d'une autre pièce), avec des images ancrées de chaque pièce ; il
   dit dans quelle pièce on est. Une autre pièce vue par Claude devient une question, jamais une pièce créée.
7. **Cap de la caméra** : boussole et gyroscope du téléphone s'ils ont été enregistrés, sinon le suivi continu de la
   vidéo (cap relatif : les murs sont alors « A, B, C, D », pas « nord, est… »).
8. **Ancrage** : chaque phrase est rattachée, à l'instant du mot qui désigne (« ce mur », « le mur de gauche »,
   « derrière moi », « le deuxième mur »), à la pièce reconnue et au mur visé, puis comparée à l'élément choisi par
   l'assistant pendant la visite.

Étape 13 (DPE par côté) : avec la boussole, l'axe des murs est celui du **logement** (les murs des pièces sont
parallèles), estimé sur toutes les pièces : il ne dépend plus des quelques images d'une pièce. Un logement tourné de
près de 45° par rapport au nord (côté d'un mur incertain) devient une question. Les murs et fenêtres de l'état de
l'assistant sont ceux du logement (« enveloppe ») : chacun reçoit ce que la carte en a vu (pièce, mur, côté filmé), et
un côté filmé différent du côté noté devient une question.

Ce n'est pas encore une carte 3D métrique (pas de plan coté ni de surfaces) : c'est une carte des lieux (quelles images
montrent le même endroit), suffisante pour les pièces, les revisites et les murs. Voir le README, « Étape 12 ».

Usage : ``python -m assistant.carte [dossier de visite] [--sans-claude]`` écrit dans le dossier de la visite
``carte.json``, ``carte.md`` et ``etat-consolide.json`` (l'état de l'assistant avec une seule pièce par endroit et les
murs nommés par repère et cap), que ``diagauto generer`` utilise.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import bisect
import copy
import json
import math
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .boussole import Boussole, Mesure, ecart, mediane_circulaire, point_cardinal
from .vision import Lien, Mouvement, Vocabulaire, Vue, decrire, lacet_relatif, lire_images, lire_video, suivre, verifier

# --- Réglages (choisis sur la vidéo de synthèse, video-001 et la visite de Noah ; voir le README) --------------------

FPS_MAX = 30.0  # suivi continu : toutes les images d'une vidéo de téléphone (30 par seconde)
FPS_SUIVI = 5.0  # en dessous (images à 1/s), le suivi image à image ne mesure pas le cap
CLE_GLISSEMENT = 0.30  # nouvelle image clé quand la vue a glissé de 30 % de sa largeur
CLE_AVANCEE = 0.12  # … ou quand la caméra a avancé (la scène a grossi de 12 %)
ROTATION_AVANCEE = 0.06  # entre deux images clés, moins de 6 % d'avancée : la caméra a tourné sur place
VOISINS = 3  # images clés voisines dans le temps, toujours comparées entre elles
CANDIDATS = 12  # images clés les plus ressemblantes (mots visuels) vérifiées par la géométrie
LIEN_MIN = 35  # points communs vérifiés pour un même lieu (hasard, ou même fenêtre ou même porte dans deux pièces : ~30 au plus)
LIENS_FUSION = 2  # liens distincts vers une pièce pour dire qu'on y est
LIENS_FORTS = 4  # au-delà, l'image l'emporte sur le nom dit (retour non annoncé dans une pièce)
ANCRAGE_MIN = 2  # liens d'une station vers des images clés ancrées de sa pièce pour l'ancrer à son tour
ANCRAGE_DEBUT_S = 10.0  # début de chaque pièce, ancré d'office : on y est entré en l'annonçant (court : on peut en
# ressortir vite sans le dire)
MARCHE_AVANCEE = 0.35  # avancée nette (log du grossissement) qui montre qu'on a marché
MARCHE_AVEUGLE_S = 2.0  # suivi perdu plus longtemps : on a pu changer de pièce sans le voir
PASSAGE_MAX_S = 4.0  # un lieu non nommé vu moins longtemps est un passage (porte, couloir entrevu), pas une pièce
DOUTE_MIN_S = 3.0  # passage non reconnu montré à Claude à partir de cette durée
RETARD_NOM_S = 20.0  # la pièce est dite jusqu'à ~15 s après la porte : passages montrés à Claude en premier
REFERENCES_PAR_PIECE = 6  # images ancrées de chaque pièce montrées à Claude, réparties dans le temps
IMAGE_TOUTES_S = 8.0  # images d'un passage montrées à Claude : une toutes les 8 s (deux au moins), chacune jugée à part
IMAGE_PORTE_S = 2.0  # une toutes les 2 s juste avant l'annonce d'une autre pièce : la porte est là, quelque part
DOUTES_PAR_APPEL = 32  # images douteuses montrées à Claude en un appel
DOUTES_MAX = 96  # au plus trois appels par visite
FOCALE_PORTRAIT, FOCALE_PAYSAGE = 1.2, 0.85  # focale en largeurs d'image (téléphone sans réglage connu)
LETTRES = "ABCD"
AXE_LOGEMENT = 0.6  # une pièce prend l'axe du logement si ses caps l'expliquent à 60 % au moins de son meilleur axe
AXE_DOUTE = 10.0  # murs à moins de 10° d'une diagonale (nord-est…) : leur côté est à confirmer

DESIGNATION = re.compile(
    r"\b(?:ce|cet|cette|ces|celui|celle|ceux|celles)\b(?:[- ]?(?:ci|là|la))?|\b(?:ici|là)\b|\bça\b", re.IGNORECASE)
# « Le mur de gauche », « sur ma droite », « celui derrière moi », « en face » : un mur désigné par sa place par rapport
# à la caméra (« ça donne derrière sur des toilettes » n'en est pas un).
POSITION = re.compile(r"\b(?:(?:de|à|a|sur (?:la|ma)|vers (?:la|ma))\s+(gauche|droite)|(?:de|le mur|celui|juste)\s+(derri[eè]re)"
                      r"|(derri[eè]re) moi|(?:d'en|en)\s+(face)|du (fond))\b", re.IGNORECASE)
DECALAGES = {"gauche": -90.0, "droite": 90.0, "derriere": 180.0, "face": 0.0, "fond": 0.0}
# « Le deuxième mur » : le deuxième montré dans la pièce (comme pendant la visite, voir Element.voir_dans).
ORDINAL = re.compile(r"\b(premier|1er|deuxi[eè]me|second|2e|2[eè]me|troisi[eè]me|3e|3[eè]me|quatri[eè]me|4e|4[eè]me"
                     r"|cinqui[eè]me|5e|5[eè]me)\s+mur\b", re.IGNORECASE)
RANGS = {"premier": 1, "1er": 1, "deuxieme": 2, "second": 2, "2e": 2, "2eme": 2, "troisieme": 3, "3e": 3, "3eme": 3,
         "quatrieme": 4, "4e": 4, "4eme": 4, "cinquieme": 5, "5e": 5, "5eme": 5}


# --- Entrées --------------------------------------------------------------------------------------------------------


@dataclass
class Phrase:
    t_debut: float
    t_fin: float
    texte: str
    elements: list[str] = field(default_factory=list)  # éléments choisis par l'assistant pour cette phrase
    estimee: bool = False  # instants estimés (anciennes visites : seul l'instant de traitement était noté)


@dataclass
class Entrees:
    vues: list[Vue]
    source: str  # « vidéo » ou « images (1 par seconde) »
    capteurs: list[Mesure] = field(default_factory=list)
    noms: list[tuple[float, str]] = field(default_factory=list)  # (instant, pièce où l'assistant se croyait)
    phrases: list[Phrase] = field(default_factory=list)
    etat: dict | None = None


def _normaliser(nom: str) -> str:
    sans_accent = "".join(c for c in unicodedata.normalize("NFD", nom) if unicodedata.category(c) != "Mn")
    return " ".join(sans_accent.lower().split())


def lire_capteurs(dossier: Path) -> list[Mesure]:
    """Capteurs du téléphone : le relevé continu envoyé en fin de visite, sinon celui reçu en direct (1 par seconde)."""
    continus = dossier / "capteurs-continus.json"
    if continus.is_file():
        brut = json.loads(continus.read_text(encoding="utf-8"))
        lignes = brut.get("mesures", []) if isinstance(brut, dict) else brut
    elif (dossier / "capteurs.jsonl").is_file():
        lignes = [json.loads(l) for l in (dossier / "capteurs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        return []

    def nombre(d: dict, cle: str) -> float | None:
        v = d.get(cle)
        return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None

    mesures = []
    for d in lignes:
        if isinstance(d, dict) and isinstance(d.get("t"), (int, float)):
            cap, lacet = nombre(d, "cap"), nombre(d, "lacet")
            mesures.append(Mesure(float(d["t"]), None if cap is None else cap % 360, None if lacet is None else lacet % 360,
                                  nombre(d, "precision"), nombre(d, "inclinaison")))
    return sorted(mesures, key=lambda m: m.t)


def lire_journal(dossier: Path) -> tuple[list[tuple[float, str]], list[Phrase]]:
    """Pièce où l'assistant se croyait (début de visite, changements acceptés) et phrases avec leurs éléments."""
    noms: list[tuple[float, str]] = []
    phrases: list[Phrase] = []
    fichier = dossier / "journal.jsonl"
    if not fichier.is_file():
        return noms, phrases
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        e = json.loads(ligne)
        if e.get("evenement") == "debut" and str(e.get("piece") or "").strip():
            noms.append((0.0, e["piece"].strip()))
        for r in e.get("resultats") or []:
            action = r.get("action") or {}
            if action.get("outil") == "piece_courante" and r.get("statut") == "accepte" and action.get("nom"):
                noms.append((float(e["t"]), str(action["nom"]).strip()))
        if e.get("evenement") == "extraction" and re.search(r"\w", e.get("texte", "")):
            elements = list(dict.fromkeys(r["element"] for r in e.get("resultats") or []
                                          if r.get("statut") == "accepte" and r.get("element")))
            if "t_debut" in e and "t_fin" in e:
                phrases.append(Phrase(float(e["t_debut"]), float(e["t_fin"]), e["texte"], elements))
            else:
                # Anciennes visites : seul l'instant de traitement est noté. La phrase a commencé avant, d'autant plus
                # tôt qu'elle est longue (environ 2,5 mots par seconde).
                fin = float(e["t"]) - 0.3
                phrases.append(Phrase(max(0.0, fin - len(e["texte"].split()) / 2.5), fin, e["texte"], elements, estimee=True))
        elif e.get("evenement") == "decision" and phrases:
            for r in e.get("resultats") or []:
                if r.get("statut") == "accepte" and r.get("element") and r["element"] not in phrases[-1].elements:
                    phrases[-1].elements.append(r["element"])
    return sorted(noms), phrases


def charger_visite(dossier: Path, fps_max: float = FPS_MAX) -> Entrees:
    """Vidéo complète de la visite si elle a été envoyée, sinon les images reçues pendant la visite."""
    video = next((v for v in (dossier / f"video{x}" for x in (".mp4", ".webm", ".mov")) if v.is_file()), None)
    if video is not None:
        vues, _ = lire_video(video, fps_max)
        source = f"vidéo continue ({video.name})"
    else:
        vues = lire_images(dossier / "images")
        source = "images envoyées pendant la visite (1 par seconde ; la vidéo complète n'a pas été envoyée)"
    noms, phrases = lire_journal(dossier)
    etat_fichier = dossier / "etat.json"
    etat = json.loads(etat_fichier.read_text(encoding="utf-8")) if etat_fichier.is_file() else None
    # Une pièce créée sans changement de pièce noté au journal (« Pièce 1 », créée d'office au début d'une visite
    # commencée sans nom) : son nom vaut à partir de sa création.
    dits = {_normaliser(nom) for _, nom in noms}
    for piece in (etat or {}).get("pieces", []):
        if piece.get("nom") and _normaliser(piece["nom"]) not in dits and isinstance(piece.get("t"), (int, float)):
            noms.append((float(piece["t"]), piece["nom"]))
    return Entrees(vues, source, lire_capteurs(dossier), sorted(noms), phrases, etat)


# --- Arbitrage des passages non reconnus ----------------------------------------------------------------------------


@dataclass
class Doute:
    """Un passage que la géométrie n'a pas reconnu : la pièce vient seulement du nom dit ou de la continuité."""

    numero: int
    debut: float
    fin: float
    piece: str | None  # pièce retenue sans preuve visuelle
    images: list[Vue]
    cles: list[int] = field(default_factory=list)  # images clés du passage


@dataclass
class Verdict:
    numero: int
    piece: str | None  # une pièce connue, ou None : autre pièce (nouvelle)
    type: str = ""  # pour une nouvelle pièce : « couloir », « chambre »…
    confiance: str = "faible"  # « forte », « moyenne » ou « faible »
    raison: str = ""


Arbitre = Callable[[dict[str, list[Vue]], list[Doute]], list[Verdict]]


# --- Résultat -------------------------------------------------------------------------------------------------------


@dataclass
class Mur:
    id: str  # « Séjour · ouest » (boussole) ou « Séjour · mur B » (cap relatif)
    piece: str
    nom: str  # « ouest » ou « mur B »
    cap: float  # direction de la caméra qui le regarde de face, depuis la pièce
    vu: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class PieceCarte:
    nom: str
    nommee: bool  # nom dit par le diagnostiqueur (sinon « Pièce non nommée n », à confirmer)
    passages: list[tuple[float, float]]
    images_cles: int
    axe: float | None = None  # orientation des murs, si le cap est connu
    corrections: list[str] = field(default_factory=list)
    sejours: int = 1  # fois où l'on y est entré (sorti vers une autre pièce, puis revenu)

    @property
    def revisitee(self) -> bool:
        return self.sejours > 1


@dataclass
class Ancrage:
    t: float  # instant du mot qui désigne (ou milieu de la phrase)
    texte: str
    designation: bool
    piece: str | None
    cap: float | None
    mur: str | None
    elements: list[str]
    accord: str  # « oui », « non : … », « sans objet »
    par: str = ""  # les mots qui désignent : « ce mur », « le mur de gauche », « le deuxième mur »


@dataclass
class Carte:
    source: str
    duree_s: float
    images: int
    images_cles: int
    suivi: float  # part des images où le suivi continu a tenu
    stations: int
    liens: int
    cap: str  # « boussole », « relatif (suivi de la vidéo) » ou « inconnu »
    pieces: list[PieceCarte]
    murs: list[Mur]
    passages_non_nommes: list[tuple[float, float]]
    ancrages: list[Ancrage]
    elements: dict[str, dict]  # élément de l'assistant -> pièce vue, mur, cap
    questions: list[str]
    arbitrage: list[dict] = field(default_factory=list)
    calcul_s: float = 0.0
    piece_des_cles: list[tuple[float, str | None]] = field(default_factory=list)
    # Pourquoi chaque image clé est dans sa pièce : « image » (lieu reconnu), « nom » (pièce dite), « continuité »,
    # « nouvelle » (pièce annoncée), « claude » (arbitrage).
    preuve_des_cles: list[tuple[float, str]] = field(default_factory=list)

    def piece_a(self, t: float) -> str | None:
        """Pièce reconnue à l'instant ``t`` (image clé la plus proche)."""
        if not self.piece_des_cles:
            return None
        return min(self.piece_des_cles, key=lambda c: abs(c[0] - t))[1]

    def en_dict(self) -> dict:
        def p2(x):
            return [[round(a, 1), round(b, 1)] for a, b in x]

        return {
            "source": self.source, "duree_s": round(self.duree_s, 1), "images": self.images, "images_cles": self.images_cles,
            "suivi_continu": round(self.suivi, 3), "stations": self.stations, "liens": self.liens, "cap": self.cap,
            "calcul_s": round(self.calcul_s, 1),
            "pieces": [{"nom": p.nom, "nommee": p.nommee, "passages": p2(p.passages), "sejours": p.sejours, "revisitee": p.revisitee,
                        "images_cles": p.images_cles, "axe": None if p.axe is None else round(p.axe, 1),
                        "corrections": p.corrections} for p in self.pieces],
            "murs": [{"id": m.id, "piece": m.piece, "nom": m.nom, "cap": round(m.cap, 1), "vu": p2(m.vu)} for m in self.murs],
            "passages_non_nommes": p2(self.passages_non_nommes),
            "ancrages": [{"t": round(a.t, 2), "texte": a.texte, "designation": a.designation, "par": a.par, "piece": a.piece,
                          "cap": None if a.cap is None else round(a.cap, 1), "mur": a.mur, "elements": a.elements,
                          "accord": a.accord} for a in self.ancrages],
            "elements": self.elements,
            "arbitrage": self.arbitrage,
            "questions": self.questions,
            "pieces_par_instant": [[round(t, 2), p] for t, p in self.piece_des_cles],
        }


# --- Calcul ---------------------------------------------------------------------------------------------------------


class _Ensembles:
    """Union-find."""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def trouver(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def unir(self, a: int, b: int) -> None:
        a, b = self.trouver(a), self.trouver(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def _intervalles(instants: list[float], trou: float) -> list[tuple[float, float]]:
    """Instants regroupés en passages (un trou de plus de ``trou`` secondes sépare deux passages)."""
    passages: list[list[float]] = []
    for t in sorted(instants):
        if passages and t - passages[-1][1] <= trou:
            passages[-1][1] = t
        else:
            passages.append([t, t])
    return [(a, b) for a, b in passages]


def _nom_a(noms: list[tuple[float, str]], t: float) -> str | None:
    """Pièce où l'assistant se croyait à l'instant t."""
    courant = None
    for instant, nom in noms:
        if instant <= t + 1e-6:
            courant = nom
        else:
            break
    return courant


def _score_axe(caps: list[float], axes) -> np.ndarray:
    """À quel point des murs orientés selon chacun de ces axes expliquent les caps (les caps proches d'une croix)."""
    ecarts = (np.array(caps)[None, :] - np.atleast_1d(np.asarray(axes, dtype=float))[:, None] + 45) % 90 - 45
    return np.exp(-(ecarts ** 2) / (2 * 15 ** 2)).sum(1)


def _axe(caps: list[float]) -> float:
    """Orientation des murs d'une pièce : on filme surtout les murs de face, donc les caps se groupent tous les 90°.
    Renvoie l'angle (0 à 90°) qui aligne le mieux les caps sur une croix."""
    if not caps:
        return 0.0
    candidats = np.arange(0, 90, 1.0)
    return float(candidats[int(np.argmax(_score_axe(caps, candidats)))])


@dataclass
class Designation:
    """Ce qui désigne un mur dans une phrase."""

    debut: int  # place du mot dans la phrase (pour son instant)
    par: str  # « ce mur », « le mur de gauche », « le deuxième mur »
    decalage: float = 0.0  # cap du mur désigné par rapport à celui de la caméra
    rang: int = 0  # « le deuxième mur » : 2


def designation(texte: str) -> Designation | None:
    """« Le deuxième mur » (son rang dans la pièce), « le mur de gauche » (−90° par rapport à la caméra), « ce mur » (en
    face) ; None si rien ne désigne un mur."""
    if m := ORDINAL.search(texte):
        return Designation(m.start(), m.group(0), rang=RANGS[_normaliser(m.group(1))])
    if m := POSITION.search(texte):
        return Designation(m.start(), m.group(0), DECALAGES[_normaliser(next(g for g in m.groups() if g))])
    if m := DESIGNATION.search(texte):
        return Designation(m.start(), m.group(0))
    return None


def _repartis(elements: list, nombre: int) -> list:
    if len(elements) <= nombre:
        return list(elements)
    return [elements[round(k * (len(elements) - 1) / (nombre - 1))] for k in range(nombre)]


def construire_carte(entrees: Entrees, arbitre: Arbitre | None = None) -> Carte:
    """Calcule la carte des pièces d'une visite."""
    debut = time.perf_counter()
    vues = entrees.vues
    if len(vues) < 2:
        raise ValueError("pas assez d'images pour une carte")
    largeur = vues[0].gris.shape[1]
    focale = largeur * (FOCALE_PORTRAIT if vues[0].gris.shape[0] > largeur else FOCALE_PAYSAGE)
    cadence = (len(vues) - 1) / max(1e-6, vues[-1].t - vues[0].t)

    # 1. Suivi continu, image par image.
    mouvements: list[Mouvement] = [Mouvement(vues[0].t, False)] + [suivre(a, b, focale) for a, b in zip(vues, vues[1:])]
    suivi = sum(m.suivi for m in mouvements[1:]) / (len(vues) - 1)

    # 2. Images clés choisies par le mouvement (images à 1 par seconde : toutes).
    for v in vues:
        decrire(v)
    cles: list[int] = [0]
    glisse = avance = 0.0
    for k in range(1, len(vues)):
        m = mouvements[k]
        if not m.suivi:
            cles.append(k)
            glisse = avance = 0.0
            continue
        glisse += math.hypot(m.dx, m.dy)
        avance += math.log(max(m.echelle, 1e-3))
        if glisse >= CLE_GLISSEMENT * largeur or abs(avance) >= CLE_AVANCEE:
            cles.append(k)
            glisse = avance = 0.0
    if cles[-1] != len(vues) - 1:
        cles.append(len(vues) - 1)
    n = len(cles)
    instants = [vues[k].t for k in cles]

    def trajet(a: int, b: int) -> tuple[float, float]:
        """Entre deux images clés : (plus long moment sans suivi, avancée nette pendant le suivi)."""
        aveugle = trou = avancee = 0.0
        for k in range(cles[a] + 1, cles[b] + 1):
            m = mouvements[k]
            if m.suivi:
                avancee += math.log(max(m.echelle, 1e-3))
                trou = 0.0
            else:
                trou += vues[k].t - vues[k - 1].t
                aveugle = max(aveugle, trou)
        return aveugle, abs(avancee)

    # 3. Mots visuels, puis liens vérifiés : voisins dans le temps et images qui se ressemblent.
    exploitables = [vues[k] for k in cles if vues[k].exploitable]
    liens: dict[tuple[int, int], Lien] = {}
    if len(exploitables) >= 2:
        vocabulaire = Vocabulaire.apprendre(exploitables)
        mots = np.array([vocabulaire.histogramme(vues[k]) if vues[k].exploitable else np.zeros(len(vocabulaire.centres))
                         for k in cles])
        ressemblance = mots @ mots.T
        for a in range(n):
            candidats = set(range(max(0, a - VOISINS), min(n, a + VOISINS + 1)))
            candidats |= {int(b) for b in np.argsort(-ressemblance[a])[:CANDIDATS] if ressemblance[a, b] > 0}
            for b in candidats:
                if b > a and (a, b) not in liens:
                    lien = verifier(vues[cles[a]], vues[cles[b]], a, b, minimum=LIEN_MIN, focale=focale)
                    if lien:
                        liens[(a, b)] = lien

    # Cap relatif le long du suivi continu : rotations 3D composées depuis le début de chaque suite d'images suivies, cap
    # = direction de l'axe de la caméra autour de la verticale de la première image (téléphone droit au départ). Un
    # téléphone penché ou couché fait alors tourner l'image sans fausser le cap ; caméra vers le plafond ou le sol : pas
    # de cap.
    lacet_vue: list[float | None] = [None] * len(vues)
    serie: list[int] = []  # numéro de la suite d'images suivies de chaque image (le cap relatif repart à chaque décrochage)
    R = np.eye(3)
    for k in range(len(vues)):
        m = mouvements[k]
        if k == 0 or not m.suivi or m.rotation is None:
            R = np.eye(3)
            serie.append(k)
        else:
            R = m.rotation @ R
            serie.append(serie[-1])
        axe = R.T @ np.array([0.0, 0.0, 1.0])
        if abs(axe[1]) < 0.85:  # moins de ~58° vers le haut ou le bas
            lacet_vue[k] = lacet_relatif(R)

    # 4. Stations : images clés successives où la caméra a tourné sur place (suivi tenu, pas d'avancée), ou que la
    # géométrie montre prises du même point (rotation pure).
    stations = _Ensembles(n)
    pas_visuel: dict[tuple[int, int], float] = {}  # rotation de la caméra entre deux images clés suivies (degrés)
    for a in range(n - 1):
        aveugle, avancee = trajet(a, a + 1)
        if aveugle == 0:
            la, lb = lacet_vue[cles[a]], lacet_vue[cles[a + 1]]
            if la is not None and lb is not None and all(m.rotation is not None for m in mouvements[cles[a] + 1:cles[a + 1] + 1]):
                pas_visuel[(a, a + 1)] = ecart(lb, la)
            if avancee < ROTATION_AVANCEE:
                stations.unir(a, a + 1)
        elif (lien := liens.get((a, a + 1))) is not None and lien.rotation_pure:
            stations.unir(a, a + 1)
    racines = sorted({stations.trouver(i) for i in range(n)})
    station_de = {i: racines.index(stations.trouver(i)) for i in range(n)}
    membres_station: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        membres_station[station_de[i]].append(i)

    # 5. Pièces, dans l'ordre du temps.
    noms = entrees.noms
    dit = [_nom_a(noms, t) for t in instants]
    affichage: dict[str, str] = {}
    for _, nom in noms:
        affichage.setdefault(_normaliser(nom), nom)
    lies: dict[int, set[int]] = defaultdict(set)
    for (a, b) in liens:
        lies[a].add(b)
        lies[b].add(a)
    piece_cle: dict[int, int] = {}  # image clé -> numéro de pièce
    preuve_cle: dict[int, str] = {}  # « image », « nom », « continuité », « nouvelle »
    # Image clé ancrée : reliée par l'image, de proche en proche, aux images où sa pièce a été vue en premier. Les autres
    # ne tiennent leur pièce que du nom dit ou de la continuité, même reliées entre elles : une suite d'images d'un
    # retour non annoncé se reconnaît en elle-même, et porte le nom de la pièce d'où l'on vient.
    ancree: dict[int, bool] = {}
    noms_pieces: list[str | None] = []  # nom (normalisé) de chaque pièce, None si pas nommée
    doutes_noms: list[tuple[float, int, int]] = []
    courante: int | None = None
    ancre: int | None = None  # dernière image clé placée par une preuve (image, nom) : la marche se compte depuis là
    for s in sorted(membres_station, key=lambda s: min(membres_station[s])):
        membres = membres_station[s]
        c = Counter(_normaliser(dit[i]) for i in membres if dit[i])
        etiquette = c.most_common(1)[0][0] if c and c.most_common(1)[0][1] >= 0.6 * len(membres) else None
        comptes = Counter()
        fiables = Counter()  # liens vers des images clés ancrées
        for i in membres:
            for j in lies[i]:
                if j in piece_cle:
                    comptes[piece_cle[j]] += 1
                    fiables[piece_cle[j]] += ancree[j]
        classement = comptes.most_common(2)
        meilleure, nb = classement[0] if classement else (None, 0)
        second = classement[1][1] if len(classement) > 1 else 0
        nommee = next((k for k, nom in enumerate(noms_pieces) if nom and nom == etiquette), None)
        reconnue = meilleure is not None and nb >= LIENS_FUSION and nb >= 2 * second
        doute = False
        if reconnue and etiquette is not None and nommee != meilleure and fiables[meilleure] < LIENS_FORTS:
            # Contre la pièce dite (connue ou qu'il vient d'annoncer), il faut des images clés ancrées : le nom des
            # autres retarde de quelques secondes sur la porte. Visite de Noah du 22/10 après-midi : les premières
            # images de la chambre, filmées avant qu'il l'annonce, portaient encore le nom de la pièce U, et toute la
            # chambre s'y reconnaissait ; au retour de la cuisine, de même.
            reconnue = False
            doute = fiables[meilleure] >= LIENS_FUSION  # un peu de preuves contre le nom dit : on le demandera
        aveugle, avancee = trajet(ancre, min(membres)) if ancre is not None else (0.0, 0.0)
        a_marche = aveugle >= MARCHE_AVEUGLE_S or avancee >= MARCHE_AVANCEE
        if reconnue:
            choix, preuve = meilleure, "image"
        elif nommee is not None:
            choix, preuve = nommee, "nom"
        elif etiquette is not None:
            noms_pieces.append(etiquette)  # pièce annoncée et jamais vue
            choix, preuve = len(noms_pieces) - 1, "nouvelle"
        elif courante is not None and not a_marche:
            choix, preuve = courante, "continuité"  # on ne change pas de pièce en tournant sur place
        else:
            noms_pieces.append(None)
            choix, preuve = len(noms_pieces) - 1, "nouvelle"
        if noms_pieces[choix] is None and etiquette is not None and etiquette not in noms_pieces:
            noms_pieces[choix] = etiquette
        if doute:
            doutes_noms.append((instants[min(membres)], meilleure, choix))
        for i in membres:
            piece_cle[i] = choix
            preuve_cle[i] = preuve
            ancree[i] = preuve == "nouvelle" or fiables[choix] >= ANCRAGE_MIN
        courante = choix
        if preuve != "continuité":
            ancre = max(membres)

    # Deux lieux non nommés qui se reconnaissent nettement sont le même endroit.
    pieces = _Ensembles(len(noms_pieces))
    entre: Counter = Counter()
    for (a, b) in liens:
        pa, pb = piece_cle[a], piece_cle[b]
        if pa != pb:
            entre[(min(pa, pb), max(pa, pb))] += 1
    for (pa, pb), nb in entre.most_common():
        if nb >= LIENS_FORTS and (noms_pieces[pa] is None or noms_pieces[pb] is None):
            autres = max([v for (x, y), v in entre.items() if {x, y} & {pa, pb} and (x, y) != (pa, pb)] or [0])
            if nb >= 2 * autres:
                pieces.unir(pa, pb)

    def nom_de(numero: int) -> str | None:
        racine = pieces.trouver(numero)
        return next((noms_pieces[k] for k in range(len(noms_pieces)) if pieces.trouver(k) == racine and noms_pieces[k]), None)

    # La voix retarde sur la porte : la pièce est annoncée jusqu'à ~15 s après y être entré (visite de Noah du 22/10
    # après-midi : sorti de la cuisine vers 4:13, « pièce U » dite à 4:28 ; cuisine filmée dès 3:03, dite à 3:18).
    changements = [t for k, (t, nom) in enumerate(noms) if k and _normaliser(nom) != _normaliser(noms[k - 1][1])]

    def ancrer() -> None:
        """Ancrage de proche en proche sur toute la visite, dans les deux sens du temps. Départ : le début de chaque pièce
        (ANCRAGE_DEBUT_S après l'image où elle apparaît, sans aller jusqu'au retard de la voix sur l'annonce suivante :
        à une image par seconde, la toute première image est souvent floue et liée à rien). Puis une station est ancrée
        par ANCRAGE_MIN liens au moins vers des images clés ancrées de sa pièce (un seul lien peut être une porte)."""
        for i in range(n):
            ancree[i] = ancree[i] or preuve_cle[i] in ("nouvelle", "claude")
        for k in range(len(noms_pieces)):
            entree = min((instants[i] for i in range(n) if piece_cle[i] == k and preuve_cle[i] == "nouvelle"), default=None)
            if entree is None:
                continue
            fin = min([entree + ANCRAGE_DEBUT_S] + [t - RETARD_NOM_S for t in changements if t > entree + 1.0])
            for i in range(n):
                if piece_cle[i] == k and entree <= instants[i] <= fin:
                    ancree[i] = True
        change = True
        while change:
            change = False
            for membres in membres_station.values():
                for numero in {pieces.trouver(piece_cle[i]) for i in membres if not ancree[i]}:
                    meme = [i for i in membres if pieces.trouver(piece_cle[i]) == numero]
                    appuis = sum(ancree[j] and pieces.trouver(piece_cle[j]) == numero for i in meme for j in lies[i])
                    if appuis >= ANCRAGE_MIN:
                        for i in meme:
                            ancree[i] = True
                        change = True

    ancrer()

    def passages_douteux() -> list[list[int]]:
        """Suites d'images clés non ancrées, dans une même pièce : elle ne vient que du nom dit ou de la continuité. Un
        trou sans image exploitable (caméra au plafond, flou) coupe la suite : on a pu changer de pièce pendant ce temps."""
        groupes_douteux: list[list[int]] = []
        groupe: list[int] = []
        vu_en_dernier = -1e9  # instant de la dernière image exploitable de la suite
        for i in range(n):
            if i:  # toutes les images vues depuis l'image clé précédente comptent, pas seulement les images clés
                vu_en_dernier = max([vu_en_dernier] + [vues[k].t for k in range(cles[i - 1], cles[i]) if vues[k].exploitable])
            douteuse = not ancree[i]
            if douteuse and groupe and piece_cle[groupe[-1]] == piece_cle[i] and instants[i] - vu_en_dernier <= 2.5:
                groupe.append(i)
            else:
                if groupe:
                    groupes_douteux.append(groupe)
                groupe = [i] if douteuse else []
                vu_en_dernier = instants[i]
            if douteuse and vues[cles[i]].exploitable:
                vu_en_dernier = instants[i]
        if groupe:
            groupes_douteux.append(groupe)
        return groupes_douteux

    # Réexamen d'un passage entier : image par image il ne reconnaissait rien de net (images à 1/s, retour bref), mais
    # l'ensemble peut montrer clairement une autre pièce (retour non annoncé). Les liens doivent venir de la moitié au
    # moins de ses images : quelques liens au bout d'un long passage sont ceux d'une porte.
    for groupe in passages_douteux():
        dans = set(groupe)
        comptes = Counter(pieces.trouver(piece_cle[j]) for i in groupe for j in lies[i]
                          if j not in dans and ancree[j])  # seulement des endroits sûrs
        ici = pieces.trouver(piece_cle[groupe[0]])
        autre, nb = next(((k, v) for k, v in comptes.most_common() if k != ici), (None, 0))
        reste = max([v for k, v in comptes.items() if k != autre] or [0])
        relies = sum(any(j not in dans and ancree[j] and pieces.trouver(piece_cle[j]) == autre for j in lies[i])
                     for i in groupe)
        nettes = sum(vues[cles[i]].exploitable for i in groupe)
        if autre is not None and nb >= LIENS_FORTS and nb >= 2 * reste and relies >= 0.5 * nettes:
            for i in groupe:
                piece_cle[i] = autre
                preuve_cle[i] = "image"
                ancree[i] = True
    ancrer()

    # 6. Arbitrage par Claude des passages non reconnus (vue jamais filmée sous cet angle, retour non annoncé…).
    arbitrage: list[dict] = []
    corrections_claude: list[tuple[float, float, str, str, str]] = []
    # Autre pièce vue par Claude : une question, jamais une pièce créée d'après une image (on demande plutôt que de
    # dédoubler une pièce dont les références ne montrent qu'un coin).
    autres_vues: list[tuple[float, float, str, str | None]] = []
    if arbitre is not None:
        doutes: list[Doute] = []
        passages = []
        for groupe in passages_douteux():
            bons = [i for i in groupe if vues[cles[i]].exploitable]
            if instants[groupe[-1]] - instants[groupe[0]] >= DOUTE_MIN_S and len(bons) >= 2:
                passages.append((groupe, bons))
        # D'abord les passages juste avant un changement de pièce dit (la voix retarde sur la porte), puis les plus
        # longs. Chaque image montrée est un doute à part (un passage peut mêler deux endroits : « l'escalier, puis le
        # séjour »), et chaque image clé du passage prend le verdict de l'image montrée la plus proche.
        def a_la_porte(a: float, b: float) -> bool:
            return any(t - RETARD_NOM_S <= b and a <= t + 2.0 for t in changements)

        def priorite(passage: tuple[list[int], list[int]]) -> tuple[bool, float]:
            a, b = instants[passage[0][0]], instants[passage[0][-1]]
            return not a_la_porte(a, b), a - b

        for groupe, bons in sorted(passages, key=priorite):
            montrees: list[int] = []
            for i in bons:
                pas = IMAGE_PORTE_S if a_la_porte(instants[i], instants[i]) else IMAGE_TOUTES_S
                if not montrees or instants[i] - instants[montrees[-1]] >= pas:
                    montrees.append(i)
            if montrees[-1] != bons[-1]:
                montrees.append(bons[-1])
            for i in montrees:
                part = [j for j in groupe if min(montrees, key=lambda m: abs(instants[m] - instants[j])) == i]
                if len(doutes) < DOUTES_MAX:
                    doutes.append(Doute(len(doutes) + 1, instants[part[0]], instants[part[-1]],
                                        affichage.get(nom_de(piece_cle[groupe[0]]) or "", None), [vues[cles[i]]], part))
        racines_nommees = {pieces.trouver(k): affichage[nom] for k, nom in enumerate(noms_pieces) if nom}
        if doutes and len(racines_nommees) >= 1:
            references = {}
            for racine, nom in racines_nommees.items():
                prouvees = [i for i in range(n) if pieces.trouver(piece_cle[i]) == racine and ancree[i]
                            and vues[cles[i]].exploitable]
                references[nom] = [vues[cles[i]] for i in _repartis(prouvees, REFERENCES_PAR_PIECE)]
            verdicts: list[Verdict] = []
            for k in range(0, len(doutes), DOUTES_PAR_APPEL):
                verdicts += arbitre(references, doutes[k:k + DOUTES_PAR_APPEL])
            for verdict in verdicts:
                doute = next((d for d in doutes if d.numero == verdict.numero), None)
                if doute is None:
                    continue
                arbitrage.append({"passage": [round(doute.debut, 1), round(doute.fin, 1)], "piece_retenue": doute.piece,
                                  "claude": verdict.piece or f"autre pièce ({verdict.type or '?'})",
                                  "confiance": verdict.confiance, "raison": verdict.raison})
                if verdict.confiance not in ("forte", "moyenne"):
                    continue
                cible = next((k for k, nom in enumerate(noms_pieces) if nom and verdict.piece
                              and nom == _normaliser(verdict.piece)), None)
                if verdict.piece and cible is not None and _normaliser(verdict.piece) != _normaliser(doute.piece or ""):
                    for i in doute.cles:
                        piece_cle[i] = cible
                        preuve_cle[i] = "claude"
                    corrections_claude.append((doute.debut, doute.fin, doute.piece or "?", verdict.piece, verdict.raison))
                elif verdict.piece is None:
                    autres_vues.append((doute.debut, doute.fin, verdict.type, doute.piece))

    # Pièces finales, nommées ; les lieux non nommés et brefs sont des passages.
    groupes: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groupes[pieces.trouver(piece_cle[i])].append(i)
    resultat_pieces: list[PieceCarte] = []
    nom_des_groupes: dict[int, str | None] = {}
    passages_non_nommes: list[tuple[float, float]] = []
    numero = 0
    for racine, membres in sorted(groupes.items(), key=lambda g: instants[min(g[1])]):
        ts = [instants[i] for i in membres]
        duree = sum(b - a + 0.5 for a, b in _intervalles(ts, 3.0))
        nom = nom_de(racine)
        if nom is not None:
            nom, nommee = affichage[nom], True
        elif duree < PASSAGE_MAX_S:
            nom_des_groupes[racine] = None
            passages_non_nommes += _intervalles(ts, 3.0)
            continue
        else:
            numero += 1
            nom, nommee = f"Pièce non nommée {numero}", False
        nom_des_groupes[racine] = nom
        resultat_pieces.append(PieceCarte(nom, nommee, _intervalles(ts, 8.0), len(membres)))
    piece_de = {i: nom_des_groupes[pieces.trouver(piece_cle[i])] for i in range(n)}

    # Séjours : sorti vers une autre pièce, puis revenu. Les passages de moins de PASSAGE_MAX_S ne comptent pas (coup d'œil
    # par une porte, image floue), ni les trous entre deux passages d'une même pièce (caméra au plafond).
    sejours: Counter = Counter()
    precedente = None
    for _, nom in sorted((a, p.nom) for p in resultat_pieces for a, b in p.passages if b - a + 1.0 >= PASSAGE_MAX_S):
        if nom != precedente:
            sejours[nom] += 1
            precedente = nom
    for p in resultat_pieces:
        p.sejours = max(1, sejours[p.nom])

    # Corrections : endroit reconnu alors que l'assistant se croyait ailleurs (retour non annoncé).
    connues = {_normaliser(p.nom) for p in resultat_pieces}
    ecarts_dits: dict[tuple[str, str], list[float]] = defaultdict(list)
    for i in range(n):
        vu = piece_de[i]
        if (dit[i] and vu and _normaliser(dit[i]) != _normaliser(vu) and _normaliser(dit[i]) in connues
                and preuve_cle[i] == "image"):
            ecarts_dits[(dit[i], vu)].append(instants[i])
    for (nom_dit, vu), ts in ecarts_dits.items():
        piece = next(p for p in resultat_pieces if p.nom == vu)
        for a, b in _intervalles(ts, 5.0):
            piece.corrections.append(f"{_passage(a, b)} : l'assistant se croyait dans « {nom_dit} », l'image montre « {vu} »")
    corrections_claude = _regrouper(corrections_claude)
    for a, b, avant, apres, raison in corrections_claude:
        piece = next((p for p in resultat_pieces if p.nom == apres), None)
        if piece is not None:
            piece.corrections.append(f"{_passage(a, b)} : « {avant} » d'après la voix, « {apres} » d'après Claude "
                                     f"(images : {raison})")

    # 7. Cap de la caméra à chaque image clé : capteurs, sinon suivi continu de la vidéo (relatif).
    boussole = Boussole()
    for m in entrees.capteurs:
        boussole.ajouter(m)
    correction = boussole.correction()

    def cap_capteur(t: float) -> float | None:
        visee = boussole.visee(t - 0.4, t + 0.4)
        if visee is None:
            return None
        if visee.lacet is not None and correction is not None:
            return (visee.lacet + correction) % 360
        return visee.cap

    caps: list[float | None] = [cap_capteur(t) for t in instants]
    suivi_cap = [False] * n  # cap tiré du suivi continu de la vidéo
    source_cap = "boussole" if any(c is not None for c in caps) else "inconnu"
    if cadence >= FPS_SUIVI:
        # Cap relatif mesuré par le suivi continu : exact le long d'une suite d'images suivies (rotations composées),
        # puis les suites d'une même pièce raccordées entre elles par les lieux reconnus (rotation mesurée sur les points
        # communs ; médiane de tous les liens entre deux suites). Recalé sur la boussole si elle existe.
        suites = _Ensembles(n)
        for (a, b) in pas_visuel:
            suites.unir(a, b)
        lacet_suite: dict[int, float] = {}
        for depart in range(n):
            racine = suites.trouver(depart)
            if racine == depart:
                lacet_suite[depart] = 0.0
        for a in range(n - 1):  # les arêtes de suivi relient des images clés consécutives
            if (a, a + 1) in pas_visuel:
                lacet_suite[a + 1] = lacet_suite[a] + pas_visuel[(a, a + 1)]
        decalages: dict[tuple[int, int], list[float]] = defaultdict(list)  # (suite i, suite j) -> écarts
        for (a, b), lien in liens.items():
            ra, rb = suites.trouver(a), suites.trouver(b)
            if ra != rb and lien.lacet is not None and piece_de[a] is not None and piece_de[a] == piece_de[b]:
                # cap(b) = cap(a) + lacet du lien ; cap(x) = origine(suite de x) + lacet_suite[x]
                decalages[(ra, rb)].append(ecart(lacet_suite[a] + lien.lacet, lacet_suite[b]))
        origine: dict[int, float] = {}
        racines_suites = sorted({suites.trouver(i) for i in range(n)}, key=lambda r: -sum(suites.trouver(i) == r for i in range(n)))
        # Recalage sur la boussole d'abord : chaque mesure comparée au cap suivi à son propre instant (pas à celui de
        # l'image clé voisine : en balayant, la caméra tourne de plusieurs degrés en 0,4 s, toujours dans le même sens).
        temps = [v.t for v in vues]
        par_suite: dict[int, list[float]] = defaultdict(list)
        for mesure in entrees.capteurs:
            cap_m = mesure.cap if mesure.cap is not None else (
                (mesure.lacet + correction) % 360 if mesure.lacet is not None and correction is not None else None)
            j = bisect.bisect_left(temps, mesure.t)
            k = min((x for x in (j - 1, j) if 0 <= x < len(vues)), key=lambda x: abs(temps[x] - mesure.t), default=None)
            if cap_m is None or k is None or abs(temps[k] - mesure.t) > 0.6 / max(cadence, 1.0) or lacet_vue[k] is None:
                continue
            memes = [i for i in range(n) if serie[cles[i]] == serie[k] and lacet_vue[cles[i]] is not None]
            if memes:
                i = min(memes, key=lambda i: abs(instants[i] - mesure.t))
                par_suite[suites.trouver(i)].append(ecart(cap_m, lacet_suite[i] + ecart(lacet_vue[k], lacet_vue[cles[i]])))
        # Les suites reliées entre elles (même pièce, lieux reconnus) sont recalées ensemble, sur toutes leurs mesures :
        # une courte suite n'a souvent qu'une ou deux mesures de boussole (une par seconde), bruitées de ±20°.
        voisines: dict[int, list[tuple[int, float, int]]] = defaultdict(list)
        for (ra, rb), lst in decalages.items():
            d = mediane_circulaire(lst)
            voisines[ra].append((rb, d, len(lst)))
            voisines[rb].append((ra, -d, len(lst)))
        groupe: dict[int, int] = {}
        relatif_a: dict[int, float] = {}  # origine de la suite moins celle de la première suite de son groupe
        for depart in racines_suites:  # les plus longues d'abord
            if depart in groupe:
                continue
            groupe[depart], relatif_a[depart] = depart, 0.0
            pile = [depart]
            while pile:
                x = pile.pop()
                for y, d, _ in sorted(voisines[x], key=lambda v: -v[2]):
                    if y not in groupe:
                        groupe[y], relatif_a[y] = depart, (relatif_a[x] + d) % 360
                        pile.append(y)
        mesures_groupe: dict[int, list[float]] = defaultdict(list)
        for r in racines_suites:
            connus = par_suite.get(r) or [ecart(caps[i], lacet_suite[i]) for i in range(n) if suites.trouver(i) == r and caps[i] is not None]
            mesures_groupe[groupe[r]] += [ecart(c, relatif_a[r]) for c in connus]
        for r in racines_suites:
            if mesures_groupe[groupe[r]]:
                origine[r] = (mediane_circulaire(mesures_groupe[groupe[r]]) + relatif_a[r]) % 360
        if not origine and racines_suites:
            for r in racines_suites:  # sans boussole : la plus longue suite de chaque pièce donne l'origine (cap relatif)
                piece = piece_de[min(i for i in range(n) if suites.trouver(i) == r)]
                if piece is not None and not any(piece_de[min(i for i in range(n) if suites.trouver(i) == o)] == piece
                                                 for o in origine):
                    origine[r] = 0.0
            if origine:
                source_cap = "relatif (suivi de la vidéo)"
        while True:  # raccord des autres suites, par le plus grand nombre de liens
            meilleur = None
            for (ra, rb), lst in decalages.items():
                for x, y, sens in ((ra, rb, 1), (rb, ra, -1)):
                    if x in origine and y not in origine and (meilleur is None or len(lst) > meilleur[3]):
                        meilleur = (x, y, sens, len(lst), lst)
            if meilleur is None:
                break
            x, y, sens, _, lst = meilleur
            origine[y] = (origine[x] + sens * mediane_circulaire(lst)) % 360
        # Étape 13 : le cap suivi, recalé sur la médiane de toutes les mesures de sa suite, remplace la mesure isolée de la
        # boussole (bruitée, une par seconde sur les anciens téléphones) : le côté d'un mur ne se joue plus sur une mesure.
        for i in range(n):
            r = suites.trouver(i)
            if r in origine and lacet_vue[cles[i]] is not None:
                caps[i] = (origine[r] + lacet_suite[i]) % 360
                suivi_cap[i] = True
    relatif = source_cap.startswith("relatif")

    def cle_proche(t: float) -> int:
        proches = [i for i in range(n) if abs(instants[i] - t) <= 1.5 and vues[cles[i]].exploitable]
        return min(proches or range(n), key=lambda i: abs(instants[i] - t))

    temps_vues = [v.t for v in vues]

    def cap_a(t: float) -> float | None:
        """Cap à l'instant t : celui du suivi continu (image clé de la même suite, plus la rotation suivie depuis), sinon
        les capteurs, sinon l'image clé la plus proche (à 1 s près) dont le cap est connu."""
        k = min(range(max(0, bisect.bisect_left(temps_vues, t) - 1), min(len(vues), bisect.bisect_left(temps_vues, t) + 1)),
                key=lambda j: abs(temps_vues[j] - t))
        suivies = [i for i in range(n) if suivi_cap[i] and serie[cles[i]] == serie[k]]
        if suivies and lacet_vue[k] is not None and abs(temps_vues[k] - t) <= 0.5:
            i = min(suivies, key=lambda i: abs(instants[i] - t))
            return (caps[i] + ecart(lacet_vue[k], lacet_vue[cles[i]])) % 360
        c = cap_capteur(t)
        if c is not None:
            return c
        connues = [i for i in range(n) if caps[i] is not None and abs(instants[i] - t) <= 1.0]
        return caps[min(connues, key=lambda i: abs(instants[i] - t))] if connues else None

    # Les phrases qui désignent un mur (« ce mur », « le mur de gauche ») : à cet instant, la caméra vise un mur.
    designations = [(ph, designation(ph.texte)) for ph in entrees.phrases]

    def instant_de(ph: Phrase, d: Designation | None) -> float:
        return ph.t_debut + (ph.t_fin - ph.t_debut) * (d.debut / max(1, len(ph.texte)) if d else 0.5)

    vises: dict[str, list[float]] = defaultdict(list)  # pièce -> caps des murs désignés
    for ph, d in designations:
        if d is not None and not d.rang and (c := cap_a(instant_de(ph, d))) is not None:
            vises[piece_de[cle_proche(instant_de(ph, d))] or ""].append((c + d.decalage) % 360)

    # Murs : les quatre directions de chaque pièce. Avec la boussole, les murs des pièces sont parallèles : l'axe est celui
    # du logement, estimé sur toutes les pièces (étape 13 ; étape 12 : l'axe de la pièce U variait de 40° d'un calcul à
    # l'autre, selon ses images retenues). Une pièce que l'axe du logement explique mal garde le sien.
    murs: dict[str, Mur] = {}
    axes: dict[str, float] = {}
    elements_etat = _elements_de(entrees.etat)
    caps_pieces: dict[str, list[float]] = {}
    for p in resultat_pieces:
        # Les images clés sont prises en balayant : leurs caps disent peu de l'axe. Un mur désigné, ou décrit par
        # l'assistant pendant qu'il le filmait, le dit bien mieux : il compte triple.
        caps_piece = [caps[i] for i in range(n) if piece_de[i] == p.nom and caps[i] is not None] + vises[p.nom] * 3
        if not relatif:
            caps_piece += [e["cap"] for e in elements_etat if e["type"] == "mur" and e["cap"] is not None
                           and _normaliser(e["piece"] or "") == _normaliser(p.nom)] * 3
        caps_pieces[p.nom] = caps_piece
    tous_caps = [c for liste in caps_pieces.values() for c in liste]
    axe_logement = _axe(tous_caps) if tous_caps and source_cap == "boussole" else None
    for p in resultat_pieces:
        caps_piece = caps_pieces[p.nom]
        if caps_piece and source_cap != "inconnu":
            axe = _axe(caps_piece)
            if axe_logement is not None and _score_axe(caps_piece, axe_logement)[0] >= AXE_LOGEMENT * _score_axe(caps_piece, axe)[0]:
                axe = axe_logement
            p.axe = axes[p.nom] = axe

    def mur_vise(piece: str | None, cap: float | None) -> Mur | None:
        if piece is None or cap is None or piece not in axes:
            return None
        k = round(ecart(cap, axes[piece]) / 90) % 4
        direction = (axes[piece] + 90 * k) % 360
        nom = f"mur {LETTRES[k]}" if relatif else point_cardinal(direction)
        cle = f"{piece} · {nom}"
        if cle not in murs:
            murs[cle] = Mur(cle, piece, nom, direction)
        return murs[cle]

    vus: dict[str, list[float]] = defaultdict(list)
    for i in range(n):
        mur = mur_vise(piece_de[i], caps[i])
        if mur is not None and vues[cles[i]].exploitable:
            vus[mur.id].append(instants[i])
    for cle, ts in vus.items():
        murs[cle].vu = _intervalles(ts, 3.0)

    # 8. Éléments de l'assistant et ancrage des phrases. Un mur désigné par sa place (« le mur de gauche ») : sans boussole,
    # son cap est celui de la caméra décalé, comme pendant la visite (avec la boussole, l'assistant l'a noté décalé).
    decalage_de: dict[str, float] = {}
    for ph, d in designations:
        for x in ph.elements:
            if d is not None and d.decalage:
                decalage_de.setdefault(x, d.decalage)
    elements: dict[str, dict] = {}
    for e in elements_etat:
        if e["type"] not in ("mur", "fenetre", "porte", "emetteur"):
            continue
        t = e["t_image"] if e["t_image"] is not None else e["t"]
        piece_vue = piece_de[cle_proche(t)]
        cap = e["cap"] if e["cap"] is not None and not relatif else cap_a(t)
        if cap is not None and (e["cap"] is None or relatif):
            cap = (cap + decalage_de.get(e["id"], 0.0)) % 360
        mur = mur_vise(piece_vue, cap) if e["type"] in ("mur", "fenetre", "porte") else None
        elements[e["id"]] = {"piece_dite": e["piece"], "piece_vue": piece_vue, "cap": None if cap is None else round(cap, 1),
                             "mur": mur.id if mur else None, "nom": e["nom"], "t": round(t, 2)}
    ancrages: list[Ancrage] = []
    montres: dict[str, list[str]] = defaultdict(list)  # murs de chaque pièce, dans l'ordre où il les a montrés
    for ph, d in designations:
        t = instant_de(ph, d)
        i = cle_proche(t)
        piece = piece_de[i] if abs(instants[i] - t) <= 1.5 else None
        cap = cap_a(t)
        if d is not None and d.rang:
            # « Le deuxième mur » : le deuxième qu'il a montré dans la pièce, pas celui que vise la caméra en le disant ;
            # sinon, le deuxième des murs que l'assistant a notés dans la pièce.
            notes = [elements[e["id"]]["mur"] for e in sorted(elements_etat, key=lambda e: e["t"])
                     if e["type"] == "mur" and elements.get(e["id"], {}).get("mur") and elements[e["id"]]["piece_vue"] == piece]
            ordre = montres[piece] if len(montres[piece]) >= d.rang else list(dict.fromkeys(notes))
            mur = murs.get(ordre[d.rang - 1]) if len(ordre) >= d.rang else None
            cap = mur.cap if mur is not None else None
        else:
            if cap is not None and d is not None:
                cap = (cap + d.decalage) % 360
            mur = mur_vise(piece, cap)
            if d is not None and mur is not None and mur.id not in montres[piece]:
                montres[piece].append(mur.id)
        murs_assistant = [x for x in ph.elements if elements.get(x, {}).get("mur")]
        if not murs_assistant or mur is None or d is None:
            accord = "sans objet"
        elif all(elements[x]["mur"] == mur.id for x in murs_assistant):
            accord = "oui"
        else:
            accord = "non : " + ", ".join(f"{x} = {elements[x]['mur']}" for x in murs_assistant if elements[x]["mur"] != mur.id)
        ancrages.append(Ancrage(t, ph.texte, d is not None, piece, cap, mur.id if mur else None, ph.elements, accord,
                                d.par if d else ""))

    # Questions pour l'écran de validation : on demande plutôt que de fusionner à tort.
    questions: list[str] = []
    for p in resultat_pieces:
        if not p.nommee:
            questions.append(f"« {p.nom} » vue {', '.join(_passage(a, b) for a, b in p.passages)} : nouvelle "
                             "pièce (laquelle ?) ou partie d'une pièce déjà nommée ?")
    for a, b, type_vu, retenue in _regrouper(autres_vues):
        questions.append(f"{_passage(a, b)} : Claude voit une autre pièce ({type_vu or '?'}), rangé dans « {retenue} » : "
                         "pièce à ajouter ?")
    vus_doutes = set()
    for t, a, b in doutes_noms:
        vu, dit_alors = nom_de(a), nom_de(b)
        if vu and dit_alors and vu != dit_alors and (vu, dit_alors, int(t // 10)) not in vus_doutes:
            vus_doutes.add((vu, dit_alors, int(t // 10)))
            questions.append(f"Vers {_hms(t)}, l'image ressemble un peu à « {affichage[vu]} », mais la pièce dite était "
                             f"« {affichage[dit_alors]} » : laquelle ?")
    hesitations = [(*a["passage"], a["piece_retenue"], a["claude"]) for a in arbitrage
                   if a["confiance"] == "faible" and a["claude"] != a["piece_retenue"]]
    for a, b, retenue, vu in _regrouper(hesitations):
        questions.append(f"{_passage(a, b)} : pièce « {retenue} » retenue, Claude hésite (« {vu} ») : laquelle ?")
    par_mur: dict[str, list[str]] = defaultdict(list)
    for ident, e in elements.items():
        if e["mur"] and ident.startswith("M"):
            par_mur[e["mur"]].append(ident)
    for mur, ids in par_mur.items():
        if len(ids) > 1:
            questions.append(f"{' et '.join(ids)} visent le même mur ({mur}) : même mur, ou deux murs du même côté ?")
    # Étape 13 : le DPE se décrit par côté. Des murs tournés de près de 45° par rapport au nord : leur côté (nord ou
    # est…) se joue à quelques degrés de boussole, on le demande (une fois pour le logement).
    douteux = sorted({("le logement" if axe == axe_logement else f"« {nom} »", axe) for nom, axe in axes.items()
                      if not relatif and abs(axe - 45) < AXE_DOUTE})
    for qui, axe in douteux:
        questions.append(f"Murs de {qui} tournés de {axe:.0f}° par rapport au nord : le côté de chaque mur (nord ou est, "
                         "sud ou ouest) est à confirmer.")
    return Carte(entrees.source, vues[-1].t - vues[0].t, len(vues), n, suivi, len(racines), len(liens), source_cap,
                 resultat_pieces, sorted(murs.values(), key=lambda m: m.id), _intervalles(
                     [t for a, b in passages_non_nommes for t in (a, b)], 3.0), ancrages, elements, questions, arbitrage,
                 time.perf_counter() - debut, [(instants[i], piece_de[i]) for i in range(n)],
                 [(instants[i], preuve_cle[i]) for i in range(n)])


def _regrouper(lignes: list[tuple]) -> list[tuple]:
    """(début, fin, …) jugés image par image : les lignes qui se suivent (images montrées voisines, IMAGE_TOUTES_S
    d'écart au plus) avec le même contenu n'en font qu'une (« de 5:33 à 5:47 » au lieu de quatre)."""
    regroupees: list[tuple] = []
    for ligne in sorted(lignes, key=lambda l: l[0]):
        if regroupees and ligne[2:4] == regroupees[-1][2:4] and ligne[0] - regroupees[-1][1] <= IMAGE_TOUTES_S:
            regroupees[-1] = (regroupees[-1][0], max(regroupees[-1][1], ligne[1]), *regroupees[-1][2:])
        else:
            regroupees.append(tuple(ligne))
    return regroupees


def _hms(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60)}:{int(t % 60):02d}"


def _passage(a: float, b: float) -> str:
    return f"de {_hms(a)} à {_hms(b)}" if b - a >= 1 else f"à {_hms(a)}"


def _elements_de(etat: dict | None) -> list[dict]:
    """Éléments de l'état de l'assistant, avec leur pièce, leur instant, leur image et leur cap (s'il a été mesuré).
    Étape 13 : murs et ouvertures sont ceux du logement (« enveloppe », avec les pièces où ils ont été vus), les
    radiateurs ceux du logement ; les états d'avant rangeaient tout par pièce."""
    etat = etat or {}
    enveloppe = etat.get("enveloppe") or {}
    sources = [(e, p["nom"]) for p in etat.get("pieces", []) for e in p.get("elements", [])]
    sources += [(e, (e.get("pieces") or [None])[0]) for cle in ("murs", "murs_interieurs", "fenetres")
                for e in enveloppe.get(cle) or []]
    sources += [(e, None) for e in (etat.get("logement") or {}).get("elements") or [] if e.get("type") == "emetteur"]
    elements = []
    for e, piece in sources:
        orientation = e.get("orientation") or {}
        image = e.get("image") or ""
        m = re.match(r"^(\d+(?:\.\d+)?)\.jpg$", image)
        elements.append({"id": e["id"], "type": e["type"], "piece": e.get("piece") or piece, "t": float(e.get("t") or 0),
                         "t_image": float(m.group(1)) if m else None, "cap": orientation.get("cap_brut"),
                         "point": orientation.get("point") or "", "nom": e.get("nom") or e.get("description") or ""})
    return elements


# --- Arbitre : Claude, par l'abonnement (Claude Code), comme le reste du projet ------------------------------------

CONSIGNES_ARBITRE = """Tu aides un diagnostiqueur immobilier qui a filmé un logement en une seule vidéo, en passant d'une pièce \
à l'autre et en revenant parfois dans une pièce déjà vue. Tu reçois des images de référence de chaque pièce connue, puis \
des images de la vidéo dont la pièce n'est pas sûre. Pour chaque image, dis dans quelle pièce connue elle a été filmée, \
d'après ce qu'on voit (meubles, fenêtres, sols, murs, objets), ou « autre » si c'est une pièce différente (dis alors son \
type : couloir, chambre, salle de bains, entrée…). Les références ne montrent qu'une partie de chaque pièce : une image \
peut montrer un autre coin d'une pièce connue (le coin repas d'un séjour, le côté fenêtre d'une chambre) ; décide alors \
d'après ce qu'elles ont en commun (sol, rideaux, fenêtres, plafond, mobilier de même style), et ne réponds « autre » que \
pour une pièce d'un autre usage ou sans rien de commun. N'invente rien : si l'image ne permet pas de trancher (plafond, \
flou), confiance « faible ». Réponds uniquement par un objet JSON : {"passages": [{"numero": 1, "piece": "<nom exact d'une pièce \
connue, ou autre>", "type": "<si autre>", "confiance": "forte|moyenne|faible", "raison": "<10 mots au plus>"}]}"""


class ArbitreClaude:
    """Un appel à Claude Code (abonnement, sans clé API) par lot d'images douteuses."""

    def __init__(self, modele: str = "claude-sonnet-5-5", dossier: Path | None = None, delai_s: float = 180.0):
        self.modele = modele
        self.dossier = dossier or Path.cwd()
        self.delai_s = delai_s
        self.mesures: dict = {}

    def contenu(self, references: dict[str, list[Vue]], doutes: list[Doute]) -> list[dict]:
        def image(v: Vue) -> dict:
            return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                "data": base64.b64encode(v.vignette).decode()}}

        blocs: list[dict] = [{"type": "text", "text": "Pièces connues (images de référence) :"}]
        for nom, vues in references.items():
            blocs.append({"type": "text", "text": f"Pièce « {nom} » :"})
            blocs += [image(v) for v in vues if v.vignette]
        blocs.append({"type": "text", "text": "Images à identifier :"})
        for d in doutes:
            blocs.append({"type": "text", "text": f"Image n° {d.numero} ({_hms(d.images[0].t if d.images else d.debut)}) :"})
            blocs += [image(v) for v in d.images if v.vignette]
        blocs.append({"type": "text", "text": "Réponds par le JSON demandé, un élément par image."})
        return blocs

    def __call__(self, references: dict[str, list[Vue]], doutes: list[Doute]) -> list[Verdict]:
        from .cerveau import ProcessusClaude, trouver_claude

        binaire = trouver_claude()
        if binaire is None:
            raise RuntimeError("Claude Code introuvable sur ce PC")
        commande = [binaire, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                    "--model", self.modele, "--effort", "low", "--safe-mode", "--no-session-persistence",
                    "--permission-prompts", "none", "--system-prompt", CONSIGNES_ARBITRE, "--tools", ""]

        async def demander() -> str:
            processus = ProcessusClaude(commande, self.dossier)
            await processus.demarrer()
            try:
                texte, _, self.mesures = await processus.demander(self.contenu(references, doutes), None, self.delai_s)
                return texte
            finally:
                processus.arreter()

        return analyser_verdicts(asyncio.run(demander()), {_normaliser(n): n for n in references})


def analyser_verdicts(texte: str, noms: dict[str, str]) -> list[Verdict]:
    """Réponse JSON de Claude -> verdicts ; un nom de pièce inconnu compte comme « autre »."""
    m = re.search(r"\{.*\}", texte, re.DOTALL)
    if not m:
        return []
    try:
        donnees = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    verdicts = []
    for p in donnees.get("passages", []):
        if not isinstance(p, dict) or not isinstance(p.get("numero"), int):
            continue
        nom = noms.get(_normaliser(str(p.get("piece") or "")))
        confiance = str(p.get("confiance") or "faible")
        verdicts.append(Verdict(p["numero"], nom, str(p.get("type") or ""),
                                confiance if confiance in ("forte", "moyenne", "faible") else "faible", str(p.get("raison") or "")))
    return verdicts


# --- Branchement sur l'état de l'assistant ------------------------------------------------------------------------


def consolider(etat: dict, carte: Carte) -> dict:
    """État de l'assistant vu par la carte : une seule pièce par endroit (pièces fusionnées), murs nommés par leur repère
    et leur cap, revisites et questions. Étape 13 : les murs et fenêtres du logement (« enveloppe ») reçoivent ce que la
    carte en a vu, dont le côté filmé ; un côté filmé différent du côté noté devient une question. L'état d'origine
    n'est pas modifié."""
    sortie = copy.deepcopy(etat)
    pieces_carte = {_normaliser(p.nom): p for p in carte.pieces}
    enveloppe = sortie.get("enveloppe") or {}
    parois = [e for cle in ("murs", "murs_interieurs", "fenetres") for e in enveloppe.get(cle) or []]

    def vus_dans(p: dict) -> list[dict]:
        """Les éléments de la pièce, et ceux du logement qui y ont été vus (étape 13)."""
        return [*p.get("elements", []), *(e for e in parois if p["nom"] in (e.get("pieces") or []))]

    # Pièces de l'assistant qui sont le même endroit qu'une autre sur la carte (ex. « Pièce 1 » puis « Séjour ») :
    # fusionnées, jamais deux pièces pour le même endroit.
    destination: dict[str, str] = {}
    for p in sortie.get("pieces", []):
        vus = Counter(carte.elements[e["id"]]["piece_vue"] for e in vus_dans(p)
                      if e["id"] in carte.elements and carte.elements[e["id"]]["piece_vue"])
        if _normaliser(p["nom"]) not in pieces_carte and vus:
            vu, nb = vus.most_common(1)[0]
            if nb >= 0.6 * sum(vus.values()) and _normaliser(vu) != _normaliser(p["nom"]):
                destination[p["nom"]] = vu
    fusions = []
    for source, cible in destination.items():
        piece_source = next(p for p in sortie["pieces"] if p["nom"] == source)
        piece_cible = next((p for p in sortie["pieces"] if _normaliser(p["nom"]) == _normaliser(cible)), None)
        if piece_cible is None:
            continue
        for e in piece_source["elements"]:
            if e["type"] in ("plafond", "plancher") and any(x["type"] == e["type"] for x in piece_cible["elements"]):
                continue  # créés d'office : la pièce cible a déjà les siens
            e["piece"] = piece_cible["nom"]
            piece_cible["elements"].append(e)
        for e in parois:
            if source in (e.get("pieces") or []):
                e["pieces"] = list(dict.fromkeys(piece_cible["nom"] if x == source else x for x in e["pieces"]))
        sortie["pieces"].remove(piece_source)
        fusions.append(f"« {source} » est le même endroit que « {piece_cible['nom']} » : fusionnées.")
    for p in sortie.get("pieces", []):
        pc = pieces_carte.get(_normaliser(p["nom"]))
        p["carte"] = {"reconnue": pc is not None, "passages": [[round(a, 1), round(b, 1)] for a, b in pc.passages] if pc else [],
                      "sejours": pc.sejours if pc else 0, "revisitee": bool(pc and pc.revisitee),
                      "corrections": pc.corrections if pc else []}
        for e in p.get("elements", []):
            _annoter(e, carte, [p["nom"]])
    questions = list(carte.questions)
    for e in parois:
        _annoter(e, carte, e.get("pieces") or [])
        note, filme = (e.get("orientation") or {}).get("point"), (e.get("carte") or {}).get("cote")
        if note and filme and note != filme and not (e.get("type") == "mur" and e.get("interieur")):
            questions.append(f"{e.get('nom') or e.get('description') or e['id']} ({e['id']}) : noté côté {note}, filmé côté "
                             f"{filme} : lequel ?")
    sortie["carte"] = {
        "source": carte.source, "cap": carte.cap, "fusions": fusions,
        "pieces": [{"nom": p.nom, "nommee": p.nommee, "passages": [[round(a, 1), round(b, 1)] for a, b in p.passages],
                    "sejours": p.sejours, "revisitee": p.revisitee} for p in carte.pieces],
        "questions": questions,
    }
    return sortie


def _annoter(e: dict, carte: Carte, lieux: list[str]) -> None:
    """Ce que la carte a vu de cet élément : pièce, mur visé et cap ; pour un mur, son nom par son cap et son repère ;
    avec la boussole, le côté filmé ; et s'il a été filmé ailleurs que là où il a été noté."""
    info = carte.elements.get(e["id"])
    if not info:
        return
    e["carte"] = {k: info[k] for k in ("piece_vue", "mur", "cap")}
    nom_mur = info["mur"].split(" · ")[-1] if info["mur"] else ""
    if nom_mur and not nom_mur.startswith("mur "):
        e["carte"]["cote"] = nom_mur  # « nord » : avec la boussole (sans elle, « mur A » ne dit pas de côté)
    if nom_mur and e["type"] == "mur":
        repere = e.get("repere") or _repere(e.get("nom") or "")
        e["carte"]["nom"] = (f"le {nom_mur}" if nom_mur.startswith("mur ") else f"le mur {nom_mur}") + (f", {repere}" if repere else "")
    if info["piece_vue"] and lieux and _normaliser(info["piece_vue"]) not in {_normaliser(x) for x in lieux}:
        e["carte"]["a_verifier"] = f"noté dans « {' », « '.join(lieux)} », mais filmé dans « {info['piece_vue']} »"


def _repere(nom: str) -> str:
    """« le mur ouest, celui avec la fenêtre » -> « celui avec la fenêtre »."""
    m = re.search(r",\s*(celui.*)$", nom)
    return m.group(1) if m else ""


# --- Rapport et ligne de commande ---------------------------------------------------------------------------------


def rapport(carte: Carte) -> str:
    lignes = ["# Carte des pièces", "", f"- Source : {carte.source}.",
              f"- {carte.images} images, {carte.images_cles} images clés, {carte.stations} stations, {carte.liens} liens "
              f"vérifiés ; suivi continu tenu sur {round(100 * carte.suivi)} % des images ; cap : {carte.cap} ; calcul : "
              f"{carte.calcul_s:.0f} s.", "", "## Pièces", ""]
    for p in carte.pieces:
        lignes.append(f"- **{p.nom}**{'' if p.nommee else ' (à confirmer)'} : "
                      f"{', '.join(_passage(a, b) for a, b in p.passages)}" + (" — **revisitée**" if p.revisitee else ""))
        lignes += [f"  - {c}" for c in p.corrections]
    if carte.passages_non_nommes:
        lignes.append(f"- Passages (porte, couloir entrevu) : {', '.join(_passage(a, b) for a, b in carte.passages_non_nommes)}")
    if carte.arbitrage:
        lignes += ["", "## Passages non reconnus par l'image, montrés à Claude", "",
                   "| Passage | Pièce retenue sans preuve | Claude | Confiance | Raison |", "|---|---|---|---|---|"]
        lignes += [f"| {_passage(*a['passage'])} | {a['piece_retenue'] or '—'} | {a['claude']} | {a['confiance']} | {a['raison']} |"
                   for a in carte.arbitrage]
    if carte.murs:
        lignes += ["", "## Murs vus", ""]
        lignes += [f"- {m.id} (cap {m.cap:.0f}°) : {', '.join(_passage(a, b) for a, b in m.vu) or '—'}" for m in carte.murs]
    if carte.ancrages:
        lignes += ["", "## Phrases rattachées", "", "| Instant | Phrase | Pièce vue | Cap | Mur visé | Élément de l'assistant | Accord |",
                   "|---|---|---|---|---|---|---|"]
        for a in carte.ancrages:
            lignes.append(f"| {_hms(a.t)} | {a.texte[:70]} | {a.piece or '—'} | {'—' if a.cap is None else f'{a.cap:.0f}°'} | "
                          f"{a.mur or '—'} | {', '.join(a.elements) or '—'} | {a.accord} |")
    if carte.questions:
        lignes += ["", "## Questions pour le diagnostiqueur", ""] + [f"- {q}" for q in carte.questions]
    return "\n".join(lignes) + "\n"


def traiter_visite(dossier: Path, arbitre: Arbitre | None = None, fps_max: float = FPS_MAX) -> Carte:
    entrees = charger_visite(dossier, fps_max)
    carte = construire_carte(entrees, arbitre)
    (dossier / "carte.json").write_text(json.dumps(carte.en_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    (dossier / "carte.md").write_text(rapport(carte), encoding="utf-8")
    if entrees.etat is not None:
        (dossier / "etat-consolide.json").write_text(json.dumps(consolider(entrees.etat, carte), ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    return carte


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m assistant.carte", description=__doc__.split("\n")[0])
    parser.add_argument("visite", nargs="?", type=Path, help="dossier de la visite (par défaut : la plus récente avec des images)")
    parser.add_argument("--fps", type=float, default=FPS_MAX, help="images par seconde lues dans la vidéo (suivi continu)")
    parser.add_argument("--sans-claude", action="store_true", help="ne pas montrer les passages non reconnus à Claude")
    parser.add_argument("--modele", default="claude-sonnet-5-5", help="modèle Claude de l'arbitrage (après la visite)")
    args = parser.parse_args(argv)
    dossier = args.visite
    if dossier is None:
        racine = Path(__file__).resolve().parents[1] / "sessions"
        dossier = sorted(d for d in racine.iterdir() if (d / "images").is_dir() and any((d / "images").iterdir()))[-1]
    arbitre = None if args.sans_claude else ArbitreClaude(args.modele, dossier / "claude-carte")
    carte = traiter_visite(dossier, arbitre, args.fps)
    print(rapport(carte))
    print(f"Écrit : {dossier / 'carte.json'}, {dossier / 'carte.md'}"
          + (f", {dossier / 'etat-consolide.json'}" if (dossier / "etat-consolide.json").exists() else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
