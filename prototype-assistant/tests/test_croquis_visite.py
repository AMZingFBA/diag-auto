"""Croquis en direct pendant une visite : pièces reconnues sur la vidéo, posées dans la direction de marche, corrigées à la
voix ou au doigt (demande de Noah du 23/10 pour le plomb et l'amiante)."""

import asyncio

import pytest

from assistant.regard import AvisPiece
from assistant.session import Session
from test_conversation import CerveauScenario, poli
from test_fluidite import attendre, ouvrir, parler


class ClaudeQuiVoitLesPieces:
    """Faux Claude : l'avis sur la pièce dépend de l'instant de la dernière image."""

    def __init__(self, avis: dict[float, AvisPiece]):
        self.avis = avis
        self.references: list[list[str]] = []

    async def demarrer(self, propositions=True, pieces=True, voix=False):
        self.propositions, self.pieces, self.voix = propositions, pieces, voix

    async def fermer(self):
        pass

    async def proposer(self, question, options, images):
        return None

    async def reconnaitre(self, images, references, courante):
        self.references.append(list(references))
        return self.avis.get(images[-1].t)


@pytest.fixture(autouse=True)
def sans_boucle_de_fond(monkeypatch):
    async def rien(self):
        return None

    monkeypatch.setattr(Session, "_boucle_pieces", rien)


async def filmer(session, t: float, cap: float) -> None:
    for dt in (-1.0, -0.5, 0.0):
        await session.recevoir_controle({"type": "capteurs", "t": t + dt, "cap": cap, "lacet": cap, "inclinaison": 80.0})
    await session.recevoir_image(t, b"\xff\xd8image " + str(t).encode())
    session.t_video = t
    await session._reconnaitre_piece()


def test_croquis_dessine_en_marchant_et_corrige(tmp_path):
    avis = {1.0: AvisPiece(None, "Entrée", "forte"), 8.0: AvisPiece(None, "Séjour", "moyenne"),
            9.0: AvisPiece(None, "Séjour", "moyenne"), 20.0: AvisPiece(None, "Cuisine", "forte"),
            30.0: AvisPiece("Séjour", "", "forte"), 31.0: AvisPiece(None, "Chambre", "faible")}
    claude = ClaudeQuiVoitLesPieces(avis)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await filmer(session, 1.0, 0.0)  # l'entrée, première pièce : décidée tout de suite
        await filmer(session, 8.0, 2.0)  # un avis « moyen » : on attend le second
        assert session.checklist.nom_piece(session.checklist.piece_courante) == "Entrée"
        await filmer(session, 9.0, 3.0)  # second avis : le séjour, au nord de l'entrée
        await filmer(session, 20.0, 91.0)  # la cuisine, à l'est du séjour (avis « fort » : tout de suite)
        await parler(session, "Non, c'est la buanderie.")  # reconnue à tort : la même pièce, renommée
        await attendre(session)
        await filmer(session, 30.0, 270.0)  # retour au séjour : rien de nouveau
        await filmer(session, 31.0, 270.0)  # avis « faible » : rien
        await session.recevoir_controle({"type": "renommer_piece", "cle": "entree", "nom": "Couloir"})  # touché sur le croquis
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    croquis = [m for m in recus if m["type"] == "etat"][-1]["checklist"]["croquis"]
    assert [(p["nom"], p["x"], p["y"], p["source"]) for p in croquis["pieces"]] == [
        ("Couloir", 0, 0, "tapé"), ("Séjour", 0, -1, "image"), ("Buanderie", 1, -1, "dit")]
    assert croquis["courante"] == "sejour" and croquis["oriente"]
    assert croquis["portes"] == [{"a": "couloir", "b": "sejour", "cote": "nord"}, {"a": "sejour", "b": "buanderie", "cote": "est"}]
    buanderie = next(p for p in croquis["pieces"] if p["nom"] == "Buanderie")
    assert buanderie["murs"]["ouest"] == "A"  # entrée par l'ouest (en marchant vers l'est) : la porte est sur le mur A
    assert list(session.checklist.pieces) == ["couloir", "sejour", "buanderie"]  # les pièces du Carrez et du repérage
    assert [m["nom"] for m in recus if m["type"] == "piece_reconnue"] == ["Entrée", "Séjour", "Cuisine", "Séjour"]
    assert claude.references[-1] == ["Entrée", "Séjour", "Buanderie"]  # une image de chaque pièce, sous son nom du moment
    # Jamais demandée : seulement annoncée (« Nouvelle pièce : … »), pour être corrigée aussitôt.
    assert all(m["texte"].startswith("Nouvelle pièce : ") for m in recus if m["type"] == "dire" and "pièce" in m["texte"].lower())


def test_coin_du_sejour_reconnu_a_tort_puis_corrige_a_la_voix(tmp_path):
    # Essai sur la visite du 22/10 : le coin repas du séjour pris pour une « salle à manger ». « Non, c'est le séjour. »
    avis = {1.0: AvisPiece(None, "Séjour", "forte"), 40.0: AvisPiece(None, "Salle à manger", "forte"),
            50.0: AvisPiece(None, "Séjour", "moyenne")}  # « nouvelle séjour » dans le séjour : un autre coin, pas « Séjour 2 »
    claude = ClaudeQuiVoitLesPieces(avis)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await filmer(session, 1.0, 0.0)
        await filmer(session, 40.0, 90.0)
        await parler(session, "Non, c'est le séjour.")
        await attendre(session)
        await filmer(session, 50.0, 90.0)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert list(session.checklist.pieces) == ["sejour"] and session.checklist.nom_piece(session.checklist.piece_courante) == "Séjour"
    croquis = [m for m in recus if m["type"] == "etat"][-1]["checklist"]["croquis"]
    assert [p["nom"] for p in croquis["pieces"]] == ["Séjour"] and croquis["portes"] == []


def test_salle_a_manger_apres_la_salle_de_bains_est_une_autre_piece(tmp_path):
    # « Salle de bains » puis « nouvelle salle à manger » : même premier mot, mais deux pièces différentes.
    avis = {1.0: AvisPiece(None, "Salle de bains", "forte"), 20.0: AvisPiece(None, "Salle à manger", "forte"),
            30.0: AvisPiece(None, "Salle à manger", "forte")}  # puis un autre coin de la salle à manger : la même
    claude = ClaudeQuiVoitLesPieces(avis)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await filmer(session, 1.0, 0.0)
        await filmer(session, 20.0, 90.0)
        await filmer(session, 30.0, 90.0)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert [session.checklist.nom_piece(k) for k in session.checklist.pieces] == ["Salle de bains", "Salle à manger"]
