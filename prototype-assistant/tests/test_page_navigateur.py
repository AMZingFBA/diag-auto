"""La vraie page du téléphone, dans un vrai navigateur (Edge, sans fenêtre), touchée au doigt (écran tactile simulé).

Plusieurs retours de Noah du 23/10 venaient de la page, que les autres tests ne voyaient pas (« Autre… » sans clavier, « OK »
qui ne fait rien). Ici, la page est servie par le serveur, une question arrive avec ses boutons, et l'on vérifie ce qui
part vers le serveur quand on touche un bouton, puis « Autre… », un nombre et « OK ».

Sauté si Edge n'est pas installé. Ce n'est pas Safari : un défaut propre à l'iPhone peut encore passer (le « OK » du
23/10 venait de ce que Safari ne donne pas la main à un bouton touché : la page ne compte plus sur ce comportement).
"""

import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest

EDGE = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                         r"C:\Program Files\Microsoft\Edge\Application\msedge.exe") if Path(p).is_file()), None)
pytestmark = pytest.mark.skipif(EDGE is None, reason="Edge absent")


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Navigateur:
    """Edge sans fenêtre, piloté par son protocole de débogage (CDP)."""

    def __init__(self, dossier: Path):
        from websockets.sync.client import connect

        self.port = port_libre()
        self.processus = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={self.port}", f"--user-data-dir={dossier}",
                                           "--no-first-run", "--no-default-browser-check", "about:blank"],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                cibles = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json").read())
                page = next(c for c in cibles if c["type"] == "page")
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Edge ne répond pas")
        self.ws = connect(page["webSocketDebuggerUrl"], max_size=None)
        self.n = 0

    def appel(self, methode: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": methode, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def js(self, expression: str):
        resultat = self.appel("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in resultat:
            raise RuntimeError(resultat["exceptionDetails"])
        return resultat["result"].get("value")

    def toucher(self, selecteur: str) -> None:
        """Un doigt sur le centre de l'élément."""
        x, y = self.js(f"(() => {{ const e = document.querySelector({json.dumps(selecteur)}); e.scrollIntoView({{block: 'center'}});"
                       " const r = e.getBoundingClientRect();"
                       " return [r.x + r.width / 2, r.y + r.height / 2]; })()")
        point = [{"x": x, "y": y}]
        self.appel("Input.dispatchTouchEvent", type="touchStart", touchPoints=point)
        self.appel("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        time.sleep(0.15)

    def fermer(self) -> None:
        self.ws.close()
        self.processus.kill()


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    import uvicorn

    from assistant.serveur import creer_app
    from test_serveur import reglages

    dossier = tmp_path_factory.mktemp("page")
    port = port_libre()
    serveur = uvicorn.Server(uvicorn.Config(creer_app(reglages(dossier)), host="127.0.0.1", port=port, log_level="error"))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    while not serveur.started:
        time.sleep(0.05)
    navigateur = Navigateur(dossier / "edge")
    navigateur.appel("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=3, mobile=True)
    navigateur.appel("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
    navigateur.appel("Page.enable")
    navigateur.appel("Page.navigate", url=f"http://127.0.0.1:{port}/")
    for _ in range(100):
        if navigateur.js("document.readyState === 'complete' && typeof afficherChoix === 'function'"):
            break
        time.sleep(0.1)
    # L'écran de la visite, sans caméra ni serveur : ce qui part vers le serveur est gardé pour être vérifié.
    navigateur.js("""(() => {
        $("accueil").hidden = true; $("visite").hidden = false;
        window.envoyes = []; envoyerJson = (m) => window.envoyes.push(m);
        return true; })()""")
    yield navigateur
    navigateur.fermer()
    serveur.should_exit = True
    shutil.rmtree(dossier / "edge", ignore_errors=True)


@pytest.fixture(autouse=True)
def page_propre(page):
    """Chaque test part du même état : mission DPE, écran de visite, plan et fiche fermés, croquis vide (page partagée)."""
    page.js("(() => { etat.demarrage = false; choisirMission('dpe'); $('plan').hidden = true; $('fiche').hidden = true;"
            " $('accueil').hidden = true; $('visite').hidden = false; etat.croquis = null; afficherCroquis(null); alerte('');"
            " window.envoyes = []; return true; })()")
    yield


def question(page, cible: str, options: list[dict]) -> None:
    page.js(f"(() => {{ window.envoyes = []; afficherChoix({json.dumps(cible)}, {json.dumps(options)}); return true; }})()")


EPAISSEUR = [{"libelle": "15 cm", "valeur": "15 cm"}, {"libelle": "20 cm", "valeur": "20 cm"},
             {"libelle": "Je ne sais pas", "valeur": "inconnu"},
             {"libelle": "Autre…", "valeur": "", "saisie": "nombre", "unite": "cm", "min": 3, "max": 150}]


def test_bouton_touche_envoie_la_reponse(page):
    question(page, "M1.epaisseur", EPAISSEUR)
    page.toucher("#choix button")
    assert page.js("window.envoyes") == [{"type": "reponse", "cible": "M1.epaisseur", "valeur": "15 cm", "libelle": "15 cm",
                                          "t": page.js("window.envoyes[0].t")}]


def test_autre_puis_nombre_puis_ok_envoie_la_valeur(page):
    question(page, "M1.epaisseur", EPAISSEUR)
    assert page.js("getComputedStyle(document.querySelector('#choix form.autre button')).display") == "none"  # un bouton parmi d'autres
    page.toucher("#choix form.autre input")
    assert page.js("document.activeElement === document.querySelector('#choix form.autre input')")  # le clavier s'ouvre
    page.appel("Input.insertText", text="23")
    page.toucher("#choix form.autre button")  # « OK »
    envoyes = page.js("window.envoyes")
    assert [(m["cible"], m["valeur"], m["saisie"]) for m in envoyes] == [("M1.epaisseur", "23", "nombre")]
    assert page.js("document.querySelector('#choix form.autre').classList.contains('ouverte')") is False


def test_ok_sans_nombre_ne_part_pas(page):
    question(page, "M1.epaisseur", EPAISSEUR)
    page.toucher("#choix form.autre input")
    page.appel("Input.insertText", text="abc")
    page.toucher("#choix form.autre button")
    assert page.js("window.envoyes") == [] and "nombre" in page.js("$('latence').textContent")


def test_ok_encore_la_quand_la_case_perd_la_main_comme_sur_iphone(page):
    # Safari ne donne pas la main au bouton touché : la case la perd d'abord. Avant, « OK » disparaissait alors.
    question(page, "M1.epaisseur", EPAISSEUR)
    page.toucher("#choix form.autre input")
    page.appel("Input.insertText", text="22,5")
    page.js("document.activeElement.blur()")
    assert page.js("getComputedStyle(document.querySelector('#choix form.autre button')).display") != "none"
    page.toucher("#choix form.autre button")
    assert [m["valeur"] for m in page.js("window.envoyes")] == ["22,5"]


def test_bouton_vu_sur_l_image_s_allume_et_se_confirme_d_un_appui(page):
    # L'image propose la réponse (assistant/regard.py) : le bouton s'allume ; c'est l'appui qui répond.
    question(page, "F1.menuiserie", [{"libelle": "PVC", "valeur": "PVC"}, {"libelle": "Bois", "valeur": "bois"}])
    page.js("recevoir({type: 'proposition', cible: 'F1.menuiserie', valeur: 'PVC', libelle: 'PVC', raison: 'cadre blanc'})")
    assert page.js("[...document.querySelectorAll('#choix button.vu')].map((b) => b.textContent)") == ["📷 PVC"]
    assert "Sur l'image : PVC" in page.js("$('latence').textContent") and page.js("window.envoyes") == []  # rien d'envoyé
    page.js("recevoir({type: 'proposition', cible: 'F9.vitrage', valeur: 'bois', libelle: 'Bois', raison: ''})")  # autre question
    assert page.js("document.querySelectorAll('#choix button.vu').length") == 1
    page.toucher("#choix button.vu")
    assert [(m["cible"], m["valeur"]) for m in page.js("window.envoyes")] == [("F1.menuiserie", "PVC")]


def test_croquis_dessine_dans_le_coin_puis_agrandi_et_renomme(page):
    croquis = {"oriente": True, "courante": "cuisine", "portes": [{"a": "sejour", "b": "cuisine", "cote": "est"}],
               "pieces": [{"cle": "sejour", "nom": "Séjour", "source": "dit", "x": 0, "y": 0,
                           "murs": {"sud": "A", "ouest": "B", "nord": "C", "est": "D"}},
                          {"cle": "cuisine", "nom": "Cuisine", "source": "image", "x": 1, "y": 0,
                           "murs": {"ouest": "A", "nord": "B", "est": "C", "sud": "D"}}],
               "ouvertures": [{"piece": "cuisine", "cote": "est", "type": "fenetre", "nombre": 1}]}
    page.js("choisirMission('amiante')")  # le croquis : amiante et plomb seulement
    page.js(f"(() => {{ window.envoyes = []; afficherCroquis({json.dumps(croquis)}); return true; }})()")
    assert page.js("$('croquis').hidden") is False
    assert page.js("$('croquis-petit').querySelectorAll('rect').length") == 2  # une case par pièce
    page.toucher("#croquis")
    assert page.js("$('plan').hidden") is False
    assert "A" in page.js("[...$('croquis-grand').querySelectorAll('text')].map((t) => t.textContent)")  # murs repérés
    page.js("(() => { const s = $('plan-pieces').querySelectorAll('.bloc-piece')[1].querySelector('select'); s.value = 'Buanderie'; s.onchange(); return true; })()")
    assert page.js("window.envoyes") == [{"type": "renommer_piece", "cle": "cuisine", "nom": "Buanderie"}]
    page.js("(() => { window.envoyes = []; const s = $('plan-pieces').querySelectorAll('.bloc-piece')[1].querySelectorAll('select')[1];"
            " s.value = 'sejour'; s.onchange(); return true; })()")
    page.toucher("#plan-pieces .bloc-piece:nth-child(2) .fleche:nth-of-type(4)")  # « → » : vers l'est
    assert page.js("window.envoyes") == [{"type": "fusionner_pieces", "cle": "cuisine", "dans": "sejour"},
                                         {"type": "deplacer_piece", "cle": "cuisine", "vers": "est"}]
    page.js("$('fermer-plan').onclick()")



def test_mission_choisie_avant_de_demarrer(page):
    # Noah, 23/10 : « choisir avant le bouton ce que je veux faire : DPE → la vidéo du DPE ; amiante → le croquis ».
    page.js("(() => { $('visite').hidden = true; $('accueil').hidden = false; etat.mission = null;"
            " document.querySelectorAll('#missions button').forEach((b) => b.classList.remove('choisi'));"
            " $('demarrer').disabled = true; return true; })()")
    page.toucher("#missions button[data-mission='amiante']")
    assert page.js("$('demarrer').disabled") is False and page.js("$('demarrer').textContent") == "Démarrer l'amiante (croquis)"
    assert page.js("messageDebut([]).mission") == "amiante" and page.js("document.body.dataset.mission") == "amiante"
    assert "faites-en le tour" in page.js("$('aide-mission').textContent")
    page.toucher("#missions button[data-mission='dpe']")
    assert page.js("[...document.querySelectorAll('#missions button.choisi')].map((b) => b.dataset.mission)") == ["dpe"]
    assert page.js("messageDebut([]).mission") == "dpe" and page.js("$('demarrer').textContent") == "Démarrer le DPE"
    page.js("(() => { $('accueil').hidden = true; $('visite').hidden = false; etat.croquis = null; afficherCroquis(null); return true; })()")
    assert page.js("$('croquis').hidden") is True and page.js("$('voir-fiche').textContent") == "📋 Fiche"  # DPE : pas de croquis


def test_amiante_croquis_en_grand_et_bouton_plan(page):
    page.js("(() => { choisirMission('plomb'); etat.croquis = null; afficherCroquis(null); return true; })()")
    assert page.js("$('croquis').hidden") is False and page.js("$('croquis-aide').hidden") is False  # vide : ce qu'il faut faire
    assert page.js("$('croquis').getBoundingClientRect().width") > 200  # en grand, pas dans le coin
    assert page.js("$('manques-bloc').hidden") is True and page.js("$('voir-fiche').textContent") == "🗺️ Plan"
    page.js("majEtat({taux: 0, piece: 'Séjour', manques: [], nb_manques_visite: 0, checklist: {pieces: [{nom: 'Séjour'}]}})")
    assert page.js("$('piece-courante').textContent") == "Plomb (CREP) · 1 pièce · Séjour"
    page.toucher("#voir-fiche")
    assert page.js("$('plan').hidden") is False and page.js("$('fiche').hidden") is True
    page.js("(() => { $('fermer-plan').onclick(); choisirMission('dpe'); return true; })()")


def test_images_cles_pendant_un_tour(page):
    # Étape 15 : pendant une rotation, une image part à chaque demi-champ tourné (22,5° en portrait), pas plus de 8 par
    # seconde ; trop vite (> 200°/s), on attend un peu une image moins floue.
    r = page.js("""(() => {
        const vrai = { capturer: capturerImage, champ: champHorizontal, liaison: etat.liaison };
        const prises = [];
        capturerImage = (raison) => { prises.push([raison, mouvement.deroule]);
                                      mouvement.derniereImage = { deroule: mouvement.deroule, elevation: 0, quand: performance.now() - 1000 }; };
        champHorizontal = () => 45;
        etat.liaison = {};
        mouvement.derniereImage = { deroule: 0, elevation: 0, quand: performance.now() - 1000 };
        mouvement.vitesse = 100;
        for (const d of [10, 20, 23, 30, 46]) { mouvement.deroule = d; examinerTrame(null); }
        mouvement.vitesse = 300;  // tour trop rapide : image floue
        for (const d of [70, 80]) { mouvement.deroule = d; examinerTrame(null); }
        capturerImage = vrai.capturer; champHorizontal = vrai.champ; etat.liaison = vrai.liaison;
        mouvement.derniereImage = null; mouvement.deroule = null; mouvement.vitesse = 0;
        return prises; })()""")
    assert r == [["rotation", 23], ["rotation", 46], ["rotation", 80]]  # 70 : trop vite (24°) ; 80 : 34° ≥ 1,5 × 22,5°


def test_pose_d_une_image_a_l_instant_de_sa_prise(page):
    r = page.js("""(() => {
        mouvement.anneau = [{ quand: 1000, deroule: 350, cap: 350, lacet: 10, elevation: -10, roulis: 0 },
                            { quand: 1100, deroule: 370, cap: 10, lacet: 30, elevation: -20, roulis: 2 }];
        const p = poseA(1050);
        mouvement.anneau = [];
        return p; })()""")
    assert r["deroule"] == 360 and r["elevation"] == -15
    assert round(r["cap"]) % 360 == 0 and round(r["lacet"]) == 20  # 350 + 10 (rotation depuis la mesure) : le nord



def test_serveur_pas_relance_signale(page):
    # Premier essai de Noah du 23/10 : la page était nouvelle, le serveur ancien (il ignorait la mission).
    page.js("(() => { choisirMission('amiante'); recevoir({type: 'statut', session: 'x', options: {}, cerveau: '', transcription: ''}); return true; })()")
    assert "relancer" in page.js("$('alerte').textContent") and page.js("$('alerte').hidden") is False
    page.js("recevoir({type: 'statut', session: 'x', mission: 'amiante', options: {}, cerveau: '', transcription: ''})")
    assert page.js("$('alerte').hidden") is True


def test_plan_vide_dit_quoi_faire_et_annonce_garde_l_indication(page):
    page.js("(() => { choisirMission('amiante'); etat.croquis = null; afficherCroquis(null); return true; })()")
    page.toucher("#voir-fiche")  # « 🗺️ Plan » avant la première pièce
    assert "faites-en le tour" in page.js("$('plan-pieces').textContent")
    page.js("(() => { $('fermer-plan').onclick(); recevoir({type: 'piece_reconnue', nom: 'Cuisine', nouvelle: true});"
            " recevoir({type: 'dire', id: 1, texte: 'Nouvelle pièce : Cuisine.', muet: true, latence_s: null}); return true; })()")
    assert "Touchez le croquis pour corriger" in page.js("$('latence').textContent")


def test_mission_figee_pendant_l_ouverture_de_la_camera(page):
    page.js("(() => { choisirMission('dpe'); etat.demarrage = true; choisirMission('amiante'); return true; })()")
    assert page.js("etat.mission") == "dpe"  # la caméra s'ouvre : la mission ne change plus


def test_grand_croquis_au_dessus_du_bas(page):
    croquis = {"oriente": False, "courante": "a", "portes": [], "ouvertures": [],
               "pieces": [{"cle": "a", "nom": "Séjour", "source": "image", "x": 0, "y": 0, "murs": {"sud": "A", "ouest": "B", "nord": "C", "est": "D"}}]}
    page.js(f"(() => {{ choisirMission('plomb'); $('question').hidden = false; $('question').textContent = 'Je dessine le croquis : entrez dans chaque pièce et faites-en le tour.';"
            f" afficherCroquis({json.dumps(croquis)}); return true; }})()")
    time.sleep(0.3)  # ResizeObserver
    assert page.js("$('croquis').getBoundingClientRect().bottom <= document.querySelector('.bas').getBoundingClientRect().top + 1")


def test_plan_dans_un_repere_commun(page):
    # Noah, 23/10 : les pièces placées là où l'on a marché (plus en ligne droite), la porte au passage, le trajet, et
    # « vous êtes ici » avec une flèche qui suit la caméra.
    croquis = {"oriente": True, "courante": "sejour", "portes": [], "ouvertures": [],
               "pieces": [{"cle": "entree", "nom": "Entrée", "source": "image", "x": 0, "y": 0, "murs": {}},
                          {"cle": "sejour", "nom": "Séjour", "source": "image", "x": 1, "y": 0, "murs": {}}],
               "plan": {"oriente": True, "courante": "sejour", "position": [0.0, 4.0],
                        "pieces": [{"cle": "entree", "nom": "Entrée", "source": "image", "polygone": [[-1.2, -1.2], [1.2, -1.2], [1.2, 1.5], [-1.2, 1.5]],
                                    "lettres": ["A", "D", "C", "B"]},
                                   {"cle": "sejour", "nom": "Séjour", "source": "image", "polygone": [[-2, 1.5], [2, 1.5], [2, 5.5], [-2, 5.5]],
                                    "lettres": ["A", "D", "C", "B"]}],
                        "portes": [{"a": "entree", "b": "sejour", "x": 0.0, "y": 1.5}],
                        "trajet": [[0, 0], [0, 1], [0, 2], [0, 3], [0, 4]]}}
    page.js(f"(() => {{ choisirMission('amiante'); capteurs.cap = 90; afficherCroquis({json.dumps(croquis)}); return true; }})()")
    assert page.js("$('croquis-petit').querySelectorAll('polygon').length") == 3  # 2 pièces + la flèche
    assert page.js("$('croquis-petit').querySelectorAll('polyline').length") == 1  # le trajet
    assert "rotate(90)" in page.js("$('croquis-petit').querySelector('.vous-ici').getAttribute('transform')")
    # Le séjour (au nord de l'entrée) est dessiné au-dessus d'elle : y plus petit à l'écran.
    ys = page.js("[...$('croquis-petit').querySelectorAll('polygon')].slice(0, 2).map((p) => p.getBBox().y)")
    assert ys[1] < ys[0]
    page.toucher("#croquis")
    assert "A" in page.js("[...$('croquis-grand').querySelectorAll('text')].map((t) => t.textContent)")
    assert page.js("$('plan-pieces').querySelectorAll('.fleche').length") == 0  # pas de flèches de case sur le plan
    page.js("(() => { $('fermer-plan').onclick(); capteurs.cap = null; return true; })()")
