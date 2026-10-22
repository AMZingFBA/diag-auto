"""Dialogue complet (extraction immédiate + parcours du serveur + garde-fous), sans Claude ni réseau.

Étape 2 de Noah : seulement les questions utiles ; une seule fois chacune ; jamais « répétez ». Étape 13 : le DPE
décrit l'enveloppe du logement par côté, pas pièce par pièce : « ce mur donne sur quoi ? », les côtés qui manquent, le
plafond et le plancher une fois pour le logement, puis fenêtres, radiateurs, pièce suivante."""

import asyncio
import json
import statistics

from assistant.cerveau import Decision
from assistant.checklist import VALEUR_INCONNUE, Checklist
from assistant.evaluer import VISITE_PAR_COTES, phrase_filmee
from assistant.garde import DELAI_REDEMANDE_S, Questions
from assistant.reglages import Reglages
from assistant.session import Session, phrase_inachevee
from assistant.simulation import CerveauSimulation
from assistant.transcription import TranscripteurSimulation


async def visite(dossier, echanges, cerveau=None, conversation="claude"):
    """Joue les phrases une par une ; renvoie la session et, pour chaque phrase, les questions posées après. Une phrase
    peut être (phrase, cap de la caméra) : la boussole du téléphone est alors envoyée juste avant (étape 13)."""
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
    for numero, echange in enumerate(echanges, 1):
        phrase, cap = echange if isinstance(echange, tuple) else (echange, None)
        avant = len(recus)
        await phrase_filmee(session, phrase, cap, 10.0 * numero)
        await asyncio.sleep(0.02)
        while session.occupe:
            await asyncio.sleep(0.02)
        questions_apres.append([m["texte"] for m in recus[avant:] if m["type"] == "dire"])
    await session.terminer()
    return session, questions_apres, recus


# La visite jouée ici est la même que dans l'évaluation avec Claude (python -m assistant.evaluer).


def test_visite_par_cotes_sans_piece(tmp_path):
    session, questions_apres, recus = asyncio.run(visite(tmp_path, [(phrase, cap) for phrase, cap, _ in VISITE_PAR_COTES]))
    for (phrase, _, attendue), posees in zip(VISITE_PAR_COTES, questions_apres):
        assert posees == ([attendue] if attendue else []), f"après « {phrase} » : {posees}"

    c = session.checklist
    valeurs = {e.id: {champ: v[-1].valeur for champ, v in e.valeurs.items()} for e in c.elements}
    toutes = [q for posees in questions_apres for q in posees]
    # Étape 13 (Noah) : la pièce ne compte pas pour le DPE. Jamais demandée ; seule celle qu'il a dite est notée.
    assert not [q for q in toutes if "pièce" in q.lower()]
    assert list(c.pieces) == ["chambre"]
    assert not [e for p in c.vers_dict()["pieces"] for e in p["elements"]]  # rien n'est rangé par pièce
    # L'enveloppe du logement, par côté : un mur par côté, décrit une fois ; le mur ouest en deux parties.
    assert [(m.id, m.orientation) for m in c.enveloppe("mur")] == [("M1", "ouest"), ("M2", "nord"), ("M3", "est"), ("M4", "sud"),
                                                                     ("M5", "ouest")]
    assert valeurs["M1"] == {"donne_sur": "extérieur", "materiau": "brique", "epaisseur": "30 cm", "isolation": "ITI"}
    assert valeurs["M2"] == {"donne_sur": "local chauffé (voisin)"}  # un voisin : rien d'autre demandé
    assert valeurs["M3"] == {"donne_sur": "local non chauffé : parties communes", "materiau": "parpaing", "epaisseur": "20 cm",
                             "isolation": "non isolé"}
    assert valeurs["M4"] == {"donne_sur": "extérieur", "materiau": "brique", "epaisseur": "30 cm", "isolation": "ITI"}
    # Fenêtres et portes sur leur mur, mur par mur ; la porte sur la cage d'escalier donne sur le palier (déduit).
    assert [(o.id, o.support, o.orientation) for o in c.enveloppe() if o.type in ("fenetre", "porte")] == [
        ("F1", "M1", "ouest"), ("PO1", "M3", "est"), ("F2", "M4", "sud"), ("F3", "M4", "sud")]
    assert c.trouver_element("F1").nombre == 3 and valeurs["F1"] == {"menuiserie": "PVC", "vitrage": "double", "volets": "roulants"}
    assert valeurs["PO1"] == {"type": "bois", "donne_sur": "palier (local non chauffé)"}
    assert c.trouver_element("PO1").valeur("donne_sur").note == "déduit : sur le mur est"
    assert valeurs["F2"] == {"menuiserie": "alu", "vitrage": "double", "volets": "aucun"}
    # Dans la chambre : rien n'est redemandé. Face au nord, « le mur de gauche » est le mur ouest, ici sur le voisin : une
    # autre partie du mur ouest. La fenêtre filmée face au sud va sur le mur sud.
    assert valeurs["M5"] == {"donne_sur": "local chauffé (voisin)"} and c.trouver_element("M5").pieces == ["chambre"]
    assert c.nom(c.trouver_element("M5"), demonstratif=False) == "le mur ouest côté voisin"
    assert valeurs["F3"] == {"menuiserie": "bois", "vitrage": "simple", "volets": "aucun"}
    assert valeurs["PL1"] == {"donne_sur": "combles perdus", "isolation": "isolé laine de verre 30 cm"}
    assert valeurs["PB1"] == {"donne_sur": "terre-plein", "isolation": "non isolé"}
    assert [e.id for e in c.enveloppe() if e.type in ("plafond", "plancher")] == ["PL1", "PB1"]  # ceux du logement
    # Les équipements du logement : les radiateurs aussi (leur type, pas leur nombre par pièce).
    assert valeurs["E1"] == {"type": "radiateur à eau"} and c.trouver_element("E1").piece is None
    assert valeurs["CH1"] == {"energie": "gaz", "type": "chaudière à condensation", "annee": "2015"}
    assert valeurs["ECS1"] == {"systeme": "chaudière", "energie": "gaz"}
    assert c.trouver_element("ECS1").valeur("energie").note == "déduit : même chaudière que le chauffage (CH1)"
    assert valeurs["V1"] == {"type": "VMC simple flux hygro B"}
    assert not c.orientations_manquantes() and c.taux_dpe() == 1.0 and not c.manques_secondaires()

    assert len(toutes) == len([a for _, _, a in VISITE_PAR_COTES if a])  # une seule question par phrase, au plus
    assert not any("répét" in q.lower() or "pardon" in q.lower() or "épaisseur d" in q.lower() for q in toutes)
    assert all(len([m for m in q.split() if any(c.isalpha() for c in m)]) <= 11 for q in toutes)  # questions courtes
    # Posées par le serveur, sans attendre d'IA. Contrôle non chronométrique d'abord : seule « On commence. », que les
    # règles ne comprennent pas, est passée par le cerveau (ici sans IA). Puis le temps : médiane serrée, et aucun cas
    # proche d'un appel à Claude ou à Whisper (≥ 2 s) ; une borne de 0,5 s sur le pire cas échouait parfois sous la charge
    # de la suite complète (0,56 s mesurés par Hermes).
    decisions = [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [d["mesures"]["texte"] for d in decisions if d["evenement"] == "decision" and d.get("mode") != "parcours"] == ["On commence."]
    latences = [m["latence_s"] for m in recus if m["type"] == "dire"]
    assert statistics.median(latences) < 0.25 and max(latences) < 1.5


def test_mise_en_place_de_la_conversation_comprise_par_les_regles_seules(tmp_path):
    # La visite jouée avant les 30 phrases libres (python -m assistant.evaluer --conversation) : sans Claude, les règles
    # suivent tout le parcours, « Pas d'autre mur. » compris.
    from assistant.evaluer import MISE_EN_PLACE
    session, questions_apres, _ = asyncio.run(visite(tmp_path, MISE_EN_PLACE))
    for phrase, posees in zip(MISE_EN_PLACE, questions_apres):
        assert len(posees) <= 1 and not [q for q in posees if "pièce" in q.lower()], f"après « {phrase} » : {posees}"
    assert questions_apres[:3] == [["Ce mur donne sur quoi ?"], ["Les 2 fenêtres : des volets ?"],
                                   ["Les autres côtés du logement donnent sur quoi ?"]]  # sans boussole : on ne sait pas lesquels
    assert questions_apres[-1] == ["Des fenêtres ou une porte sur ce mur ?"]
    c = session.checklist
    assert "mur" in c.clos and c.trouver_element("F1").valeur("volets").valeur == "roulants"
    assert [m.valeur("donne_sur").valeur for m in c.enveloppe("mur")] == ["extérieur", "local chauffé (voisin)", "extérieur"]


def test_plafond_et_plancher_du_logement_et_partie_differente(tmp_path):
    # Étape 13 : le plafond et le plancher sont ceux du logement, jamais redemandés ; une pièce nommée où le plancher est
    # différent en a sa propre partie, sans contradiction.
    echanges = [(phrase, cap) for phrase, cap, _ in VISITE_PAR_COTES[:15]] + [
        ("On passe dans la chambre.", 0), ("Ici le plancher donne sur une cave, pas isolé.", 0)]
    session, questions_apres, _ = asyncio.run(visite(tmp_path, echanges))
    assert questions_apres[-2:] == [[], []]  # rien à demander : la nouvelle partie est entièrement dite
    c = session.checklist
    plafond, plancher = c.element_de_piece("plafond"), c.element_de_piece("plancher")
    assert plafond.id == "PL1" and plafond.valeur("isolation").valeur == "isolé laine de verre 30 cm"
    assert plancher.id == "PB2" and plancher.pieces == ["chambre"] and plancher.parent == "PB1"
    assert (plancher.valeur("donne_sur").valeur, plancher.valeur("isolation").valeur) == ("sous-sol / cave", "non isolé")
    assert c.trouver_element("PB1").valeur("donne_sur").valeur == "terre-plein" and not c.signalements


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
    assert questions_apres == [["Ce mur donne sur quoi ?"], [], ["Ce mur est en quoi ?"]]  # « répétez » jamais dit


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


def test_question_des_fenetres_retenue_par_mur():
    # Étape 13 : les fenêtres se demandent mur par mur, plus pièce par pièce.
    c = Checklist()
    for description in ("le mur 1", "le mur 2"):
        mur = c.signaler_element("mur", description, 1)
        c.enregistrer(type_element="mur", champ="donne_sur", valeur="extérieur", citation="dehors", t=2, element_id=mur.id)
    q = Questions()
    _, _, _, cle = q.filtrer("Des fenêtres ou une porte sur ce mur ?", "fenetres:M1", c, 0)
    q.noter(cle, 0)
    assert q.filtrer("Des fenêtres sur ce mur ?", "fenetres:M1", c, 10)[2] == "déjà demandé il y a moins de 2 minutes"
    assert q.filtrer("Des fenêtres ou une porte sur ce mur ?", "fenetres:M2", c, 30)[2] == ""  # un autre mur : on peut demander
    c.marquer_sans_objet(type_element="fenetre", champ="presence", citation="pas de fenêtre", t=40, support="M2")
    assert q.filtrer("Des fenêtres ou une porte sur ce mur ?", "fenetres:M2", c, 50)[2] == "fenetres:M2 déjà renseigné"
