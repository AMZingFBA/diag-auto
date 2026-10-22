"""Étape 6 de Noah : boussole et murs nommés par leur orientation (« le mur nord, celui avec la télé »).

Dans LICIEL et en DPE 3CL, parois et fenêtres sont décrites par leur orientation (apports solaires).
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from assistant import parcours
from assistant.actions import appliquer
from assistant.boussole import Boussole, Mesure, Visee, dispersion, ecart, mediane_circulaire, oppose, point_cardinal
from assistant.checklist import Checklist
from assistant.extraction import Cible, extraire
from assistant.reglages import Reglages
from assistant.session import Session
from assistant.simulation import CerveauSimulation
from assistant.transcription import TranscripteurSimulation


def dire(c: Checklist, phrase: str, cible: str | None = None):
    extraction = extraire(phrase, c, Cible.depuis_code(cible, c) if cible else None)
    resultats = appliquer(c, extraction.actions, 10.0, [phrase])
    assert all(r["statut"] == "accepte" for r in resultats), resultats
    return extraction


def sejour(fiabilite: str = "bonne", correction: float | None = None, gyroscope: bool = True) -> Checklist:
    c = Checklist()
    c.definir_piece("Séjour", 0)
    c.regler_boussole(correction, fiabilite, gyroscope)
    return c


def mur_filme(c: Checklist, phrase: str, lacet: float | None, cap: float | None = None):
    """Le diagnostiqueur décrit le mur qu'il filme de face (lacet du gyroscope, cap de la boussole)."""
    extraction = dire(c, phrase)
    mur = c.trouver_element(c.dernier["mur"])
    c.mesurer(mur.id, Visee(cap=cap, lacet=lacet, stable=True))
    return mur, extraction


# --- Calcul : cap → orientation ------------------------------------------------------------------------

@pytest.mark.parametrize("cap, attendu", [(0, "nord"), (10, "nord"), (350, "nord"), (316, "nord"), (80, "est"), (100, "est"),
                                          (190, "sud"), (226, "ouest"), (260, "ouest"), (-90, "ouest"), (720, "nord")])
def test_cap_vers_point_cardinal(cap, attendu):
    assert point_cardinal(cap) == attendu


def test_angles():
    assert ecart(10, 350) == 20 and ecart(350, 10) == -20 and ecart(180, 0) == -180
    assert oppose("nord") == "sud" and oppose("est") == "ouest"
    assert round(mediane_circulaire([350, 5, 10, 200])) in (5, 10)  # robuste à une mesure aberrante, autour du nord
    assert dispersion([350, 0, 10]) == 10


# --- Boussole du téléphone : visée, correction, fiabilité --------------------------------------------------

def test_visee_et_correction_avec_boussole_fiable():
    b = Boussole()
    assert b.fiabilite() == "inconnue"  # rien reçu : pas de question d'orientation (essai écrit, ancien rejeu)
    for t in range(10):
        b.ajouter(Mesure(t, cap=(100 + t + 20) % 360, lacet=100 + t, precision=5, inclinaison=90))
    b.ajouter(Mesure(10.0, cap=300, lacet=150, inclinaison=10))  # téléphone à plat (on filme le sol) : écarté
    visee = b.visee(2, 4)
    assert round(visee.lacet) == 103 and round(visee.cap) == 123 and visee.stable
    assert round(b.correction()) == 20 and b.fiabilite() == "bonne" and b.gyroscope


def test_boussole_perturbee_ou_absente():
    b = Boussole()
    for t, cap in enumerate([20, 80, 150, 210, 300, 10, 120]):  # « cap − lacet » qui saute partout : métal, électricité
        b.ajouter(Mesure(t, cap=cap, lacet=0))
    assert b.correction() is None and b.fiabilite() == "faible"
    b = Boussole()
    for t in range(6):
        b.ajouter(Mesure(t, cap=10, lacet=0, precision=45))  # l'iPhone annonce ±45°
    assert b.fiabilite() == "faible"
    b = Boussole()
    for t in range(6):
        b.ajouter(Mesure(t, cap=None, lacet=t * 10))  # pas de boussole, mais un gyroscope
    assert b.fiabilite() == "absente" and b.gyroscope and b.correction() is None
    b = Boussole()
    b.ajouter(Mesure(0, lacet=0, inclinaison=90))
    b.ajouter(Mesure(1, lacet=120, inclinaison=90))  # la caméra a balayé la pièce pendant la phrase
    assert not b.visee(0, 1).stable


# --- Orientation des murs ----------------------------------------------------------------------------

def test_murs_orientes_par_la_boussole_et_murs_opposes():
    c = sejour(correction=20.0)
    nord, _ = mur_filme(c, "Ce mur donne dehors, brique 30 cm, isolé.", lacet=340, cap=0)
    est, _ = mur_filme(c, "Un autre mur avec la télé, il donne sur le voisin.", lacet=70, cap=91)
    sud, _ = mur_filme(c, "Un autre mur donne dehors, en parpaing de 20, pas isolé.", lacet=160, cap=181)
    assert [(m.orientation, m.orientation_source) for m in (nord, est, sud)] == [("nord", "boussole"), ("est", "boussole"), ("sud", "boussole")]
    assert nord.orientation == oppose(sud.orientation)  # face à face (lacets à 180°) : nord ↔ sud
    assert nord.orientation_note == "cap 0°" and nord.cap == 0 and nord.lacet == 340  # cap brut gardé
    assert [c.nom(m, demonstratif=False) for m in (nord, est, sud)] == ["le mur nord", "le mur est, celui avec la télé", "le mur sud"]
    d = c.vers_dict()["pieces"][0]["elements"]
    assert next(e for e in d if e["id"] == nord.id)["orientation"] == {"point": "nord", "source": "boussole", "note": "cap 0°",
                                                                      "cap_brut": 0, "lacet": 340}


def test_fenetres_orientees_comme_leur_mur():
    c = sejour(correction=0.0)
    mur, _ = mur_filme(c, "Ce mur donne dehors, il y a deux fenêtres dessus.", lacet=185)
    fenetres = next(e for e in c.elements if e.type == "fenetre")
    assert fenetres.support == mur.id and (fenetres.orientation, fenetres.orientation_source) == ("sud", "mur")


def test_boussole_perturbee_pres_d_un_mur_le_gyroscope_l_emporte():
    c = sejour(correction=0.0)
    mur, _ = mur_filme(c, "Ce mur donne dehors.", lacet=90, cap=200)  # radiateur en fonte à côté : la boussole dit sud
    assert mur.orientation == "est" and "boussole perturbée ici (sud mesuré)" in mur.orientation_note


# --- Correction orale, et pièces sans boussole fiable ------------------------------------------------------

def test_correction_orale_et_deduction_des_autres_murs():
    c = sejour(correction=20.0)
    m1, _ = mur_filme(c, "Ce mur donne dehors, brique 30 cm, isolé.", lacet=340, cap=0)
    m2, _ = mur_filme(c, "Un autre mur donne dehors, en parpaing de 20, pas isolé.", lacet=160, cap=180)
    dire(c, "Non, c'est le mur ouest.", cible="M2.isolation")  # le mur dont on parle : M2
    assert (m2.orientation, m2.orientation_source) == ("ouest", "dit")
    assert m2.orientation_note == "dit : « Non, c'est le mur ouest. » (la boussole donnait sud)"
    assert (m1.orientation, m1.orientation_source) == ("est", "déduit")  # face à face : toujours opposés
    assert c.boussole_fiabilite == "faible"  # la boussole s'est trompée de 90° : on ne s'y fie plus
    dire(c, "Il est orienté plein nord.", cible="M1.isolation")
    assert (m1.orientation, m1.orientation_source) == ("nord", "dit")
    assert c.signalements[-1].texte == ("Attention : le mur nord et le mur ouest sont face à face, l'orientation de l'un "
                                        "des deux est fausse.")


@pytest.mark.parametrize("phrase, attendu", [
    ("Le mur est en brique, il donne dehors.", ""),  # « est » : le verbe
    ("Le mur est donne dehors.", "est"),
    ("Ce mur est à l'est.", "est"),
    ("Ce mur donne dehors, il est orienté plein sud.", "sud"),
    ("Le mur sud donne dehors, en brique.", "sud"),
    ("La baie vitrée plein ouest, en alu.", "ouest"),
])
def test_orientation_dite_dans_une_description(phrase, attendu):
    c = sejour(fiabilite="inconnue")
    dire(c, phrase)
    element = c.elements[-1]
    assert element.orientation == attendu and (not attendu or element.orientation_source == "dit")


def test_le_mur_nord_designe_le_mur_oriente_nord():
    c = sejour(correction=0.0)
    nord, _ = mur_filme(c, "Ce mur donne dehors, brique 30 cm, isolé.", lacet=5)
    mur_filme(c, "Un autre mur donne dehors, en parpaing.", lacet=180)
    dire(c, "Le mur nord, en fait c'est du béton.")
    assert nord.valeur("materiau").valeur == "béton" and len([e for e in c.elements if e.type == "mur"]) == 2


def test_sans_boussole_une_seule_question_et_les_autres_murs_deduits():
    c = sejour(fiabilite="absente")
    m1, _ = mur_filme(c, "Ce mur donne dehors, brique 30 cm, isolé.", lacet=10)
    question = next(q for q in parcours.questions(c) if q.code.startswith("orientation:"))
    assert (question.code, question.texte, question.cle) == ("orientation:M1", "Ce mur est orienté nord, sud, est ou ouest ?",
                                                             "orientation@visite")
    dire(c, "Plein sud.", cible="orientation:M1")
    m2, _ = mur_filme(c, "Un autre mur donne dehors, en parpaing de 20, pas isolé.", lacet=100)
    assert (m1.orientation, m2.orientation, m2.orientation_source) == ("sud", "ouest", "déduit")
    assert not [q for q in parcours.questions(c) if q.code.startswith("orientation:")]  # plus jamais demandé
    # Rien reçu du téléphone (essai écrit, rejeu d'une ancienne visite) : on ne demande rien.
    c = sejour(fiabilite="inconnue")
    mur_filme(c, "Ce mur donne dehors, brique 30 cm, isolé.", lacet=None)
    assert not [q for q in parcours.questions(c) if q.code.startswith("orientation:")]


@pytest.mark.parametrize("reponse, attendu", [("Sud.", "sud"), ("Est.", "est"), ("À l'est.", "est"), ("Il est au nord.", "nord"),
                                              ("Plein ouest.", "ouest")])
def test_reponses_a_la_question_d_orientation(reponse, attendu):
    c = sejour(fiabilite="absente")
    mur_filme(c, "Ce mur donne dehors.", lacet=0)
    dire(c, reponse, cible="orientation:M1")
    assert c.trouver_element("M1").orientation == attendu


# --- Noms par orientation ------------------------------------------------------------------------------

def test_nom_par_orientation_puis_repere():
    c = sejour(correction=0.0)
    tele, _ = mur_filme(c, "Le mur avec la télé donne dehors, en brique.", lacet=2)
    fond, _ = mur_filme(c, "Le mur du fond donne dehors, en brique.", lacet=358)  # pièce en L : deux murs nord
    mur_filme(c, "Un autre mur donne dehors.", lacet=180)
    assert c.nom(tele, demonstratif=False) == "le mur nord, celui avec la télé"
    assert c.nom(fond, demonstratif=False) == "le mur nord, celui du fond"
    texte = next(q.texte for q in parcours.questions(c) if q.code == f"{tele.id}.epaisseur")
    assert texte == "Le mur nord, celui avec la télé, quelle épaisseur ?"


# --- Visite simulée : le téléphone envoie boussole et gyroscope ---------------------------------------------

def test_visite_avec_la_boussole_du_telephone(tmp_path):
    async def scenario():
        cerveau = CerveauSimulation()
        session = Session("essai", tmp_path, cerveau, cerveau, TranscripteurSimulation(),
                          Reglages(cerveau="simulation", transcription="simulation", dossier_sessions=tmp_path, veille_s=1000,
                                   questions_par_minute=60))
        dits = []

        async def envoyer(m):
            if m["type"] == "dire":
                dits.append(m["texte"])

        session.envoyer = envoyer
        await session.demarrer()
        t = 0.0
        for lacet, phrase in [(0, "Ici c'est le séjour."), (340, "Ce mur donne dehors, brique 30 cm, isolé."),
                              (160, "Un autre mur donne dehors, en parpaing de 20, pas isolé."), (160, "Le mur nord est isolé ?")]:
            for _ in range(4):
                t += 1
                await session.recevoir_controle({"type": "capteurs", "t": t, "lacet": lacet, "cap": (lacet + 20) % 360,
                                                 "precision": 5, "inclinaison": 88})
                await session.recevoir_image(t, b"\xff\xd8image")
            await session.recevoir_controle({"type": "texte", "texte": phrase})
            await asyncio.sleep(0.03)
            while session.occupe:
                await asyncio.sleep(0.02)
        await session.terminer()
        return session, dits

    session, dits = asyncio.run(scenario())
    c = session.checklist
    assert [(c.nom(e, demonstratif=False), e.orientation) for e in c.elements if e.type == "mur"] == [
        ("le mur nord", "nord"), ("le mur sud", "sud")]
    assert c.boussole_fiabilite == "bonne" and round(c.correction_cap) == 20
    assert not [d for d in dits if "orienté" in d]  # boussole fiable : aucune question d'orientation
