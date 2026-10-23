"""Serveur du prototype : page web (PWA), liaison temps réel avec le téléphone (WebSocket),
réception de la vidéo enregistrée, bilans de visite.

Messages binaires du téléphone : 1 octet de type + instant dans la vidéo (float64, petit-boutiste)
+ données. Type 1 = son PCM 16 bits mono 16 kHz ; type 2 = image JPEG.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
import secrets
import struct
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .boussole import REGLAGES as REGLAGES_BOUSSOLE
from .cerveau import CerveauClaudeCode, trouver_claude
from .regard import RegardClaude
from .reglages import DOSSIER_PROTOTYPE, Reglages
from .reponses import options_par_champ
from .session import Session
from .simulation import CerveauSimulation
from .transcription import creer_transcripteur

log = logging.getLogger(__name__)
mimetypes.add_type("application/manifest+json", ".webmanifest")
IDENTIFIANT = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
NOM_IMAGE = re.compile(r"^\d{5}\.\d{2}\.jpg$")  # images/<instant>.jpg d'une visite
TAILLE_MAX_VIDEO = 4 * 1024**3
TAILLE_MAX_CAPTEURS = 64 * 1024**2  # relevé continu des capteurs : ~10 Mo pour 1 h


class Gestionnaire:
    """Garde les visites en cours : un téléphone qui se reconnecte reprend la même visite."""

    def __init__(self, reglages: Reglages) -> None:
        self.reglages = reglages
        self.sessions: dict[str, Session] = {}
        self.transcripteur = creer_transcripteur(reglages.transcription, reglages.whisper_modele, reglages.whisper_appareil, reglages.whisper_faisceau)
        self.binaire_claude = trouver_claude() if reglages.cerveau in ("auto", "claude") else None
        if reglages.cerveau == "claude" and not self.binaire_claude:
            raise FileNotFoundError("Claude Code introuvable : indiquez son chemin dans DIAGAUTO_CLAUDE")

    @property
    def mode_cerveau(self) -> str:
        return "claude" if self.binaire_claude else "simulation"

    def _cerveaux(self, dossier: Path):
        if self.mode_cerveau == "simulation":
            cerveau = CerveauSimulation()
            return cerveau, cerveau
        r = self.reglages

        def nouveau(nom: str) -> CerveauClaudeCode:
            return CerveauClaudeCode(dossier / nom, modele=r.modele, effort=r.effort, images=r.images, binaire=self.binaire_claude)

        # Deux processus : la veille ne fait jamais attendre la réponse à une phrase.
        return nouveau("claude-reponses"), nouveau("claude-veille")

    async def ouvrir(self, ident: str | None, piece: str, mission: str = "dpe") -> tuple[Session, bool]:
        if ident and ident in self.sessions and not self.sessions[ident].termine:
            return self.sessions[ident], True
        ident = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        dossier = self.reglages.dossier_sessions / ident
        dossier.mkdir(parents=True, exist_ok=True)
        cerveau, veille = self._cerveaux(dossier)
        regard = None
        if self.mode_cerveau == "claude":  # l'image propose la réponse (assistant/regard.py)
            regard = RegardClaude(dossier / "claude-regard", binaire=self.binaire_claude)
        session = Session(ident, dossier, cerveau, veille, self.transcripteur, self.reglages, regard=regard, mission=mission)
        self.sessions[ident] = session
        await session.demarrer(piece)
        return session, False

    async def fermer(self) -> None:
        for session in self.sessions.values():
            await session.terminer()


class PageSansCache(StaticFiles):
    """La page du téléphone, toujours revérifiée : test du 23/10, l'iPhone gardait l'ancienne page (sans « Cache-Control »,
    Safari la réutilisait sans redemander), et le bouton « Autre » corrigé n'arrivait pas."""

    async def get_response(self, path, scope):
        reponse = await super().get_response(path, scope)
        reponse.headers["Cache-Control"] = "no-cache"
        return reponse


# Version de la page (web/app.js) : si le téléphone en a une autre, il le dit (« rechargez la page »).
VERSION_PAGE = (re.search(r'VERSION_PAGE = "([^"]+)"', (DOSSIER_PROTOTYPE / "web" / "app.js").read_text(encoding="utf-8")) or [None, ""])[1]


def creer_app(reglages: Reglages | None = None) -> FastAPI:
    reglages = reglages or Reglages()
    gestionnaire = Gestionnaire(reglages)

    @asynccontextmanager
    async def cycle_de_vie(_app: FastAPI):
        # Le modèle de transcription est chargé en tâche de fond (téléchargé au premier lancement).
        asyncio.get_running_loop().run_in_executor(None, gestionnaire.transcripteur.prechauffer)
        yield
        await gestionnaire.fermer()

    app = FastAPI(title="DiagAuto — assistant vocal (prototype V1bis)", lifespan=cycle_de_vie)
    app.state.gestionnaire = gestionnaire

    def verifier_code(code: str | None) -> None:
        if reglages.code and code != reglages.code:
            raise HTTPException(status_code=401, detail="code d'accès incorrect")

    def dossier_session(ident: str) -> Path:
        if not IDENTIFIANT.match(ident):
            raise HTTPException(status_code=404, detail="visite inconnue")
        dossier = reglages.dossier_sessions / ident
        if not dossier.is_dir():
            raise HTTPException(status_code=404, detail="visite inconnue")
        return dossier

    @app.get("/api/statut")
    async def statut() -> dict:
        cerveau = (f"Claude Code (abonnement), modèle {reglages.modele}" if gestionnaire.mode_cerveau == "claude"
                   else "simulation (règles simples, sans Claude)")
        return {"cerveau": cerveau, "mode_cerveau": gestionnaire.mode_cerveau, "transcription": gestionnaire.transcripteur.nom,
                "code_requis": bool(reglages.code), "boussole": REGLAGES_BOUSSOLE, "version_page": VERSION_PAGE,
                # Réponses en boutons, par information : la fiche de la pièce sur le téléphone (questionnaire en direct).
                "options": options_par_champ()}

    @app.post("/api/sessions/{ident}/video")
    async def recevoir_video(ident: str, request: Request) -> dict:
        verifier_code(request.headers.get("x-code"))
        dossier = dossier_session(ident)
        extension = ".mp4" if "mp4" in request.headers.get("content-type", "") else ".webm"
        chemin, taille = dossier / f"video{extension}", 0
        with open(chemin, "wb") as fichier:
            async for morceau in request.stream():
                taille += len(morceau)
                if taille > TAILLE_MAX_VIDEO:
                    raise HTTPException(status_code=413, detail="vidéo trop grosse")
                fichier.write(morceau)
        session = gestionnaire.sessions.get(ident)
        if session:
            session.journaliser("video_recue", fichier=chemin.name, octets=taille)
        return {"fichier": chemin.name, "octets": taille}

    @app.post("/api/sessions/{ident}/capteurs")
    async def recevoir_capteurs(ident: str, request: Request) -> dict:
        """Relevé continu de la boussole et du gyroscope (20 par seconde), envoyé en fin de visite (étape 12)."""
        verifier_code(request.headers.get("x-code"))
        dossier = dossier_session(ident)
        corps = await request.body()
        if len(corps) > TAILLE_MAX_CAPTEURS:
            raise HTTPException(status_code=413, detail="relevé trop gros")
        try:
            mesures = json.loads(corps).get("mesures")
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="relevé illisible") from None
        if not isinstance(mesures, list):
            raise HTTPException(status_code=400, detail="relevé illisible")
        propres = [m for m in mesures if isinstance(m, dict) and isinstance(m.get("t"), (int, float))]
        (dossier / "capteurs-continus.json").write_text(json.dumps({"mesures": propres}), encoding="utf-8")
        session = gestionnaire.sessions.get(ident)
        if session:
            session.journaliser("capteurs_recus", mesures=len(propres))
        return {"mesures": len(propres)}

    @app.get("/api/sessions/{ident}/bilan")
    async def bilan(ident: str, code: str = "") -> JSONResponse:
        verifier_code(code)
        dossier = dossier_session(ident)
        session = gestionnaire.sessions.get(ident)
        if session and not session.termine:
            return JSONResponse(session.bilan())
        fichier = dossier / "bilan.json"
        if not fichier.exists():
            raise HTTPException(status_code=404, detail="bilan pas encore disponible")
        return JSONResponse(json.loads(fichier.read_text(encoding="utf-8")))

    @app.get("/api/sessions/{ident}/images/{nom}")
    async def image(ident: str, nom: str, code: str = "") -> FileResponse:
        """Vignette d'un élément, montrée avec la question qui le concerne (« le mur affiché »)."""
        verifier_code(code)
        chemin = dossier_session(ident) / "images" / nom
        if not NOM_IMAGE.match(nom) or not chemin.is_file():
            raise HTTPException(status_code=404, detail="image inconnue")
        return FileResponse(chemin, media_type="image/jpeg")

    @app.websocket("/ws")
    async def liaison(websocket: WebSocket, code: str = "") -> None:
        await websocket.accept()
        if reglages.code and code != reglages.code:
            await websocket.close(code=4401)  # la page affiche « code incorrect » et ne se reconnecte pas
            return
        session: Session | None = None
        verrou = asyncio.Lock()

        async def envoyer(message: dict) -> None:
            async with verrou:  # plusieurs tâches écrivent : un message à la fois
                await websocket.send_text(json.dumps(message, ensure_ascii=False))

        code_fin = None
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    code_fin = message.get("code")
                    break
                try:
                    if message.get("bytes"):
                        donnees = message["bytes"]
                        if session is None or len(donnees) < 9:
                            continue
                        t = struct.unpack("<d", donnees[1:9])[0]
                        if donnees[0] == 1:
                            await session.recevoir_audio(t, donnees[9:])
                        elif donnees[0] == 2:
                            await session.recevoir_image(t, donnees[9:])
                    elif message.get("text"):
                        controle = json.loads(message["text"])
                        if controle.get("type") == "ping":
                            # Battement de cœur (étape 10) : réponse immédiate, même quand Claude réfléchit ; c'est ce qui
                            # distingue « serveur lent » de « pas de réseau » côté téléphone.
                            await envoyer({"type": "pong", "n": controle.get("n")})
                        elif controle.get("type") == "debut":
                            session, reprise = await gestionnaire.ouvrir(controle.get("session"), str(controle.get("piece") or ""),
                                                                         str(controle.get("mission") or "dpe"))
                            session.envoyer = envoyer
                            session.journaliser("connexion", reprise=reprise, appareil=str(controle.get("appareil", ""))[:300],
                                                coupures=controle.get("coupures") or [])
                            await envoyer({"type": "statut", "session": session.id, "reprise": reprise, "mission": session.mission,
                                           **(await statut())})
                            await session.envoyer_etat()
                            await session.rattraper()  # questions calculées pendant la coupure
                            if not reprise:
                                await session.ouvrir_visite()  # la première question, dès le lancement
                        elif session is not None:
                            await session.recevoir_controle(controle)
                except (WebSocketDisconnect, RuntimeError):
                    raise
                except Exception as e:
                    # Une erreur sur un message ne coupe plus la liaison (avant : le téléphone affichait « Hors réseau »).
                    log.exception("Message du téléphone")
                    if session is not None:
                        session.journaliser("erreur", etape="liaison", message=str(e))
        except WebSocketDisconnect as e:
            code_fin = e.code
        except RuntimeError:
            pass  # liaison déjà fermée
        finally:
            if session is not None and session.envoyer is envoyer:
                session.envoyer = None
                session.journaliser("deconnexion", code=code_fin)

    @app.post("/api/sessions/{ident}/terminer")
    async def terminer(ident: str, request: Request) -> JSONResponse:
        verifier_code(request.headers.get("x-code"))
        dossier_session(ident)
        session = gestionnaire.sessions.get(ident)
        if session is None:
            raise HTTPException(status_code=404, detail="visite inconnue")
        return JSONResponse(await session.terminer())

    app.mount("/", PageSansCache(directory=DOSSIER_PROTOTYPE / "web", html=True), name="web")
    return app
