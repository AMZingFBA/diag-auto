"""Test de Noah du 22/10 après-midi (sessions/20261022-153605-67f6df, 11 min 43) : « il pose trop de questions que je
répète, des fois plus de réponse pendant 2 minutes, il me fait passer à une pièce alors qu'on n'a pas fini celle-là ;
un questionnaire en direct sur le téléphone pour cocher les réponses, en même temps qu'à l'oral ».

1. Questionnaire en direct : chaque question arrive avec ses réponses en boutons ; un appui vaut une réponse dite.
2. Les bruits (« A. », « F. ») ne sont plus pris pour des réponses ; les réponses courtes mal transcrites (« Vaime s. »,
   « Na. ») sont réécoutées par Whisper.
3. Une réponse coupée par plusieurs bruits de suite est reprise (30 s de silence au test).
4. « Un autre mur dans cette pièce ? » posé 10 fois ; « c'est le même mur » non compris ; « la pièce U »."""

import asyncio
import json
import time

from fastapi.testclient import TestClient

from assistant.extraction import Cible, extraire, normaliser
from assistant.reponses import options_pour, suspecte
from assistant.serveur import creer_app
from test_conversation import CerveauScenario, attendre, dits, poli
from test_fluidite import TranscripteurFactice, jouer_son, ouvrir, parler, son
from test_serveur import reglages


class TranscripteurDouteux(TranscripteurFactice):
    """Transcription rapide écrite à l'avance, et réécoute par Whisper (seul, puis guidé par les réponses attendues)."""

    def __init__(self, textes, whisper=(), guide=()):
        super().__init__(textes)
        self.whisper, self.guide = list(whisper), list(guide)
        self.reecoutes, self.attendues = 0, []

    def second_avis(self, audio):
        self.reecoutes += 1
        return self.whisper.pop(0) if self.whisper else ""

    def reecoute_guidee(self, audio, attendues):
        self.attendues = list(attendues)
        return self.guide.pop(0) if self.guide else ""


def journal(dossier):
    return [json.loads(l) for l in (dossier / "journal.jsonl").read_text(encoding="utf-8").splitlines()]


def questions(messages):
    return [m for m in messages if m["type"] == "dire" and "cible" in m]


# --- 1. Questionnaire en direct -----------------------------------------------------------------------------------


def test_chaque_question_arrive_avec_ses_reponses_en_boutons(tmp_path):
    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()))
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        await parler(session, "Ce mur donne dehors.")
        await attendre(session)
        await session.terminer()
        return recus

    q = questions(asyncio.run(scenario()))
    assert [(m["texte"], m["cible"]) for m in q] == [("Décrivez le premier mur.", "presence:mur"), ("Ce mur est en quoi ?", "M1.materiau")]
    assert q[0]["options"] == []  # « Décrivez le premier mur » : réponse libre
    assert {"libelle": "Brique", "valeur": "brique"} in q[1]["options"] and len(q[1]["options"]) <= 12


def test_reponse_cochee_appliquee_et_question_suivante_aussitot(tmp_path):
    cerveau = CerveauScenario(poli())

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        await parler(session, "Ce mur donne dehors.")
        await attendre(session)
        appels, debut = len(cerveau.phrases), len(recus)
        avant = time.perf_counter()
        await session.recevoir_controle({"type": "reponse", "cible": "M1.materiau", "valeur": "brique", "libelle": "Brique"})
        duree = time.perf_counter() - avant
        apres = recus[debut:]
        await session.terminer()
        return session, apres, duree, len(cerveau.phrases) - appels

    session, apres, duree, appels = asyncio.run(scenario())
    valeur = session.checklist.trouver_element("M1").valeur("materiau")
    assert (valeur.valeur, valeur.citation) == ("brique", "coché sur le téléphone : Brique")
    assert dits(apres) == ["Quelle épaisseur ?"] and questions(apres)[0]["options"][0] == {"libelle": "15 cm", "valeur": "15 cm"}
    assert appels == 0 and duree < 0.5  # sans attendre Claude
    assert any(m["type"] == "etat" for m in apres)  # la fiche du téléphone est à jour
    assert [e for e in journal(tmp_path) if e["evenement"] == "reponse_cochee"][0]["valeur"] == "brique"


def test_oui_non_piece_et_fiche_cochees(tmp_path):
    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()))
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        await parler(session, "Ce mur donne dehors, brique 30 cm, non isolé.")
        await attendre(session)
        debut = len(recus)
        await session.recevoir_controle({"type": "reponse", "cible": "suite:mur", "valeur": "non", "libelle": "Non, c'est tout"})
        apres_murs = dits(recus[debut:])
        # Fiche de la pièce : correction d'un champ déjà rempli, sans changer la question en cours.
        debut = len(recus)
        await session.recevoir_controle({"type": "reponse", "element": "M1", "champ": "materiau", "valeur": "parpaing",
                                         "libelle": "Parpaing"})
        apres_fiche = dits(recus[debut:])
        await session.terminer()
        return session, apres_murs, apres_fiche

    session, apres_murs, apres_fiche = asyncio.run(scenario())
    c = session.checklist
    assert "mur" in c.pieces["sejour"].clos and apres_murs == ["Au-dessus du plafond : combles, terrasse ou logement ?"]
    assert c.trouver_element("M1").valeur("materiau").valeur == "parpaing" and apres_fiche == []


def test_pieces_et_equipements_coches_comme_s_ils_etaient_dits(tmp_path):
    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()))
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        session._cible = Cible.depuis_code("presence:chauffage", session.checklist)
        await session.recevoir_controle({"type": "reponse", "cible": "presence:chauffage", "valeur": "gaz", "libelle": "Gaz"})
        session._cible = Cible.depuis_code("piece:suivante", session.checklist)
        await session.recevoir_controle({"type": "reponse", "cible": "piece:suivante", "valeur": "Cuisine", "libelle": "Cuisine"})
        await session.terminer()
        return session

    c = asyncio.run(scenario()).checklist
    assert [(e.type, e.valeur("energie").valeur) for e in c.elements_de(None) if e.type == "chauffage"] == [("chauffage", "gaz")]
    assert c.piece_courante == "cuisine"


def test_statut_du_serveur_donne_les_reponses_par_information(tmp_path):
    with TestClient(creer_app(reglages(tmp_path))) as client:
        options = client.get("/api/statut").json()["options"]
    assert {"libelle": "PVC", "valeur": "PVC"} in options["fenetre.menuiserie"]
    assert {"libelle": "Non isolé", "valeur": "non isolé"} in options["mur.isolation"]
    assert all(set(o) == {"libelle", "valeur"} for liste in options.values() for o in liste)


def test_boutons_selon_la_question():
    def libelles(code, checklist=None):
        from assistant.checklist import Checklist

        c = checklist or Checklist()
        return [o["libelle"] for o in options_pour(Cible.depuis_code(code, c))]

    assert libelles("presence:fenetre") == ["Oui", "Non"]
    assert libelles("suite:mur") == ["Oui, un autre", "Non, c'est tout"]
    assert "VMC simple flux" in libelles("presence:ventilation") and "Aucune" in libelles("presence:ventilation")
    assert libelles("piece:suivante")[:2] == ["Séjour", "Cuisine"]
    assert options_pour(None) == []


# --- 2. Bruits et réponses courtes -------------------------------------------------------------------------------


def test_bruits_et_reponses_courtes_reperes():
    # Transcriptions réelles du test (bruits, puis réponses mal transcrites) : toutes à réécouter.
    for texte in ("A.", "F.", "P.", "Il.", "Qu.", "Il ré.", "Unf.", "Lour.", "Elle par su.", "Vaime s.", "GMC.", "Na.", "Nur."):
        assert suspecte(texte), texte
    # Vraies réponses du test, comprises telles quelles : pas de réécoute (pas de temps perdu).
    for texte in ("Non.", "Oui.", "E oui.", "Le gaz.", "Un voisin.", "Simple.", "Tu es là?", "Trente centimètres.",
                  "basse température.", "Bois. c'est du bois.", "Il n'est pas isolé."):
        assert not suspecte(texte), texte


def test_un_bruit_transcrit_a_n_est_pas_une_reponse(tmp_path):
    cerveau = CerveauScenario(poli())
    transcripteur = TranscripteurDouteux(["A."], whisper=[""])

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau, transcripteur)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        await parler(session, "Ce mur donne dehors.")
        await attendre(session)
        debut = len(recus)
        await jouer_son(session, son((0.5, 0), (0.6, 8000), (1.0, 0)), 20.0)  # le téléphone manipulé : « A. »
        await attendre(session)
        await session.terminer()
        return recus[debut:]

    apres = asyncio.run(scenario())
    assert "A." not in cerveau.phrases and transcripteur.reecoutes == 1
    assert dits(apres) == []  # la question n'est pas reposée pour un bruit
    reecoute = [e for e in journal(tmp_path) if e["evenement"] == "reecoute"][0]
    assert reecoute["rapide"] == "A." and reecoute["retenu"] == "" and reecoute["raison"].startswith("bruit")


def test_non_mal_transcrit_retrouve_par_whisper(tmp_path):
    transcripteur = TranscripteurDouteux(["Na."], whisper=["Non."])

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), transcripteur)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        await parler(session, "Ce mur donne dehors, brique 30 cm.")  # → « Il est isolé ? »
        await attendre(session)
        await jouer_son(session, son((0.5, 0), (0.6, 8000), (1.0, 0)), 20.0)
        await attendre(session)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert session.checklist.trouver_element("M1").valeur("isolation").valeur == "non isolé"


def test_vmc_mal_transcrite_retrouvee_par_whisper_guide(tmp_path):
    transcripteur = TranscripteurDouteux(["Vaime s."], whisper=["Je vais me cacher."], guide=["VMC"])

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), transcripteur)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        session._cible = Cible.depuis_code("presence:ventilation", session.checklist)  # « Ventilation : VMC ou naturelle ? »
        await jouer_son(session, son((0.5, 0), (0.6, 8000), (1.0, 0)), 20.0)
        await attendre(session)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert "VMC simple flux" in transcripteur.attendues and "naturelle" in transcripteur.attendues
    assert any(e.type == "ventilation" for e in session.checklist.elements_de(None))
    raisons = [e["raison"] for e in journal(tmp_path) if e["evenement"] == "reecoute"]
    assert raisons == ["réponse attendue reconnue par Whisper guidé"]


# --- 3. Réponse coupée par plusieurs bruits ------------------------------------------------------------------------


def test_reponse_coupee_par_deux_bruits_de_suite_redite(tmp_path):
    # Au test : la réponse coupée par un bruit, puis d'autres bruits (« . », « A. ») : jamais redite, 30 s de silence.
    cerveau = CerveauScenario(poli({"C'est quoi un pont thermique ?": "Une fuite de chaleur. Souvent aux jonctions."}), pause_s=0.3)
    transcripteur = TranscripteurDouteux([".", "A."], whisper=[""])

    async def scenario():
        session, recus = await ouvrir(tmp_path, cerveau, transcripteur)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        debut = len(recus)
        await parler(session, "C'est quoi un pont thermique ?")
        await asyncio.sleep(0.15)
        await jouer_son(session, son((0.5, 0), (0.5, 8000), (0.8, 0), (0.5, 8000), (1.0, 0)), 10.0)  # deux bruits forts
        await attendre(session)
        await session.terminer()
        return recus[debut:]

    apres = asyncio.run(scenario())
    assert sum(m["type"] == "parole_debut" for m in apres) == 2  # coupé deux fois…
    assert dits(apres)[-2:] == ["Souvent aux jonctions.", "Décrivez le premier mur."]  # … puis redit en entier
    assert "A." not in cerveau.phrases


# --- 4. Murs, doublons, nom de pièce ------------------------------------------------------------------------------


def test_un_autre_mur_jamais_repose_par_claude_sous_une_autre_forme(tmp_path):
    # Au test, Claude reposait « Un autre mur dans cette pièce ? » (10 fois) : la question du parcours et la sienne ont
    # maintenant la même clé.
    def repondre(contexte):
        if contexte.phrase.startswith("Celui-ci"):
            return "Un autre mur dans cette pièce ?", "suite:mur", []
        return poli()(contexte)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(repondre))
        for phrase in ("Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm, non isolé.",
                       "Celui-ci donne sur le voisin."):
            await parler(session, phrase)
            await attendre(session)
        await session.terminer()
        return recus

    toutes = dits(asyncio.run(scenario()))
    assert toutes.count("D'autres murs sur l'extérieur ou un local non chauffé ?") == 1
    assert "Un autre mur dans cette pièce ?" not in toutes


def test_c_est_le_meme_mur_reunit_les_deux_murs():
    from assistant.checklist import Checklist

    c = Checklist()
    c.definir_piece("Séjour", 0.0)
    m1 = c.signaler_element("mur", "le mur ouest", 1.0, source="voix")
    m2 = c.signaler_element("mur", "le mur affiché", 2.0, source="voix")
    cible = Cible("doublon", "mur", "", m2.id, source=m1.id)
    for phrase in ("Je sais pas c'est le mur ouest mais c'est bien extérieur, c'est le même mur.",
                   "Savez dire quoi c'est le même mur que le mur ouest extérieur ?", "Oui.", "Pareil."):
        assert [a["outil"] for a in extraire(phrase, c, cible).actions][:1] == ["fusionner"], phrase
    for phrase in ("Non, c'est un autre mur.", "C'est pas le même.", "Non."):
        assert "fusionner" not in [a["outil"] for a in extraire(phrase, c, cible).actions], phrase


def test_doublon_repropose_par_claude_apres_confirmation_reuni_sans_question(tmp_path):
    # Au test : « c'est le même mur » ; Claude reproposait le doublon, et la question « C'est le même mur… ? » repartait.
    def repondre(contexte):
        if "même mur" in contexte.phrase:
            return "Compris, c'est le même mur.", "", [{"outil": "doublon", "element_id": "M2", "meme_que": "M1",
                                                       "preuve": "même description, confirmé à l'oral"}]
        return poli()(contexte)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(repondre))
        for phrase in ("Ici c'est le séjour.", "Ce mur donne dehors, brique 30 cm, non isolé.", "Ce mur-là donne dehors.",
                       "C'est bien extérieur, c'est le même mur."):
            await parler(session, phrase)
            await attendre(session)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    assert [e.id for e in session.checklist.elements if e.type == "mur"] == ["M1"]
    assert not [q for q in dits(recus) if "même" in q and q.endswith("?")]


def test_premiere_piece_jamais_nommee_u(tmp_path):
    def repondre(contexte):
        if "première pièce" in contexte.phrase:
            return "On commence par cette pièce.", "", [{"outil": "piece_courante", "nom": "U", "citation": "c'est la première pièce"}]
        return poli()(contexte)

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(repondre))
        await parler(session, "Donc là c'est la première pièce, c'est le premier mur.")
        await attendre(session)
        await session.terminer()
        return session

    c = asyncio.run(scenario()).checklist
    assert [p.nom for p in c.pieces.values()] == ["Pièce 1"]


def test_pas_d_autre_mur_dit_a_tout_moment():
    from assistant.checklist import Checklist

    c = Checklist()
    c.definir_piece("Séjour", 0.0)
    plafond = Cible.depuis_code("PL1.donne_sur", c) or Cible("champ", "plafond", "donne_sur", "PL1")
    for phrase in ("Pas d'autre mur.", "Non, pas d'autres murs.", "C'est tout pour les murs."):
        actions = extraire(normaliser(phrase) and phrase, c, plafond).actions
        assert [(a["outil"], a.get("type")) for a in actions] == [("cloturer", "mur")], phrase


def test_non_coche_a_une_proposition_passe_a_la_question_suivante(tmp_path):
    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()))
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        session._cible = Cible.depuis_code("piece:proposee:Cuisine", session.checklist)
        debut = len(recus)
        await session.recevoir_controle({"type": "reponse", "cible": "piece:proposee:Cuisine", "valeur": "non", "libelle": "Non"})
        await session.terminer()
        return session, dits(recus[debut:])

    session, apres = asyncio.run(scenario())
    assert session.checklist.piece_courante == "sejour"
    assert apres == ["Au-dessus du plafond : combles, terrasse ou logement ?"]  # la visite continue dans le séjour


def test_reponse_courte_incomprise_reecoutee_meme_avec_des_mots_connus(tmp_path):
    # Rejeu du test : « V'aime ça. » (VMC) n'était pas réécouté (« ça » est un mot connu) : la question revenait.
    transcripteur = TranscripteurDouteux(["V'aime ça."], whisper=["Je vais me cacher."], guide=["VMC."])

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), transcripteur)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        session._cible = Cible.depuis_code("presence:ventilation", session.checklist)
        await jouer_son(session, son((0.5, 0), (0.6, 8000), (1.0, 0)), 20.0)
        await attendre(session)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert transcripteur.reecoutes == 1 and any(e.type == "ventilation" for e in session.checklist.elements_de(None))


def test_reponse_courte_comprise_pas_reecoutee(tmp_path):
    transcripteur = TranscripteurDouteux(["Le gaz."])

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()), transcripteur)
        await parler(session, "Ici c'est le séjour.")
        await attendre(session)
        session._cible = Cible.depuis_code("presence:chauffage", session.checklist)
        await jouer_son(session, son((0.5, 0), (0.6, 8000), (1.0, 0)), 20.0)
        await attendre(session)
        await session.terminer()
        return session

    session = asyncio.run(scenario())
    assert transcripteur.reecoutes == 0  # comprise telle quelle : aucune seconde perdue
    assert [e.valeur("energie").valeur for e in session.checklist.elements_de(None) if e.type == "chauffage"] == ["gaz"]
