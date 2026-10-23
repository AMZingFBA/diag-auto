"""Tracé guidé du plan pendant la visite (amiante, plomb ; Noah, 23/10) : chaque coin visé avec la croix et validé d'un
appui (sa place au sol calculée sur le téléphone), le contour fermé en revenant au premier coin, un coin annulé ou corrigé ;
le plan 2D fait des points réellement enregistrés, avec leurs angles, chaque pièce tracée à sa place."""

import asyncio
import math

import assistant.session as module_session
from assistant.regard import AvisPiece
from test_conversation import CerveauScenario, poli
from test_croquis_visite import ClaudeQuiVoitLesPieces, filmer
from test_fluidite import attendre, ouvrir, parler

CHAMBRE = [(1.0, 2.0), (5.0, 2.0), (5.0, 5.0), (1.0, 5.0)]
# Une pièce pas d'équerre (un mur en biais) : ses angles sont gardés tels quels.
BIAIS = [(0.0, 0.0), (3.0, 0.0), (3.6, 2.5), (0.0, 2.5)]


async def tracer(session, points, fermer=True, t0=5.0):
    await session.recevoir_controle({"type": "trace", "action": "debut"})
    for k, (x, y) in enumerate(points):
        await session.recevoir_controle({"type": "trace", "action": "point", "x": x, "y": y, "t": t0 + k})
    if fermer:
        await session.recevoir_controle({"type": "trace", "action": "fermer"})


def plan_final(recus):
    return [m for m in recus if m["type"] == "etat"][-1]["checklist"]["croquis"]["plan"]


def meme_contour(polygone, points):
    """Les mêmes sommets (à 1 mm près), dans l'ordre ou à l'envers."""
    n = len(points)
    if len(polygone) != n:
        return False
    for depart in range(n):
        for sens in (1, -1):
            if all(math.dist(polygone[(depart + sens * k) % n], points[k]) < 1e-3 for k in range(n)):
                return True
    return False


def test_coins_valides_contour_ferme_et_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Chambre", "forte")})
        await filmer(session, 1.0, 0.0)
        await tracer(session, CHAMBRE)
        await attendre(session)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    trace = [m for m in recus if m["type"] == "trace"][-1]
    assert trace["ouvert"] and trace["pieces"] == [{"cle": "chambre", "nom": "Chambre", "ferme": True, "points": [list(p) for p in CHAMBRE]}]
    assert "Chambre : 4 murs." in [m["texte"] for m in recus if m["type"] == "dire"]
    chambre = next(p for p in plan_final(recus)["pieces"] if p["nom"] == "Chambre")
    assert chambre["mesuree"] and meme_contour(chambre["polygone"], CHAMBRE)  # à sa place, tel que tracé
    assert sorted(chambre["murs"]) == [3.0, 3.0, 4.0, 4.0]


def test_les_angles_sont_gardes_et_deux_pieces_tracees_ne_bougent_pas(tmp_path, monkeypatch):
    # Un mur en biais reste en biais ; deux pièces tracées qui se touchent (ou se chevauchent un peu, la position dérive)
    # restent là où leurs coins ont été validés.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    voisine = [(3.5, 0.0), (6.0, 0.0), (6.0, 2.5), (3.5, 2.5)]  # 10 cm sur la pièce en biais

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="plomb")
        session.regard = ClaudeQuiVoitLesPieces({})
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        await tracer(session, BIAIS)
        await parler(session, "Ici c'est la cuisine.")
        await attendre(session)
        await tracer(session, voisine, t0=20.0)
        await attendre(session)
        await session.terminer()
        return recus

    recus = asyncio.run(scenario())
    pieces = {p["nom"]: p for p in plan_final(recus)["pieces"]}
    assert meme_contour(pieces["Séjour"]["polygone"], BIAIS) and meme_contour(pieces["Cuisine"]["polygone"], voisine)
    assert any(abs(m - math.dist((3.0, 0.0), (3.6, 2.5))) < 0.01 for m in pieces["Séjour"]["murs"])


def test_annuler_puis_corriger_un_coin(tmp_path, monkeypatch):
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Chambre", "forte")})
        await filmer(session, 1.0, 0.0)
        await tracer(session, CHAMBRE)
        await session.recevoir_controle({"type": "trace", "action": "annuler"})  # rouvre le contour
        rouvert = [m for m in recus if m["type"] == "trace"][-1]["pieces"][0]
        await session.recevoir_controle({"type": "trace", "action": "annuler"})  # efface le dernier coin
        efface = [m for m in recus if m["type"] == "trace"][-1]["pieces"][0]
        await session.recevoir_controle({"type": "trace", "action": "point", "x": 1.0, "y": 5.2, "t": 30.0})
        await session.recevoir_controle({"type": "trace", "action": "deplacer", "cle": "chambre", "index": 1, "x": 5.1, "y": 2.0})
        await session.recevoir_controle({"type": "trace", "action": "fermer"})
        await session.terminer()
        return recus, rouvert, efface

    recus, rouvert, efface = asyncio.run(scenario())
    assert not rouvert["ferme"] and len(rouvert["points"]) == 4
    assert not efface["ferme"] and len(efface["points"]) == 3
    final = [m for m in recus if m["type"] == "trace"][-1]["pieces"][0]
    assert final["ferme"] and final["points"] == [[1.0, 2.0], [5.1, 2.0], [5.0, 5.0], [1.0, 5.2]]


def test_piece_a_nommer_nommee_a_la_voix_puis_une_autre_piece(tmp_path, monkeypatch):
    # Pas encore de pièce : le premier coin en ouvre une à nommer ; « ici c'est la cuisine », dit sans bouger, la nomme
    # (son tracé la suit). La cuisine fermée, un nouveau coin sans avoir nommé de pièce : une autre pièce à nommer.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({})
        await session.recevoir_controle({"type": "trace", "action": "debut"})
        await session.recevoir_controle({"type": "trace", "action": "point", "x": 0.0, "y": 0.0, "t": 2.0})
        await parler(session, "Ici c'est la cuisine.")
        await attendre(session)
        for k, (x, y) in enumerate([(3.0, 0.0), (3.0, 3.0), (0.0, 3.0)]):
            await session.recevoir_controle({"type": "trace", "action": "point", "x": x, "y": y, "t": 10.0 + k})
        await session.recevoir_controle({"type": "trace", "action": "fermer"})
        await session.recevoir_controle({"type": "trace", "action": "point", "x": 3.2, "y": 0.0, "t": 20.0})
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert [p.nom for p in session.checklist.pieces.values()] == ["Cuisine", "Pièce"]
    assert session.traces["cuisine"]["ferme"] and len(session.traces["cuisine"]["points"]) == 4
    assert [x for x, _, _ in session.traces["piece"]["points"]] == [3.2]


def test_a_la_voix_les_murs_annule_et_fini(tmp_path, monkeypatch):
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Chambre", "forte")})
        await filmer(session, 1.0, 0.0)
        await parler(session, "Les murs.")
        await attendre(session)
        ouvert = session.trace_ouvert
        for k, (x, y) in enumerate(CHAMBRE[:3]):
            await session.recevoir_controle({"type": "trace", "action": "point", "x": x, "y": y, "t": 5.0 + k})
        await parler(session, "Annule.")
        await attendre(session)
        apres = len(session.traces["chambre"]["points"])
        await parler(session, "C'est fini.")
        await attendre(session)
        await session.terminer()
        return session, recus, ouvert, apres

    session, recus, ouvert, apres = asyncio.run(scenario())
    assert ouvert and apres == 2 and not session.trace_ouvert
    assert [m["ouvert"] for m in recus if m["type"] == "trace"][0] is True  # le téléphone passe en mode tracé


def test_position_suivie_par_le_telephone(tmp_path, monkeypatch):
    # Le téléphone envoie sa position (suivie par le sol filmé) avec chaque mesure : la trajectoire la reprend telle quelle.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)

    async def scenario():
        session, _ = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        mesures = [{"t": 2.0 + k / 15, "lacet": 90.0, "elevation": -30.0, "x": round(min(k, 30) * 0.05, 3), "y": 0.0}
                   for k in range(45)]
        for k in range(0, len(mesures), 4):
            await session.recevoir_controle({"type": "capteurs_lot", "mesures": mesures[k:k + 4]})
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    t = session.trajectoire
    assert t.avec_pas() and abs(t.position(10.0)[0] - 1.5) < 0.1 and abs(t.distance(0.0, 10.0) - 1.5) < 0.11
    assert [round(p.direction) for p in t.pas] == [90, 90]  # deux pas déduits (0,6 m chacun), vers l'est
