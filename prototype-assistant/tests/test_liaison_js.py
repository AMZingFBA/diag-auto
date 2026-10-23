"""Liaison du téléphone avec le serveur (web/liaison.js), exécutée avec Node et une fausse horloge (étape 10).

Noah voyait « Hors réseau » alors qu'il avait du réseau : toute fermeture de la liaison (écran verrouillé, serveur
redémarré, erreur sur un message) l'affichait. Maintenant : battement de cœur toutes les 2 s, « hors réseau » seulement
après 3 battements sans réponse (ou 6 s de reconnexion impossible), reconnexion silencieuse, rattrapage dans l'ordre.
Chaque cas fait tourner un faux serveur : joignable ou non, réponse aux battements rapide, lente ou absente."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LIAISON_JS = Path(__file__).resolve().parents[1] / "web" / "liaison.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node n'est pas installé")

SIMULATION = """
const { Liaison } = require(%s);
let maintenant = 0, minuteries = [], prochain = 1;
const planifier = (f, ms) => { const id = prochain++; minuteries.push({ id, quand: maintenant + ms, f }); return id; };
const annuler = (id) => { minuteries = minuteries.filter((m) => m.id !== id); };
function avancer(ms) {
  const fin = maintenant + ms;
  for (;;) {
    minuteries.sort((a, b) => a.quand - b.quand || a.id - b.id);
    const m = minuteries[0];
    if (!m || m.quand > fin) break;
    minuteries.shift();
    maintenant = m.quand;
    m.f();
  }
  maintenant = fin;
}
// Faux serveur. joignable : une nouvelle liaison s'ouvre (sinon elle échoue) et les messages arrivent ;
// delaiPong : temps de réponse au battement (réseau lent) ; repond : le serveur répond aux battements.
const serveur = { joignable: true, delaiPong: 50, repond: true, recus: [], liaisons: [] };
class FausseLiaison {
  constructor() {
    this.readyState = 0;
    this.bufferedAmount = 0;
    serveur.liaisons.push(this);
    planifier(() => {
      if (serveur.joignable) { this.readyState = 1; this.onopen(); }
      else { this.readyState = 3; this.onclose({ code: 1006 }); }
    }, 100);
  }
  send(d) {
    if (this.readyState !== 1) throw new Error("liaison fermée");
    if (!serveur.joignable) return; // réseau perdu sans fermeture : rien n'arrive
    serveur.recus.push(typeof d === "string" ? d : `binaire:${d.nom}`);
    const m = typeof d === "string" ? JSON.parse(d) : null;
    if (m && m.type === "ping" && serveur.repond) {
      planifier(() => { if (this.readyState === 1 && serveur.joignable) this.onmessage({ data: JSON.stringify({ type: "pong", n: m.n }) }); },
                serveur.delaiPong);
    }
  }
  close() { if (this.readyState !== 3) { this.readyState = 3; planifier(() => this.onclose({ code: 1000 }), 0); } }
  couper(code = 1006) { this.readyState = 3; this.onclose({ code }); }
  recevoir(m) { this.onmessage({ data: JSON.stringify(m) }); }
}
const etats = [], messages = [];
const liaison = new Liaison({
  horloge: () => maintenant, planifier, annuler, creerSocket: () => new FausseLiaison(),
  debut: (coupures) => ({ type: "debut", coupures }), surMessage: (m) => messages.push(m),
  surEtat: (e) => etats.push([maintenant, e]),
});
const derniere = () => serveur.liaisons[serveur.liaisons.length - 1];
const son = (nom) => ({ nom, size: 3200 });
const premier = (e) => { const x = etats.find(([, f]) => f === e); return x ? x[0] : null; };
"""


def node(scenario: str):
    """Exécute la simulation puis le scénario, qui affiche un JSON."""
    code = SIMULATION % json.dumps(str(LIAISON_JS)) + scenario
    sortie = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=30)
    assert sortie.returncode == 0, sortie.stderr
    return json.loads(sortie.stdout)


def test_reseau_lent_n_est_pas_hors_reseau():
    r = node("""
liaison.demarrer(); avancer(1000);
serveur.delaiPong = 2500; avancer(30000);   // 30 s de réponses en 2,5 s
const pendant = etats.map(([, e]) => e);
serveur.delaiPong = 50; avancer(6000);
console.log(JSON.stringify({ pendant, fin: liaison.etat, liaisons: serveur.liaisons.length }));
""")
    assert "lent" in r["pendant"] and "hors_reseau" not in r["pendant"] and "reconnexion" not in r["pendant"]
    assert r["fin"] == "connecte" and r["liaisons"] == 1  # jamais coupée


def test_claude_lent_n_est_pas_une_coupure():
    # Claude réfléchit 20 s sans que le serveur n'envoie rien d'autre : les battements, eux, répondent.
    r = node("""
liaison.demarrer(); avancer(20000);
console.log(JSON.stringify({ etats: etats.map(([, e]) => e), messages: messages.length }));
""")
    assert r["etats"] == ["connexion", "connecte"] and r["messages"] == 0


def test_vraie_coupure_puis_retour_et_rattrapage():
    r = node("""
liaison.demarrer(); avancer(1000);
liaison.envoyer(son("avant"));
serveur.joignable = false; derniere().couper();          // le réseau tombe à t = 1 s
const debut = maintenant;
for (let i = 1; i <= 8; i++) { liaison.envoyer(son("coupure" + i)); avancer(1000); }   // 8 s de son pendant la coupure
const etatA5s = etats.filter(([t]) => t <= debut + 5000).map(([, e]) => e);
const horsReseau = premier("hors_reseau") - debut;
serveur.joignable = true; avancer(3000);                 // retour du réseau
liaison.envoyer(son("apres"));
const binaires = serveur.recus.filter((d) => d.startsWith("binaire:"));
const ouverture = JSON.parse(serveur.recus.filter((d) => d.includes('"debut"')).pop());
console.log(JSON.stringify({ etatA5s, horsReseau, fin: liaison.etat, binaires, coupures: ouverture.coupures }));
""")
    assert "hors_reseau" not in r["etatA5s"] and "reconnexion" in r["etatA5s"]
    assert 6000 <= r["horsReseau"] <= 6600  # 3 battements de 2 s, pas avant
    assert r["fin"] == "connecte"
    # Rattrapage : tout le son dit pendant la coupure arrive, dans l'ordre, avant le son suivant.
    assert r["binaires"] == ["binaire:avant"] + [f"binaire:coupure{i}" for i in range(1, 9)] + ["binaire:apres"]
    assert len(r["coupures"]) == 1 and r["coupures"][0]["duree_s"] >= 8 and r["coupures"][0]["gardes"] == 8


def test_coupure_breve_reparee_en_silence():
    # Serveur redémarré, écran rallumé… : la liaison se ferme mais se rouvre aussitôt.
    r = node("""
liaison.demarrer(); avancer(1000);
derniere().couper(1012); avancer(5000);
console.log(JSON.stringify({ etats: etats.map(([, e]) => e), liaisons: serveur.liaisons.length,
                            coupures: JSON.parse(serveur.recus.filter((d) => d.includes('"debut"')).pop()).coupures }));
""")
    assert r["etats"] == ["connexion", "connecte", "reconnexion", "connecte"]  # jamais « hors réseau »
    assert r["liaisons"] == 2 and r["coupures"][0]["cause"] == "liaison fermée (1012)" and r["coupures"][0]["duree_s"] < 1


def test_liaison_morte_detectee_par_les_battements():
    # Wi-Fi perdu sans que la liaison ne se ferme : plus aucun battement ne répond.
    r = node("""
liaison.demarrer(); avancer(1000);
serveur.joignable = false; const debut = maintenant;
avancer(12000);
console.log(JSON.stringify({ horsReseau: premier("hors_reseau") - debut, lent: premier("lent") - debut, liaisons: serveur.liaisons.length }));
""")
    assert r["lent"] < r["horsReseau"]  # d'abord « lent » (un battement en retard)
    assert 5000 <= r["horsReseau"] <= 8000  # puis « hors réseau » après 3 battements sans réponse
    assert r["liaisons"] >= 3  # et la reconnexion est retentée


def test_page_cachee_pas_d_alerte_puis_reprise():
    r = node("""
liaison.demarrer(); avancer(1000);
liaison.pageCachee(true); serveur.joignable = false; derniere().couper(1001);   // écran verrouillé : iOS coupe
avancer(60000);
const pendant = etats.map(([, e]) => e);
serveur.joignable = true; liaison.pageCachee(false); avancer(300);
console.log(JSON.stringify({ pendant, fin: liaison.etat }));
""")
    assert "hors_reseau" not in r["pendant"] and r["pendant"][-1] == "pause"
    assert r["fin"] == "connecte"  # reconnecté dès le retour de la page


def test_tampon_borne_et_messages_de_voix_abandonnes():
    r = node("""
liaison.o.tamponMaxOctets = 10000;
liaison.demarrer(); avancer(1000);
serveur.joignable = false; derniere().couper();
for (let i = 1; i <= 5; i++) liaison.envoyer(son("s" + i));            // 5 × 3200 octets : les 2 plus anciens sont perdus
liaison.envoyerJson({ type: "tts", etat: "fin" }, false);               // l'état de la voix n'a plus de sens après
serveur.joignable = true; avancer(3000);
console.log(JSON.stringify({ recus: serveur.recus.filter((d) => !d.includes('"ping"')), perdus: liaison.perdus }));
""")
    assert [d for d in r["recus"] if d.startswith("binaire:")] == ["binaire:s3", "binaire:s4", "binaire:s5"]
    assert not [d for d in r["recus"] if '"tts"' in d] and r["perdus"] == 2


def test_code_incorrect_pas_de_reconnexion():
    r = node("""
liaison.demarrer(); avancer(1000);
derniere().couper(4401); avancer(10000);
console.log(JSON.stringify({ fin: liaison.etat, liaisons: serveur.liaisons.length }));
""")
    assert r == {"fin": "refuse", "liaisons": 1}



def test_images_apres_le_son():
    # Étape 15 : la rafale d'images d'un tour de pièce attend que la liaison se vide ; le son, lui, part tout de suite.
    r = node("""
liaison.demarrer(); avancer(1000);
derniere().bufferedAmount = 500000;                      // liaison chargée (4G faible)
for (let i = 1; i <= 3; i++) liaison.envoyerImage({ nom: "image" + i, size: 30000 });
liaison.envoyer(son("son1"));
const pendant = serveur.recus.filter((d) => d.startsWith("binaire:"));
derniere().bufferedAmount = 0;                           // la liaison se vide
liaison.envoyer(son("son2"));
console.log(JSON.stringify({ pendant, apres: serveur.recus.filter((d) => d.startsWith("binaire:")) }));
""")
    assert r["pendant"] == ["binaire:son1"]  # le son passe devant les images
    assert r["apres"] == ["binaire:son1", "binaire:son2", "binaire:image1", "binaire:image2", "binaire:image3"]


def test_images_en_attente_bornees_et_rattrapees_apres_le_son():
    r = node("""
liaison.o.imagesMaxOctets = 70000;
liaison.demarrer(); avancer(1000);
serveur.joignable = false; derniere().couper();
for (let i = 1; i <= 4; i++) liaison.envoyerImage({ nom: "image" + i, size: 30000 });   // la 1re et la 2e sont perdues
liaison.envoyerImage({ nom: "image-minuterie", size: 30000 }, false);                    // pas gardée pendant la coupure
liaison.envoyer(son("coupure"));
serveur.joignable = true; avancer(3000);
const coupures = JSON.parse(serveur.recus.filter((d) => d.includes('"debut"')).pop()).coupures;
console.log(JSON.stringify({ recus: serveur.recus.filter((d) => d.startsWith("binaire:")), perdues: liaison.imagesPerdues, coupures }));
""")
    assert r["recus"] == ["binaire:coupure", "binaire:image3", "binaire:image4"]  # le son d'abord, puis les images gardées
    assert r["perdues"] == 2 and r["coupures"][0]["images_gardees"] == 2
