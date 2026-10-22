"""Étape 10 de Noah, côté serveur : faux « Hors réseau ».

Le téléphone envoie un battement de cœur toutes les 2 s ; le serveur répond tout de suite, même quand Claude réfléchit (c'est
ce qui distingue « serveur lent » de « pas de réseau »). Une erreur sur un message ne coupe plus la liaison. À la
reconnexion, le serveur redit ce qu'il a dit pendant la coupure, et traite le son gardé par le téléphone."""

import asyncio
import json
import time

import numpy as np
from fastapi.testclient import TestClient

from assistant.cerveau import Decision
from assistant.serveur import creer_app
from assistant.simulation import CerveauSimulation
from test_serveur import attendre, binaire, reglages


class ClaudeLent:
    """Claude qui réfléchit longtemps avant d'écrire."""

    nom = "Claude lent"

    def __init__(self, reflexion_s=1.5):
        self.reflexion_s = reflexion_s

    async def demarrer(self):
        pass

    async def fermer(self):
        pass

    async def decider(self, contexte, sur_dire=None):
        await asyncio.sleep(self.reflexion_s)
        dire = "Une fuite de chaleur. Décrivez le premier mur."
        if sur_dire:
            for phrase in ("Une fuite de chaleur.", "Décrivez le premier mur."):
                await sur_dire(phrase, "presence:mur")
        return Decision(dire=dire, cible="presence:mur")


class FauxTranscripteur:
    nom = "faux"

    def prechauffer(self):
        pass

    def transcrire(self, audio):
        return "c'est quoi un pont thermique ?"


def application(dossier, reflexion_s=1.5):
    app = creer_app(reglages(dossier))
    app.state.gestionnaire._cerveaux = lambda _dossier: (ClaudeLent(reflexion_s), CerveauSimulation())
    app.state.gestionnaire.transcripteur = FauxTranscripteur()
    return app


def journal(dossier, session):
    return [json.loads(l) for l in (dossier / session / "journal.jsonl").read_text(encoding="utf-8").splitlines()]


def test_battement_repondu_pendant_que_claude_reflechit(tmp_path):
    with TestClient(application(tmp_path, reflexion_s=2.0)) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "Séjour"})
        attendre(ws, "statut")
        assert attendre(ws, "dire")["texte"] == "Ce mur donne sur quoi ?"  # dès le lancement, par le serveur seul
        ws.send_json({"type": "texte", "texte": "C'est quoi un pont thermique ?"})
        debut = time.monotonic()
        ws.send_json({"type": "ping", "n": 1})
        recus = []
        while (m := ws.receive_json())["type"] != "pong":
            recus.append(m)
        assert m["n"] == 1 and time.monotonic() - debut < 1.0  # tout de suite : le serveur est joignable
        assert not [r for r in recus if r["type"] == "dire"]  # alors que Claude n'a encore rien dit


def test_une_erreur_sur_un_message_ne_coupe_pas_la_liaison(tmp_path):
    with TestClient(application(tmp_path)) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "Séjour"})
        session = attendre(ws, "statut")["session"]
        ws.send_text("ceci n'est pas du JSON")  # avant : la liaison se fermait, et le téléphone affichait « Hors réseau »
        ws.send_json({"type": "ping", "n": 7})
        assert attendre(ws, "pong")["n"] == 7
    assert any(e["evenement"] == "erreur" and e.get("etape") == "liaison" for e in journal(tmp_path, session))


def test_reconnexion_rattrape_ce_qui_a_ete_dit_pendant_la_coupure(tmp_path):
    with TestClient(application(tmp_path, reflexion_s=0.5)) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "debut", "piece": "Séjour"})
            session = attendre(ws, "statut")["session"]
            ws.send_json({"type": "texte", "texte": "C'est quoi un pont thermique ?"})
        # La liaison tombe aussitôt : Claude répond pendant la coupure.
        time.sleep(1.5)
        with client.websocket_connect("/ws") as ws:
            coupure = {"duree_s": 1.5, "cause": "liaison fermée (1006)", "gardes": 0, "perdus": 0}
            ws.send_json({"type": "debut", "session": session, "piece": "Séjour", "coupures": [coupure]})
            statut = attendre(ws, "statut")
            assert statut["reprise"] is True and statut["session"] == session  # la même visite continue
            rattrapes = [attendre(ws, "dire") for _ in range(2)]
            assert [m["texte"] for m in rattrapes] == ["Une fuite de chaleur.", "Décrivez le premier mur."]
            assert all(m["rattrapage"] for m in rattrapes) and [m["suite"] for m in rattrapes] == [False, True]
    evenements = journal(tmp_path, session)
    connexions = [e for e in evenements if e["evenement"] == "connexion"]
    assert [c["reprise"] for c in connexions] == [False, True] and connexions[1]["coupures"] == [coupure]
    assert any(e["evenement"] == "rattrapage" for e in evenements)
    assert [e.get("code") for e in evenements if e["evenement"] == "deconnexion"][0] is not None  # la cause est notée


def test_son_garde_pendant_la_coupure_traite_au_retour(tmp_path):
    rng = np.random.default_rng(1)
    voix = 6000 * np.sin(2 * np.pi * 200 * np.arange(int(1.5 * 16000)) / 16000)
    signal = np.concatenate([rng.normal(0, 30, 16000), voix, rng.normal(0, 30, 24000)]).astype("<i2")
    with TestClient(application(tmp_path, reflexion_s=0.2)) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "debut", "piece": "Séjour"})
            session = attendre(ws, "statut")["session"]
            ws.send_bytes(binaire(1, 0.0, rng.normal(0, 30, 16000).astype("<i2").tobytes()))  # 1 s avant la coupure
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "debut", "session": session, "piece": "Séjour"})
            attendre(ws, "statut")
            # Le téléphone envoie tout ce qu'il a gardé pendant la coupure, à la suite : la phrase est rattrapée.
            for i in range(0, len(signal), 1600):
                ws.send_bytes(binaire(1, 1.0 + i / 16000, signal[i:i + 1600].tobytes()))
            assert attendre(ws, "transcription", maximum=80)["texte"] == "c'est quoi un pont thermique ?"
            assert attendre(ws, "dire", maximum=80)["texte"] in ("Alors…", "Voyons…", "Une fuite de chaleur.")
