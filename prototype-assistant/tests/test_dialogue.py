"""Dialogue complet (extraction immédiate + parcours du serveur + garde-fous), sans Claude ni réseau.

Étape 2 de Noah : parcours mur par mur, puis plafond, plancher, fenêtres, radiateurs, pièce suivante ;
seulement les questions utiles ; une seule fois chacune ; jamais « répétez »."""

import asyncio
import json
import statistics

from assistant.cerveau import Decision
from assistant.checklist import VALEUR_INCONNUE, Checklist
from assistant.evaluer import PIECE_A_4_MURS
from assistant.garde import DELAI_REDEMANDE_S, Questions
from assistant.reglages import Reglages
from assistant.session import Session, phrase_inachevee
from assistant.simulation import CerveauSimulation
from assistant.transcription import TranscripteurSimulation


async def visite(dossier, echanges, cerveau=None, conversation="claude"):
    """Joue les phrases une par une ; renvoie la session et, pour chaque phrase, les questions posées après."""
    cerveau = cerveau or CerveauSimulation()
    reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=dossier, veille_s=1000, questions_par_minute=60,
                        conversation=conversation)
    session = Session("essai", dossier, cerveau, cerveau, TranscripteurSimulation(), reglages)
    recus: list[dict] = []

    async def envoyer(message):
        recus.append(message)

    session.envoyer = envoyer
    await session.demarrer()
    questions_apres = []
    for phrase in echanges:
        avant = len(recus)
        await session.recevoir_controle({"type": "texte", "texte": phrase})
        await asyncio.sleep(0.02)
        while session.occupe:
            await asyncio.sleep(0.02)
        questions_apres.append([m["texte"] for m in recus[avant:] if m["type"] == "dire"])
    await session.terminer()
    return session, questions_apres, recus


# La pièce à 4 murs jouée ici est la même que dans l'évaluation avec Claude (python -m assistant.evaluer).


def test_piece_complete_a_4_murs(tmp_path):
    session, questions_apres, recus = asyncio.run(visite(tmp_path, [phrase for phrase, _ in PIECE_A_4_MURS]))
    for (phrase, attendue), posees in zip(PIECE_A_4_MURS, questions_apres):
        assert posees == [attendue], f"après « {phrase} » : {posees}"

    c = session.checklist
    valeurs = {e.id: {champ: v[-1].valeur for champ, v in e.valeurs.items()} for e in c.elements}
    assert valeurs["M1"] == {"donne_sur": "extérieur", "materiau": "brique", "epaisseur": "30 cm", "isolation": "ITI"}
    assert valeurs["M2"] == {"materiau": "parpaing", "epaisseur": "20 cm", "isolation": "non isolé", "donne_sur": "local non chauffé : garage"}
    assert valeurs["M3"] == {"donne_sur": "extérieur", "materiau": "brique", "epaisseur": "30 cm", "isolation": VALEUR_INCONNUE}
    assert valeurs["M4"] == {"donne_sur": "local chauffé"}  # paroi non déperditive : rien d'autre demandé
    assert valeurs["PL1"] == {"donne_sur": "combles perdus", "isolation": "isolé laine de verre 30 cm"}
    assert valeurs["PB1"] == {"donne_sur": "terre-plein", "isolation": "non isolé"}
    assert c.trouver_element("F1").nombre == 3 and valeurs["F1"] == {"menuiserie": "PVC", "vitrage": "double", "volets": "roulants"}
    assert c.trouver_element("E1").nombre == 2 and valeurs["E1"]["type"] == "radiateur à eau"
    assert valeurs["CH1"] == {"energie": "gaz", "type": "chaudière à condensation", "annee": "2015"}
    assert valeurs["ECS1"] == {"systeme": "chaudière", "energie": "gaz"}
    assert c.trouver_element("ECS1").valeur("energie").note == "déduit : même chaudière que le chauffage (CH1)"
    assert valeurs["V1"] == {"type": "VMC simple flux hygro B"}
    assert c.taux_remplissage("sejour") == 1.0 and not c.manques_secondaires()

    toutes = [q for posees in questions_apres for q in posees]
    assert len(toutes) == len(PIECE_A_4_MURS)  # une seule question par phrase
    assert not any("répét" in q.lower() or "pardon" in q.lower() or "épaisseur d" in q.lower() for q in toutes)
    assert all(len([m for m in q.split() if any(c.isalpha() for c in m)]) <= 10 for q in toutes)  # questions courtes
    # Posées par le serveur, sans attendre d'IA. Contrôle non chronométrique d'abord : aucune phrase n'est passée par le
    # cerveau. Puis le temps : médiane serrée, et aucun cas proche d'un appel à Claude ou à Whisper (≥ 2 s) ; une borne
    # de 0,5 s sur le pire cas échouait parfois sous la charge de la suite complète (0,56 s mesurés par Hermes).
    decisions = [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert not [d for d in decisions if d["evenement"] == "decision" and d.get("mode") != "parcours"]
    latences = [m["latence_s"] for m in recus if m["type"] == "dire"]
    assert statistics.median(latences) < 0.25 and max(latences) < 1.5


def test_mise_en_place_de_la_conversation_comprise_par_les_regles_seules(tmp_path):
    # La visite jouée avant les 30 phrases libres (python -m assistant.evaluer --conversation) : sans Claude, les règles
    # suivent tout le parcours, « Pas d'autre mur. » compris.
    from assistant.evaluer import MISE_EN_PLACE
    session, questions_apres, _ = asyncio.run(visite(tmp_path, MISE_EN_PLACE))
    assert questions_apres == [
        # « Un autre mur donne sur le voisin » : mur sur un local chauffé, la question des murs n'est pas reposée.
        ["Décrivez le premier mur."], ["D'autres murs sur l'extérieur ou un local non chauffé ?"],
        ["Au-dessus du plafond : combles, terrasse ou logement ?"],
        ["Au-dessus du plafond : combles, terrasse ou logement ?"], ["Sous le plancher : terre-plein, vide sanitaire, cave ou logement ?"],
        ["Les 2 fenêtres : des volets ?"], ["D'autres fenêtres, ou une porte vers l'extérieur ?"], ["Des radiateurs dans cette pièce ?"],
        ["Quel est le chauffage principal ?"], ["Et l'eau chaude, comment est-elle produite ?"], ["Décrivez le premier mur."],
        ["D'autres murs sur l'extérieur ou un local non chauffé ?"]]
    assert "mur" in session.checklist.pieces["sejour"].clos


def test_piece_suivante_plafond_pareil_et_plancher_different(tmp_path):
    echanges = [phrase for phrase, _ in PIECE_A_4_MURS] + [
        "Ce mur donne dehors, parpaing 20, non isolé.",
        "Non.",
        "Oui.",
        "Non, il donne sur une cave, pas isolé.",
    ]
    session, questions_apres, _ = asyncio.run(visite(tmp_path, echanges))
    assert questions_apres[-4:] == [
        ["D'autres murs sur l'extérieur ou un local non chauffé ?"],
        ["Plafond pareil que dans le séjour ?"],
        ["Plancher pareil que dans le séjour ?"],
        ["Des fenêtres dans cette pièce ?"],
    ]
    c = session.checklist
    plafond, plancher = c.element_de_piece("plafond"), c.element_de_piece("plancher")
    assert plafond.valeur("isolation").valeur == "isolé laine de verre 30 cm" and plafond.valeur("isolation").note == "pareil que Séjour"
    assert (plancher.valeur("donne_sur").valeur, plancher.valeur("isolation").valeur) == ("sous-sol / cave", "non isolé")


class CerveauEspion:
    """Un cerveau qui note quand on l'appelle, et qui se comporte mal (il fait répéter)."""

    nom = "espion"

    def __init__(self):
        self.appels = []

    async def demarrer(self):
        pass

    async def fermer(self):
        pass

    async def decider(self, contexte, sur_dire=None):
        self.appels.append((contexte.mode, contexte.phrase))
        if sur_dire:
            await sur_dire("Pardon, pouvez-vous répéter ?", "")
        return Decision(dire="Pardon, pouvez-vous répéter ?")


def test_mode_rapide_le_cerveau_n_est_appele_que_si_les_regles_n_ont_pas_compris(tmp_path):
    # Mode « rapide » (DIAGAUTO_CONVERSATION=rapide, étape 5) ; par défaut, Claude lit chaque phrase (test_conversation.py).
    cerveau = CerveauEspion()
    _, questions_apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Euh voilà.", "Ce mur donne dehors."], cerveau,
                                               conversation="rapide"))
    assert cerveau.appels == [("reponse", "Euh voilà.")]  # compris : le serveur répond seul, tout de suite
    assert questions_apres == [["Décrivez le premier mur."], [], ["Ce mur est en quoi ?"]]  # « répétez » jamais dit


def test_phrase_coupee_attend_la_suite(tmp_path):
    async def scenario():
        reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=tmp_path, veille_s=1000)
        cerveau = CerveauSimulation()
        session = Session("essai", tmp_path, cerveau, cerveau, TranscripteurSimulation(), reglages)
        await session.demarrer()
        await session.recevoir_controle({"type": "texte", "texte": "Ce mur, il est..."})
        await asyncio.sleep(0.5)  # il cherche ses mots
        await session.recevoir_controle({"type": "texte", "texte": "en parpaing de 20."})
        await asyncio.sleep(0.3)
        while session.occupe:
            await asyncio.sleep(0.02)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert [m["texte"] for m in session.mesures] == ["Ce mur, il est... en parpaing de 20."]
    assert session.checklist.trouver_element("M1").valeur("materiau").valeur == "parpaing"
    assert phrase_inachevee("Et il fait...") and phrase_inachevee("Il est") and not phrase_inachevee("Brique.")


def test_filtre_des_questions():
    c = Checklist()
    c.definir_piece("Séjour", 0)
    c.signaler_element("mur", "le mur avec la télé", 1)
    c.enregistrer(type_element="mur", champ="materiau", valeur="brique", citation="brique", t=2, element_id="M1")
    q = Questions()
    assert q.filtrer("Pardon, vous pouvez répéter ?", "", c, 0)[2] == "demande de répétition interdite"
    assert q.filtrer("Je n'ai pas compris, c'est quel matériau ?", "", c, 0)[2] == "demande de répétition interdite"
    assert q.filtrer("Quel isolant ? Et quelle épaisseur ?", "M1.isolation", c, 0)[0] == "Quel isolant ?"
    assert q.filtrer("Il est en quoi ?", "M1.materiau", c, 0)[2] == "M1.materiau déjà renseigné"
    _, _, _, cle = q.filtrer("Il est isolé ?", "M1.isolation", c, 0)
    q.noter(cle, 0)
    assert q.filtrer("Et l'isolation ?", "M1.isolation", c, 30)[2] == "déjà demandé il y a moins de 2 minutes"
    assert q.filtrer("Et l'isolation ?", "M1.isolation", c, DELAI_REDEMANDE_S + 1)[2] == ""
    q.noter("suite:mur@sejour#1", 0, une_fois=True)
    assert q.filtrer("Un autre mur ?", "suite:mur", c, 1000, cle="suite:mur@sejour#1")[2] == "déjà demandé une fois"
    assert q.recentes(30, "sejour") == ["M1.isolation", "suite:mur"]


def test_question_de_presence_retenue_par_piece():
    c = Checklist()
    c.definir_piece("Séjour", 0)
    q = Questions()
    _, _, _, cle = q.filtrer("Y a-t-il une fenêtre ?", "presence:fenetre", c, 0)
    q.noter(cle, 0)
    assert q.filtrer("Une fenêtre ici ?", "presence:fenetre", c, 10)[2] == "déjà demandé il y a moins de 2 minutes"
    c.definir_piece("Cuisine", 20)
    assert q.filtrer("Y a-t-il une fenêtre ?", "presence:fenetre", c, 30)[2] == ""  # autre pièce : on peut demander
    assert q.recentes(30, c.piece_courante) == []
