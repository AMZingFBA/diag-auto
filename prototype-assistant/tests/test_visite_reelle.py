"""Étape 5 de Noah : ce qui n'allait pas au test réel du 22/10/2026 (sessions/20261022-083308-20ef54).

Noah : « trop lent, ne s'adapte pas, je dois répéter, je ne sais pas c'est quel mur 3 / mur 4 ».
1. noms de murs abstraits (« Le mur 3 est en quoi ? ») ;
2. phrases globales ignorées (« le reste donne sur l'intérieur ou les voisins ») ;
3. questions inutiles (matériau d'un mur sur local chauffé) ;
4. valeurs aberrantes (un mur de 30 m de long dans un séjour) ;
5. transcription trop lente (second avis de Whisper seulement quand les règles n'ont pas compris) ;
6. mots métier mal transcrits (« combles bleus », « des pays isolés »).
"""

import asyncio
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from assistant import parcours
from assistant.actions import appliquer
from assistant.cerveau import Decision
from assistant.checklist import Checklist
from assistant.extraction import Cible, extraire, valeur_normalisee
from assistant.garde import Questions
from assistant.lexique import corriger
from assistant.boussole import point_cardinal
from assistant.plausibilite import filtrer, verifier
from assistant.reglages import Reglages
from assistant.serveur import creer_app
from assistant.session import Session
from assistant.simulation import CerveauSimulation
from assistant.vad import Phrase
from test_dialogue import visite


def dire(c: Checklist, phrase: str, cible: str | None = None):
    extraction = extraire(phrase, c, Cible.depuis_code(cible, c) if cible else None)
    resultats = appliquer(c, extraction.actions, 10.0, [phrase])
    assert all(r["statut"] == "accepte" for r in resultats if r["raison"] != "pièce déduite de l'image, à confirmer"), resultats
    return extraction


def sejour() -> Checklist:
    c = Checklist()
    c.definir_piece("Séjour", 0)
    return c


def questions(c: Checklist, dernier_id: str | None = None) -> list[str]:
    return [q.texte for q in parcours.questions(c, dernier_id)]


# --- 1. Des noms de murs compréhensibles, jamais « le mur 3 » ------------------------------------------------

def test_mur_nomme_par_ce_qui_en_a_ete_dit():
    c = sejour()
    dire(c, "Ce premier mur donne sur l'extérieur. Il y a trois fenêtres dessus, c'est du bois.")
    dire(c, "Un autre mur donne vers un voisin.")
    dire(c, "C'est un mur qui donne derrière sur des toilettes.")
    murs = [e for e in c.elements if e.type == "mur"]
    assert [c.nom(m, demonstratif=False) for m in murs] == ["le mur des 3 fenêtres", "le mur côté voisin", "le mur côté WC"]
    assert c.trouver_element("F1").support == "M1"  # « trois fenêtres dessus » : sur ce mur
    assert c.nom(murs[-1]) == "ce mur"  # celui dont on vient de parler


def test_repere_dit_et_boussole():
    c = sejour()
    dire(c, "Le mur avec la télé donne dehors, en brique.")
    assert c.nom(c.trouver_element("M1"), demonstratif=False) == "le mur avec la télé"
    mur = c.signaler_element("mur", "le mur 2", 5, source="voix")
    mur.orientation, mur.orientation_source = point_cardinal(355), "boussole"
    c.signaler_element("mur", "le mur 3", 6, source="voix")
    assert c.nom(mur) == "le mur nord"
    assert [point_cardinal(cap) for cap in (0, 44, 90, 180, 200, 275, 330)] == ["nord", "nord", "est", "sud", "sud", "ouest", "nord"]


def test_sans_indice_la_vignette_jamais_un_numero():
    c = sejour()
    premier = c.signaler_element("mur", "le mur 1", 1, source="voix")
    c.signaler_element("mur", "le mur 2", 2, source="voix")
    assert c.nom(premier) == "le premier mur"  # sans image (essais écrits)
    premier.image = "00001.00.jpg"
    assert c.nom(premier) == "le mur affiché"  # la vignette est montrée avec la question


def test_les_questions_ne_disent_jamais_mur_et_un_numero():
    c = sejour()
    for phrase in ("Ce mur donne dehors.", "Un autre mur donne sur le garage.", "Le troisième mur donne dehors, en brique."):
        dire(c, phrase)
    textes = questions(c)
    assert textes[0] == "Ce mur, quelle épaisseur ?"  # le dernier mur décrit
    assert "Le mur côté garage est en quoi ?" in textes
    assert not [t for t in textes if any(f"mur {n}" in t for n in range(1, 9))]


def test_question_de_claude_avec_un_numero_refusee():
    c = sejour()
    c.signaler_element("mur", "le mur 3", 1, source="voix")
    q = Questions()
    assert q.filtrer("Ce mur 3, il est en quoi ?", "M1.materiau", c, 0)[2] == "nom abstrait interdit (« le mur 3 »)"
    assert q.filtrer("Et le quatrième mur, il donne sur quoi ?", "", c, 0)[2] == "nom abstrait interdit (« le mur 3 »)"


# --- 2. Phrases globales ------------------------------------------------------------------------------

def test_un_seul_mur_exterieur_et_le_reste_sur_l_interieur():
    """La phrase réelle de Noah : elle clôt la pièce, sans mur en plus ni question de matériau."""
    c = sejour()
    dire(c, "Ce premier mur donne sur l'extérieur, brique 30, isolé par l'intérieur.")
    c.signaler_element("mur", "le mur 2", 20)  # vu à l'image, pas encore décrit
    dire(c, "Il y a juste un mur dans la pièce qui donne sur l'extérieur. Le reste ne donne que sur l'intérieur de la maison "
            "ou sinon un voisin.", cible="M2.donne_sur")
    murs = [e for e in c.elements if e.type == "mur"]
    assert [(m.description, m.valeur("donne_sur").valeur) for m in murs] == [
        ("le mur 1", "extérieur"), ("le mur 2", "local chauffé"), ("les autres murs", "local chauffé")]
    assert c.murs_complets() and not [m for m in c.manques_piece() if m.type == "mur"]
    # Étape 13 : les fenêtres du mur qui donne dehors, puis le plafond du logement.
    assert questions(c)[:2] == ["Le mur extérieur : des fenêtres ou une porte ?",
                                "Au-dessus du logement : combles, terrasse ou un autre logement ?"]


def test_la_piece_fait_quatre_murs():
    # Étape 13 : le nombre de murs d'une pièce est noté pour son plan, mais le DPE ne se fait pas pièce par pièce : on
    # demande ce qui entoure le logement, jamais « il reste 2 murs ».
    c = sejour()
    dire(c, "Ce mur donne dehors, brique 30 cm, isolé.")
    dire(c, "Un autre mur donne sur le voisin.")
    dire(c, "En fait, cette pièce fait quatre murs.")
    assert c.pieces["sejour"].nombre_murs.valeur == "4"
    assert not [q for q in questions(c) if "reste" in q or "pièce" in q]
    assert "Un autre mur autour du logement, à me montrer ?" in questions(c)


def test_pareil_pour_celui_la():
    c = sejour()
    dire(c, "Ce mur donne dehors, brique 30 cm, isolé par l'intérieur.")
    dire(c, "Pareil pour celui-là.")
    mur = c.trouver_element("M2")
    assert {k: v[-1].valeur for k, v in mur.valeurs.items()} == {"donne_sur": "extérieur", "materiau": "brique", "epaisseur": "30 cm",
                                                                 "isolation": "ITI"}
    assert mur.valeur("materiau").note == "pareil que le mur extérieur"


# --- 3. Pas de questions inutiles ------------------------------------------------------------------------

def test_mur_sur_une_autre_piece_ou_un_voisin_rien_a_demander():
    c = sejour()
    dire(c, "C'est un mur qui donne derrière sur des toilettes.")
    dire(c, "Un autre mur donne vers un voisin.")
    assert not [m for m in c.manques_piece() if m.type == "mur"]
    # « Le mur de la chambre donne dehors » : la chambre ne fait pas croire qu'il donne sur la chambre.
    c = sejour()
    dire(c, "Le mur de la chambre donne dehors.")
    assert c.trouver_element("M1").valeur("donne_sur").valeur == "extérieur"


def test_valeur_libre_de_claude_ramenee_au_vocabulaire():
    assert valeur_normalisee("mur", "donne_sur", "toilettes") == "local chauffé : WC"
    assert valeur_normalisee("mur", "donne_sur", "local chauffé (voisin)") == "local chauffé (voisin)"
    assert valeur_normalisee("mur", "isolation", "ITI laine de verre 10 cm") == "ITI laine de verre 10 cm"


# --- 4. Valeurs aberrantes et contradictions ----------------------------------------------------------------

def test_plausibilite():
    assert verifier("mur", "longueur", "30 m") == (False, "3 m")
    assert verifier("mur", "longueur", "4,50 m") == (True, None)
    assert verifier("mur", "epaisseur", "300 cm") == (False, "30 cm")
    assert verifier("chauffage", "annee", "2035") == (False, None)
    gardees, propositions, ecartees = filtrer([{"outil": "enregistrer_reponse", "element_id": "M1", "type": "mur",
                                                "champ": "longueur", "valeur": "30 m", "citation": "il fait 30 mètres"}])
    assert not gardees and len(ecartees) == 1
    assert propositions[0]["valeur"] == "3 m" and propositions[0]["question"] == "J'ai compris 30 m de long : plutôt 3 m ?"


def test_mur_de_30_metres_propose_3_metres(tmp_path):
    session, questions_apres, _ = asyncio.run(visite(tmp_path, [
        "Ici c'est le séjour.", "Ce mur fait 30 mètres de long, il donne dehors.", "Oui."]))
    assert questions_apres[1] == ["J'ai compris 30 m de long : plutôt 3 m ?"]
    longueur = session.checklist.trouver_element("M1").valeur("longueur")
    assert longueur.valeur == "3 m" and longueur.note == "confirmé : « 3 m »"


def test_reprise_dans_la_meme_phrase_n_est_pas_une_contradiction():
    c = sejour()
    dire(c, corriger("Le plafond isolé dans le plafonds des pays isolés."))
    plafond = c.element_de_piece("plafond")
    assert plafond.valeur("isolation").valeur == "non isolé" and not c.signalements


# --- 5 et 6. Transcription : corrections métier, pas de devinette sur une question --------------------------

@pytest.mark.parametrize("entendu, corrige", [
    ("Au-dessus du plafond, des combles bleus.", "Au-dessus du plafond, des combles perdus."),
    ("Et le mur y embrique.", "Et le mur est en brique."),
    ("Le plafond des pays isolés.", "Le plafond est pas isolés."),
    ("Le plafond isolé dans le plafonds DPE isolé.", "Le plafond isolé dans le plafonds est pas isolé."),
    ("Au- dessus du plafond, il y a des comblots, exactement.", "Au- dessus du plafond, il y a des combles, exactement."),
])
def test_mots_metier_mal_transcrits(entendu, corrige):
    assert corriger(entendu) == corrige


def test_pas_de_devinette_sur_une_phrase_longue_ou_une_question():
    c = sejour()
    c.signaler_element("mur", "le mur 1", 1, source="voix")
    extraction = dire(c, "Laine de verre de 30 cm.", cible="M1.materiau")
    assert extraction.proposition is None  # plus de « J'ai compris pierre ? »
    assert c.trouver_element("M1").valeur("isolation").valeur == "isolé laine de verre 30 cm"
    extraction = dire(c, "Il te faut quoi d'être comme information sur ce mur ?", cible="M1.materiau")
    assert c.trouver_element("M1").valeur("materiau") is None and extraction.demande == "manques"  # plus de « tuffeau »


def test_quel_mur_et_qu_est_ce_qui_manque(tmp_path):
    session, questions_apres, _ = asyncio.run(visite(tmp_path, [
        "Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm, isolé.", "Un autre mur donne sur le garage.",
        "Quel mur ?", "Il te faut quoi d'autre ?"]))
    assert questions_apres[2] == ["Ce mur est en quoi ?"]
    assert questions_apres[3] == ["Je parle du mur côté garage. Il est en quoi ?"]
    assert questions_apres[4] == ["Pour le mur côté garage, il me manque le matériau, l'épaisseur et l'isolation. Il est en quoi ?"]


class TranscripteurRapideFactice:
    """Le moteur rapide entend mal ; Whisper, en second avis, entend juste (ou n'entend que du bruit)."""

    nom = "factice"

    def __init__(self, rapide: list[str], whisper: list[str]):
        self.rapide, self.whisper, self.second = list(rapide), list(whisper), 0

    def prechauffer(self):
        pass

    def transcrire(self, audio):
        return self.rapide.pop(0)

    def second_avis(self, audio):
        self.second += 1
        return self.whisper.pop(0)


class CerveauCompteur(CerveauSimulation):
    def __init__(self):
        self.appels = 0

    async def decider(self, contexte, sur_dire=None):
        self.appels += 1
        return Decision()


def test_second_avis_de_whisper_seulement_si_pas_compris(tmp_path):
    async def scenario():
        # 2e phrase : Whisper entend juste ; 3e : ce n'était que du bruit.
        transcripteur = TranscripteurRapideFactice(["Ici c'est le séjour.", "Ce mur donne de or.", "er."], ["Ce mur donne dehors.", ""])
        cerveau = CerveauCompteur()
        reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=tmp_path, veille_s=1000,
                            questions_par_minute=60)
        session = Session("essai", tmp_path, cerveau, cerveau, transcripteur, reglages)
        dits = []

        async def envoyer(m):
            if m["type"] == "dire":
                dits.append(m["texte"])

        session.envoyer = envoyer
        await session.demarrer()
        for k in range(3):
            await session._file.put(("audio", Phrase(np.zeros(16_000, np.float32), 2.0 * k, 2.0 * k + 1), time.monotonic(), k + 1))
            await asyncio.sleep(0.05)
            while session.occupe or not session._file.empty():
                await asyncio.sleep(0.02)
        await session.terminer()
        return session, transcripteur, cerveau, dits

    session, transcripteur, cerveau, dits = asyncio.run(scenario())
    assert transcripteur.second == 2  # seulement pour les phrases que les règles n'ont pas comprises
    assert session.checklist.trouver_element("M1").valeur("donne_sur").valeur == "extérieur"
    assert dits == ["Ce mur donne sur quoi ?", "Ce mur est en quoi ?"]
    assert cerveau.appels == 0  # ni pour la phrase rattrapée par Whisper, ni pour le bruit


def test_vignette_et_boussole_avec_la_question(tmp_path):
    with TestClient(creer_app(Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=tmp_path,
                                       veille_s=1000))) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "debut", "piece": "Séjour"})
            session_id = next(m for m in iter(ws.receive_json, None) if m["type"] == "statut")["session"]
            ws.send_bytes(bytes([2]) + np.float64(3.0).tobytes() + b"\xff\xd8image du mur")
            ws.send_json({"type": "capteurs", "t": 3.0, "cap": 92})
            ws.send_json({"type": "texte", "texte": "Ce mur donne dehors, en brique."})
            question = next(m for m in iter(ws.receive_json, None) if m["type"] == "dire" and "épaisseur" in m["texte"])
            assert question["image"] == f"/api/sessions/{session_id}/images/00003.00.jpg"
            assert client.get(question["image"]).content == b"\xff\xd8image du mur"
            assert client.get(f"/api/sessions/{session_id}/images/..%2Fjournal.jsonl").status_code == 404


# --- La visite réelle de Noah, rejouée en texte (transcription du moteur rapide sur audio.wav) ----------------

PHRASES_DE_NOAH = [
    "Ici c'est le séjour.",
    "Alors c'est le premier mur Ce premier mur y donne sur l'extérieur y fait trente trente mètres il y a trois fenêtres "
    "dessus c'est du bois",
    "c'est une laine de verre de trente centimètres et l'.",
    "Et le mur est en brique.",
    "Trente centimètres.",
    "Au- dessus du plafond, il y a des comblots, exactement.",
    "Le plafond est isolé dans le plafond dépa isolés.",
    "Le plafond n'est pas isolé.",
    "Il te faut quoi d'autre comme information sur ce mur?",
    "Un sous- sol.",
    "Et là, le mur que j suis en train de te montrer y donne sur de deux maisons, derrière, d'oxula, et mur qui donnent vers "
    "un voisin simplement voilà",
    "c'est un mur qui donne derrière sur des toilettes par as une chambre, et là, voilà, c'est un mur qui.",
    "Ben en fait, ce mur, c c'est cette pièce fait quatre f a quatre murs voilà toute la pièce.",
    "Quel mur.",
    "Il y a juste un mur dans la pièce qui donne sur l'extérieur le reste donne que sur l'intérieur, de la maison ou sinon "
    "un voisin.",
]


def test_visite_reelle_de_noah(tmp_path):
    session, questions_apres, _ = asyncio.run(visite(tmp_path, PHRASES_DE_NOAH))
    toutes = [q for posees in questions_apres for q in posees]
    assert not [q for q in toutes if any(f"mur {n}" in q for n in range(1, 9)) or "quatrième" in q]
    assert not [q for q in toutes if "pierre" in q or "tuffeau" in q or "répét" in q]
    c = session.checklist
    murs = {c.nom(e, demonstratif=False): e.valeur("donne_sur").valeur for e in c.elements if e.type == "mur"}
    assert murs == {"le mur des 3 fenêtres": "extérieur", "le mur côté voisin": "local chauffé (voisin)",
                    "le mur côté WC": "local chauffé : WC", "les autres murs": "local chauffé"}
    mur = c.trouver_element("M1")
    assert (mur.valeur("materiau").valeur, mur.valeur("epaisseur").valeur) == ("brique", "30 cm")
    assert mur.valeur("longueur") is None  # « trente mètres » n'est pas noté comme une longueur de mur
    assert c.element_de_piece("plafond").valeur("isolation").valeur == "non isolé"
    assert c.murs_complets()
    # « Il te faut quoi d'autre sur ce mur ? » : réponse, puis la question en attente reposée. Étape 13 : les fenêtres du mur
    # sont demandées avant le plancher ; « Un sous-sol », dit alors (il répondait à l'ancien parcours), n'est pas pris
    # pour des volets : une confirmation est demandée, rien n'est noté.
    assert questions_apres[8] == ["Pour le mur des 3 fenêtres, j'ai tout. Des volets ?"]
    assert c.trouver_element("F1").valeur("volets") is None
    assert questions_apres[13] == ["Un mur qu'on n'a pas encore décrit. Un autre mur autour du logement, à me montrer ?"]
