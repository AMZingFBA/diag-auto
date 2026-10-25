"""Trajectoire du téléphone (assistant/trajectoire.py) et plan qui en découle (assistant/plan.py) : les pièces sont là où
l'on a marché, dans un repère commun ; une rotation sur place n'est pas un déplacement ; les tournants sont suivis (avant :
toutes les pièces en ligne droite, dans l'ordre de leur détection)."""

import math

import pytest

from assistant.plan import axe_du_logement, construire, vers_dict
from assistant.trajectoire import Trajectoire


class Marcheur:
    """Fabrique des mesures (lacet à 15 par seconde) et des pas, comme le téléphone."""

    def __init__(self):
        self.t = 0.0
        self.lacet = 0.0
        self.traj = Trajectoire()
        self.mesurer(0.5)

    def mesurer(self, duree, rotation=0.0):
        n = max(1, round(duree * 15))
        for _ in range(n):
            self.t += duree / n
            self.lacet = (self.lacet + rotation / n) % 360
            self.traj.ajouter_mesure({"t": round(self.t, 3), "lacet": self.lacet})

    def tourner_vers(self, lacet, duree=0.6):
        self.mesurer(duree, ((lacet - self.lacet + 180) % 360) - 180)

    def marcher(self, pas):
        for _ in range(pas):
            self.mesurer(0.25)
            self.traj.ajouter_pas(self.t)
            self.mesurer(0.25)

    def tour_sur_place(self, duree=3.0, pietinements=4):
        debut = self.t
        for k in range(pietinements):  # quelques petits pas en tournant
            self.mesurer(duree / pietinements, 360.0 / pietinements)
            self.traj.ajouter_pas(self.t)
        self.traj.ajouter_tour(debut, self.t)


def test_marche_avec_tournants_et_rotation_sur_place():
    m = Marcheur()
    m.marcher(5)  # 3 m vers le « nord » du gyroscope
    m.tour_sur_place()  # un tour de la pièce : pas un déplacement
    m.tourner_vers(90)
    m.marcher(5)  # 3 m vers l'« est »
    x, y = m.traj.position(m.t)
    assert x == pytest.approx(3.0, abs=0.05) and y == pytest.approx(3.0, abs=0.05)
    assert m.traj.distance(0, m.t) == pytest.approx(6.0)  # les piétinements du tour ne comptent pas
    assert [round(mr.distance, 1) for mr in m.traj.marches()] == [3.0, 3.0]


def test_pas_pendant_une_rotation_rapide_ignores_meme_sans_tour_repere():
    m = Marcheur()
    for _ in range(4):
        m.mesurer(0.4, 90.0)  # 225°/s : on tourne sur place
        m.traj.ajouter_pas(m.t)
    assert m.traj.distance(0, m.t) == 0.0 and m.traj.position(m.t) == (0.0, 0.0)


def test_plan_suit_les_deplacements_et_pas_l_ordre_de_detection():
    # Entrée, puis 4 m vers le nord : séjour ; tour sur place ; puis 4 m vers l'ouest : cuisine ; retour au séjour ; puis
    # 4 m vers le sud depuis le séjour... vers l'est : chambre. Avant : Entrée, Séjour, Cuisine, Chambre en ligne droite.
    m = Marcheur()
    changements = [("entree", 0.0)]
    m.marcher(2)
    m.marcher(5)
    changements.append(("sejour", m.t + 3.0))  # reconnu 3 s après y être entré
    m.tour_sur_place()
    m.tourner_vers(270)
    m.mesurer(2.0)
    m.marcher(7)
    changements.append(("cuisine", m.t + 4.0))
    m.mesurer(4.0)
    m.tourner_vers(90)
    m.mesurer(2.0)
    m.marcher(7)
    changements.append(("sejour", m.t + 2.0))
    m.mesurer(3.0)
    m.marcher(7)
    changements.append(("chambre", m.t + 3.0))
    m.mesurer(3.0)
    plan = construire(m.traj, changements, m.t)
    centres = {cle: (sum(p[0] for p in s) / 4, sum(p[1] for p in s) / 4) for cle, s in plan.pieces.items()}
    assert set(centres) == {"entree", "sejour", "cuisine", "chambre"}
    assert centres["sejour"][1] > centres["entree"][1] + 1.5  # au nord de l'entrée
    assert centres["cuisine"][0] < centres["sejour"][0] - 1.5  # à l'ouest du séjour
    assert centres["chambre"][0] > centres["sejour"][0] + 1.5  # à l'est du séjour : pas en ligne
    # Aucune pièce ne recouvre une autre, et les portes sont entre les pièces voisines.
    assert {(a, b) for a, b, _, _ in plan.portes} >= {("entree", "sejour"), ("sejour", "cuisine"), ("sejour", "chambre")}
    d = vers_dict(plan, {"sejour": "Séjour"}, {}, "chambre")
    assert d["courante"] == "chambre" and len(d["trajet"]) >= 10 and d["pieces"][0]["polygone"]


def test_plan_tourne_vers_le_nord_quand_la_boussole_est_connue():
    m = Marcheur()
    m.marcher(5)  # vers le lacet 0, qui est en vrai le cap 90 (est) : correction cap − lacet = 90
    plan = construire(m.traj, [("a", 0.0)], m.t, correction=90.0)
    x, y = plan.position
    assert plan.oriente and x == pytest.approx(3.0, abs=0.05) and y == pytest.approx(0.0, abs=0.05)


def test_axe_du_logement_pris_sur_les_marches():
    assert axe_du_logement([10, 11, 100, 190, 281, 9]) == pytest.approx(10.0, abs=1.5)
    assert axe_du_logement([0, 45, 90]) == 0.0  # trop peu de pas


def test_distance_au_mur_commun_et_portes_sur_le_mur():
    m = Marcheur()
    m.marcher(6)
    changements = [("a", 0.0), ("b", m.t)]
    m.mesurer(2.0)
    plan = construire(m.traj, changements, m.t)
    (a, b, x, y), = plan.portes
    ya = max(p[1] for p in plan.pieces["a"])
    yb = min(p[1] for p in plan.pieces["b"])
    assert ya == pytest.approx(yb) and y == pytest.approx(ya)  # la porte est sur le mur commun
    assert math.isfinite(x)


def test_visite_amiante_plan_et_rotation_sur_place_sans_changement_de_piece(tmp_path, monkeypatch):
    # Entrée ; 6 pas vers le nord : séjour ; un tour sur place (Claude croit voir une cuisine : refusé, on n'a pas marché) ;
    # 6 pas vers l'est : cuisine. Le plan : le séjour au nord de l'entrée, la cuisine à l'est du séjour.
    import asyncio

    import assistant.session as module_session
    from assistant.regard import AvisPiece
    from test_conversation import CerveauScenario, poli
    from test_croquis_visite import ClaudeQuiVoitLesPieces
    from test_fluidite import ouvrir

    monkeypatch.setattr(module_session, "INTERVALLE_PIECES_S", 1000.0)
    monkeypatch.setattr(module_session, "RECONNAITRE_PIECES", True)  # pièces reconnues sur l'image (coupé depuis le 25/10)
    claude = ClaudeQuiVoitLesPieces({1.0: AvisPiece(None, "Entrée", "forte"), 8.0: AvisPiece(None, "Séjour", "forte"),
                                     14.0: AvisPiece(None, "Cuisine", "forte"), 24.0: AvisPiece(None, "Cuisine", "forte")})

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        etat = {"t": 0.0, "lacet": 0.0}

        async def bouger(duree, rotation=0.0, pas=0):
            n = max(1, round(duree * 15))
            mesures, instants_pas = [], []
            for k in range(n):
                etat["t"] += duree / n
                etat["lacet"] = (etat["lacet"] + rotation / n) % 360
                mesures.append({"t": round(etat["t"], 3), "lacet": round(etat["lacet"], 1), "inclinaison": 80.0})
                if pas and k % max(1, n // pas) == n // pas // 2 and len(instants_pas) < pas:
                    instants_pas.append(round(etat["t"], 3))
            await session.recevoir_controle({"type": "capteurs_lot", "mesures": mesures, "pas": instants_pas})

        async def regarder(t):
            await session.recevoir_image(t, b"\xff\xd8image " + str(t).encode())
            session.t_video = t
            await session._reconnaitre_piece()

        await bouger(1.0)
        await regarder(1.0)  # l'entrée
        await bouger(4.0, pas=6)  # vers le nord
        await bouger(3.0)
        await regarder(8.0)  # le séjour
        await bouger(3.0, rotation=360.0)  # un tour sur place
        await bouger(3.0)
        await regarder(14.0)  # « nouvelle cuisine » sans avoir marché : refusé
        await bouger(0.6, rotation=90.0)
        await bouger(4.0, pas=6)  # vers l'est
        await bouger(4.0)
        await regarder(24.0)  # la cuisine
        await session.envoyer_etat()
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert [session.checklist.nom_piece(k) for k in session.checklist.pieces] == ["Entrée", "Séjour", "Cuisine"]
    journal = (tmp_path / "journal.jsonl").read_text(encoding="utf-8")
    assert '"evenement": "changement_refuse"' in journal  # la rotation sur place n'a pas changé de pièce
    plan = [m for m in recus if m["type"] == "etat"][-1]["checklist"]["croquis"]["plan"]
    centres = {p["cle"]: (sum(q[0] for q in p["polygone"]) / 4, sum(q[1] for q in p["polygone"]) / 4) for p in plan["pieces"]}
    assert centres["sejour"][1] > centres["entree"][1] + 1.0
    assert centres["cuisine"][0] > centres["sejour"][0] + 1.0
    assert not plan["oriente"]  # sans boussole : le repère du gyroscope


def test_piece_decidee_sur_les_images_du_tour(tmp_path, monkeypatch):
    # Test de Noah du 23/10 : la chambre, visitée 10 s avec un tour de 13 images, n'avait eu qu'un avis « moyen ». Un tour
    # de la pièce suffit maintenant pour la décider (sur ses images, pas sur 2 images prises au hasard).
    import asyncio

    import assistant.session as module_session
    from assistant.regard import AvisPiece
    from test_conversation import CerveauScenario, poli
    from test_fluidite import ouvrir

    async def sans_coup_d_oeil(self):  # seul le tour regarde la pièce dans ce test
        return None

    monkeypatch.setattr(module_session.Session, "_boucle_pieces", sans_coup_d_oeil)
    monkeypatch.setattr(module_session, "RECONNAITRE_PIECES", True)  # pièces reconnues sur l'image (coupé depuis le 25/10)

    class ClaudeDuTour:
        def __init__(self):
            self.vues = []

        async def demarrer(self, **_):
            pass

        async def fermer(self):
            pass

        async def reconnaitre(self, images, references, courante):
            self.vues.append([round(i.t, 1) for i in images])
            return AvisPiece(None, "Chambre", "moyenne")

    claude = ClaudeDuTour()

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), mission="amiante")
        session.regard = claude
        t, lacet = 0.0, 0.0
        for k in range(75):  # 1 s immobile, 3 s de tour, 1 s immobile
            t += 1 / 15
            if 1.0 < t <= 4.0:
                lacet = (lacet + 360 / 45) % 360
            mesure = {"t": round(t, 3), "lacet": round(lacet, 1), "inclinaison": 80.0}
            await session.recevoir_controle({"type": "capteurs_lot", "mesures": [mesure], "pas": []})
            if k % 7 == 3:
                await session.recevoir_image(t, b"\xff\xd8image " + str(k).encode(), {"raison": "rotation", "lacet": lacet})
        await asyncio.sleep(1.5)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert [p.nom for p in session.checklist.pieces.values()] == ["Chambre"]
    assert claude.vues and len(claude.vues[0]) >= 2 and all(1.0 <= t <= 3.6 for t in claude.vues[0])  # images du tour, sans la fin



def test_pas_reperes_dans_l_acceleration_meme_faibles():
    # Visite de Noah du 23/10 : en marchant lentement en filmant, des pics de 0,6 à 0,8 m/s², que le seuil du téléphone
    # (1 m/s²) manquait. Ici repérés ; les pas envoyés par le téléphone sont alors ignorés (pas de double compte).
    traj = Trajectoire()
    t = 0.0
    for k in range(60):  # 4 s à 15 mesures par seconde, un pic toutes les 0,67 s (1,5 pas par seconde)
        t += 1 / 15
        acc = 0.7 if k % 10 == 5 else 0.0
        traj.ajouter_mesure({"t": round(t, 3), "lacet": 0.0, "acc": acc})
        traj.ajouter_pas(t)  # pas du téléphone : ignorés
    assert len([p for p in traj.pas if p.compte]) == 6
    x, y = traj.position(t)
    assert y == pytest.approx(3.6) and x == pytest.approx(0.0, abs=1e-9)
