"""Le geste d'une phrase du croquis lu dans la réponse de Claude (assistant/voix_croquis.py)."""

from assistant.voix_croquis import analyser_voix, contenu_voix, nom_entendu, nom_propre


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


def test_nom_entendu_meme_mal_transcrit():
    # Rejeu du 23/10 (12:46) : la transcription en direct abîme les noms, Claude les retrouve ; mais un nom absent de la
    # phrase est une invention (« tu m'as mis l'emploi » compris « Entrée »).
    phrase = "Tu continues au bout du séjour, là je suiseux s jour, tu m'as mis l'emploi."
    assert nom_entendu("Séjour", phrase) and not nom_entendu("Entrée", phrase)
    assert nom_entendu("Couloir", "J'y suis, je suis dans le couir.")
    assert nom_entendu("Salle de bain", "Ici il y a là salle de bin.")
    assert nom_entendu("Séjour", "le couloir qui relie la cuisine à ses jours")
    assert nom_entendu("WC", "Ici les toilettes.") and nom_entendu("Séjour", "Ici c'est le salon.")  # synonymes
    assert not nom_entendu("Cuisine", "Ici il y a la salle de bain.")
