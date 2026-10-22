import asyncio
import sys
import time
from pathlib import Path

from assistant.actions import appliquer
from assistant.cerveau import (
    CerveauClaudeCode, Contexte, ImageInstant, analyser_reponse, commande_claude, consignes, contenu_message,
    dire_partiel, env_claude, extraire_cible, extraire_dire, phrases_finies,
)
from assistant.checklist import Checklist

FAUX_CLAUDE = [sys.executable, str(Path(__file__).with_name("faux_claude.py"))]


def contexte(phrase="ce mur-là, brique, 30 cm", mode="reponse", checklist=None):
    return Contexte(mode=mode, t=12.0, checklist=checklist or Checklist(), phrase=phrase, t_phrase=(10.0, 12.0),
                    images=[ImageInstant(11.0, b"\xff\xd8jpeg"), ImageInstant(12.0, b"\xff\xd8jpeg")])


def test_consignes_listent_tous_les_champs():
    texte = consignes()
    assert "- mur (mur, pièce) : donne_sur = donne sur, materiau = matériau, epaisseur = épaisseur, isolation = isolation, [longueur = longueur]" in texte
    assert "- ventilation (ventilation, logement) : type = type" in texte
    assert "{champs}" not in texte


def test_commande_sans_cle_ni_outils_et_env_nettoye(monkeypatch):
    commande = commande_claude("claude", "claude-haiku-5-5", "low", "message")
    assert commande[commande.index("--tools") + 1] == ""
    assert "--safe-mode" in commande and "--no-session-persistence" in commande
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "claude-vscode")
    env = env_claude()
    assert "ANTHROPIC_API_KEY" not in env and "CLAUDECODE" not in env and "CLAUDE_CODE_ENTRYPOINT" not in env


def test_contenu_message_images_jointes_ou_fichiers(tmp_path):
    c = contexte()
    contenu = contenu_message(c, "message")
    assert [b["type"] for b in contenu] == ["text", "image", "text", "image", "text"]
    assert "Nouvelle phrase du diagnostiqueur [0:10–0:12] : « ce mur-là, brique, 30 cm »" in contenu[-1]["text"]
    c.images[1].chemin = tmp_path / "image-12.jpg"
    contenu = contenu_message(c, "fichiers")
    assert len(contenu) == 1 and "image-12.jpg" in contenu[0]["text"]


def test_extraire_dire_des_qu_il_est_complet():
    assert extraire_dire('{"dire": "Il est is') is None
    assert extraire_dire('{"dire": "Il est \\"isolé\\" ?", "act') == 'Il est "isolé" ?'
    assert extraire_cible('{"cible": "M1.isolation", "dire": "Il est') == "M1.isolation"


def test_dire_lu_phrase_par_phrase_pendant_qu_il_s_ecrit():
    # Étape 7 : la voix démarre dès la première phrase de Claude, sans attendre la fin de sa réponse.
    assert dire_partiel("""{"cible": "", "dire": "Un pont thermique, c'est une fuite. Souv""") == ("Un pont thermique, c'est une fuite. Souv", False)
    assert dire_partiel(r'{"cible": "", "dire": "Il dit \"oui\". Il est isolé ?", "actions": []}') == ('Il dit "oui". Il est isolé ?', True)
    assert dire_partiel(r'{"cible": "", "dire": "Accent \u00e9') == ("Accent é", False)
    assert dire_partiel(r'{"cible": "", "dire": "Coupé \u00')[1] is False  # échappement pas encore arrivé en entier
    assert dire_partiel('{"cible": "M1.isolation", "di') == ("", False)
    assert phrases_finies("Une fuite de chaleur. Souvent aux jonctions. Il est isol", complet=False) == [
        "Une fuite de chaleur.", "Souvent aux jonctions."]
    assert phrases_finies("D'accord ! Je t'attends… Il est isolé ?") == ["D'accord !", "Je t'attends…", "Il est isolé ?"]


def test_cerveau_lit_la_premiere_phrase_avant_la_fin_de_la_reponse(tmp_path):
    async def scenario():
        cerveau = CerveauClaudeCode(tmp_path, commande=FAUX_CLAUDE, delai_s=5)
        await cerveau.demarrer()
        dits = []

        async def dire(texte, cible):
            dits.append((texte, cible, time.perf_counter()))

        decision = await cerveau.decider(contexte(phrase="PONT"), dire)
        fin = time.perf_counter()
        await cerveau.fermer()
        return decision, dits, fin

    decision, dits, fin = asyncio.run(scenario())
    assert [(t, c) for t, c, _ in dits] == [("Un pont thermique, c'est une fuite de chaleur.", "M1.isolation"),
                                            ('Souvent aux jonctions, "entre" mur et plancher.', "M1.isolation"),
                                            ("Il est isolé ?", "M1.isolation")]
    assert fin - dits[0][2] >= 0.3  # la première phrase est partie pendant que Claude écrivait encore
    assert decision.mesures["premiere_phrase_s"] is not None and decision.dire.endswith("Il est isolé ?")


def test_analyser_reponse_tolerante():
    d = analyser_reponse('```json\n{"dire": "Quel vitrage ?", "actions": [{"outil": "x"}, 3]}\n```')
    assert d.dire == "Quel vitrage ?" and d.actions == [{"outil": "x"}] and not d.erreur
    assert analyser_reponse("je ne sais pas").erreur


def test_actions_refusees_sans_citation_dite():
    c = Checklist()
    resultats = appliquer(c, [
        {"outil": "enregistrer_reponse", "type": "mur", "description": "le mur", "champ": "materiau", "valeur": "brique", "citation": "brique"},
        {"outil": "enregistrer_reponse", "type": "mur", "description": "le mur", "champ": "epaisseur", "valeur": "20 cm", "citation": "il fait 20 cm"},
        {"outil": "piece_courante", "nom": "Cuisine", "citation": ""},
        {"outil": "effacer_tout"},
    ], t=5.0, phrases=["ce mur-là, brique, 30 cm"])
    assert [r["statut"] for r in resultats] == ["accepte", "refuse", "accepte", "refuse"]
    assert resultats[1]["raison"] == "citation introuvable dans ce qui a été dit"
    assert c.nom_piece(c.piece_courante) == "Cuisine"


def test_cerveau_claude_code_avec_un_faux_claude(tmp_path):
    async def scenario():
        cerveau = CerveauClaudeCode(tmp_path, commande=FAUX_CLAUDE, delai_s=3)
        await cerveau.demarrer()
        dits = []

        async def dire(texte, cible):
            dits.append(texte)

        decision = await cerveau.decider(contexte(), dire)
        lent = await cerveau.decider(contexte(phrase="LENT"), dire)
        apres = await cerveau.decider(contexte(), dire)  # relancé automatiquement après le délai
        await cerveau.fermer()
        return decision, lent, apres, dits

    decision, lent, apres, dits = asyncio.run(scenario())
    assert decision.dire == "Il est isolé ?" and decision.actions[0]["valeur"] == "brique"
    assert decision.mesures["jetons_entree"] == 12  # deux images jointes
    assert dits == ["Il est isolé ?", "Il est isolé ?"]  # dit dès que le champ est complet, une fois par décision
    assert "pas de réponse de Claude" in lent.erreur
    assert apres.dire == "Il est isolé ?"


def test_cerveau_claude_code_arrete_signale(tmp_path):
    async def scenario():
        cerveau = CerveauClaudeCode(tmp_path, commande=FAUX_CLAUDE, delai_s=3)
        await cerveau.demarrer()
        decision = await cerveau.decider(contexte(phrase="PLANTE"))
        await cerveau.fermer()
        return decision

    assert "s'est arrêté" in asyncio.run(scenario()).erreur


def test_cerveau_relaye_par_un_processus_neuf(tmp_path):
    async def scenario():
        cerveau = CerveauClaudeCode(tmp_path, commande=FAUX_CLAUDE, delai_s=3, tours_max=7)
        await cerveau.demarrer()
        premier = cerveau._actuel
        for _ in range(8):
            await cerveau.decider(contexte())
            await asyncio.sleep(0.05)
        actuel = cerveau._actuel
        await cerveau.fermer()
        return premier, actuel

    premier, actuel = asyncio.run(scenario())
    assert actuel is not premier and actuel.tours < 7
