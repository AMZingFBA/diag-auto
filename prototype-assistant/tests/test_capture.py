"""Étape 12 : ce qu'il faut garder d'une visite pour la carte des pièces.

Les capteurs reçus en direct (boussole, gyroscope) sont écrits sur disque ; le relevé continu du téléphone (20 mesures
par seconde) est reçu en fin de visite ; l'instant de chaque phrase dans la vidéo est noté au journal."""

import json
import time

from test_serveur import attendre, client  # noqa: F401  (fixture)


def journal(dossier, session):
    return [json.loads(l) for l in (dossier / session / "journal.jsonl").read_text(encoding="utf-8").splitlines()]


def test_capteurs_recus_en_direct_gardes_sur_disque(client, tmp_path):  # noqa: F811
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "Séjour"})
        session = attendre(ws, "statut")["session"]
        for t, cap in ((1.0, 274.1), (2.0, 276.0)):
            ws.send_json({"type": "capteurs", "t": t, "cap": cap, "lacet": 10.0, "precision": 12.0, "inclinaison": 88.0})
        ws.send_json({"type": "capteurs", "t": 3.0, "cap": None, "lacet": None})  # téléphone sans boussole
        ws.send_json({"type": "ping", "n": 1})
        attendre(ws, "pong")
    lignes = [json.loads(l) for l in (tmp_path / session / "capteurs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(l["t"], l["cap"]) for l in lignes] == [(1.0, 274.1), (2.0, 276.0), (3.0, None)]


def test_releve_continu_recu_en_fin_de_visite(client, tmp_path):  # noqa: F811
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "Séjour"})
        session = attendre(ws, "statut")["session"]
    mesures = [{"t": k / 20, "cap": 270 + k % 5, "lacet": 3.0, "precision": None, "inclinaison": 90.0} for k in range(200)]
    reponse = client.post(f"/api/sessions/{session}/capteurs", content=json.dumps({"mesures": mesures + ["illisible"]}),
                          headers={"content-type": "application/json"})
    assert reponse.status_code == 200 and reponse.json() == {"mesures": 200}
    recu = json.loads((tmp_path / session / "capteurs-continus.json").read_text(encoding="utf-8"))
    assert recu["mesures"] == mesures
    assert client.post(f"/api/sessions/{session}/capteurs", content=b"pas du json").status_code == 400
    assert client.post("/api/sessions/20990101-000000-abcdef/capteurs", content=b"{}").status_code == 404


def test_instants_de_chaque_phrase_au_journal(client, tmp_path):  # noqa: F811
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "debut", "piece": "Séjour"})
        session = attendre(ws, "statut")["session"]
        ws.send_json({"type": "texte", "texte": "Ce mur donne sur l'extérieur, en brique."})
        attendre(ws, "dire")
    for _ in range(50):
        extractions = [e for e in journal(tmp_path, session) if e["evenement"] == "extraction"]
        if extractions:
            break
        time.sleep(0.1)
    assert extractions and {"t_debut", "t_fin"} <= set(extractions[0])
