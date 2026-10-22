import json
import struct

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from assistant.checklist import Checklist
from assistant.reglages import Reglages
from assistant.serveur import creer_app
from assistant.session import rappel_fin


def reglages(dossier, **autres):
    return Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=dossier, veille_s=1000, **autres)


@pytest.fixture
def client(tmp_path):
    with TestClient(creer_app(reglages(tmp_path))) as c:
        yield c


def attendre(ws, genre, maximum=40):
    for _ in range(maximum):
        message = ws.receive_json()
        if message["type"] == genre:
            return message
    raise AssertionError(f"pas de message {genre}")


def binaire(genre, t, donnees):
    return bytes([genre]) + struct.pack("<d", t) + donnees


def test_statut(client):
    statut = client.get("/api/statut").json()
    assert statut["mode_cerveau"] == "simulation" and not statut["code_requis"]
    assert client.get("/").status_code == 200 and "Assistant de visite" in client.get("/").text


def test_visite_par_texte_puis_video_et_bilan(client, tmp_path):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": ""})
        statut = attendre(ws, "statut")
        ws.send_bytes(binaire(2, 1.0, b"\xff\xd8faux jpeg"))
        ws.send_bytes(binaire(1, 0.0, np.zeros(1600, "<i2").tobytes()))
        ws.send_json({"type": "texte", "texte": "ici c'est la cuisine"})
        dire = attendre(ws, "dire")
        assert dire["texte"] == "Décrivez le premier mur."
        attendre(ws, "etat")  # fin du traitement de la 1re phrase
        ws.send_json({"type": "tts", "etat": "debut", "id": dire["id"]})
        ws.send_json({"type": "texte", "texte": "ce mur-là, brique, 30 cm, il donne sur l'extérieur"})
        actions = attendre(ws, "actions")
        assert actions["source"] == "extraction"  # notées tout de suite, sans attendre le cerveau
        valeurs = {r["champ"]: r["statut"] for r in actions["resultats"] if r["outil"] == "enregistrer_reponse"}
        assert valeurs == {"materiau": "accepte", "epaisseur": "accepte", "donne_sur": "accepte"}
        question = attendre(ws, "dire")  # posée tout de suite par le parcours du serveur
        assert question["texte"] == "Le mur 1 est isolé ?" and question["latence_s"] >= 0
        etat = attendre(ws, "etat")
        assert etat["piece"] == "Cuisine" and etat["manques"][0] == "le mur 1 : isolation"
        ws.send_json({"type": "fin"})
        rappel = attendre(ws, "dire")
        assert rappel["texte"].startswith("Avant d'arrêter, il manque")
        bilan = attendre(ws, "bilan")
        assert bilan["bilan"]["phrases"] == 2 and bilan["bilan"]["acceptees"] == 3
    ident = statut["session"]
    dossier = tmp_path / ident
    assert (dossier / "images" / "00001.00.jpg").exists()
    evenements = [json.loads(l)["evenement"] for l in (dossier / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {"debut", "connexion", "decision", "dire", "voix_debut"} <= set(evenements)

    r = client.post(f"/api/sessions/{ident}/video", content=b"video", headers={"content-type": "video/mp4"})
    assert r.json() == {"fichier": "video.mp4", "octets": 5}
    final = client.post(f"/api/sessions/{ident}/terminer").json()
    assert final["latences_s"]["texte_ecrit_a_voix"]["n"] == 1
    assert json.loads((dossier / "etat.json").read_text(encoding="utf-8"))["pieces"][0]["nom"] == "Cuisine"
    assert client.get(f"/api/sessions/{ident}/bilan").json()["session"] == ident


class FauxTranscripteur:
    nom = "faux"

    def prechauffer(self):
        pass

    def transcrire(self, audio):
        assert audio.dtype == np.float32 and len(audio) > 16000
        return "ici c'est la chambre 2"


def test_visite_par_la_voix(tmp_path):
    app = creer_app(reglages(tmp_path))
    app.state.gestionnaire.transcripteur = FauxTranscripteur()
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut"})
        attendre(ws, "statut")
        rng = np.random.default_rng(1)
        voix = 6000 * np.sin(2 * np.pi * 200 * np.arange(int(1.5 * 16000)) / 16000)
        signal = np.concatenate([rng.normal(0, 30, 16000), voix, rng.normal(0, 30, 24000)]).astype("<i2")
        for i in range(0, len(signal), 1600):
            ws.send_bytes(binaire(1, 5.0 + i / 16000, signal[i:i + 1600].tobytes()))
        assert attendre(ws, "parole_debut")["t"] == pytest.approx(6.0, abs=0.15)
        transcription = attendre(ws, "transcription")
        assert transcription["texte"] == "ici c'est la chambre 2"
        assert attendre(ws, "etat")["piece"] == "Chambre 2"


def test_identifiants_et_code_d_acces(client, tmp_path):
    assert client.post("/api/sessions/..%2F..%2Fx/video", content=b"x").status_code in (404, 405)
    assert client.post("/api/sessions/..x/video", content=b"x").status_code == 404
    assert not list(tmp_path.glob("**/video*"))
    assert client.get("/api/sessions/20260101-000000-abcdef/bilan").status_code == 404
    with TestClient(creer_app(reglages(tmp_path, code="1234"))) as protege:
        with protege.websocket_connect("/ws") as ws, pytest.raises(WebSocketDisconnect):
            ws.receive_json()
        with protege.websocket_connect("/ws?code=1234") as ws:
            ws.send_json({"type": "debut"})
            assert attendre(ws, "statut")["code_requis"] is True


def test_rappel_de_fin():
    c = Checklist()
    assert rappel_fin(c) == ("Avant d'arrêter, il manque 3 informations. logement, générateur de chauffage : présence à confirmer ; "
                             "logement, eau chaude sanitaire : présence à confirmer ; logement, ventilation : présence à confirmer.")
    c.definir_piece("séjour", 0)
    c.signaler_element("mur", "le mur du fond", 1)
    assert rappel_fin(c).startswith("Avant d'arrêter, il manque 13 informations. Séjour, le mur du fond : donne sur ;")
    assert rappel_fin(c).endswith("et 10 autres, à l'écran.")


def test_phrases_regroupees_pendant_une_reponse(tmp_path):
    import asyncio

    from assistant.session import Session
    from assistant.simulation import CerveauSimulation
    from assistant.transcription import TranscripteurSimulation

    class CerveauLent(CerveauSimulation):
        vus: list[str] = []

        async def decider(self, contexte, sur_dire=None):
            await asyncio.sleep(0.3)
            self.vus.append(contexte.phrase)
            return await super().decider(contexte, sur_dire)

    async def scenario():
        cerveau = CerveauLent()
        session = Session("essai", tmp_path, cerveau, cerveau, TranscripteurSimulation(), reglages(tmp_path))
        await session.demarrer()
        # Phrases que les règles ne comprennent pas : seules celles-là attendent le cerveau.
        for texte in ["Euh.", "Bon alors.", "Voilà."]:
            await session.recevoir_controle({"type": "texte", "texte": texte})
            await asyncio.sleep(0.05)
        await asyncio.sleep(1.2)
        return cerveau.vus, await session.terminer()

    vus, bilan = asyncio.run(scenario())
    assert vus == ["Euh.", "Bon alors. Voilà."]
    assert bilan["phrases"] == 3 and bilan["appels_reponse"] == 2
