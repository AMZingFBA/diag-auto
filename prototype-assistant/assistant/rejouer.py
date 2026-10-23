"""Rejoue une vidéo de test, ou une visite enregistrée, comme si un téléphone filmait : envoie au
serveur le son et une image par seconde, au rythme réel, affiche les échanges, puis le bilan
(latences mesurées).

    python -m assistant.rejouer ..\\samples\\video-001\\video.mp4
    python -m assistant.rejouer sessions\\20261022-083308-20ef54      (son audio.wav + images/ d'une visite)

La voix de l'assistant n'est pas jouée : le début de « voix » est signalé dès réception de la
question (comme un téléphone qui parlerait instantanément), et sa fin après une durée estimée.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import ssl
import struct
import time
import wave
from pathlib import Path

import av
import httpx
import numpy as np
import websockets
from PIL import Image

TAUX = 16_000
BLOC = 1600  # 0,1 s


def decoder_son(chemin: Path) -> np.ndarray:
    morceaux = []
    with av.open(str(chemin)) as conteneur:
        reechantillonneur = av.AudioResampler(format="s16", layout="mono", rate=TAUX)
        for trame in conteneur.decode(audio=0):
            morceaux += [t.to_ndarray().reshape(-1) for t in reechantillonneur.resample(trame)]
        morceaux += [t.to_ndarray().reshape(-1) for t in reechantillonneur.resample(None)]
    return np.concatenate(morceaux).astype("<i2")


def decoder_images(chemin: Path, cote: int = 512) -> list[tuple[float, bytes]]:
    """Une image par seconde de vidéo, réduite à `cote` pixels sur le grand côté."""
    images, prochaine = [], 0.0
    with av.open(str(chemin)) as conteneur:
        flux = conteneur.streams.video[0]
        for trame in conteneur.decode(flux):
            t = float(trame.pts * flux.time_base)
            if t + 1e-6 < prochaine:
                continue
            image: Image.Image = trame.to_image()
            rotation = getattr(trame, "rotation", 0) or 0  # vidéo de téléphone : redressée comme à l'affichage (vision.redresser)
            if round(rotation / 90) % 4:
                image = image.rotate(round(rotation / 90) * 90, expand=True)
            image.thumbnail((cote, cote))
            tampon = io.BytesIO()
            image.save(tampon, "JPEG", quality=70)
            images.append((t, tampon.getvalue()))
            prochaine += 1.0
    return images


def lire_visite(dossier: Path) -> tuple[np.ndarray, list[tuple[float, bytes]]]:
    """Son et images d'une visite enregistrée par le serveur (audio.wav, images/<instant>.jpg)."""
    with wave.open(str(dossier / "audio.wav"), "rb") as wav:
        if wav.getframerate() != TAUX or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("audio.wav doit être en 16 kHz, mono, 16 bits")
        son = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    images = sorted((float(chemin.stem), chemin.read_bytes()) for chemin in (dossier / "images").glob("*.jpg"))
    return son, images


def message_binaire(genre: int, t: float, donnees: bytes) -> bytes:
    return bytes([genre]) + struct.pack("<d", t) + donnees


async def rejouer(video: Path, serveur: str, code: str, piece: str, mission: str = "dpe", duree: float | None = None) -> dict:
    son, images = lire_visite(video) if video.is_dir() else (decoder_son(video), decoder_images(video))
    capteurs = []  # boussole et gyroscope enregistrés (une mesure par seconde), rejoués à leur instant
    if video.is_dir() and (video / "capteurs.jsonl").exists():
        capteurs = [json.loads(ligne) for ligne in (video / "capteurs.jsonl").read_text(encoding="utf-8").splitlines() if ligne.strip()]
    # Étape 15 : les mesures à 15 par seconde et les pas (capteurs-lot.jsonl), rejoués par lots de 0,25 s, et la pose de
    # chaque image (images.jsonl), renvoyée avec elle : la visite se rejoue comme le téléphone l'a envoyée.
    lots, poses = [], {}
    if video.is_dir() and (video / "capteurs-lot.jsonl").exists():
        for ligne in (video / "capteurs-lot.jsonl").read_text(encoding="utf-8").splitlines():
            m = json.loads(ligne)
            lots.append((m["pas"], "pas", m["pas"]) if "pas" in m else (m["t"], "mesure", m))
        lots.sort(key=lambda e: (e[0], e[1] == "pas"))
    if video.is_dir() and (video / "images.jsonl").exists():
        for ligne in (video / "images.jsonl").read_text(encoding="utf-8").splitlines():
            pose = json.loads(ligne)
            poses[round(float(pose.pop("t")), 2)] = {k: v for k, v in pose.items() if k != "fichier"}
    if duree is not None:  # seulement le début de la visite
        son, images, capteurs = son[: int(duree * TAUX)], [i for i in images if i[0] <= duree], [m for m in capteurs if m["t"] <= duree]
        lots = [e for e in lots if e[0] <= duree]
    print(f"{video.name} : {len(son) / TAUX:.1f} s de son, {len(images)} images")
    url_ws = serveur.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws" + (f"?code={code}" if code else "")
    contexte_ssl = None
    if url_ws.startswith("wss://"):
        contexte_ssl = ssl.create_default_context()
        contexte_ssl.check_hostname = False
        contexte_ssl.verify_mode = ssl.CERT_NONE  # certificat auto-signé du prototype
    depart = time.monotonic()
    dernier_message = time.monotonic()
    session = {}

    def horloge() -> str:
        return f"[{time.monotonic() - depart:6.1f} s]"

    async with websockets.connect(url_ws, max_size=None, ssl=contexte_ssl) as ws:
        await ws.send(json.dumps({"type": "debut", "piece": piece, "mission": mission, "appareil": "rejouer.py"}))

        async def lire() -> None:
            nonlocal dernier_message
            async for brut in ws:
                m = json.loads(brut)
                dernier_message = time.monotonic()
                if m["type"] == "statut":
                    session.update(m)
                    print(f"{horloge()} visite {m['session']} — cerveau : {m['cerveau']} — transcription : {m['transcription']}")
                elif m["type"] == "transcription":
                    print(f"{horloge()} DIAGNOSTIQUEUR ({m['t']:.1f} s) : « {m['texte']} »")
                elif m["type"] == "dire":
                    latence = (f" (question {m['latence_s']} s après la fin de phrase détectée)" if m.get("latence_s") is not None
                               else " (suite)" if m.get("suite") else "")  # réponse de Claude lue phrase par phrase
                    print(f"{horloge()} ASSISTANT : « {m['texte']} »{latence}")
                    await ws.send(json.dumps({"type": "tts", "etat": "debut", "id": m["id"]}))
                    asyncio.get_running_loop().call_later(
                        0.07 * len(m["texte"]), lambda: asyncio.ensure_future(ws.send(json.dumps({"type": "tts", "etat": "fin"}))))
                elif m["type"] == "actions":
                    for r in m["resultats"]:
                        detail = f"{r.get('element') or ''} {r.get('champ') or ''} = {r.get('valeur') or ''}".strip()
                        print(f"{horloge()}    {'✓' if r['statut'] == 'accepte' else '✗'} {r['outil']} {detail} {r['raison']}")
                elif m["type"] == "bip":
                    print(f"{horloge()}    (bip : noté {m.get('latence_s')} s après la fin de phrase détectée)")
                elif m["type"] == "erreur":
                    print(f"{horloge()} ERREUR : {m['message']}")
                elif m["type"] == "piece_reconnue":
                    print(f"{horloge()} PIÈCE : {m['nom']}{' (nouvelle)' if m.get('nouvelle') else ''}")
                elif m["type"] == "etat" and (m.get("checklist") or {}).get("croquis"):
                    session["croquis"] = m["checklist"]["croquis"]
                elif m["type"] == "bilan":
                    session["bilan"] = m

        lecteur = asyncio.create_task(lire())
        prochaine_image = 0
        silence = np.zeros(int(4 * TAUX), dtype="<i2")  # 4 s de silence à la fin, pour clore la dernière phrase
        flux = np.concatenate([son, silence])
        debut_envoi = time.monotonic()
        prochain_capteur = prochain_lot = 0
        for i in range(0, len(flux), BLOC):
            t = i / TAUX
            while prochain_capteur < len(capteurs) and capteurs[prochain_capteur]["t"] <= t:
                await ws.send(json.dumps({"type": "capteurs", **capteurs[prochain_capteur]}))
                prochain_capteur += 1
            lot = []
            while prochain_lot < len(lots) and lots[prochain_lot][0] <= t:
                lot.append(lots[prochain_lot])
                prochain_lot += 1
            if lot:
                await ws.send(json.dumps({"type": "capteurs_lot", "mesures": [e[2] for e in lot if e[1] == "mesure"],
                                          "pas": [e[2] for e in lot if e[1] == "pas"]}))
            while prochaine_image < len(images) and images[prochaine_image][0] <= t:
                t_image, jpeg = images[prochaine_image]
                pose = poses.get(round(t_image, 2))
                if pose is not None:  # image avec sa pose (type 3)
                    entete = json.dumps(pose).encode("utf-8")
                    await ws.send(bytes([3]) + struct.pack("<d", t_image) + struct.pack("<H", len(entete)) + entete + jpeg)
                else:
                    await ws.send(message_binaire(2, t_image, jpeg))
                prochaine_image += 1
            await ws.send(message_binaire(1, t, flux[i:i + BLOC].tobytes()))
            await asyncio.sleep(max(0.0, debut_envoi + (i + BLOC) / TAUX - time.monotonic()))
        while time.monotonic() - dernier_message < 8:  # attend la fin des traitements en cours
            await asyncio.sleep(0.5)
        await ws.send(json.dumps({"type": "fin"}))
        for _ in range(40):
            if "bilan" in session:
                break
            await asyncio.sleep(0.25)
        lecteur.cancel()

    entetes = {"x-code": code} if code else {}
    async with httpx.AsyncClient(verify=False, timeout=30) as client:
        r = await client.post(f"{serveur.rstrip('/')}/api/sessions/{session['session']}/terminer", headers=entetes)
        bilan = r.json()
    print(json.dumps(bilan, ensure_ascii=False, indent=2))
    if session.get("croquis"):
        croquis = session["croquis"]
        print("Croquis :", ", ".join(f"{p['nom']} ({p['x']}, {p['y']})" for p in croquis["pieces"]),
              "— portes :", ", ".join(f"{p['a']}→{p['b']} ({p['cote']})" for p in croquis["portes"]))
        if croquis.get("plan"):  # le plan dans un repère commun (étape 15)
            plan = croquis["plan"]
            centre = lambda pts: (round(sum(p[0] for p in pts) / len(pts), 1), round(sum(p[1] for p in pts) / len(pts), 1))  # noqa: E731
            print("Plan :", ", ".join(f"{p['nom']} {centre(p['polygone'])}" for p in plan["pieces"]),
                  "— portes :", ", ".join(f"{p['a']}→{p['b']}" for p in plan["portes"]), "— orienté :", plan["oriente"])
    return bilan


def main() -> None:
    parser = argparse.ArgumentParser(description="Rejoue une vidéo de test vers le serveur de l'assistant")
    parser.add_argument("video", type=Path)
    parser.add_argument("--serveur", default="https://localhost:8443")
    parser.add_argument("--code", default="")
    parser.add_argument("--piece", default="")
    parser.add_argument("--mission", default="dpe", choices=["dpe", "amiante", "plomb"])
    parser.add_argument("--duree", type=float, default=None, help="ne rejouer que les N premières secondes")
    args = parser.parse_args()
    asyncio.run(rejouer(args.video, args.serveur, args.code, args.piece, args.mission, args.duree))


if __name__ == "__main__":
    main()
