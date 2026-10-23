"""Relevé des murs pendant la visite (amiante, plomb ; Noah, 23/10 : « le plus safe, ce serait de suivre les murs de la
maison ») : le bouton « Murs » ou la voix, chaque coin visé une seconde, la pièce fermée en revenant sur le premier coin, sa
forme exacte sur le plan."""

import asyncio

import assistant.session as module_session
from assistant.regard import AvisPiece
from test_coins import RECTANGLE, cibles, flux
from test_conversation import CerveauScenario, poli
from test_croquis_visite import ClaudeQuiVoitLesPieces, filmer
from test_fluidite import attendre, ouvrir, parler


async def envoyer_mesures(session, mesures):
    for k in range(0, len(mesures), 4):  # comme le téléphone : un lot de mesures toutes les 0,25 s
        await session.recevoir_controle({"type": "capteurs_lot", "mesures": mesures[k:k + 4]})


def plan_final(recus):
    return [m for m in recus if m["type"] == "etat"][-1]["checklist"]["croquis"]["plan"]


def test_releve_au_bouton_quatre_coins_puis_le_premier(tmp_path, monkeypatch):
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    claude = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Chambre", "forte")})

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        await filmer(session, 1.0, 0.0)
        await session.recevoir_controle({"type": "releve", "action": "debut"})
        await envoyer_mesures(session, flux(cibles(RECTANGLE, (1.2, 1.0)), t0=2.0))
        await attendre(session)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert [m["n"] for m in recus if m["type"] == "coin"] == [1, 2, 3, 4]
    releve = [m for m in recus if m["type"] == "releve"]
    assert releve[0]["etat"] == "ouvert" and releve[-1] == {"type": "releve", "etat": "ferme", "piece": "Chambre", "murs": 4}
    assert "Chambre : 4 murs." in [m["texte"] for m in recus if m["type"] == "dire"]
    chambre = next(p for p in plan_final(recus)["pieces"] if p["nom"] == "Chambre")
    assert chambre["mesuree"] and all(abs(a - b) / b < 0.05 for a, b in zip(sorted(chambre["murs"]), [3.0, 3.0, 4.0, 4.0]))
    assert session.releve is None and len(session.releves["chambre"]) == 4


def test_releve_a_la_voix_piece_a_nommer_annule_et_fini(tmp_path, monkeypatch):
    # Pas encore de pièce : « les murs » en ouvre une à nommer ; « ici c'est la cuisine », dit sans bouger, la nomme (ses
    # coins la suivent) ; « annule » efface la dernière visée (ratée) ; « c'est fini » ferme la pièce.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    mesures = flux(cibles(RECTANGLE, (1.2, 1.0)), t0=2.0, fermer=False)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({})
        await parler(session, "Les murs.")
        await attendre(session)
        ouverte = session.checklist.nom_piece(session.releve)
        await parler(session, "Ici c'est la cuisine.")
        await attendre(session)
        await envoyer_mesures(session, mesures)
        await parler(session, "Annule.")
        await attendre(session)
        apres_annule = len(session.releves["cuisine"])
        await parler(session, "C'est fini.")
        await attendre(session)
        await session.terminer()
        return session, recus, ouverte, apres_annule

    session, recus, ouverte, apres_annule = asyncio.run(scenario())
    assert ouverte == "Pièce"
    assert [p.nom for p in session.checklist.pieces.values()] == ["Cuisine"]  # nommée, pas une deuxième pièce
    assert apres_annule == 3 and session.releve is None
    assert [m for m in recus if m["type"] == "releve"][-1]["murs"] == 4  # trois coins d'un rectangle suffisent
    assert "Cuisine : 4 murs." in [m["texte"] for m in recus if m["type"] == "dire"]


def test_sans_relevé_les_arrets_ne_sont_pas_des_coins(tmp_path, monkeypatch):
    # Visites de Noah du 23/10 : la caméra s'arrête souvent en regardant le sol (pour parler) ; sans relevé ouvert, rien.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Chambre", "forte")})
        await filmer(session, 1.0, 0.0)
        await envoyer_mesures(session, flux(cibles(RECTANGLE, (1.2, 1.0)), t0=2.0))
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert not [m for m in recus if m["type"] in ("coin", "releve")] and not session.releves


def marcher(depart, arrivees, t, rotation=17.0):
    """Mesures en marchant (un pas de 0,6 m toutes les 0,53 s, caméra dans le sens de la marche, 22° vers le sol)."""
    import math

    mesures, (x, y) = [], depart
    for bx, by in arrivees:
        while math.dist((x, y), (bx, by)) > 0.3:
            cap = math.degrees(math.atan2(bx - x, by - y))
            for k in range(8):
                t += 1 / 15
                mesures.append({"t": round(t, 3), "lacet": round((cap + rotation) % 360.0, 2), "elevation": -22.0,
                                "acc": 1.0 if k == 1 else 0.0})
            x, y = x + 0.6 * math.sin(math.radians(cap)), y + 0.6 * math.cos(math.radians(cap))
    return mesures, t, (x, y)


def test_deux_pieces_relevees_mur_contre_mur(tmp_path, monkeypatch):
    # Un couloir de 1 × 4,5 m, puis une chambre de 4 × 3 m à l'est, qui partage son mur : chacune relevée depuis l'endroit
    # où l'on s'arrête, la marche entre les deux comptée en pas. Le plan les pose côte à côte, mur contre mur.
    import math

    from assistant.trajectoire import tourner

    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    couloir = [(0.0, 0.0), (1.0, 0.0), (1.0, 4.5), (0.0, 4.5)]
    chambre = [(1.0, 2.0), (5.0, 2.0), (5.0, 5.0), (1.0, 5.0)]
    depart = (0.5, 0.8)  # le téléphone part d'ici : origine de la trajectoire

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({})
        await parler(session, "Ici c'est le couloir.")
        await attendre(session)
        await parler(session, "Les murs.")
        await attendre(session)
        aim = flux(cibles(couloir, depart), t0=5.0)
        await envoyer_mesures(session, aim)
        marche, t, arrivee = marcher(depart, [(0.5, 3.2), (2.3, 3.2)], aim[-1]["t"])
        await envoyer_mesures(session, marche)
        session.t_video = t
        await parler(session, "Ici c'est la chambre.")
        await attendre(session)
        await parler(session, "Les murs.")
        await attendre(session)
        await envoyer_mesures(session, flux(cibles(chambre, arrivee), t0=t + 2.0))
        await attendre(session)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert [m["murs"] for m in recus if m["type"] == "releve" and m["etat"] == "ferme"] == [4, 4]
    plan = plan_final(recus)
    pieces = {p["nom"]: p for p in plan["pieces"]}
    assert pieces["Couloir"]["mesuree"] and pieces["Chambre"]["mesuree"]
    assert all(abs(a - b) / b < 0.06 for a, b in zip(sorted(pieces["Couloir"]["murs"]), [1.0, 1.0, 4.5, 4.5]))
    assert all(abs(a - b) / b < 0.06 for a, b in zip(sorted(pieces["Chambre"]["murs"]), [3.0, 3.0, 4.0, 4.0]))
    # Dans le repère du monde (le gyroscope était décalé de 17°) : la chambre à l'est du couloir, mur contre mur.
    monde = {nom: [tourner(x, y, -17.0) for x, y in p["polygone"]] for nom, p in pieces.items()}
    est_couloir = max(x for x, _ in monde["Couloir"])
    ouest_chambre = min(x for x, _ in monde["Chambre"])
    assert abs(est_couloir - ouest_chambre) < 0.15
    centre = {nom: (sum(x for x, _ in pts) / 4, sum(y for _, y in pts) / 4) for nom, pts in monde.items()}
    assert math.dist((centre["Chambre"][0] - centre["Couloir"][0], centre["Chambre"][1] - centre["Couloir"][1]), (2.5, 1.25)) < 0.5


def test_secousses_en_visant_ne_sont_pas_des_pas(tmp_path, monkeypatch):
    # Entre deux coins, le téléphone est secoué : le serveur y voit des « pas » (pics d'accélération). Tous les coins sont vus
    # d'où l'on était au premier, et ces pas ne déplacent pas la trajectoire.
    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    mesures = flux(cibles(RECTANGLE, (1.2, 1.0)), t0=2.0)
    for k, m in enumerate(mesures):
        m["acc"] = 1.0 if k % 20 == 10 else 0.0

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Chambre", "forte")})
        await filmer(session, 1.0, 0.0)
        await session.recevoir_controle({"type": "releve", "action": "debut"})
        await envoyer_mesures(session, mesures)
        await attendre(session)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert session.trajectoire.pas and not any(p.compte for p in session.trajectoire.pas)
    chambre = next(p for p in plan_final(recus)["pieces"] if p["nom"] == "Chambre")
    assert all(abs(a - b) / b < 0.05 for a, b in zip(sorted(chambre["murs"]), [3.0, 3.0, 4.0, 4.0]))
