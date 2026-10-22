"""Étape 9 de Noah : ne pas répéter ce qu'il dit, et jamais de faux doublon.

Au test du 22/10/2026 (sessions/20261022-120410-53ecb1, 154-157 s et 268-273 s), l'assistant a dit « c'était déjà noté, je
retire mon doublon » et supprimé un vrai mur. Règles : ne jamais affirmer qu'un élément existe déjà sans preuve dans l'état
(même repère, même orientation, même description) ; dans le doute, créer l'élément et, s'il y a une preuve, demander
brièvement (« C'est le même mur que… ? ») ; ne jamais supprimer un élément de soi-même. Ici, un faux Claude essaie de
supprimer ou de déclarer des doublons : le serveur doit l'en empêcher."""

import asyncio
import json
import statistics

import pytest

from assistant.repetition import mots_repetes, reformulation
from test_conversation import CerveauScenario, dits, poli, visite

SUPPRIMER = "Celui-là, je l'avais déjà noté, c'est un doublon, je le retire."


def claude(reponses: dict):
    """phrase → (ce que Claude dit avant la question suivante, ses actions) ; sinon : la question suivante seule."""
    def repondre(contexte):
        texte, actions = reponses.get(contexte.phrase, ("", []))
        # Comme le demandent ses consignes : quand il propose un doublon, il ne pose pas d'autre question.
        avec_question = not any(a.get("outil") == "doublon" for a in actions)
        return poli({contexte.phrase: (texte, actions, avec_question)})(contexte)
    return repondre


def journal(dossier) -> list[dict]:
    return [json.loads(l) for l in (dossier / "journal.jsonl").read_text(encoding="utf-8").splitlines()]


def murs(session) -> list[str]:
    return [e.id for e in session.checklist.elements if e.type == "mur"]


def jouer(dossier, phrases, reponses):
    session, apres, _ = asyncio.run(visite(dossier, phrases, CerveauScenario(claude(reponses))))
    evenements = journal(dossier)
    supprime = [c for e in evenements if e["evenement"] == "commandes" for c in e["commandes"] if c.startswith("annuler M") and "." not in c]
    tout_dit = [t for messages in apres for t in dits(messages)]
    assert not supprime, f"supprimé sans qu'il le demande : {supprime}"
    assert not [t for t in tout_dit if "doublon" in t.lower() or "retire" in t.lower() or "déjà noté" in t.lower()], tout_dit
    return session, apres, evenements


# --- 10 nouveaux murs qui ressemblent à d'anciens --------------------------------------------------------------------

def test_01_meme_donne_sur_et_meme_materiau(tmp_path):
    session, _, ev = jouer(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, en brique.", "Un autre mur donne dehors, en brique."],
                           {"Un autre mur donne dehors, en brique.": (SUPPRIMER, [{"outil": "annuler", "element_id": "M2", "champ": ""}])})
    assert murs(session) == ["M1", "M2"] and any(e["evenement"] == "suppression_refusee" for e in ev)


def test_02_meme_phrase_redite_pour_un_autre_mur(tmp_path):
    session, _, ev = jouer(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm, isolé.", "Ce mur donne dehors, brique 30 cm, isolé."],
                           {"Ce mur donne dehors, brique 30 cm, isolé.": (SUPPRIMER, [{"outil": "annuler", "element_id": "M2", "champ": ""}])})
    assert murs(session) == ["M1", "M2"]


def test_03_mur_cote_couloir_jamais_decrit(tmp_path):
    # Noah, 268-273 s : « c'est le mur côté couloir déjà noté, je retire le doublon » : faux.
    session, _, ev = jouer(tmp_path, ["Ici c'est le séjour.", "Ce mur donne sur le voisin.", "Ce mur-là donne sur le couloir."],
                           {"Ce mur-là donne sur le couloir.": ("C'est le mur côté couloir déjà noté, je retire le doublon.",
                                                                [{"outil": "annuler", "element_id": "M2", "champ": ""}])})
    assert murs(session) == ["M1", "M2"]
    assert session.checklist.trouver_element("M2").valeur("donne_sur").valeur == "local chauffé : couloir"


def test_04_le_mur_du_tableau_va_sur_le_mur_du_tableau(tmp_path):
    # Noah, 154-157 s : « le mur du tableau » rangé sur le mur du miroir, puis le mur du tableau supprimé comme doublon.
    deux_murs = [{"outil": "signaler_element", "type": "mur", "description": "le mur avec le tableau"},
                 {"outil": "signaler_element", "type": "mur", "description": "le mur avec le grand miroir"}]
    session, _, _ = jouer(tmp_path, ["Ici c'est le séjour.", "Il y a ces deux murs.", "Le mur du tableau donne derrière sur les toilettes."],
                          {"Il y a ces deux murs.": ("", deux_murs),
                           "Le mur du tableau donne derrière sur les toilettes.": (SUPPRIMER, [{"outil": "annuler", "element_id": "M1", "champ": ""}])})
    c = session.checklist
    assert murs(session) == ["M1", "M2"]
    assert c.trouver_element("M1").valeur("donne_sur").valeur == "local chauffé : WC" and not c.trouver_element("M2").valeurs


def test_05_murs_montres_un_par_un(tmp_path):
    session, _, _ = jouer(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors.", "Il y a ce mur, ce mur et ce mur."],
                          {"Il y a ce mur, ce mur et ce mur.": (SUPPRIMER, [{"outil": "annuler", "element_id": "M2", "champ": ""}])})
    assert murs(session) == ["M1", "M2", "M3", "M4"]


def test_06_meme_repere_demande_puis_non(tmp_path):
    doublon = [{"outil": "doublon", "element_id": "M2", "meme_que": "M1", "preuve": "même repère"}]
    session, apres, ev = jouer(tmp_path, ["Ici c'est le séjour.", "Le mur avec la télé donne dehors.", "Un autre mur avec la télé donne sur le voisin.",
                                          "Non, c'est un autre."],
                               {"Un autre mur avec la télé donne sur le voisin.": ("", doublon)})
    assert len(dits(apres[2])) == 1 and dits(apres[2])[0].startswith("C'est le même mur que le mur")  # demandé brièvement
    assert murs(session) == ["M1", "M2"]  # « non » : les deux restent


def test_07_meme_repere_demande_puis_oui(tmp_path):
    doublon = [{"outil": "doublon", "element_id": "M2", "meme_que": "M1", "preuve": "même repère"}]
    session, _, _ = jouer(tmp_path, ["Ici c'est le séjour.", "Le mur avec la télé donne dehors.", "Un autre mur avec la télé, en brique.", "Oui."],
                          {"Un autre mur avec la télé, en brique.": ("", doublon)})
    mur = session.checklist.trouver_element("M1")
    assert murs(session) == ["M1"]  # réuni seulement parce qu'il l'a confirmé
    assert (mur.valeur("donne_sur").valeur, mur.valeur("materiau").valeur) == ("extérieur", "brique")


def test_08_doute_sans_preuve_demande_jamais_affirme(tmp_path):
    # « En cas de doute, créer l'élément et demander une confirmation brève » : la question, jamais l'affirmation.
    doublon = [{"outil": "doublon", "element_id": "M2", "meme_que": "M1", "preuve": ""}]
    session, apres, ev = jouer(tmp_path, ["Ici c'est le séjour.", "Le mur côté voisin, en brique.", "Le mur côté jardin, en brique.",
                                          "Non."], {"Le mur côté jardin, en brique.": ("Ce mur est déjà noté. Je pense que c'est le même mur.",
                                                                                         doublon)})
    assert murs(session) == ["M1", "M2"]
    assert dits(apres[2]) == ["C'est le même mur que le mur côté voisin ?"]  # « déjà noté » : pas dit
    assert any("sans preuve : demandé" in " ".join(e.get("commandes") or []) for e in ev if e["evenement"] == "decision")


def test_fenetres_montrees_une_par_une_et_redites(tmp_path):
    # Rejeu du test de Noah (45 s et 60 s) : il y avait 9 fenêtres au lieu de 3.
    session, _, _ = jouer(tmp_path, ["Ici c'est le séjour.", "Il y a aussi une fenêtre ici, une fenêtre ici, une fenêtre aussi là-bas.",
                                     "Dans le même mur, il y a trois fenêtres, ces trois fenêtres sont en PVC."], {})
    fenetres = [(e.nombre, e.valeur("menuiserie").valeur if e.valeur("menuiserie") else None)
                for e in session.checklist.elements if e.type == "fenetre"]
    assert fenetres == [(3, "PVC")]


def test_09_fenetre_annoncee_puis_decrite(tmp_path):
    session, _, _ = jouer(tmp_path, ["Ici c'est le séjour.", "Il y a aussi une fenêtre, cette fenêtre en bois."],
                          {"Il y a aussi une fenêtre, cette fenêtre en bois.": (SUPPRIMER, [{"outil": "annuler", "element_id": "F1", "champ": ""}])})
    fenetres = [e for e in session.checklist.elements if e.type == "fenetre"]
    assert len(fenetres) == 1 and fenetres[0].valeur("menuiserie").valeur == "bois"  # une seule, et pas supprimée


def test_10_meme_orientation_demandee(tmp_path):
    # Deux murs orientés nord dans la même pièce : peut-être le même ; demandé, jamais réuni sans son « oui ».
    nord = [{"outil": "orienter", "element_id": "M2", "orientation": "nord", "citation": "plein nord"},
            {"outil": "doublon", "element_id": "M2", "meme_que": "M1", "preuve": "même orientation"}]
    session, apres, _ = jouer(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, plein nord.", "Un autre mur donne dehors, plein nord."],
                              {"Ce mur donne dehors, plein nord.": ("", [{"outil": "orienter", "element_id": "M1", "orientation": "nord",
                                                                          "citation": "plein nord"}]),
                               "Un autre mur donne dehors, plein nord.": ("", nord)})
    assert murs(session) == ["M1", "M2"]
    assert dits(apres[2])[-1].startswith("C'est le même mur que")


def test_suppression_seulement_quand_il_la_demande(tmp_path):
    reponses = {"Oublie ce mur, je me suis trompé.": ("", [{"outil": "annuler", "element_id": "M2", "champ": ""}])}
    session, _, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors.", "Un autre mur donne sur le voisin.",
                                                  "Oublie ce mur, je me suis trompé."], CerveauScenario(claude(reponses))))
    assert murs(session) == ["M1"]


# --- Ne pas répéter ce qu'il dit -------------------------------------------------------------------------------------

def test_mesure_des_mots_repetes():
    assert mots_repetes("L'isolant, c'est de la laine de verre trente centimètres.", "OK, c'est noté laine de verre 30 cm.") == [
        "laine", "verre", "30", "centimetre"]
    assert mots_repetes("Ce mur donne dehors, en brique.", "Ce mur, quelle épaisseur ?") == []  # nommer le mur : permis
    assert reformulation("Tous les murs de la maison sont en briques.", "Noté, tous les murs en brique.")
    assert not reformulation("Ici c'est le séjour.", "Décrivez le premier mur.")


def test_claude_bavard_ne_repete_jamais(tmp_path):
    # Un Claude qui reprend tout ce qu'on lui dit : le serveur ne laisse passer que la question (objectif : 0 mot répété).
    def bavard(contexte):
        question, code = poli()(contexte)[:2]
        return f"OK, c'est noté : {contexte.phrase.rstrip('.')}. {question}", code, []

    phrases = ["Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm.", "L'isolant, c'est de la laine de verre 10 cm.",
               "Au-dessus, des combles perdus.", "Terre-plein, pas isolé.", "Deux fenêtres PVC double vitrage.", "Volets roulants."]
    session, apres, _ = asyncio.run(visite(tmp_path, phrases, CerveauScenario(bavard)))
    repetes = [len(mots_repetes(phrase, " ".join(dits(messages)))) for phrase, messages in zip(phrases, apres)]
    assert repetes == [0] * len(phrases), list(zip(phrases, [dits(m) for m in apres]))
    assert all(len(dits(m)) <= 1 for m in apres)  # rien d'autre que la question suivante
    mesures = [m["mots_repetes"] for m in session.mesures if "mots_repetes" in m]
    assert mesures and statistics.mean(len(m) for m in mesures) == 0


@pytest.mark.parametrize("question", ["C'est quoi un pont thermique ?", "Tu as noté quoi pour le séjour ?"])
def test_une_question_peut_reprendre_ses_mots(tmp_path, question):
    # Répondre à une question reprend forcément ses mots (« un pont thermique, c'est… ») : rien n'est retiré.
    reponses = {question: ("Un pont thermique, c'est une fuite de chaleur." if "pont" in question else "Le séjour : un mur en brique.", [])}
    _, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur est en brique.", question], CerveauScenario(claude(reponses))))
    assert dits(apres[2])[0] == reponses[question][0]


def test_correction_dite_une_seule_fois_par_le_serveur(tmp_path):
    reponses = {"En fait, c'est du parpaing, pas de la brique.": ("D'accord, je corrige : ce mur est en parpaing.", []),
                "En fait, la chaudière date de 2012.": ("", [{"outil": "enregistrer_reponse", "element_id": "CH1", "champ": "annee",
                                                             "valeur": "2012", "citation": "la chaudière date de 2012"}])}
    phrases = ["Ici c'est le séjour.", "Ce mur donne dehors, en brique.", "En fait, c'est du parpaing, pas de la brique.",
               "Une chaudière gaz de 2015.", "En fait, la chaudière date de 2012.", "Volets roulants."]
    _, apres, _ = asyncio.run(visite(tmp_path, phrases, CerveauScenario(claude(reponses))))
    assert dits(apres[2])[0] == "Je remplace brique." and not [t for t in dits(apres[2]) if "corrige" in t]
    assert dits(apres[4])[0] == "Je remplace 2015."
    assert not [t for t in dits(apres[5]) if "remplace" in t]  # pas redit à la phrase suivante


def test_bip_pour_tout_ce_qui_est_compris(tmp_path):
    _, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne sur le voisin.", "Pas d'autre mur.", "On passe dans la cuisine."],
                                     CerveauScenario(claude({}))))
    for messages in apres[2:]:
        assert [m["type"] for m in messages].count("bip") == 1  # compris : un bip, pas de « Alors… »
