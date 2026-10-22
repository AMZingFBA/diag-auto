"""Étape 12 : carte des pièces d'une visite filmée (assistant/carte.py), sur une vidéo de synthèse dont on connaît tout.

Deux pièces (séjour, cuisine), porte à porte ; la caméra balaie le séjour, passe dans la cuisine, revient au séjour sans
que le diagnostiqueur l'annonce, puis retourne dans la cuisine. On vérifie :
- deux pièces seulement, chacune reconnue lors de la revisite (jamais de doublon), même quand l'assistant se croyait
  ailleurs ;
- chaque phrase « ce mur… » rattachée au mur visé à cet instant, avec la boussole, puis sans boussole (cap relatif tiré du
  suivi continu de la vidéo : murs « A, B, C, D ») ;
- sans rien dire : deux pièces non nommées, chacune revisitée ; à une image par seconde : le retour est tranché par
  l'arbitre (Claude) ;
- l'état de l'assistant consolidé (pièces fusionnées, murs nommés par repère et cap), puis lu par diagauto generer.

Les vidéos réelles (visite de Noah, video-001) ne sont pas versionnées : leurs tests sont sautés si elles manquent.
"""

import json
from pathlib import Path

import cv2
import pytest

from assistant.boussole import Mesure
from assistant.carte import (ArbitreClaude, Carte, Doute, Entrees, Phrase, PieceCarte, Verdict, analyser_verdicts,
                             charger_visite, consolider, construire_carte, lire_journal, traiter_visite)
from assistant.vision import Vue
from scene_synthetique import deux_pieces, tourner

PARCOURS = [("balayer", "Séjour", 0, 360, 10), ("passer", "Séjour", "Cuisine", 3), ("balayer", "Cuisine", 90, 450, 9),
            ("passer", "Cuisine", "Séjour", 3), ("balayer", "Séjour", 200, -100, 9), ("passer", "Séjour", "Cuisine", 3),
            ("balayer", "Cuisine", 300, 100, 5)]
# L'assistant entend « ici le séjour » au début et « on passe dans la cuisine » à la première entrée ; le retour au séjour
# n'est pas annoncé.
NOMS = [(0.0, "Séjour"), (11.5, "Cuisine")]
DESIGNATIONS = [("Séjour", "nord", 0.0), ("Séjour", "ouest", 0.0), ("Cuisine", "sud", 0.0), ("Séjour", "nord", 22.0),
                ("Cuisine", "est", 32.0)]


@pytest.fixture(scope="module")
def tournage():
    return tourner(deux_pieces(), PARCOURS, fps=10, graine=3)


def vues_de(tournage, pas=1):
    return [Vue(v.t, cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)) for image, v in zip(tournage.images[::pas], tournage.verite[::pas])]


def phrases_de(tournage):
    phrases = []
    for piece, mur, apres in DESIGNATIONS:
        t = tournage.instant_face(piece, mur, apres)
        phrases.append(Phrase(max(0.0, t - 0.3), t + 1.5, f"ce mur c'est de la brique ({piece} {mur})"))
    return phrases


def piece_vraie(tournage, t):
    return min(tournage.verite, key=lambda v: abs(v.t - t)).piece


def passages_hors_portes(tournage, carte, marge=2.0):
    """Images clés loin d'un passage de porte : la marche vers la porte dure 1,8 s dans la synthèse, et la porte, filmée en
    gros plan, est la même dans les deux pièces (là, même un humain hésite sur la pièce)."""
    changements = [b.t for a, b in zip(tournage.verite, tournage.verite[1:]) if a.piece != b.piece]
    return [(t, p) for t, p in carte.piece_des_cles if all(abs(t - c) > marge for c in changements)]


@pytest.fixture(scope="module")
def carte_boussole(tournage):
    capteurs = [Mesure(c["t"], c["cap"]) for c in tournage.capteurs]
    return construire_carte(Entrees(vues_de(tournage), "synthèse", capteurs, NOMS, phrases_de(tournage)))


def test_deux_pieces_revisitees_jamais_de_doublon(tournage, carte_boussole):
    carte = carte_boussole
    assert [p.nom for p in carte.pieces] == ["Séjour", "Cuisine"]
    assert all(p.revisitee and len(p.passages) == 2 for p in carte.pieces)
    # Le retour au séjour n'était pas annoncé : l'assistant se croyait encore dans la cuisine, l'image l'emporte.
    assert any("l'image montre « Séjour »" in c for c in carte.pieces[0].corrections)
    justes = [(t, p) for t, p in passages_hors_portes(tournage, carte) if p == piece_vraie(tournage, t)]
    assert len(justes) == len(passages_hors_portes(tournage, carte))  # aucune erreur loin des portes


def test_phrases_rattachees_au_mur_vise_avec_la_boussole(carte_boussole):
    murs = [a.mur for a in carte_boussole.ancrages]
    assert murs == ["Séjour · nord", "Séjour · ouest", "Cuisine · sud", "Séjour · nord", "Cuisine · est"]
    assert carte_boussole.cap == "boussole"


def test_sans_boussole_murs_relatifs_coherents(tournage):
    carte = construire_carte(Entrees(vues_de(tournage), "synthèse", [], NOMS, phrases_de(tournage)))
    murs = [a.mur for a in carte.ancrages]
    assert carte.cap == "relatif (suivi de la vidéo)"
    assert all(m and " · mur " in m for m in murs)  # pas de nord ni d'est inventés
    assert murs[0] == murs[3]  # le même mur du séjour, à la revisite
    assert len({murs[0], murs[1]}) == 2 and len({murs[2], murs[4]}) == 2  # deux murs différents, deux noms différents


def test_sans_rien_dire_deux_pieces_non_nommees_revisitees(tournage):
    capteurs = [Mesure(c["t"], c["cap"]) for c in tournage.capteurs]
    carte = construire_carte(Entrees(vues_de(tournage), "synthèse", capteurs, [], []))
    assert [p.nom for p in carte.pieces] == ["Pièce non nommée 1", "Pièce non nommée 2"]
    assert all(p.revisitee for p in carte.pieces)
    assert len([q for q in carte.questions if "nouvelle pièce" in q]) == 2  # on demande leur nom, rien n'est inventé


class ArbitreVerite:
    """Faux Claude : regarde la vérité de la vidéo de synthèse."""

    def __init__(self, tournage):
        self.tournage = tournage
        self.doutes: list[Doute] = []
        self.references: dict = {}

    def __call__(self, references, doutes):
        self.references, self.doutes = references, doutes
        return [Verdict(d.numero, piece_vraie(self.tournage, (d.debut + d.fin) / 2), confiance="forte", raison="vérité")
                for d in doutes]


def test_une_image_par_seconde_retour_tranche_par_l_arbitre(tournage):
    sans = construire_carte(Entrees(vues_de(tournage, pas=10), "1 image/s", [], NOMS, []))
    arbitre = ArbitreVerite(tournage)
    avec = construire_carte(Entrees(vues_de(tournage, pas=10), "1 image/s", [], NOMS, []), arbitre)
    assert set(arbitre.references) == {"Séjour", "Cuisine"} and arbitre.doutes
    assert all(d.images for d in arbitre.doutes)

    def justes(carte):
        return sum(p == piece_vraie(tournage, t) for t, p in passages_hors_portes(tournage, carte))

    assert justes(avec) > justes(sans)
    assert [p.nom for p in avec.pieces] == ["Séjour", "Cuisine"] and avec.pieces[0].revisitee
    assert avec.arbitrage and all(a["claude"] in ("Séjour", "Cuisine") for a in avec.arbitrage)


def test_reponse_de_claude_lue_sans_rien_inventer():
    noms = {"sejour": "Séjour", "cuisine": "Cuisine"}
    texte = ('Voici : {"passages": [{"numero": 1, "piece": "séjour", "confiance": "forte", "raison": "table"},'
             ' {"numero": 2, "piece": "autre", "type": "couloir", "confiance": "moyenne"},'
             ' {"numero": 3, "piece": "Salle de bains", "confiance": "certaine"}, {"piece": "Cuisine"}]}')
    verdicts = analyser_verdicts(texte, noms)
    assert [(v.numero, v.piece, v.type, v.confiance) for v in verdicts] == [
        (1, "Séjour", "", "forte"), (2, None, "couloir", "moyenne"), (3, None, "", "faible")]
    assert analyser_verdicts("pas de JSON", noms) == []


def test_arbitre_claude_montre_les_images_avec_leurs_noms():
    vue = Vue(1.0, None, vignette=b"\xff\xd8jpeg")
    contenu = ArbitreClaude().contenu({"Séjour": [vue]}, [Doute(1, 340.0, 347.0, "Cuisine", [vue])])
    textes = [b["text"] for b in contenu if b["type"] == "text"]
    assert "Pièce « Séjour » :" in textes and "Image n° 1 (0:01) :" in textes
    assert sum(b["type"] == "image" for b in contenu) == 2


def test_lecture_d_une_vraie_video_et_du_journal(tmp_path, tournage):
    dossier = tmp_path / "visite"
    dossier.mkdir()
    tournage.ecrire(dossier / "video.mp4")
    (dossier / "capteurs-continus.json").write_text(json.dumps({"mesures": tournage.capteurs}), encoding="utf-8")
    journal = [{"evenement": "debut", "t": 0.0, "piece": "Séjour"},
               {"evenement": "decision", "t": 11.5, "resultats": [{"action": {"outil": "piece_courante", "nom": "Cuisine"},
                                                                    "statut": "accepte"}]},
               {"evenement": "extraction", "t": 3.0, "t_debut": 1.0, "t_fin": 2.5, "texte": "Ce mur donne dehors.",
                "resultats": [{"statut": "accepte", "element": "M1"}]},
               {"evenement": "extraction", "t": 9.0, "texte": "Il est en brique.", "resultats": []}]
    (dossier / "journal.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in journal), encoding="utf-8")
    noms, phrases = lire_journal(dossier)
    assert noms == [(0.0, "Séjour"), (11.5, "Cuisine")]
    assert (phrases[0].t_debut, phrases[0].elements, phrases[0].estimee) == (1.0, ["M1"], False)
    assert phrases[1].estimee and phrases[1].t_fin == 8.7  # ancien journal : instants estimés
    entrees = charger_visite(dossier)
    assert entrees.source.startswith("vidéo continue") and len(entrees.vues) == len(tournage.images)
    assert entrees.vues[0].vignette and len(entrees.capteurs) == len(tournage.capteurs)
    carte = traiter_visite(dossier)
    assert [p.nom for p in carte.pieces] == ["Séjour", "Cuisine"]
    assert (dossier / "carte.json").is_file() and (dossier / "carte.md").is_file()


def test_etat_consolide_une_seule_piece_par_endroit():
    etat = {"pieces": [
        {"nom": "Pièce 1", "elements": [{"id": "M1", "type": "mur", "piece": "Pièce 1", "t": 2.0, "nom": "le mur, celui avec le tableau"},
                                        {"id": "PL1", "type": "plafond", "piece": "Pièce 1", "t": 0.0}]},
        {"nom": "Séjour", "elements": [{"id": "M2", "type": "mur", "piece": "Séjour", "t": 30.0, "nom": "le mur nord"},
                                       {"id": "PL2", "type": "plafond", "piece": "Séjour", "t": 25.0}]},
        {"nom": "Cuisine", "elements": [{"id": "F1", "type": "fenetre", "piece": "Cuisine", "t": 60.0, "nom": "la fenêtre"}]}],
        "logement": {"elements": []}}
    carte = Carte("essai", 90.0, 10, 10, 1.0, 3, 5, "boussole",
                  [PieceCarte("Séjour", True, [(0.0, 40.0)], 6), PieceCarte("Cuisine", True, [(41.0, 90.0)], 4)], [], [], [],
                  {"M1": {"piece_dite": "Pièce 1", "piece_vue": "Séjour", "cap": 3.0, "mur": "Séjour · nord", "nom": "", "t": 2.0},
                   "M2": {"piece_dite": "Séjour", "piece_vue": "Séjour", "cap": 1.0, "mur": "Séjour · nord", "nom": "", "t": 30.0},
                   "F1": {"piece_dite": "Cuisine", "piece_vue": "Séjour", "cap": 180.0, "mur": "Séjour · sud", "nom": "", "t": 60.0}},
                  ["M1 et M2 visent le même mur (Séjour · nord) : même mur, ou deux murs du même côté ?"])
    sortie = consolider(etat, carte)
    assert [p["nom"] for p in sortie["pieces"]] == ["Séjour", "Cuisine"]  # « Pièce 1 » était le séjour
    sejour = sortie["pieces"][0]
    assert [e["id"] for e in sejour["elements"]] == ["M2", "PL2", "M1"]  # plafond de « Pièce 1 » non dupliqué
    assert sejour["elements"][2]["carte"]["nom"] == "le mur nord, celui avec le tableau"
    assert "a_verifier" in sortie["pieces"][1]["elements"][0]["carte"]  # noté en cuisine, filmé au séjour
    assert sortie["carte"]["fusions"] == ["« Pièce 1 » est le même endroit que « Séjour » : fusionnées."]
    assert [p["nom"] for p in etat["pieces"]] == ["Pièce 1", "Séjour", "Cuisine"]  # l'état d'origine n'est pas modifié


# --- Vraies vidéos (non versionnées) --------------------------------------------------------------------------------

RACINE = Path(__file__).resolve().parents[1]
VISITE_NOAH = RACINE / "sessions" / "20261022-120410-53ecb1"
VIDEO_001 = RACINE.parent / "samples" / "video-001" / "video.mp4"


@pytest.mark.skipif(not (VISITE_NOAH / "images").is_dir(), reason="visite de Noah absente (non versionnée)")
def test_visite_reelle_de_noah_sejour_cuisine_et_retour_au_sejour():
    entrees = charger_visite(VISITE_NOAH)
    sans = construire_carte(entrees)
    assert [p.nom for p in sans.pieces] == ["Séjour", "Cuisine"]  # jamais de doublon
    assert sans.cap == "inconnu"  # images à 1/s sans capteurs : pas de murs inventés
    assert not sans.murs

    class ArbitreNoah:  # faux Claude : de retour au séjour dès 5:39 sur les images (table, fauteuils, voilages)
        def __init__(self):
            self.doutes = []

        def __call__(self, references, doutes):
            self.doutes += doutes
            return [Verdict(d.numero, "Séjour", confiance="forte", raison="table et voilages")
                    for d in doutes if d.images[0].t >= 339]

    arbitre = ArbitreNoah()
    avec = construire_carte(entrees, arbitre)
    # Le retour au séjour (5:39 à 5:47, filmé depuis la cuisine, après le trajet caméra au plafond) n'est pas reconnu par la
    # géométrie : il est montré à Claude.
    assert any(d.images[0].t >= 339 and d.piece == "Cuisine" for d in arbitre.doutes)  # image par image
    assert avec.piece_a(345.0) == "Séjour" and avec.pieces[0].revisitee


VISITE_APRES_MIDI = RACINE / "sessions" / "20261022-153605-67f6df"
# Ce que montre chaque image, relevé image par image (entre deux : l'escalier de l'entrée).
VUES_APRES_MIDI = [(0, 178.5, "U"), (182.5, 254.5, "Cuisine"), (256.5, 428.5, "U"), (428.5, 689.5, "Chambre"),
                   (689.5, 706, "U")]


def vue_apres_midi(t, marge=0.0):
    """Pièce filmée à l'instant t ; avec une marge, None à moins de ``marge`` secondes d'une porte (chaque image clé prend
    le verdict de l'image montrée la plus proche, une toutes les 2 s près d'une porte)."""
    return next((p for a, b, p in VUES_APRES_MIDI if a + (marge if a else 0) <= t <= b - marge), None)


@pytest.mark.skipif(not (VISITE_APRES_MIDI / "images").is_dir(), reason="visite de Noah absente (non versionnée)")
def test_visite_reelle_apres_midi_porte_et_nom_en_retard():
    entrees = charger_visite(VISITE_APRES_MIDI)
    sans = construire_carte(entrees)
    assert [p.nom for p in sans.pieces] == ["U", "Cuisine", "Chambre"]  # jamais de doublon
    # Depuis la pièce U, on voyait la chambre par la porte, et les premières images de la chambre portaient encore le nom
    # « U » : la chambre ne doit pas s'y reconnaître.
    assert sans.piece_a(450.0) == "Chambre" and sans.piece_a(600.0) == "Chambre"
    assert sans.piece_a(220.0) == "Cuisine" and sans.piece_a(360.0) == "U"
    assert [p.revisitee for p in sans.pieces] == [True, False, False]  # les trous d'images ne sont pas des retours

    class ArbitreVerite:  # faux Claude qui dit ce que montre l'image (rien pour l'escalier)
        def __call__(self, references, doutes):
            return [Verdict(d.numero, vue_apres_midi(d.images[0].t), confiance="forte", raison="vérité")
                    for d in doutes if vue_apres_midi(d.images[0].t)]

    avec = construire_carte(entrees, ArbitreVerite())
    assert [p.nom for p in avec.pieces] == ["U", "Cuisine", "Chambre"]
    # La voix annonce la pièce jusqu'à 15 s après la porte : les images d'avant l'annonce sont montrées à Claude.
    fausses = [(t, p) for t, p in avec.piece_des_cles if vue_apres_midi(t, 1.0) and p and p != vue_apres_midi(t, 1.0)]
    assert not fausses
    assert [p.revisitee for p in avec.pieces] == [True, False, False] and avec.pieces[0].sejours == 3


@pytest.mark.skipif(not VIDEO_001.is_file(), reason="video-001 absente (non versionnée)")
def test_video_001_une_seule_piece():
    from assistant.vision import lire_video

    vues, _ = lire_video(VIDEO_001, 15)
    carte = construire_carte(Entrees(vues, "video-001", [], [], []))
    assert len(carte.pieces) == 1  # une seule pièce filmée : jamais coupée en deux
    assert carte.cap == "relatif (suivi de la vidéo)" and len(carte.murs) >= 3


# --- Étape 13 : « le mur de gauche », « le deuxième mur », boussole bruitée, état par côté -------------------------------


def test_mur_designe_par_sa_place_ou_son_rang(tournage):
    nord, est = tournage.instant_face("Séjour", "nord"), tournage.instant_face("Séjour", "est")
    sud = tournage.instant_face("Séjour", "sud")
    phrases = [Phrase(nord, nord + 0.3, "ce mur c'est de la brique"), Phrase(nord, nord + 0.3, "le mur de gauche est en parpaing"),
               Phrase(nord, nord + 0.3, "sur ma droite une fenêtre"), Phrase(est, est + 0.3, "celui derrière moi donne sur le couloir"),
               Phrase(sud, sud + 0.3, "le deuxième mur est isolé")]  # le deuxième montré : celui de gauche
    capteurs = [Mesure(c["t"], c["cap"]) for c in tournage.capteurs]
    carte = construire_carte(Entrees(vues_de(tournage), "synthèse", capteurs, NOMS, phrases))
    assert [(a.par, a.mur) for a in carte.ancrages] == [
        ("ce", "Séjour · nord"), ("de gauche", "Séjour · ouest"), ("sur ma droite", "Séjour · est"),
        ("celui derrière", "Séjour · ouest"), ("deuxième mur", "Séjour · ouest")]


@pytest.mark.parametrize("graine", [1, 3])
def test_boussole_bruitee_une_mesure_par_seconde(tournage, graine):
    """Une mesure de boussole par seconde, à ±20° (vieux téléphone, ou pièce perturbée) : l'axe des murs est celui du
    logement, recalé sur toutes les mesures, et chaque phrase tombe sur le bon mur."""
    import random

    rng = random.Random(graine)
    capteurs = [Mesure(c["t"], (c["cap"] + rng.gauss(0, 20)) % 360) for c in tournage.capteurs[::10]]
    carte = construire_carte(Entrees(vues_de(tournage), "synthèse", capteurs, NOMS, phrases_de(tournage)))
    assert [a.mur for a in carte.ancrages] == ["Séjour · nord", "Séjour · ouest", "Cuisine · sud", "Séjour · nord", "Cuisine · est"]
    assert len({p.axe for p in carte.pieces}) == 1 and min(carte.pieces[0].axe, 90 - carte.pieces[0].axe) < 15


def test_etat_par_cote_consolide():
    """Étape 13 : murs et fenêtres sont ceux du logement. Ils reçoivent ce que la carte en a vu ; la pièce « Pièce 1 »,
    même endroit que le séjour, est fusionnée ; un côté filmé différent du côté noté devient une question."""
    mur = {"id": "M1", "type": "mur", "nom": "le mur ouest", "pieces": ["Pièce 1"], "orientation": {"point": "ouest"}, "t": 2.0}
    fenetre = {"id": "F1", "type": "fenetre", "nom": "la fenêtre ouest", "pieces": ["Pièce 1", "Séjour"], "support": "M1",
               "orientation": {"point": "ouest"}, "t": 3.0}
    etat = {"pieces": [{"nom": "Pièce 1", "elements": []}, {"nom": "Séjour", "elements": []}],
            "enveloppe": {"murs": [mur], "murs_interieurs": [], "fenetres": [fenetre]}, "logement": {"elements": []}}
    carte = Carte("essai", 60.0, 10, 10, 1.0, 2, 5, "boussole", [PieceCarte("Séjour", True, [(0.0, 60.0)], 10)], [], [], [],
                  {"M1": {"piece_dite": "Pièce 1", "piece_vue": "Séjour", "cap": 2.0, "mur": "Séjour · nord", "nom": "", "t": 2.0},
                   "F1": {"piece_dite": "Pièce 1", "piece_vue": "Séjour", "cap": 5.0, "mur": "Séjour · nord", "nom": "", "t": 3.0}}, [])
    sortie = consolider(etat, carte)
    assert [p["nom"] for p in sortie["pieces"]] == ["Séjour"]
    m1, f1 = sortie["enveloppe"]["murs"][0], sortie["enveloppe"]["fenetres"][0]
    assert m1["pieces"] == ["Séjour"] and f1["pieces"] == ["Séjour"]
    assert (m1["carte"]["cote"], m1["carte"]["nom"]) == ("nord", "le mur nord")
    assert sortie["carte"]["questions"] == ["le mur ouest (M1) : noté côté ouest, filmé côté nord : lequel ?",
                                            "la fenêtre ouest (F1) : noté côté ouest, filmé côté nord : lequel ?"]
