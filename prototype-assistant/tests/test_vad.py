import numpy as np

from assistant.vad import TAUX, DetecteurPhrases


def son(*parties):
    """Construit un signal : suite de (durée en s, amplitude) ; amplitude 0 = bruit de fond faible."""
    rng = np.random.default_rng(0)
    morceaux = []
    for duree, amplitude in parties:
        n = int(duree * TAUX)
        bruit = rng.normal(0, 30, n)
        voix = amplitude * np.sin(2 * np.pi * 220 * np.arange(n) / TAUX) if amplitude else 0
        morceaux.append(bruit + voix)
    return np.concatenate(morceaux).clip(-32768, 32767).astype("<i2")


def envoyer(detecteur, signal, t0=0.0, taille=1600):
    evenements = []
    for i in range(0, len(signal), taille):
        evenements += detecteur.ajouter(signal[i : i + taille].tobytes(), t0 + i / TAUX)
    return evenements


def test_une_phrase_detectee_avec_ses_instants():
    d = DetecteurPhrases()
    ev = envoyer(d, son((1.0, 0), (1.5, 6000), (1.2, 0)), t0=10.0)
    assert [e.type for e in ev] == ["debut", "fin"]
    phrase = ev[1].phrase
    assert abs(phrase.t_debut - 10.7) < 0.1  # 0,3 s de pré-roll avant 11,0 s
    assert abs(phrase.t_fin - 12.7) < 0.15
    assert ev[1].t - 12.5 < 0.9  # fin déclarée moins de 0,9 s après la fin de la voix


def test_bruit_court_ignore():
    d = DetecteurPhrases()
    ev = envoyer(d, son((1.0, 0), (0.15, 8000), (1.2, 0)))
    assert [e.phrase for e in ev if e.type == "fin"] == [None]


def test_phrase_trop_longue_coupee():
    d = DetecteurPhrases()
    d.reglages.duree_max_s = 3.0
    ev = envoyer(d, son((0.5, 0), (7.0, 6000), (1.0, 0)))
    phrases = [e.phrase for e in ev if e.type == "fin" and e.phrase]
    assert len(phrases) >= 2


def test_trou_dans_le_son_clot_la_phrase():
    d = DetecteurPhrases()
    envoyer(d, son((0.5, 0), (1.0, 6000)), t0=0.0)
    ev = envoyer(d, son((1.0, 0)), t0=30.0)  # 28 s plus tard : perte de réseau
    assert ev and ev[0].type == "fin" and ev[0].phrase is not None


def test_ia_qui_parle_releve_le_seuil():
    d = DetecteurPhrases(ia_parle=True)
    ev = envoyer(d, son((1.0, 0), (1.0, 150), (1.0, 0)))  # son faible : écho du haut-parleur
    assert ev == []
