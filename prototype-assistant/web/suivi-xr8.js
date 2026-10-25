"use strict";
// Suivi de position par le moteur de 8th Wall (Noah, 25/10 : choix 1, « le croquis se dessine mal par rapport à mes
// déplacements »). Safari sur iPhone n'a pas de réalité augmentée ; le moteur de 8th Wall (SLAM : position et orientation
// du téléphone en 3D, échelle en mètres) tourne dans la page. Binaire fermé de Niantic Spatial, sous sa licence
// (web/vendor/8thwall/LICENSE) : gratuit, usage commercial admis tant que la valeur du service ne vient pas « entièrement
// ou essentiellement » de lui (hypothèse : le croquis n'est qu'une partie de DiagAuto ; à confirmer par un juriste avant
// tout usage commercial) ; ni modification ni décompilation ; attribution visible.
//
// Repères. Le moteur : x à droite, y en haut, z vers l'arrière (la caméra regarde -z) ; le sol est y = 0 et la caméra part
// à 1,40 m au-dessus (échelle « responsive » : les unités sont des mètres si le téléphone est bien tenu à 1,40 m). Essai
// du 25/10 (17:25) avec l'échelle « absolute » : elle ne s'était jamais réglée, un aller-retour de 2 à 3 m comptait 15 cm.
// L'application : x vers la direction 90°, y vers la direction 0° du gyroscope (le lacet), à l'horizontale ; les deux
// sont reliés par le cap de la caméra (le décalage entre le cap vu par le moteur et le lacet). Le sol est le plan
// horizontal y = sol du moteur (estimé par ses surfaces).
// Calculs testés par tests/test_suivi_xr8_js.py (Node) ; le moteur lui-même ne s'essaie que sur le téléphone.

(function (racine) {
  const RAD = Math.PI / 180;
  const PRES = 0.05;
  const HAUTEUR_M = 1.4;

  // Rotation du vecteur v par le quaternion q ({x, y, z, w}).
  function tournerQ(q, v) {
    const tx = 2 * (q.y * v[2] - q.z * v[1]), ty = 2 * (q.z * v[0] - q.x * v[2]), tz = 2 * (q.x * v[1] - q.y * v[0]);
    return [v[0] + q.w * tx + (q.y * tz - q.z * ty), v[1] + q.w * ty + (q.z * tx - q.x * tz), v[2] + q.w * tz + (q.x * ty - q.y * tx)];
  }

  const conjugue = (q) => ({ x: -q.x, y: -q.y, z: -q.z, w: q.w });

  // Direction de la caméra dans le repère du moteur.
  function avant(pose) {
    return tournerQ(pose.rotation, [0, 0, -1]);
  }

  // Cap (degrés, 0 = -z du moteur, 90 = +x) d'une direction horizontale du moteur.
  function cap(d) {
    return ((Math.atan2(d[0], -d[2]) / RAD) % 360 + 360) % 360;
  }

  // Repère du moteur → repère de l'application (le décalage : lacet − cap du moteur, mesuré au même instant).
  function versApp(p, decalage) {
    const a = decalage * RAD, x = p[0], y = -p[2];
    return [x * Math.cos(a) + y * Math.sin(a), -x * Math.sin(a) + y * Math.cos(a)];
  }

  function versMoteur(P, decalage, sol) {
    const a = -decalage * RAD;
    const x = P[0] * Math.cos(a) + P[1] * Math.sin(a), y = -P[0] * Math.sin(a) + P[1] * Math.cos(a);
    return [x, sol, -y];
  }

  // Le point du sol (repère du moteur) que vise le centre de l'image ; null si la caméra ne regarde pas assez bas.
  function viseAuSol(pose, sol, portee = 15) {
    const c = [pose.position.x, pose.position.y, pose.position.z], d = avant(pose);
    if (d[1] >= -0.02 || c[1] <= sol) return null;
    const s = (sol - c[1]) / d[1];
    const p = [c[0] + s * d[0], sol, c[2] + s * d[2]];
    return Math.hypot(p[0] - c[0], p[2] - c[2]) > portee ? null : p;
  }

  // Point du moteur → repère de la caméra.
  function versCamera(pose, p) {
    return tournerQ(conjugue(pose.rotation), [p[0] - pose.position.x, p[1] - pose.position.y, p[2] - pose.position.z]);
  }

  // Repère de la caméra → pixels de l'écran, par la matrice de projection du moteur (4 × 4, par colonnes).
  function projeterCamera(K, pc, largeur, hauteur) {
    const w = K[3] * pc[0] + K[7] * pc[1] + K[11] * pc[2] + K[15];
    if (w <= 1e-6) return null;
    const x = (K[0] * pc[0] + K[4] * pc[1] + K[8] * pc[2] + K[12]) / w;
    const y = (K[1] * pc[0] + K[5] * pc[1] + K[9] * pc[2] + K[13]) / w;
    return [((x + 1) / 2) * largeur, ((1 - y) / 2) * hauteur];
  }

  function projeter(pose, K, p, largeur, hauteur) {
    const pc = versCamera(pose, p);
    return pc[2] > -PRES ? null : projeterCamera(K, pc, largeur, hauteur);
  }

  // Le mur a → b à l'écran : la partie devant la caméra (coupée à 5 cm devant l'objectif).
  function segment(pose, K, a, b, largeur, hauteur) {
    let pa = versCamera(pose, a), pb = versCamera(pose, b);
    if (pa[2] > -PRES && pb[2] > -PRES) return null;
    const couper = (p, q) => {
      const k = (-PRES - p[2]) / (q[2] - p[2]);
      return [p[0] + k * (q[0] - p[0]), p[1] + k * (q[1] - p[1]), -PRES];
    };
    if (pa[2] > -PRES) pa = couper(pa, pb);
    else if (pb[2] > -PRES) pb = couper(pb, pa);
    const ea = projeterCamera(K, pa, largeur, hauteur), eb = projeterCamera(K, pb, largeur, hauteur);
    return ea && eb ? [ea, eb] : null;
  }

  function mediane(v) {
    const s = [...v].sort((a, b) => a - b);
    return s.length ? s[s.length >> 1] : null;
  }

  // --- Le moteur sur le téléphone -------------------------------------------------------------------------------------

  // Le sol : la hauteur des surfaces horizontales que le moteur voit sous la croix (médiane des dernières) ; avant la
  // première, 1,40 m sous la caméra (téléphone tenu devant la poitrine, hypothèse).
  function Suivi() {
    this.actif = false;
    this.pose = null; // { position, rotation, intrinsics }
    this.statut = "UNSPECIFIED";
    this.raison = "";
    this.flux = null; // la vidéo de la caméra arrière (pour l'enregistrer)
    this.toile = null;
    this.hauteursSol = [];
    this.derniereVisee = 0;
    this.decalages = []; // lacet − cap du moteur
    this.surImage = null; // rappel à chaque image suivie
    this.signaler = null; // rappel pour le diagnostic (état du suivi, erreurs) : envoyé au serveur
  }

  Suivi.prototype.sol = function () {
    const m = mediane(this.hauteursSol);
    return m != null ? m : 0;
  };

  Suivi.prototype.decalage = function () {
    if (!this.decalages.length) return 0;
    const s = this.decalages.reduce((a, d) => a + Math.sin(d * RAD), 0), c = this.decalages.reduce((a, d) => a + Math.cos(d * RAD), 0);
    return Math.atan2(s, c) / RAD;
  };

  // À chaque image : la pose ; quatre fois par seconde, la hauteur du sol sous la croix et l'accord avec le gyroscope.
  Suivi.prototype.noter = function (reality, lacet) {
    if (!reality || !reality.position || !reality.rotation) return;
    this.pose = { position: reality.position, rotation: reality.rotation, intrinsics: reality.intrinsics || (this.pose && this.pose.intrinsics) };
    const statut = reality.trackingStatus || this.statut, raison = reality.trackingReason || "";
    if ((statut !== this.statut || raison !== this.raison) && this.signaler) this.signaler(`suivi ${statut} ${raison}`.trim());
    this.statut = statut;
    this.raison = raison;
    const maintenant = Date.now();
    if (this.statut === "NORMAL" && maintenant - this.derniereVisee > 250 && globalThis.XR8) {
      this.derniereVisee = maintenant;
      const touches = globalThis.XR8.XrController.hitTest(0.5, 0.5, ["DETECTED_SURFACE", "ESTIMATED_SURFACE"]) || [];
      for (const t of touches.slice(0, 1)) {
        if (t.position && t.position.y < this.pose.position.y - 0.3) this.hauteursSol = [...this.hauteursSol, t.position.y].slice(-40);
      }
      const d = avant(this.pose);
      if (lacet != null && Math.hypot(d[0], d[2]) > 0.3) {
        this.decalages = [...this.decalages, ((lacet - cap(d)) % 360 + 540) % 360 - 180].slice(-60);
      }
    }
  };

  // La position du téléphone (repère de l'application) et le point du sol visé, ou null.
  Suivi.prototype.position = function () {
    return this.pose ? versApp([this.pose.position.x, 0, this.pose.position.z], this.decalage()) : null;
  };

  Suivi.prototype.vise = function () {
    if (!this.pose || this.statut !== "NORMAL") return null;
    const p = viseAuSol(this.pose, this.sol());
    return p && versApp(p, this.decalage());
  };

  // Un point du sol (repère de l'application) à l'écran, et un mur.
  Suivi.prototype.ecran = function (P, largeur, hauteur) {
    if (!this.pose || !this.pose.intrinsics) return null;
    return projeter(this.pose, this.pose.intrinsics, versMoteur(P, this.decalage(), this.sol()), largeur, hauteur);
  };

  Suivi.prototype.mur = function (A, B, largeur, hauteur) {
    if (!this.pose || !this.pose.intrinsics) return null;
    const d = this.decalage(), s = this.sol();
    return segment(this.pose, this.pose.intrinsics, versMoteur(A, d, s), versMoteur(B, d, s), largeur, hauteur);
  };

  // Charge le moteur (web/vendor/8thwall) et le lance sur la toile ; résout quand la caméra est ouverte, échoue sinon
  // (téléphone non pris en charge, caméra refusée) : l'application garde alors son propre suivi par le sol filmé.
  Suivi.prototype.demarrer = function (toile, lacetActuel, delaiMs = 20000) {
    this.toile = toile;
    const charge = () => new Promise((resolve, reject) => {
      if (globalThis.XR8) return resolve(globalThis.XR8);
      const s = document.createElement("script");
      s.src = "vendor/8thwall/xr.js";
      s.async = true;
      s.dataset.preloadChunks = "slam";
      s.onerror = () => reject(new Error("moteur introuvable"));
      racine.addEventListener("xrloaded", () => resolve(globalThis.XR8), { once: true });
      document.head.appendChild(s);
    });
    const lance = (XR8) => new Promise((resolve, reject) => {
      XR8.XrController.configure({ scale: "responsive", disableWorldTracking: false });
      XR8.addCameraPipelineModules([XR8.GlTextureRenderer.pipelineModule(), XR8.XrController.pipelineModule(), {
        name: "diagauto",
        // La caméra part à 1,40 m au-dessus du sol (téléphone tenu devant la poitrine, hypothèse) : l'échelle en mètres.
        onStart: () => XR8.XrController.updateCameraProjectionMatrix({ origin: { x: 0, y: HAUTEUR_M, z: 0 }, facing: { w: 1, x: 0, y: 0, z: 0 } }),
        onCameraStatusChange: ({ status, stream }) => {
          if (status === "hasStream") { this.flux = stream; this.actif = true; resolve(this); }
          if (status === "hasVideo") { this.actif = true; resolve(this); }
          if (status === "failed") reject(new Error("caméra refusée"));
          if (this.signaler) this.signaler(`caméra ${status}`);
        },
        onUpdate: ({ processCpuResult }) => {
          const reality = processCpuResult && processCpuResult.reality;
          this.noter(reality, lacetActuel());
          if (this.surImage) this.surImage(this);
        },
        onException: (e) => { if (this.signaler) this.signaler(`erreur ${e && e.message ? e.message : e}`); reject(e); },
      }]);
      XR8.run({ canvas: toile, glContextConfig: { preserveDrawingBuffer: true } });
    });
    const delai = new Promise((_, reject) => setTimeout(() => reject(new Error("délai dépassé")), delaiMs));
    return Promise.race([charge().then(lance), delai]);
  };

  Suivi.prototype.arreter = function () {
    if (this.actif && globalThis.XR8) try { globalThis.XR8.stop(); } catch { /* déjà arrêté */ }
    this.actif = false;
  };

  const exporte = { tournerQ, avant, cap, versApp, versMoteur, viseAuSol, versCamera, projeterCamera, projeter, segment, Suivi };
  if (typeof module !== "undefined" && module.exports) module.exports = exporte;
  else racine.SuiviXr8 = exporte;
})(this);
