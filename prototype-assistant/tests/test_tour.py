"""Tours de pièce repérés dans les capteurs (assistant/tour.py) : sur des relevés fabriqués, puis sur les vrais relevés
des visites de Noah (tests/donnees : orientation seule, extraite de capteurs-continus.json)."""

import json
from pathlib import Path

import pytest

from assistant.tour import DetecteurTour, detecter

DONNEES = Path(__file__).parent / "donnees"


def releve(segments, depart=0.0, cap=100.0, beta=80.0, frequence=15.0):
    """Mesures à 15 par seconde : chaque segment = (durée en s, rotation en degrés pendant ce temps)."""
    mesures, t = [], depart
    for duree, rotation in segments:
        n = max(1, round(duree * frequence))
        for _ in range(n):
            t += 1.0 / frequence
            cap = (cap + rotation / n) % 360.0
            mesures.append({"t": round(t, 3), "lacet": round(cap, 1), "cap": round(cap, 1), "inclinaison": beta})
    return mesures


def test_tour_de_3_s():
    tours = detecter(releve([(2.0, 0), (3.0, 360), (2.0, 0)]))
    assert len(tours) == 1
    tour = tours[0]
    assert 1.9 <= tour.t_debut <= 2.2 and 4.8 <= tour.t_fin <= 5.1
    assert tour.rotation == pytest.approx(360, abs=30) and tour.couverture == 360.0
    assert tour.cap_avant == pytest.approx(100.0, abs=1)  # la direction de la caméra avant de tourner : l'entrée


def test_tour_dans_l_autre_sens_et_tour_lent():
    assert [round(t.rotation) < 0 for t in detecter(releve([(1, 0), (3.0, -360), (1, 0)]))] == [True]
    assert len(detecter(releve([(1, 0), (7.5, 360), (1, 0)]))) == 1  # 48°/s : encore un tour


def test_pas_de_tour():
    assert detecter(releve([(1, 0), (2.0, 180), (1, 0)])) == []  # un demi-tour
    assert detecter(releve([(1, 0), (12.0, 360), (1, 0)])) == []  # trop lent : un balayage, pas un tour de 3 s
    assert detecter(releve([(1, 0)] + [(2.0, 120), (2.0, -120)] * 6)) == []  # balayages de DPE, de long en large
    assert detecter(releve([(1, 0), (3.0, 360), (1, 0)], beta=160.0)) == []  # caméra vers le plafond


def test_pause_au_milieu_du_tour():
    tours = detecter(releve([(1, 0), (1.5, 180), (0.6, 0), (1.5, 180), (1, 0)]))
    assert len(tours) == 1 and tours[0].rotation == pytest.approx(360, abs=30)


def test_trou_dans_le_releve_interrompt_le_tour():
    mesures = releve([(1, 0), (3.0, 360), (1, 0)])
    sans_milieu = [m for m in mesures if not 2.2 < m["t"] < 3.4]  # page cachée 1,2 s au milieu du tour
    assert detecter(sans_milieu) == []


def test_mesures_en_direct_par_lots_et_rattrapage():
    # Les lots arrivent dans l'ordre, puis un lot déjà reçu revient (rattrapage après une coupure) : un seul tour.
    detecteur = DetecteurTour()
    mesures = releve([(1, 0), (3.0, 360), (1, 0)])
    tours = [tour for m in mesures + mesures[:20] if (tour := detecteur.ajouter(m))]
    assert len(tours) == 1 and detecteur.finir() is None


def charger(nom):
    return json.loads((DONNEES / nom).read_text(encoding="utf-8"))["mesures"]


def test_vrai_tour_de_noah_et_faux_tour_ignore():
    # Visite du 23/10 au matin : un vrai tour (14,6 à 17,2 s, ~380° en 2,2 s, téléphone droit) ; puis un faux (30,5 à
    # 33,4 s : le téléphone bascule vers le plafond, puis est posé).
    tours = detecter(charger("capteurs-tour-reel.json"))
    assert len(tours) == 1
    tour = tours[0]
    assert 14.0 <= tour.t_debut <= 15.2 and 16.5 <= tour.t_fin <= 17.6 and abs(tour.rotation) >= 330
    assert tour.repere == "lacet" and tour.cap_avant is not None


@pytest.mark.parametrize("nom", ["capteurs-sans-tour.json", "capteurs-sans-tour-2.json"])
def test_visites_sans_tour(nom):
    # Chambre puis passage au séjour (balayage rapide de 113° en 3,5 s) ; séjour filmé de jour (balayage de ~200°).
    assert detecter(charger(nom)) == []


def test_tour_a_une_mesure_par_seconde_invisible():
    # Ce que voyait le serveur avant (une mesure par seconde) : le tour n'y est pas.
    mesures = charger("capteurs-tour-reel.json")
    par_seconde, prochaine = [], 0.0
    for m in mesures:
        if m["t"] >= prochaine:
            par_seconde.append(m)
            prochaine = m["t"] + 1.0
    assert detecter(par_seconde) == []
