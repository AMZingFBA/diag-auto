"""Étape 15, capture d'un tour de pièce en direct : images avec leur pose (message de type 3), capteurs par lots (≈ 15
mesures par seconde, toutes les 0,25 s), tour repéré par le serveur et annoncé au téléphone (un bip), images noires
(caméra coupée par le téléphone) écartées."""

import json
import struct

import cv2
import numpy as np

from test_serveur import attendre, binaire, client  # noqa: F401 (fixture)
from test_tour import releve


def jpeg(gris: int, motif: bool = True) -> bytes:
    image = np.full((64, 48, 3), gris, np.uint8)
    if motif:
        image[10:30, 10:30] = (gris + 60) % 256
    return cv2.imencode(".jpg", image)[1].tobytes()


def image_posee(t: float, pose: dict, donnees: bytes) -> bytes:
    entete = json.dumps(pose).encode("utf-8")
    return bytes([3]) + struct.pack("<d", t) + struct.pack("<H", len(entete)) + entete + donnees


def journal(dossier) -> list[dict]:
    return [json.loads(ligne) for ligne in (dossier / "journal.jsonl").read_text(encoding="utf-8").splitlines()]


def test_tour_vu_en_direct_et_images_posees(client, tmp_path, monkeypatch):  # noqa: F811
    import assistant.session as module_session

    monkeypatch.setattr(module_session, "RECONNAITRE_PIECES", True)  # tour bipé avec la reconnaissance (coupée depuis le 25/10)
    mesures = releve([(1.0, 0), (3.0, 360), (1.0, 0)])
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "", "mission": "plomb"})
        statut = attendre(ws, "statut")
        for k in range(0, len(mesures), 4):  # un lot toutes les 0,25 s : 4 mesures
            if k == 20:  # pendant le tour : une image clé, avec sa pose
                ws.send_bytes(image_posee(2.4, {"raison": "rotation", "lacet": 190.0, "elevation": -12.0, "vitesse": 120}, jpeg(120)))
                ws.send_bytes(image_posee(2.5, {"raison": "rotation", "lacet": 205.0}, jpeg(0, motif=False)))  # noire : caméra coupée
            ws.send_json({"type": "capteurs_lot", "mesures": mesures[k:k + 4], "pas": []})
        tour = attendre(ws, "tour")
        ws.send_json({"type": "fin"})
        attendre(ws, "bilan")
    assert 0.9 <= tour["t_debut"] <= 1.2 and 3.8 <= tour["t_fin"] <= 4.2 and abs(tour["rotation"]) >= 330
    dossier = tmp_path / statut["session"]
    poses = [json.loads(ligne) for ligne in (dossier / "images.jsonl").read_text(encoding="utf-8").splitlines()]
    assert poses == [{"t": 2.4, "fichier": "00002.40.jpg", "raison": "rotation", "lacet": 190.0, "elevation": -12.0, "vitesse": 120}]
    assert not (dossier / "images" / "00002.50.jpg").exists()  # l'image noire n'est pas gardée
    evenements = journal(dossier)
    assert [e["evenement"] for e in evenements if e["evenement"] in ("camera_coupee", "tour")] == ["camera_coupee", "tour"]
    assert next(e for e in evenements if e["evenement"] == "tour")["images"] == 1
    lignes = (dossier / "capteurs-lot.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == len(mesures)


def test_dpe_tour_journalise_sans_bip(client, tmp_path):  # noqa: F811
    # DPE : le tour est noté (pour la carte d'après la visite), mais le téléphone ne bipe pas (le bip y veut dire « noté »).
    mesures = releve([(1.0, 0), (3.0, 360), (1.0, 0)])
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "", "mission": "dpe"})
        statut = attendre(ws, "statut")
        ws.send_json({"type": "capteurs_lot", "mesures": mesures, "pas": [0.5, 0.9]})
        ws.send_json({"type": "fin"})
        messages = []
        while not messages or messages[-1]["type"] != "bilan":
            messages.append(ws.receive_json())
    assert not [m for m in messages if m["type"] == "tour"]
    assert "tour" in [e["evenement"] for e in journal(tmp_path / statut["session"])]


def test_lot_de_capteurs_abime_ignore_sans_couper_la_liaison(client, tmp_path):  # noqa: F811
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "", "mission": "amiante"})
        attendre(ws, "statut")
        ws.send_json({"type": "capteurs_lot", "mesures": [{"t": "x"}, None, {"t": 1.0, "lacet": "nord"}, {"t": 1.1, "lacet": 10}], "pas": ["a"]})
        ws.send_bytes(bytes([3]) + struct.pack("<d", 1.0) + struct.pack("<H", 5) + b"{abc}" + jpeg(100))  # pose illisible
        ws.send_json({"type": "ping", "n": 1})
        assert attendre(ws, "pong")["n"] == 1  # la liaison vit toujours
