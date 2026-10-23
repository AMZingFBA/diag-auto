"""Mission choisie sur le téléphone avant de filmer (Noah, 23/10) : le DPE et ses questions, ou l'amiante et le plomb (le
croquis seul : pièces reconnues sur la vidéo et annoncées, aucune question du DPE)."""

import asyncio
import time

import assistant.session as module_session
from assistant.extraction import extraire
from assistant.checklist import Checklist
from assistant.regard import AvisPiece
from test_conversation import CerveauScenario, poli
from test_croquis_visite import ClaudeQuiVoitLesPieces, filmer
from test_fluidite import attendre, ouvrir, parler


def test_amiante_croquis_seul_sans_question_du_dpe(tmp_path, monkeypatch):
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)  # la reconnaissance est appelée par le test seul
    claude = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Séjour", "forte"), 20.0: AvisPiece(None, "Cuisine", "forte")})

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await session.ouvrir_visite()
        await filmer(session, 1.0, 0.0)
        await parler(session, "Le mur est en brique, il donne sur l'extérieur.")  # compris (un bip), mais aucune question
        await attendre(session)
        await filmer(session, 20.0, 90.0)
        await parler(session, "Non, c'est la buanderie.")  # la « cuisine » reconnue à tort, corrigée à la voix
        await attendre(session)
        await session.fin_visite()
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert [m["texte"] for m in recus if m["type"] == "dire"] == [
        "Je dessine le croquis : entrez dans chaque pièce et faites-en le tour.", "Nouvelle pièce : Séjour.",
        "Nouvelle pièce : Cuisine.", "Le croquis compte 2 pièces."]
    assert not [m for m in recus if m["type"] == "dire" and m.get("options")]  # aucune question à boutons
    assert [session.checklist.nom_piece(k) for k in session.checklist.pieces] == ["Séjour", "Buanderie"]
    # « Le mur est en brique » : rien de noté pour le DPE (seuls restent le plafond et le plancher prévus d'office, vides).
    assert not [e for e in session.checklist.elements if e.valeurs or e.source != "auto"]
    assert {r["outil"] for m in recus if m["type"] == "actions" for r in m["resultats"]} == {"piece_courante"}  # la pièce seule
    croquis = [m for m in recus if m["type"] == "etat"][-1]["checklist"]["croquis"]
    assert [p["nom"] for p in croquis["pieces"]] == ["Séjour", "Buanderie"]
    bilan = [m for m in recus if m["type"] == "bilan"][-1]
    assert bilan["manques"] == [] and bilan["bilan"]["mission"] == "amiante"


def test_dpe_ne_regarde_pas_les_pieces(tmp_path):
    # DPE : la pièce ne compte pas (étape 13) ; pas d'appel à Claude toutes les 6 s pour la reconnaître.
    claude = ClaudeQuiVoitLesPieces({})

    async def scenario():
        session, _ = await ouvrir(tmp_path, CerveauScenario(poli()))
        session.regard = claude
        await asyncio.wait_for(session._boucle_pieces(), 1.0)  # rend la main tout de suite (sinon : échec, pas blocage)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert session.mission == "dpe" and claude.references == []


def test_mission_inconnue_vaut_dpe(tmp_path):
    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="termites")
        await session.ouvrir_visite()
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert session.mission == "dpe" and [m["texte"] for m in recus if m["type"] == "dire"] == ["Ce mur donne sur quoi ?"]



def test_amiante_premier_coup_d_oeil_sans_attendre(tmp_path, monkeypatch):
    # Test de Noah du 23/10 : le croquis restait vide les premières secondes. Le premier coup d'œil part dès la 1re image.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    claude = ClaudeQuiVoitLesPieces({0.5: AvisPiece(None, "Entrée", "forte")})

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await session.recevoir_image(0.5, b"\xff\xd8image")
        for _ in range(40):
            if session.checklist.pieces:
                break
            await asyncio.sleep(0.05)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert claude.propositions is False  # amiante : seul le processus des pièces est lancé
    assert [p.nom for p in session.checklist.pieces.values()] == ["Entrée"]
    assert "Nouvelle pièce : Entrée." in [m["texte"] for m in recus if m["type"] == "dire"]



def test_une_autre_chambre_et_la_deuxieme_chambre():
    c = Checklist()
    c.definir_piece("Chambre", 0.0)
    assert [a for a in extraire("c'est une autre chambre", c, None).actions if a["outil"] == "piece_courante"] == [
        {"outil": "piece_courante", "nom": "Chambre", "nouvelle": "oui", "citation": "c'est une autre chambre"}]
    assert [a["nom"] for a in extraire("on passe dans la deuxième chambre", c, None).actions if a["outil"] == "piece_courante"] == ["Chambre 2"]
    assert [a["nom"] for a in extraire("Non, c'est la véranda.", c, None).actions if a["outil"] == "piece_courante"] == ["Véranda"]


def test_amiante_deux_chambres_semblables_et_pause(tmp_path, monkeypatch):
    # Claude reconnaît la 1re chambre en entrant dans la 2e (deux chambres semblables) : « non, c'est une autre chambre ».
    # Puis une pause : rien n'est reconnu ni annoncé (un appel, le garage filmé en passant) jusqu'à « on reprend ».
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    claude = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Chambre", "forte"), 20.0: AvisPiece("Chambre", "", "forte"),
                                     40.0: AvisPiece(None, "Garage", "forte")})

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await filmer(session, 1.0, 0.0)
        await filmer(session, 20.0, 90.0)
        await parler(session, "Non, c'est une autre chambre.")
        await attendre(session)
        await parler(session, "On fait une pause.")
        await attendre(session)
        pendant = session.en_pause
        await filmer(session, 40.0, 180.0)
        await parler(session, "On reprend.")
        await attendre(session)
        await session.terminer()
        return session, recus, pendant

    session, recus, pendant = asyncio.run(scenario())
    assert [session.checklist.nom_piece(k) for k in session.checklist.pieces] == ["Chambre", "Chambre 2"]
    assert pendant and not session.en_pause
    assert "Nouvelle pièce : Garage." not in [m["texte"] for m in recus if m["type"] == "dire"]


def test_amiante_piece_renommee_revue_sous_l_ancien_type(tmp_path, monkeypatch):
    # Relecture du 23/10 : « Cuisine » (Claude) → « non, c'est la buanderie » ; 6 s plus tard, dans un autre coin, Claude
    # répond « nouvelle Cuisine » : c'est toujours la buanderie, pas une nouvelle pièce.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    claude = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Cuisine", "forte"), 10.0: AvisPiece(None, "Cuisine", "forte")})

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await filmer(session, 1.0, 0.0)
        await parler(session, "Non, c'est la buanderie.")
        await attendre(session)
        await filmer(session, 10.0, 45.0)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert [session.checklist.nom_piece(k) for k in session.checklist.pieces] == ["Buanderie"]
    assert [m["texte"] for m in recus if m["type"] == "dire"] == ["Nouvelle pièce : Cuisine."]


def test_amiante_annonce_jamais_par_dessus_le_diagnostiqueur(tmp_path, monkeypatch):
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    claude = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Séjour", "forte")})

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        session._en_parole = True  # il parle quand la pièce est reconnue
        await filmer(session, 1.0, 0.0)
        await asyncio.sleep(0.5)
        pendant = [m["texte"] for m in recus if m["type"] == "dire"]
        session._en_parole, session._fin_parole = False, time.monotonic() - 2.0  # il s'est tu
        await asyncio.sleep(0.5)
        apres = [m["texte"] for m in recus if m["type"] == "dire"]
        await session.terminer()
        return pendant, apres

    pendant, apres = asyncio.run(scenario())
    assert pendant == [] and apres == ["Nouvelle pièce : Séjour."]


def test_dpe_lance_les_propositions_seules(tmp_path):
    claude = ClaudeQuiVoitLesPieces({})

    async def scenario():
        session, _ = await ouvrir(tmp_path, CerveauScenario(poli()))
        session.regard = claude
        await asyncio.sleep(0.2)  # démarrage des cerveaux
        await session.terminer()

    asyncio.run(scenario())
    assert claude.propositions is True and claude.pieces is False
