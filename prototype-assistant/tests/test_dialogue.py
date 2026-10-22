"""Dialogue complet (extraction immédiate + cerveau + garde-fous), sans Claude ni réseau :
une seule question à la fois, jamais de « répétez », jamais une question déjà posée ou déjà répondue."""

import asyncio

from assistant.cerveau import Decision
from assistant.checklist import VALEUR_INCONNUE, Checklist
from assistant.garde import DELAI_REDEMANDE_S, Questions
from assistant.reglages import Reglages
from assistant.session import Session, phrase_inachevee
from assistant.simulation import CerveauSimulation
from assistant.transcription import TranscripteurSimulation


async def visite(dossier, phrases, cerveau=None):
    cerveau = cerveau or CerveauSimulation()
    reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=dossier, veille_s=1000, questions_par_minute=60)
    session = Session("essai", dossier, cerveau, cerveau, TranscripteurSimulation(), reglages)
    recus: list[dict] = []

    async def envoyer(message):
        recus.append(message)

    session.envoyer = envoyer
    await session.demarrer()
    for phrase in phrases:
        await session.recevoir_controle({"type": "texte", "texte": phrase})
        await asyncio.sleep(0.02)
        while session.occupe:
            await asyncio.sleep(0.02)
    bilan = await session.terminer()
    return session, [m["texte"] for m in recus if m["type"] == "dire"], recus, bilan


def test_dialogue_en_simulation(tmp_path):
    session, questions, recus, _ = asyncio.run(visite(tmp_path, [
        "Ici c'est la chambre 1.",
        "Ce mur-là, brique, 30 cm, il donne sur l'extérieur.",
        "Je sais pas.",
        "Oui, trois fenêtres en PVC double vitrage.",
        "Volets roulants.",
        "Non.",
    ]))
    assert questions == [
        "Décrivez un premier mur : matériau, épaisseur, isolation, et sur quoi il donne.",
        "Pour le mur 1, isolé par l'intérieur, par l'extérieur, ou pas isolé ?",
        "Y a-t-il une fenêtre dans cette pièce ?",
        "Pour les 3 fenêtres, quels volets, ou pas de volet ?",
        "Y a-t-il un radiateur ou un autre émetteur de chauffage dans cette pièce ?",
        "Où est le chauffage principal du logement ?",
    ]
    c = session.checklist
    assert c.trouver_element("M1").valeur("isolation").valeur == VALEUR_INCONNUE  # « je sais pas » : noté, on passe
    fenetres = c.trouver_element("F1")
    assert fenetres.nombre == 3 and fenetres.valeur("volets").valeur == "roulants"
    assert len([e for e in c.elements if e.type == "fenetre"]) == 1
    assert c.taux_remplissage() == 1.0
    assert sum(m["type"] == "bip" for m in recus) >= 3  # valeur notée = bip immédiat


def test_description_libre_puis_seule_la_suite_est_demandee(tmp_path):
    _, questions, _, bilan = asyncio.run(visite(tmp_path, [
        "Ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois double vitrage, "
        "deux radiateurs à eau.",
    ]))
    assert questions == ["Pour le mur 1, il donne sur l'extérieur, un local non chauffé ou un local chauffé ?"]
    assert bilan["acceptees"] == 7


class CerveauQuiFaitRepeter:
    """Un cerveau qui se comporte mal : il demande de répéter, ou deux questions à la fois."""

    nom = "mauvais élève"

    def __init__(self, reponses):
        self.reponses = list(reponses)

    async def demarrer(self):
        pass

    async def fermer(self):
        pass

    async def decider(self, contexte, sur_dire=None):
        dire, cible = self.reponses.pop(0)
        if sur_dire:
            await sur_dire(dire, cible)
        return Decision(dire=dire, cible=cible)


def test_garde_fous_sur_les_questions_du_cerveau(tmp_path):
    cerveau = CerveauQuiFaitRepeter([
        ("Pardon, pouvez-vous répéter le matériau ?", "M1.materiau"),  # interdit → question de secours
        ("Il est isolé ? Et il fait quelle épaisseur ?", "M1.isolation"),  # deux questions → la 1re seulement
        ("Il est isolé ?", "M1.isolation"),  # déjà demandé → question de secours (la suivante)
    ])
    _, questions, _, _ = asyncio.run(visite(tmp_path, ["Ce mur, brique.", "Euh voilà.", "Bon."], cerveau))
    assert questions == [
        "Pour le mur 1, quelle épaisseur ?",
        "Il est isolé ?",
        "Pour le mur 1, il donne sur l'extérieur, un local non chauffé ou un local chauffé ?",
    ]
    assert not any("répét" in q.lower() or "pardon" in q.lower() for q in questions)


def test_phrase_coupee_attend_la_suite(tmp_path):
    class Memoire(CerveauSimulation):
        def __init__(self):
            self.phrases = []

        async def decider(self, contexte, sur_dire=None):
            self.phrases.append(contexte.phrase)
            return await super().decider(contexte, sur_dire)

    async def scenario():
        cerveau = Memoire()
        reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=tmp_path, veille_s=1000)
        session = Session("essai", tmp_path, cerveau, cerveau, TranscripteurSimulation(), reglages)
        await session.demarrer()
        await session.recevoir_controle({"type": "texte", "texte": "Ce mur, il est..."})
        await asyncio.sleep(0.5)  # il cherche ses mots
        await session.recevoir_controle({"type": "texte", "texte": "en parpaing de 20."})
        await asyncio.sleep(0.3)
        while session.occupe:
            await asyncio.sleep(0.02)
        await session.terminer()
        return cerveau.phrases, session.checklist

    phrases, c = asyncio.run(scenario())
    assert phrases == ["Ce mur, il est... en parpaing de 20."]
    assert c.trouver_element("M1").valeur("materiau").valeur == "parpaing"
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
    q.noter("Il est isolé ?", q.filtrer("Il est isolé ?", "M1.isolation", c, 0)[1], 0)
    assert q.filtrer("Et l'isolation ?", "M1.isolation", c, 30)[2] == "déjà demandé il y a moins de 2 minutes"
    assert q.filtrer("Et l'isolation ?", "M1.isolation", c, DELAI_REDEMANDE_S + 1)[2] == ""
    assert q.recentes(30) == ["M1.isolation"]


def test_question_de_presence_retenue_par_piece():
    c = Checklist()
    c.definir_piece("Séjour", 0)
    q = Questions()
    _, cible, _ = q.filtrer("Y a-t-il une fenêtre ?", "presence:fenetre", c, 0)
    q.noter("Y a-t-il une fenêtre ?", cible, 0, c.piece_courante)
    assert q.filtrer("Une fenêtre ici ?", "presence:fenetre", c, 10)[2] == "déjà demandé il y a moins de 2 minutes"
    c.definir_piece("Cuisine", 20)
    assert q.filtrer("Y a-t-il une fenêtre ?", "presence:fenetre", c, 30)[2] == ""  # autre pièce : on peut demander
    assert q.recentes(30, c.piece_courante) == []
