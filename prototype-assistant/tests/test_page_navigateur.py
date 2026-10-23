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
        x, y = self.js(f"(() => {{ const r = document.querySelector({json.dumps(selecteur)}).getBoundingClientRect();"
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
