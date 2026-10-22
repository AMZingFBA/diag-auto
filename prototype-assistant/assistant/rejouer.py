"""Rejoue une vidéo de test comme si un téléphone filmait : envoie au serveur le son et une image
par seconde, au rythme réel, affiche les échanges, puis le bilan (latences mesurées).

    python -m assistant.rejouer ..\\samples\\video-001\\video.mp4 --serveur http://localhost:8765

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
            image.thumbnail((cote, cote))
            tampon = io.BytesIO()
            image.save(tampon, "JPEG", quality=70)
            images.append((t, tampon.getvalue()))
            prochaine += 1.0
    return images


def message_binaire(genre: int, t: float, donnees: bytes) -> bytes:
    return bytes([genre]) + struct.pack("<d", t) + donnees


async def rejouer(video: Path, serveur: str, code: str, piece: str) -> dict:
    son, images = decoder_son(video), decoder_images(video)
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
        await ws.send(json.dumps({"type": "debut", "piece": piece, "appareil": "rejouer.py"}))

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
                    print(f"{horloge()} ASSISTANT : « {m['texte']} »")
                    await ws.send(json.dumps({"type": "tts", "etat": "debut", "id": m["id"]}))
                    asyncio.get_running_loop().call_later(
                        0.07 * len(m["texte"]), lambda: asyncio.ensure_future(ws.send(json.dumps({"type": "tts", "etat": "fin"}))))
                elif m["type"] == "actions":
                    for r in m["resultats"]:
                        detail = f"{r.get('element') or ''} {r.get('champ') or ''} = {r.get('valeur') or ''}".strip()
                        print(f"{horloge()}    {'✓' if r['statut'] == 'accepte' else '✗'} {r['outil']} {detail} {r['raison']}")
                elif m["type"] == "bip":
                    print(f"{horloge()}    (bip)")
                elif m["type"] == "erreur":
                    print(f"{horloge()} ERREUR : {m['message']}")
                elif m["type"] == "bilan":
                    session["bilan"] = m

        lecteur = asyncio.create_task(lire())
        prochaine_image = 0
        silence = np.zeros(int(4 * TAUX), dtype="<i2")  # 4 s de silence à la fin, pour clore la dernière phrase
        flux = np.concatenate([son, silence])
        debut_envoi = time.monotonic()
        for i in range(0, len(flux), BLOC):
            t = i / TAUX
            while prochaine_image < len(images) and images[prochaine_image][0] <= t:
                await ws.send(message_binaire(2, images[prochaine_image][0], images[prochaine_image][1]))
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
    return bilan


def main() -> None:
    parser = argparse.ArgumentParser(description="Rejoue une vidéo de test vers le serveur de l'assistant")
    parser.add_argument("video", type=Path)
    parser.add_argument("--serveur", default="https://localhost:8443")
    parser.add_argument("--code", default="")
    parser.add_argument("--piece", default="")
    args = parser.parse_args()
    asyncio.run(rejouer(args.video, args.serveur, args.code, args.piece))


if __name__ == "__main__":
    main()
