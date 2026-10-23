"""L'image propose la réponse (assistant/regard.py ; retour de Noah du 23/10 : « rends la vidéo plus utile »).

Quand la question porte sur quelque chose qui se voit, Claude regarde les dernières images ; s'il voit clairement la
réponse, le bouton s'allume sur le téléphone. Rien n'est jamais noté sur la seule image.
"""

import asyncio

from assistant.checklist import Checklist
from assistant.extraction import Cible
from assistant.regard import Proposition, analyser, contenu, visible
from assistant.reponses import options_pour
from test_conversation import CerveauScenario, poli
from test_fluidite import ouvrir


class RegardFactice:
    """Voit du PVC sur toute fenêtre ; rien ailleurs."""

    def __init__(self):
        self.vu: list[tuple[str, int]] = []

    async def demarrer(self):
        pass

    async def fermer(self):
        pass

    async def proposer(self, question, options, images):
        self.vu.append((question, len(images)))
        if any(o["valeur"] == "PVC" for o in options):
            return Proposition("PVC", "PVC", "cadre blanc en plastique")
        return None


def test_questions_dont_la_reponse_se_voit():
    c = Checklist()
    mur = c.signaler_element("mur", "le mur 1", 1)
    fenetre = c.signaler_element("fenetre", "la fenêtre", 2, support=mur.id)
    assert visible(Cible("champ", "fenetre", "menuiserie", fenetre.id)) and visible(Cible.depuis_code("presence:emetteur", c))
    assert not visible(Cible("champ", "mur", "donne_sur", mur.id))  # ce qu'il y a derrière un mur ne se voit pas
    assert not visible(Cible("champ", "mur", "isolation", mur.id)) and not visible(Cible.depuis_code("cote:sud", c))


def test_reponse_de_claude_jamais_inventee():
    c = Checklist()
    fenetre = c.signaler_element("fenetre", "la fenêtre", 2)
    options = options_pour(Cible("champ", "fenetre", "menuiserie", fenetre.id))
    assert analyser('{"valeur": "PVC", "raison": "cadre blanc"}', options) == Proposition("PVC", "PVC", "cadre blanc")
    assert analyser('{"valeur": "", "raison": "fenêtre hors champ"}', options) is None
    assert analyser('{"valeur": "aluminium anodisé"}', options) is None  # pas une des réponses proposées
    assert analyser('{"valeur": "inconnu"}', options) is None and analyser("pas de JSON", options) is None
    blocs = contenu("Cette fenêtre : PVC, bois ou alu ?", options, [])
    assert "« PVC »" in blocs[0]["text"] and "inconnu" not in blocs[0]["text"]


def test_bouton_vu_sur_l_image_propose_jamais_note(tmp_path):
    regard = RegardFactice()

    async def scenario():
        session, recus = await ouvrir(tmp_path, CerveauScenario(poli()))
        session.regard = regard
        await session.recevoir_image(1.0, b"\xff\xd8image")
        session.t_video = 1.5
        await session.ouvrir_visite()
        for cible, valeur in (("presence:mur", "extérieur"), ("M1.materiau", "brique"), ("M1.epaisseur", "20 cm"),
                              ("M1.isolation", "non isolé"), ("fenetres:M1", "oui")):
            await session.recevoir_controle({"type": "reponse", "cible": cible, "valeur": valeur, "libelle": valeur})
        while session.occupe:
            await asyncio.sleep(0.01)
        await session.terminer()
        return session, recus

    session, recus = asyncio.run(scenario())
    propositions = [m for m in recus if m["type"] == "proposition"]
    assert [(m["cible"], m["valeur"], m["raison"]) for m in propositions] == [("F1.menuiserie", "PVC", "cadre blanc en plastique")]
    assert session.checklist.trouver_element("F1").valeur("menuiserie") is None  # proposé, pas noté
    # Regardé seulement pour ce qui se voit : le matériau du mur et la menuiserie, pas « donne sur », l'épaisseur ni l'isolation.
    assert [q for q, _ in regard.vu] == ["Ce mur est en quoi ?", "Cette fenêtre : PVC, bois ou alu ?"]
