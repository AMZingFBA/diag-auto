"use strict";
// Liaison avec le serveur (étape 10 de Noah : faux « Hors réseau » alors qu'il avait du réseau).
//
// Avant : toute fermeture de la liaison affichait « Hors réseau » — page mise en arrière-plan ou écran verrouillé (iOS
// suspend la page), serveur redémarré, erreur sur un message — et ce qui était dit pendant ce temps était perdu.
// Maintenant :
// - un battement de cœur toutes les 2 s (« ping », le serveur répond « pong » tout de suite, même quand Claude réfléchit) ;
// - « hors réseau » seulement si le serveur est vraiment injoignable : 3 battements sans réponse (6 s), ou une
//   reconnexion qui échoue depuis 6 s ; une réponse lente (> 1,5 s) donne « réseau lent », sans alerte ;
// - reconnexion automatique et silencieuse (0,5 s, 1 s, puis toutes les 2 s) ;
// - ce qui n'a pas pu partir (son, images, capteurs, phrases écrites) est gardé et envoyé dès le retour, dans l'ordre :
//   le serveur rattrape les phrases dites pendant la coupure ;
// - page cachée (écran verrouillé, autre application) : pas d'alerte ; reconnexion dès qu'elle revient.
// Fichier chargé par la page, et testé avec une fausse horloge par tests/test_liaison_js.py (Node).

(function (racine) {
  const OUVERT = 1;

  function taille(donnees) {
    if (typeof donnees === "string") return donnees.length;
    return donnees.size || donnees.byteLength || 0;
  }

  function Liaison(options) {
    this.o = Object.assign({
      battementMs: 2000, // un battement toutes les 2 s
      echecsMax: 3, // 3 battements sans réponse : le serveur est injoignable
      lentMs: 1500, // réponse plus lente : « réseau lent » (pas une coupure)
      delais: [500, 1000, 2000], // reconnexion : 0,5 s, 1 s, puis toutes les 2 s
      saturationOctets: 2_000_000, // la liaison n'arrive pas à suivre : on garde au lieu d'empiler
      tamponMaxOctets: 12_000_000, // ~2 à 3 min de son et d'images gardés pendant une coupure
      horloge: () => Date.now(),
      planifier: (f, ms) => setTimeout(f, ms),
      annuler: (id) => clearTimeout(id),
      creerSocket: null, // () => WebSocket
      debut: () => ({ type: "debut" }), // message envoyé à chaque ouverture (reçoit les coupures à rapporter)
      surMessage: () => {},
      surEtat: () => {},
    }, options);
    this.ws = null;
    this.etat = "arret";
    this.tampon = [];
    this.octets = 0;
    this.perdus = 0;
    this.n = 0;
    this.attendus = new Map(); // numéro du battement → instant d'envoi
    this.rtt = null;
    this.essais = 0;
    this.coupureDepuis = null;
    this.causeCoupure = "";
    this.coupures = []; // à rapporter au serveur à la prochaine ouverture
    this.cachee = false;
    this.arrete = true;
    this._battement = null;
    this._reconnexion = null;
    this._horsReseau = null;
  }

  Liaison.prototype.demarrer = function () {
    this.arrete = false;
    this._changer("connexion");
    this._ouvrir();
  };

  Liaison.prototype.arreter = function () {
    this.arrete = true;
    this._annulerTout();
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      try { ws.close(); } catch (e) { /* déjà fermée */ }
    }
    this._changer("arret");
  };

  Liaison.prototype.ouverte = function () {
    return !!this.ws && this.ws.readyState === OUVERT;
  };

  // Envoie (texte ou binaire). Sans liaison, ou liaison saturée : gardé pour plus tard si `garder`, sinon abandonné.
  Liaison.prototype.envoyer = function (donnees, garder = true) {
    if (this.ouverte() && !this.tampon.length && this.ws.bufferedAmount <= this.o.saturationOctets) {
      this.ws.send(donnees);
      return true;
    }
    if (!garder) return false;
    this.tampon.push(donnees);
    this.octets += taille(donnees);
    while (this.octets > this.o.tamponMaxOctets && this.tampon.length) {
      this.octets -= taille(this.tampon.shift()); // trop long : on perd le plus ancien
      this.perdus += 1;
    }
    this._vider();
    return false;
  };

  Liaison.prototype.envoyerJson = function (message, garder = true) {
    return this.envoyer(JSON.stringify(message), garder);
  };

  Liaison.prototype.pageCachee = function (cachee) {
    this.cachee = cachee;
    if (!cachee && !this.arrete && !this.ouverte()) this.reconnecterVite();
    if (!cachee && this.etat === "pause") this._changer(this.ouverte() ? "connecte" : "reconnexion");
  };

  // Le réseau revient (événement « online »), ou la page revient : on n'attend pas la prochaine tentative.
  Liaison.prototype.reconnecterVite = function () {
    if (this.arrete || this.ouverte()) return;
    if (this._reconnexion) this.o.annuler(this._reconnexion);
    this._reconnexion = null;
    this.essais = 0;
    this._ouvrir();
  };

  Liaison.prototype._changer = function (etat) {
    if (etat === this.etat) return;
    this.etat = etat;
    this.o.surEtat(etat);
  };

  Liaison.prototype._annulerTout = function () {
    for (const cle of ["_battement", "_reconnexion", "_horsReseau"]) {
      if (this[cle]) this.o.annuler(this[cle]);
      this[cle] = null;
    }
  };

  Liaison.prototype._ouvrir = function () {
    let ws;
    try {
      ws = this.o.creerSocket();
    } catch (e) {
      this._coupe("ouverture impossible");
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      if (ws !== this.ws) return;
      this.essais = 0;
      this.attendus.clear();
      if (this._horsReseau) this.o.annuler(this._horsReseau);
      this._horsReseau = null;
      if (this.coupureDepuis !== null) {
        this.coupures.push({ duree_s: Math.round((this.o.horloge() - this.coupureDepuis) / 100) / 10, cause: this.causeCoupure,
                             gardes: this.tampon.length, perdus: this.perdus });
        this.coupureDepuis = null;
      }
      ws.send(JSON.stringify(this.o.debut(this.coupures.splice(0))));
      this._vider(); // ce qui a été dit pendant la coupure : rattrapé, dans l'ordre
      this._changer("connecte");
      this._planifierBattement();
    };
    ws.onmessage = (e) => {
      if (ws !== this.ws) return;
      const m = JSON.parse(e.data);
      if (m.type === "pong") return this._pong(m);
      this.o.surMessage(m);
    };
    ws.onerror = () => {};
    ws.onclose = (e) => {
      if (ws !== this.ws) return;
      if (e && e.code === 4401) {
        this._annulerTout();
        this._changer("refuse"); // code d'accès incorrect : pas de reconnexion
        return;
      }
      this._coupe(this.cachee ? "page cachée" : `liaison fermée (${e ? e.code : "?"})`);
    };
  };

  Liaison.prototype._planifierBattement = function () {
    if (this._battement) this.o.annuler(this._battement);
    this._battement = this.o.planifier(() => this._battre(), this.o.battementMs);
  };

  Liaison.prototype._battre = function () {
    this._battement = null;
    if (this.arrete || !this.ouverte()) return;
    if (this.attendus.size >= this.o.echecsMax) {
      // 3 battements sans réponse : la liaison est morte même si elle paraît ouverte (Wi-Fi perdu, serveur arrêté).
      const ws = this.ws;
      this.ws = null;
      try { ws.close(); } catch (e) { /* déjà fermée */ }
      this._coupe("battements sans réponse", this.o.horloge() - this.o.battementMs * this.o.echecsMax);
      return;
    }
    if (this.attendus.size > 0 && this.etat === "connecte") this._changer("lent"); // une réponse en retard : lent
    this.n += 1;
    this.attendus.set(this.n, this.o.horloge());
    this.ws.send(JSON.stringify({ type: "ping", n: this.n }));
    this._vider();
    this._planifierBattement();
  };

  Liaison.prototype._pong = function (m) {
    const envoi = this.attendus.get(m.n);
    for (const n of [...this.attendus.keys()]) if (n <= m.n) this.attendus.delete(n);
    if (envoi === undefined) return;
    this.rtt = this.o.horloge() - envoi;
    this._changer(this.rtt > this.o.lentMs || this.attendus.size ? "lent" : "connecte");
  };

  Liaison.prototype._coupe = function (cause, depuis) {
    if (this._battement) this.o.annuler(this._battement);
    this._battement = null;
    this.ws = null;
    if (this.arrete) return;
    if (this.coupureDepuis === null) {
      this.coupureDepuis = depuis !== undefined ? depuis : this.o.horloge();
      this.causeCoupure = cause;
    }
    if (this.cachee) {
      this._changer("pause"); // écran verrouillé, autre application : pas d'alerte, on reprendra au retour
    } else if (this.etat === "hors_reseau" || this.o.horloge() - this.coupureDepuis >= this.o.battementMs * this.o.echecsMax) {
      this._changer("hors_reseau"); // déjà 6 s sans réponse (battements perdus) : inutile de passer par « reconnexion »
    } else {
      this._changer("reconnexion");
      this._planifierHorsReseau();
    }
    const delai = this.o.delais[Math.min(this.essais, this.o.delais.length - 1)];
    this.essais += 1;
    if (this._reconnexion) this.o.annuler(this._reconnexion);
    this._reconnexion = this.o.planifier(() => {
      this._reconnexion = null;
      if (!this.arrete && !this.ouverte()) this._ouvrir();
    }, delai);
  };

  Liaison.prototype._planifierHorsReseau = function () {
    if (this._horsReseau || this.etat === "hors_reseau") return;
    // « Hors réseau » seulement si le serveur reste injoignable 6 s (3 battements) depuis le début de la coupure.
    const reste = Math.max(0, this.coupureDepuis + this.o.battementMs * this.o.echecsMax - this.o.horloge());
    this._horsReseau = this.o.planifier(() => {
      this._horsReseau = null;
      if (!this.arrete && !this.ouverte() && !this.cachee) this._changer("hors_reseau");
    }, reste);
  };

  Liaison.prototype._vider = function () {
    while (this.tampon.length && this.ouverte() && this.ws.bufferedAmount <= this.o.saturationOctets) {
      const donnees = this.tampon.shift();
      this.octets -= taille(donnees);
      this.ws.send(donnees);
    }
  };

  const exporte = { Liaison };
  if (typeof module !== "undefined" && module.exports) module.exports = exporte;
  else racine.Liaison = Liaison;
})(typeof window !== "undefined" ? window : this);
