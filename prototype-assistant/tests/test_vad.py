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
    # « parole » : parole confirmée (0,35 s), c'est là que la voix de l'assistant se coupe (étape 8).
    assert [e.type for e in ev] == ["debut", "parole", "fin"]
    assert abs(ev[1].t - 11.35) < 0.05  # la voix commence à 11,0 s
    phrase = ev[2].phrase
    assert abs(phrase.t_debut - 10.0) < 0.1  # 1 s de son gardé avant la voix (11,0 s)
    assert abs(phrase.t_fin - 13.0) < 0.15  # 0,5 s gardée après la voix (12,5 s)
    assert ev[2].t - 12.5 < 0.9  # fin déclarée moins de 0,9 s après la fin de la voix


def test_bruit_court_ignore():
    d = DetecteurPhrases()
    ev = envoyer(d, son((1.0, 0), (0.15, 8000), (1.2, 0)))
    assert [e.phrase for e in ev if e.type == "fin"] == [None]


def syllabes(duree):
    """Une voix : des syllabes de 0,2 s séparées de petits creux de 0,1 s (moins qu'une fin de phrase)."""
    return [partie for _ in range(int(duree / 0.3)) for partie in ((0.2, 6000), (0.1, 0))]


def test_phrase_trop_longue_coupee():
    d = DetecteurPhrases()
    d.reglages.duree_max_s = 3.0
    ev = envoyer(d, son((0.5, 0), *syllabes(7.0), (1.0, 0)))
    phrases = [e.phrase for e in ev if e.type == "fin" and e.phrase]
    assert len(phrases) >= 2


def test_bruit_fort_des_le_lancement_puis_une_phrase():
    """Visite de Noah du 22/10 au soir : bruit de fond à −45 dB dès le lancement, au-dessus du seuil de départ. Avant, tout
    était « parole » et la première phrase n'était coupée qu'au bout de 15 s ; le bruit est maintenant appris, et la
    phrase dite ensuite est détectée seule, et close à temps."""
    rng = np.random.default_rng(1)
    fond = rng.normal(0, 185, int(9.0 * TAUX))  # −45 dB, continu
    voix = son(*syllabes(1.5)).astype(float)
    signal = fond.copy()
    signal[int(5.0 * TAUX): int(5.0 * TAUX) + len(voix)] += voix
    ev = envoyer(DetecteurPhrases(), signal.clip(-32768, 32767).astype("<i2"))
    phrases = [e.phrase for e in ev if e.type == "fin" and e.phrase]
    dite = [ph for ph in phrases if ph.t_debut < 6.0 < ph.t_fin]
    assert len(dite) == 1 and dite[0].t_fin < 7.5 and dite[0].t_debut > 3.5


def test_trou_dans_le_son_clot_la_phrase():
    d = DetecteurPhrases()
    envoyer(d, son((0.5, 0), (1.0, 6000)), t0=0.0)
    ev = envoyer(d, son((1.0, 0)), t0=30.0)  # 28 s plus tard : perte de réseau
    assert ev and ev[0].type == "fin" and ev[0].phrase is not None


def test_ia_qui_parle_releve_le_seuil():
    d = DetecteurPhrases(ia_parle=True)
    ev = envoyer(d, son((1.0, 0), (1.0, 150), (1.0, 0)))  # son faible : écho du haut-parleur
    assert ev == []
