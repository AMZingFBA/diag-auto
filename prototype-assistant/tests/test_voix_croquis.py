"""Le geste d'une phrase du croquis lu dans la réponse de Claude (assistant/voix_croquis.py)."""

from assistant.voix_croquis import analyser_voix, contenu_voix, nom_propre


def test_reponse_de_claude_lue():
    g = analyser_voix('Bien sûr. {"geste": "correction", "nom": "la cuisine", "faux": "séjour", "reponse": "D\'accord, cuisine."}')
    assert (g.geste, g.nom, g.faux, g.reponse) == ("correction", "Cuisine", "Séjour", "D'accord, cuisine.")
    assert analyser_voix('{"geste": "ici", "nom": "petit couloir", "reponse": ""}').nom == "Couloir"
    assert analyser_voix('{"geste": "rien"}').geste == "rien"


def test_reponses_inutilisables():
    assert analyser_voix("pas de JSON") is None
    assert analyser_voix('{"geste": "danse"}') is None  # geste inconnu
    assert analyser_voix('{"geste": "ici", "nom": ""}') is None  # un espace sans nom


def test_nom_et_contexte():
    assert nom_propre(" l'entrée ") == "Entrée" and nom_propre("grande chambre") == "Chambre"
    texte = contenu_voix("ça c'est la cuisine du début", "Salon", ["Cuisine", "Salon"])[0]["text"]
    assert "« Salon »" in texte and "« Cuisine », « Salon »" in texte
