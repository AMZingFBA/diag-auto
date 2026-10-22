"""Étape 7 de Noah : une VRAIE conversation. Claude est le cerveau de chaque phrase ; les règles du serveur pré-remplissent
seulement, sans jamais bloquer Claude ni le contredire. Ici, un faux Claude écrit à l'avance (pas de réseau) : on vérifie
ce que le serveur fait de ses réponses (lues phrase par phrase, question de reprise, pause, annulations, file d'attente).
Le vrai Claude est essayé sur 30 phrases libres par `python -m assistant.evaluer --conversation`."""

import asyncio
import json
import re
from collections import Counter

from assistant.cerveau import Decision, phrases_finies, texte_message
from assistant.evaluer import CONVERSATION_LIBRE, MISE_EN_PLACE
from assistant.extraction import valeur_normalisee
from assistant.reglages import Reglages
from assistant.session import Session
from assistant.simulation import CerveauSimulation
from assistant.transcription import TranscripteurSimulation

_SUGGESTION = re.compile(r"« (.+?) » \[(.+?)\]")


class CerveauScenario:
    """Un faux Claude : `repondre(contexte)` donne (dire, cible, actions), ou une Decision toute faite. « dire » est lu
    phrase par phrase, comme le fait le vrai pendant qu'il écrit (avec un temps d'arrêt possible entre deux phrases)."""

    nom = "scénario"

    def __init__(self, repondre, pause_s: float = 0.0):
        self.repondre = repondre
        self.pause_s = pause_s
        self.phrases: list[str] = []  # phrase reçue à chaque appel
        self.messages: list[str] = []  # message complet reçu à chaque appel
        self.murs_a_la_fin: list[list[str]] = []  # murs connus quand la réponse se termine

    async def demarrer(self):
        pass

    async def fermer(self):
        pass

    async def decider(self, contexte, sur_dire=None):
        self.phrases.append(contexte.phrase)
        self.messages.append(texte_message(contexte))
        reponse = self.repondre(contexte)
        if isinstance(reponse, Decision):
            return reponse
        dire, cible, actions = reponse
        for phrase in phrases_finies(dire):
            if sur_dire:
                await sur_dire(phrase, cible)
            await asyncio.sleep(self.pause_s)
        self.murs_a_la_fin.append([e.id for e in contexte.checklist.elements if e.type == "mur"])
        return Decision(dire=dire, cible=cible, actions=actions)


def suggestion(contexte) -> tuple[str, str]:
    m = _SUGGESTION.search(contexte.suggestion)
    return (m.group(1), m.group(2)) if m else ("", "")


def poli(reponses: dict | None = None, defaut: str = ""):
    """Ce qu'on attend de Claude : sa réponse à la phrase, puis la question suivante proposée par le parcours. `reponses` :
    phrase → texte, ou → (texte, actions, avec la question suivante ou non)."""
    reponses = reponses or {}

    def repondre(contexte):
        prevu = reponses.get(contexte.phrase, defaut)
        texte, actions, avec_question = (prevu, [], True) if isinstance(prevu, str) else prevu
        question, code = suggestion(contexte) if avec_question else ("", "")
        return " ".join(p for p in (texte, question) if p), code, actions

    return repondre


async def ouvrir(dossier, cerveau):
    reglages = Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=dossier, veille_s=1000,
                        questions_par_minute=60, conversation="claude")
    session = Session("conversation", dossier, cerveau, CerveauSimulation(), TranscripteurSimulation(), reglages)
    recus: list[dict] = []

    async def envoyer(message):
        recus.append(message)

    session.envoyer = envoyer
    await session.demarrer()
    return session, recus


async def attendre(session):
    await asyncio.sleep(0.02)
    while session.occupe:
        await asyncio.sleep(0.02)


async def visite(dossier, phrases, cerveau):
    """Joue les phrases une par une ; renvoie la session, les messages reçus après chaque phrase, et tous les messages."""
    session, recus = await ouvrir(dossier, cerveau)
    apres = []
    for phrase in phrases:
        avant = len(recus)
        await session.recevoir_controle({"type": "texte", "texte": phrase})
        await attendre(session)
        apres.append(recus[avant:])
    await session.terminer()
    return session, apres, recus


def dits(messages):
    return [m["texte"] for m in messages if m["type"] == "dire"]


def suites(messages):
    return [m["suite"] for m in messages if m["type"] == "dire"]


def test_chaque_phrase_va_a_claude_qui_repond_a_tout_puis_reprend_la_visite(tmp_path):
    cerveau = CerveauScenario(poli({
        "C'est quoi un pont thermique ?": "Une fuite de chaleur. Souvent aux jonctions entre mur et plancher.",
        "Comment ça va ?": "Très bien, merci.",
    }))
    phrases = ["Ici c'est le séjour.", "C'est quoi un pont thermique ?", "Comment ça va ?"]
    session, apres, _ = asyncio.run(visite(tmp_path, phrases, cerveau))
    assert cerveau.phrases == phrases  # chaque phrase, comprise par les règles ou non
    # Lue phrase par phrase dès qu'elle arrive (« suite » : la voix enchaîne sans couper), une seule question, à la fin.
    assert dits(apres[1]) == ["Une fuite de chaleur.", "Souvent aux jonctions entre mur et plancher.", "Décrivez le premier mur."]
    assert suites(apres[1]) == [False, True, True]
    # La question restée sans réponse est reposée après chaque digression : la visite reprend.
    assert dits(apres[2]) == ["Très bien, merci.", "Décrivez le premier mur."]
    assert "« Décrivez le premier mur. »" in cerveau.messages[2]
    # Une question posée à l'assistant ne pré-remplit rien : pas de « noté » (bip).
    assert not [m for messages in apres[1:] for m in messages if m["type"] == "bip"]
    assert len(session.checklist.elements) == 2  # le plafond et le plancher du séjour, rien d'autre


def test_pause_puis_reprise(tmp_path):
    cerveau = CerveauScenario(poli({
        "On fait une pause, je prends un appel.": ("D'accord, je vous attends.", [{"outil": "pause"}], False),
        "Allô ? Oui, je te rappelle.": ("", [], False),  # adressé à quelqu'un d'autre : rien à dire
        "Bon, ce mur donne dehors.": ("", [], False),  # le serveur a déjà dit « Noté. »
        "C'est bon, on reprend.": ("C'est reparti.", [{"outil": "reprendre"}], False),
    }))
    phrases = ["Ici c'est le séjour.", "On fait une pause, je prends un appel.", "Allô ? Oui, je te rappelle.", "Bon, ce mur donne dehors.",
               "C'est bon, on reprend."]
    session, apres, _ = asyncio.run(visite(tmp_path, phrases, cerveau))
    assert dits(apres[1]) == ["D'accord, je vous attends."]  # pas de question du parcours en pause
    assert dits(apres[2]) == []
    assert dits(apres[3]) == ["Noté."]  # « Noté. » tout de suite (étape 8), mais aucune question en pause
    assert all("Visite EN PAUSE" in m and "Question suivante du parcours" not in m for m in cerveau.messages[2:4])
    # Reprise : Claude n'a pas posé de question, le parcours enchaîne avec la suivante, dans la même réponse.
    assert dits(apres[4]) == ["C'est reparti.", "Ce mur est en quoi ?"] and suites(apres[4]) == [False, True]
    assert not session.en_pause


def test_navigation_reviens_au_sejour(tmp_path):
    cerveau = CerveauScenario(poli({
        "Attends, reviens au séjour.": ("On revient au séjour.", [{"outil": "piece_courante", "nom": "Séjour",
                                                                    "citation": "reviens au séjour"}], False),
    }, defaut="Noté."))
    phrases = ["Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm.", "On passe à la cuisine.", "Attends, reviens au séjour."]
    session, apres, _ = asyncio.run(visite(tmp_path, phrases, cerveau))
    assert session.checklist.piece_courante == "sejour"
    # Les règles ont changé de pièce avant Claude : la question proposée est déjà celle du séjour (l'isolation du mur a
    # déjà été demandée une fois : elle restera dans les manques de fin de visite).
    assert "Pièce courante : Séjour" in cerveau.messages[3] and "[PL1.donne_sur]" in cerveau.messages[3]
    assert dits(apres[3]) == ["On revient au séjour.", "Au-dessus du plafond : combles, terrasse ou logement ?"]


def test_claude_corrige_le_pre_remplissage_sans_contradiction(tmp_path):
    correction = {"outil": "enregistrer_reponse", "element_id": "M1", "champ": "materiau", "valeur": "pierre et brique",
                  "citation": "moitié pierre moitié brique", "certitude": "sur"}  # sans « type » : celui de M1
    cerveau = CerveauScenario(poli({"Ce mur donne dehors, moitié pierre moitié brique.": ("Noté, pierre et brique.", [correction], True)}))
    session, _, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, moitié pierre moitié brique."], cerveau))
    mur = session.checklist.trouver_element("M1")
    assert [v.valeur for v in mur.valeurs["materiau"]] == ["pierre et brique"]  # le pré-remplissage « brique » a disparu
    assert not session.checklist.signalements  # les règles ne contredisent pas Claude
    # Même avec son type, la valeur de Claude n'est pas ramenée à un seul mot du vocabulaire (« brique »).
    assert valeur_normalisee("mur", "materiau", "pierre et brique") == "pierre et brique"
    assert valeur_normalisee("mur", "donne_sur", "les toilettes") == "local chauffé : WC"
    assert "nouvel élément M1 (« le mur 1 », pièce Séjour)" in cerveau.messages[1] and "M1.materiau = brique" in cerveau.messages[1]


def test_annuler_ce_que_les_regles_ont_cree_ou_ce_qu_il_faut_oublier(tmp_path):
    def repondre(contexte):
        crees = [re.match(r"nouvel élément (\w+)", n).group(1) for n in contexte.deja_note if n.startswith("nouvel élément")]
        if contexte.phrase.startswith("Le radiateur"):  # les règles ont vu deux radiateurs : il n'y en a qu'un
            return "Noté, un convecteur.", "", [
                {"outil": "annuler", "element_id": crees[-1], "champ": ""},
                {"outil": "enregistrer_reponse", "element_id": crees[0], "champ": "type", "valeur": "convecteur électrique",
                 "citation": "un vieux grille-pain"}]
        if contexte.phrase.startswith("Oublie"):
            return "C'est oublié.", "", [{"outil": "annuler", "element_id": "M1", "champ": "epaisseur"}]
        return poli(defaut="Noté.")(contexte)

    cerveau = CerveauScenario(repondre)
    phrases = ["Ici c'est le séjour.", "Le radiateur est électrique, un vieux grille-pain.", "Ce mur donne dehors, brique 30 cm.",
               "Oublie ce que je viens de dire sur l'épaisseur."]
    session, _, _ = asyncio.run(visite(tmp_path, phrases, cerveau))
    c = session.checklist
    emetteurs = [e for e in c.elements if e.type == "emetteur"]
    assert len(emetteurs) == 1 and emetteurs[0].valeur("type").valeur == "convecteur électrique"
    mur = c.trouver_element("M1")
    assert mur.valeur("epaisseur") is None and mur.valeur("materiau").valeur == "brique"
    commandes = [json.loads(l)["commandes"] for l in (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
                 if '"evenement": "commandes"' in l]
    assert commandes == [["annuler E2"], ["annuler M1.epaisseur"]]


def test_reponse_perimee_abandonnee_et_phrase_suivante_pre_remplie_sans_attendre(tmp_path):
    cerveau = CerveauScenario(poli({
        "C'est quoi un pont thermique ?": "Une fuite de chaleur. Souvent aux jonctions.",
    }), pause_s=0.3)

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau)
        await session.recevoir_controle({"type": "texte", "texte": "Ici c'est le séjour."})
        await attendre(session)
        debut = len(recus)
        await session.recevoir_controle({"type": "texte", "texte": "C'est quoi un pont thermique ?"})
        await asyncio.sleep(0.15)  # Claude a dit sa première phrase et écrit encore la suite
        await session.recevoir_controle({"type": "texte", "texte": "Ce mur donne dehors."})
        await attendre(session)
        await session.terminer()
        return session, recus[debut:]

    session, recus = asyncio.run(scenario())
    # Il a reparlé : le reste de la réponse sur le pont thermique n'est pas lu ; sa phrase reçoit sa propre réponse :
    # « Noté. » tout de suite (le serveur), puis la question (Claude).
    assert dits(recus) == ["Une fuite de chaleur.", "Noté.", "Ce mur est en quoi ?"]
    # Sa phrase a été pré-remplie (et « Noté. » dit) pendant que Claude répondait encore à la précédente : pas de file
    # bloquée.
    assert cerveau.murs_a_la_fin[1] == ["M1"]
    assert next(m for m in recus if m.get("texte") == "Noté.")["latence_s"] < 0.3
    assert cerveau.phrases[1:] == ["C'est quoi un pont thermique ?", "Ce mur donne dehors."]


def test_phrases_dites_pendant_que_claude_repond_reunies_en_un_appel(tmp_path):
    cerveau = CerveauScenario(poli({"C'est quoi un pont thermique ?": "Une fuite de chaleur. Souvent aux jonctions."},
                                   defaut="Noté."), pause_s=0.3)

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau)
        await session.recevoir_controle({"type": "texte", "texte": "Ici c'est le séjour."})
        await attendre(session)
        await session.recevoir_controle({"type": "texte", "texte": "C'est quoi un pont thermique ?"})
        await asyncio.sleep(0.1)
        await session.recevoir_controle({"type": "texte", "texte": "Ce mur donne dehors."})
        await asyncio.sleep(0.1)
        await session.recevoir_controle({"type": "texte", "texte": "Il y a deux fenêtres PVC."})
        await attendre(session)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert cerveau.phrases[-1] == "Ce mur donne dehors. Il y a deux fenêtres PVC."  # un seul appel pour les deux phrases
    assert "M1.donne_sur = extérieur" in cerveau.messages[-1] and "nouvel élément F1" in cerveau.messages[-1]
    assert sum(1 for m in session.mesures if m.get("regroupee_avec_la_suivante")) == 1


def test_question_du_parcours_si_claude_n_en_pose_pas(tmp_path):
    # Claude dit « Noté. » (ou rien si le serveur l'a déjà dit), sans question : le parcours enchaîne, dans la même réponse.
    cerveau = CerveauScenario(lambda contexte: ("" if contexte.deja_dit else "Noté.", "", []))
    _, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm."], cerveau))
    assert dits(apres[0]) == ["Noté.", "Décrivez le premier mur."]
    assert dits(apres[1]) == ["Noté.", "Ce mur est isolé ?"] and suites(apres[1]) == [False, True]


def test_consigne_de_claude_comptee_comme_sa_question(tmp_path):
    # « Dans la chambre, décrivez le premier mur. » : c'est la question ; le parcours ne la répète pas derrière.
    cerveau = CerveauScenario(lambda contexte: ("D'accord. Dans ce séjour, décrivez le premier mur.", "presence:mur", []))
    _, apres, _ = asyncio.run(visite(tmp_path, ["Ici c'est le séjour."], cerveau))
    assert dits(apres[0]) == ["D'accord.", "Dans ce séjour, décrivez le premier mur."]


def test_claude_indisponible_le_parcours_continue(tmp_path):
    cerveau = CerveauScenario(lambda contexte: Decision(erreur="pas de réponse de Claude en 25 s"))
    _, apres, recus = asyncio.run(visite(tmp_path, ["Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm.", "Quel mur ?"], cerveau))
    assert dits(apres[0]) == ["Décrivez le premier mur."]
    assert dits(apres[1]) == ["Noté.", "Ce mur est isolé ?"]
    assert len(dits(apres[2])) == 1 and dits(apres[2])[0].startswith("Je parle du mur") and dits(apres[2])[0].endswith("isolé ?")
    assert any(m["type"] == "erreur" for m in recus)


def test_le_contexte_donne_a_claude_la_question_suivante_et_les_remarques(tmp_path):
    cerveau = CerveauScenario(poli(defaut="Noté."))
    phrases = ["Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm.", "En fait c'est du parpaing, pas de la brique.",
               "Il te faut quoi d'autre sur ce mur ?"]
    asyncio.run(visite(tmp_path, phrases, cerveau))
    message = cerveau.messages[2]
    # La contradiction est dite tout de suite par le serveur (étape 8) : Claude le sait, et ne la répète pas.
    assert "Déjà dit par le serveur à l'instant : « Noté : parpaing au lieu de brique. »" in message
    assert "« Il est isolé ? » [M1.isolation] (élément : « le mur extérieur »)" in message  # pour la nommer après une digression
    deja_demande = next(l for l in message.splitlines() if l.startswith("Déjà demandé récemment"))
    assert "M1.isolation" not in deja_demande  # la question proposée est à reposer, pas « déjà demandée »
    assert "Il demande quelque chose ; réponse possible : « Pour le mur" in cerveau.messages[3]


def test_trente_phrases_libres_variees(tmp_path):
    categories = Counter(categorie for categorie, _ in CONVERSATION_LIBRE)
    assert len(CONVERSATION_LIBRE) >= 30 and len({p for _, p in CONVERSATION_LIBRE}) == len(CONVERSATION_LIBRE)
    assert {"question générale", "hors sujet", "navigation", "correction", "récapitulatif"} <= set(categories)
    assert all(n >= 5 for c, n in categories.items() if c != "description libre")

    def repondre(contexte):
        if "pause" in contexte.phrase:
            return "D'accord, je vous attends.", "", [{"outil": "pause"}]
        if "on reprend" in contexte.phrase:
            return poli(defaut="C'est reparti.")(contexte)[:2] + ([{"outil": "reprendre"}],)
        return poli(defaut="Bien sûr.")(contexte)

    cerveau = CerveauScenario(repondre)
    phrases = MISE_EN_PLACE + [p for _, p in CONVERSATION_LIBRE]
    session, apres, _ = asyncio.run(visite(tmp_path, phrases, cerveau))
    assert cerveau.phrases == phrases
    reponses = apres[len(MISE_EN_PLACE):]
    for (categorie, phrase), messages in zip(CONVERSATION_LIBRE, reponses):
        assert dits(messages), f"rien dit après « {phrase} »"
        assert sum(t.count("?") for t in dits(messages)) <= 1, phrase
        assert not any("répét" in t.lower() for t in dits(messages))
        if categorie in ("question générale", "hors sujet", "récapitulatif"):
            assert not [m for m in messages if m["type"] == "bip"], f"les règles ont noté quelque chose dans « {phrase} »"
