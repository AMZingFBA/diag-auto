"use strict";
// Page du téléphone : filme, enregistre la vidéo complète en local, envoie au serveur le son
// (16 kHz) et une image par seconde, et lit à voix haute les questions de l'assistant.

// Version de la page, comparée à celle du serveur (test du 23/10 : l'iPhone gardait l'ancienne page en mémoire).
const VERSION_PAGE = "2026-10-25-01";
const $ = (id) => document.getElementById(id);
const TAUX = 16000;
const TYPE_SON = 1;
const TYPE_IMAGE = 2;
const TYPE_IMAGE_POSEE = 3; // image + sa pose (cap, lacet, élévation, roulis) au moment de la prise (étape 15)
// L'image dessinée depuis la caméra montre ce que la vidéo a enregistré ~83 ms plus tôt (mesuré sur l'iPhone de Noah) :
// sa pose est lue à cet instant-là, sinon 10° d'erreur à 120°/s.
const LATENCE_IMAGE_MS = 80;

const etat = {
  liaison: null, // web/liaison.js : battement de cœur, reconnexion silencieuse, rattrapage (étape 10)
  dejaConnecte: false, // jamais connecté : le serveur est injoignable depuis ce téléphone (pas une coupure)
  attenteReponse: null, // « L'assistant réfléchit… » : Claude lent n'est pas une coupure
  images: 0,
  session: null,
  code: "",
  flux: null,
  debut: 0, // performance.now() au démarrage : l'instant 0 de la vidéo
  contexteAudio: null,
  noeudAudio: null,
  debutSon: 0, // instant de la vidéo au premier échantillon de son
  echantillonsLus: 0, // échantillons à 16 kHz produits depuis le début (horloge du son)
  reste: new Float32Array(0),
  tampon: [],
  enregistreur: null,
  morceaux: [],
  typeVideo: "",
  // Relevé continu de la boussole et du gyroscope (20 par seconde), envoyé avec la vidéo en fin de visite (étape 12) :
  // le serveur s'en sert pour savoir quel mur est filmé à chaque instant.
  capteursContinus: [],
  // Questionnaire en direct : réponses en boutons de la question posée, fiche de la pièce (dernier état reçu).
  options: {}, // « type.champ » → réponses en boutons (reçues avec le statut du serveur)
  dernierEtat: null,
  minuteries: [],
  muet: false,
  termine: false,
  arretDemande: false,
  voix: null,
  verrouEcran: null,
  bilan: null,
  // Seuils de la boussole (boussole.toml) ; remplacés par ceux du serveur au chargement.
  reglagesBoussole: { precision: { bonne: 15, faible: 30 }, dispersion: { bonne: 12, faible: 25 }, iphone: { inclinaison_calibrage: 60 } },
  mission: null, // choisie sur l'accueil : « dpe », « amiante » ou « plomb »
  xr8: false, // amiante, plomb : le moteur de 8th Wall suit la position (web/suivi-xr8.js)
};

// Mouvement du téléphone (étape 15 : « un tour de 3 s par pièce ») : orientation complète à chaque événement, rotation
// déroulée (sans saut à 360°), vitesse de rotation, pas ; envoyés au serveur par lots de 0,25 s, qui y voit les tours de
// pièce et les déplacements. Pendant une rotation, une image part à chaque demi-champ tourné, avec sa pose.
const mouvement = {
  lot: [], // mesures (≈ 15 par seconde) à envoyer au prochain lot
  pas: [], // instants des pas détectés depuis le dernier lot
  anneau: [], // toutes les orientations de la dernière seconde et demie : la pose d'une image à l'instant de sa prise
  deroule: null, // lacet (sinon cap) déroulé, en degrés
  dernierAngle: null,
  dernierQuand: 0,
  vitesse: 0, // degrés par seconde autour de la verticale, lissée
  acc: 0, // accélération lissée hors pesanteur (m/s²), pour les pas
  enHaut: false,
  dernierPas: -1,
  derniereImage: null, // { deroule, elevation, quand } : rotation comptée depuis la dernière image envoyée
};

// Missions (Noah, 23/10) : le DPE et ses questions ; l'amiante et le plomb, le croquis en grand (aucune question du DPE).
const MISSIONS = {
  dpe: { titre: "DPE", demarrer: "Démarrer le DPE", piece: "Pièce de départ (facultatif : sans effet sur le DPE)",
         aide: "Filmez tout le logement en une seule vidéo, en parlant normalement. L'assistant vous pose dans l'oreillette les questions qui manquent pour le DPE. Il ne devine rien : il demande." },
  amiante: { titre: "Amiante", demarrer: "Démarrer l'amiante (croquis)", piece: "Pièce de départ (facultatif)",
             aide: "Filmez tout le logement en une seule vidéo : entrez dans chaque pièce et faites-en le tour. Le croquis se dessine tout seul ; corrigez-le à la voix (« non, c'est la buanderie ») ou en le touchant." },
  plomb: { titre: "Plomb (CREP)", demarrer: "Démarrer le plomb (croquis)", piece: "Pièce de départ (facultatif)",
           aide: "Filmez tout le logement en une seule vidéo : entrez dans chaque pièce et faites-en le tour. Le croquis se dessine tout seul, murs A, B, C, D ; corrigez-le à la voix ou en le touchant." },
};

function croquisSeul() {
  return etat.mission === "amiante" || etat.mission === "plomb";
}

function choisirMission(mission) {
  if (!MISSIONS[mission] || etat.demarrage) return; // la caméra s'ouvre déjà : la mission ne change plus
  etat.mission = mission;
  for (const b of $("missions").querySelectorAll("button")) {
    b.classList.toggle("choisi", b.dataset.mission === mission);
    b.setAttribute("aria-checked", String(b.dataset.mission === mission));
  }
  const m = MISSIONS[mission];
  $("aide-mission").textContent = m.aide;
  $("aide-mission").hidden = false;
  $("libelle-piece").textContent = m.piece;
  $("demarrer").textContent = m.demarrer;
  $("demarrer").disabled = false;
  document.body.dataset.mission = mission; // style.css : le croquis en grand pour l'amiante et le plomb
  $("voir-fiche").textContent = croquisSeul() ? "🗺️ Plan" : "📋 Fiche";
  $("manques-bloc").hidden = croquisSeul();
  $("murs").hidden = !croquisSeul();
}

// --- Tracé guidé du plan sur la caméra (Noah, 23/10) ------------------------------------------------------------------
// La croix au centre vise un coin au ras du sol ; « ＋ Coin » le valide. Les coins et les murs déjà tracés restent dessinés
// à leur place réelle dans l'image, même en tournant ou en marchant : l'orientation vient du gyroscope, la position du sol
// filmé (web/odometrie.js), et la caméra est supposée à 1,40 m du sol (une erreur sur cette hauteur agrandit ou rétrécit
// tout, sans désaligner le tracé). Du dernier coin validé au point visé, le mur en cours en pointillés, avec sa longueur.
// Le serveur garde les contours et en fait le plan (assistant/session.py, _tracer).
const traceur = {
  actif: false,
  hauteur: 1.4,
  odo: null,
  toile: null, // l'image de la caméra réduite à 240 pixels de large, pour suivre la position
  orientations: [], // { quand, a, b, g } des 2 dernières secondes
  derniereTrame: 0,
  pose: null, // { R, C } de la dernière image affichée
  pieces: [], // contours reçus du serveur : { cle, nom, ferme, points: [[x, y]] }
  courant: null, // la pièce du contour en cours
  selection: null, // { cle, index } : le coin touché, à corriger
  vise: null, // le point du sol sous la croix
  ecran: [], // les coins dessinés (pour les toucher) : { cle, index, x, y }
  pres: false, // la croix est revenue près du premier coin : on peut fermer
  dureeMs: 0, // temps de calcul du suivi par image (moyenne glissante), envoyé avec les mesures pour le diagnostic
  // Tracé figé à l'arrêt (essai de Noah du 23/10, 17:30 : « les traits bougent trop ») : debout, seul le gyroscope compte
  // (très juste), la position ne bouge pas ; elle ne suit le sol filmé que quand on marche. Recaler (au premier coin en
  // fermant la pièce, ou sur un coin touché) décale tout le dessin d'un coup.
  fige: false,
  Cfige: null,
  decalage: [0, 0], // position affichée = position suivie − décalage
  historique: [], // positions suivies de la dernière seconde : { quand, C }
  secousse: -1e9, // dernier pic d'accélération (secondes de la visite) : un pas, même lent
  marche: false,
  recalage: [0, 0], // moteur de 8th Wall : décalage ajouté à ses positions par « ⇄ Recaler » ou la fermeture
};

// Le suivi par le moteur de 8th Wall (web/suivi-xr8.js ; Noah, 25/10, choix 1) : amiante et plomb. S'il ne démarre pas
// (téléphone non pris en charge), l'application garde son propre suivi par le sol filmé (web/odometrie.js).
const suivi = window.SuiviXr8 ? new SuiviXr8.Suivi() : null;
const PRES_DU_PREMIER_M = 0.3;

function afficherTrace(actif) {
  traceur.actif = actif;
  document.body.classList.toggle("trace", actif);
  $("viseur").hidden = !actif;
  $("trace-toile").hidden = !actif;
  $("outils-trace").hidden = !actif;
  $("murs").textContent = actif ? "✓ Fin du tracé" : "📐 Murs";
  if (!actif) traceur.selection = null;
  majInfoTrace();
}

function contourEnCours() {
  return traceur.pieces.find((p) => p.cle === traceur.courant && !p.ferme) || null;
}

function majInfoTrace(texte) {
  const info = $("trace-info");
  if (!traceur.actif) { info.hidden = true; return; }
  const c = contourEnCours();
  if (!texte && etat.xr8 && suivi.statut !== "NORMAL") {
    info.textContent = "Démarrage du suivi : bougez doucement le téléphone de gauche à droite en visant le sol, quelques secondes.";
    info.hidden = false;
    return;
  }
  info.textContent = texte || (traceur.selection
    ? "Coin choisi : visez sa vraie place. « ✓ Placer ici » corrige ce coin ; « ⇄ Recaler » remet tout le dessin sur lui."
    : !c ? "Placez-vous au milieu de la pièce. Visez un coin au ras du sol (pas vos pieds), puis « ＋ Coin »."
    : `${c.nom} : ${c.points.length} coin${c.points.length > 1 ? "s" : ""}. Sans marcher, visez le coin suivant ; revenez au premier pour fermer.`);
  info.hidden = false;
}

// La position du téléphone pour le tracé : celle du sol filmé quand on marche, figée quand on est arrêté (pas de pas depuis
// 1,2 s, et moins de 25 cm d'après le sol filmé en une seconde). Le passage de l'une à l'autre ne fait pas de saut.
function positionStable(Csuivi) {
  const quand = performance.now();
  traceur.historique.push({ quand, C: [...Csuivi] });
  while (traceur.historique.length && quand - traceur.historique[0].quand > 1000) traceur.historique.shift();
  const avant = traceur.historique[0].C;
  traceur.marche = Math.hypot(Csuivi[0] - avant[0], Csuivi[1] - avant[1]) > 0.25 || maintenant() - traceur.secousse < 1.2;
  if (!traceur.marche && !traceur.fige) {
    traceur.fige = true;
    traceur.Cfige = [Csuivi[0] - traceur.decalage[0], Csuivi[1] - traceur.decalage[1]];
  } else if (traceur.marche && traceur.fige) {
    traceur.fige = false;
    traceur.decalage = [Csuivi[0] - traceur.Cfige[0], Csuivi[1] - traceur.Cfige[1]];
  }
  return traceur.fige ? [...traceur.Cfige] : [Csuivi[0] - traceur.decalage[0], Csuivi[1] - traceur.decalage[1]];
}

// Recaler : le point du sol visé est en vrai le coin P (on le vise de nouveau) : tout le dessin se décale d'autant.
function recaler(P, vise) {
  const d = [P[0] - vise[0], P[1] - vise[1]];
  if (etat.xr8) {
    traceur.recalage = [traceur.recalage[0] + d[0], traceur.recalage[1] + d[1]];
    return d;
  }
  if (traceur.fige) traceur.Cfige = [traceur.Cfige[0] + d[0], traceur.Cfige[1] + d[1]];
  traceur.decalage = [traceur.decalage[0] - d[0], traceur.decalage[1] - d[1]];
  if (traceur.pose) traceur.pose.C = [traceur.pose.C[0] + d[0], traceur.pose.C[1] + d[1]];
  return d;
}

function noterOrientation(e) {
  if (e.alpha == null || e.beta == null || e.gamma == null) return;
  const quand = performance.now();
  traceur.orientations.push({ quand, a: e.alpha, b: e.beta, g: e.gamma });
  while (traceur.orientations.length && quand - traceur.orientations[0].quand > 2000) traceur.orientations.shift();
}

// L'orientation du téléphone à l'instant `quand` (la mesure la plus proche).
function orientationA(quand) {
  let meilleure = null;
  for (const o of traceur.orientations) if (!meilleure || Math.abs(o.quand - quand) < Math.abs(meilleure.quand - quand)) meilleure = o;
  return meilleure && Boussole.matrice(meilleure.a, meilleure.b, meilleure.g);
}

// À chaque image de la caméra (amiante, plomb) : la position du téléphone suivie par le sol filmé (15 fois par seconde au
// plus, dès le début de la visite), et le tracé redessiné sur cette image, avec l'orientation de sa prise (le dessin et
// l'image ont le même retard : ils restent ensemble quand on tourne).
function suivrePosition(meta) {
  if (!croquisSeul() || !window.Odometrie || etat.termine || etat.xr8) return;
  const video = $("camera");
  if (!video.videoWidth) return;
  const quand = performance.now();
  const R = orientationA(meta && meta.captureTime ? meta.captureTime : quand - LATENCE_IMAGE_MS);
  if (!R) return;
  if (quand - traceur.derniereTrame >= 60) {
    traceur.derniereTrame = quand;
    const l = 240, h = Math.round((240 * video.videoHeight) / video.videoWidth);
    const toile = traceur.toile || (traceur.toile = document.createElement("canvas"));
    if (toile.width !== l || toile.height !== h) Object.assign(toile, { width: l, height: h });
    const ctx = toile.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, l, h);
    traceur.odo = traceur.odo || new Odometrie.Odometrie({ hauteur: traceur.hauteur, champ: champHorizontal() });
    traceur.odo.image(Odometrie.gris(ctx.getImageData(0, 0, l, h).data, l, h), R, quand / 1000);
    traceur.dureeMs += 0.2 * (performance.now() - quand - traceur.dureeMs);
  }
  if (!traceur.odo) return;
  traceur.pose = { R: traceur.odo.orientation(R), C: positionStable(traceur.odo.C) };
  if (traceur.actif) dessinerTrace();
}

function dessinerTrace() {
  const toile = $("trace-toile"), video = $("camera");
  const W = toile.clientWidth || innerWidth, H = toile.clientHeight || innerHeight, dpr = window.devicePixelRatio || 1;
  if (toile.width !== Math.round(W * dpr) || toile.height !== Math.round(H * dpr)) {
    Object.assign(toile, { width: Math.round(W * dpr), height: Math.round(H * dpr) });
  }
  const ctx = toile.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  traceur.ecran = [];
  const cam = cameraTrace(W, H);
  if (!cam) { traceur.vise = null; majBoutonCoin(); return; }
  const distance = (A, B) => Math.hypot(B[0] - A[0], B[1] - A[1]);
  traceur.vise = cam.vise;
  const courant = contourEnCours();
  traceur.pres = !!(courant && courant.points.length >= 3 && traceur.vise && distance(traceur.vise, courant.points[0]) < PRES_DU_PREMIER_M);
  for (const p of traceur.pieces) {
    const n = p.points.length, couleur = p.ferme ? "#3ddc84" : "#ffd400";
    for (let i = 0; i < (p.ferme ? n : n - 1); i++) {
      const A = p.points[i], B = p.points[(i + 1) % n];
      const s = cam.mur(A, B);
      if (s) traitTrace(ctx, s[0], s[1], couleur, false, distance(A, B));
    }
    p.points.forEach((P, index) => {
      const e = cam.ecran(P);
      if (!e) return;
      const [x, y] = e;
      if (x < -40 || y < -40 || x > W + 40 || y > H + 40) return;
      traceur.ecran.push({ cle: p.cle, index, x, y });
      const choisi = traceur.selection && traceur.selection.cle === p.cle && traceur.selection.index === index;
      const premier = p === courant && index === 0;
      rondTrace(ctx, x, y, choisi ? 11 : premier && traceur.pres ? 13 : 7, choisi ? "#ff5252" : premier && traceur.pres ? "#3ddc84" : couleur);
    });
  }
  // Le mur en cours : du dernier coin validé au point visé (au premier coin quand on y revient), en pointillés.
  if (courant && courant.points.length && traceur.vise && !traceur.selection) {
    const A = courant.points[courant.points.length - 1], B = traceur.pres ? courant.points[0] : traceur.vise;
    const s = cam.mur(A, B);
    if (s) traitTrace(ctx, s[0], s[1], "#ffffff", true, distance(A, B));
  }
  majBoutonCoin();
}

// La caméra du tracé : le point du sol visé, un point du sol à l'écran, un mur à l'écran. Avec le moteur de 8th Wall
// (position en 3D, en mètres), sinon avec notre suivi (gyroscope + sol filmé, téléphone supposé à 1,40 m du sol).
function cameraTrace(W, H) {
  if (etat.xr8) {
    const r = traceur.recalage, plus = (P) => P && [P[0] + r[0], P[1] + r[1]], moins = (P) => [P[0] - r[0], P[1] - r[1]];
    return { vise: plus(suivi.vise()), ecran: (P) => suivi.ecran(moins(P), W, H), mur: (A, B) => suivi.mur(moins(A), moins(B), W, H) };
  }
  const pose = traceur.pose, video = $("camera");
  if (!pose || !video.videoWidth) return null;
  const F = Trace.focaleEcran(champHorizontal(), video.videoWidth, video.videoHeight, W, H);
  const h = traceur.hauteur, E = (uv) => Trace.versEcran(uv, F, W, H);
  return {
    vise: Trace.auSol(pose.C, h, Trace.rayon(pose.R), 12),
    ecran: (P) => { const uv = Trace.projeter(pose.R, pose.C, h, P); return uv && E(uv); },
    mur: (A, B) => { const s = Trace.segment(pose.R, pose.C, h, A, B); return s && [E(s[0]), E(s[1])]; },
  };
}

// Position du téléphone pour le serveur (repère de l'application).
function positionTrace() {
  if (etat.xr8) {
    const p = suivi.position();
    return p && [p[0] + traceur.recalage[0], p[1] + traceur.recalage[1]];
  }
  return traceur.pose ? traceur.pose.C : traceur.odo ? traceur.odo.C : null;
}

function traitTrace(ctx, a, b, couleur, pointille, longueur) {
  ctx.lineCap = "round";
  ctx.setLineDash(pointille ? [10, 8] : []);
  for (const [largeur, c] of [[7, "rgba(0, 0, 0, 0.55)"], [3.5, couleur]]) {
    ctx.lineWidth = largeur;
    ctx.strokeStyle = c;
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  if (longueur != null && Math.hypot(b[0] - a[0], b[1] - a[1]) > 60) {
    const texte = `${longueur.toFixed(2).replace(".", ",")} m`;
    ctx.font = "600 15px system-ui, sans-serif";
    const l = ctx.measureText(texte).width + 12, x = (a[0] + b[0]) / 2, y = (a[1] + b[1]) / 2;
    ctx.fillStyle = "rgba(20, 33, 61, 0.85)";
    ctx.fillRect(x - l / 2, y - 12, l, 24);
    ctx.fillStyle = "#fff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(texte, x, y);
  }
}

function rondTrace(ctx, x, y, r, couleur) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, 2 * Math.PI);
  ctx.fillStyle = couleur;
  ctx.fill();
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = "rgba(0, 0, 0, 0.7)";
  ctx.stroke();
}

function majBoutonCoin() {
  const b = $("trace-point"), f = $("trace-fermer");
  const texte = traceur.selection ? "✓ Placer ici" : traceur.pres ? "⟲ Fermer la pièce" : traceur.vise ? "＋ Coin" : "Visez le sol";
  if (b.textContent !== texte) b.textContent = texte;
  b.disabled = !traceur.vise && !traceur.pres;
  const texteF = traceur.selection ? "⇄ Recaler" : "⟲ Fermer";
  if (f.textContent !== texteF) f.textContent = texteF;
  f.disabled = traceur.selection ? !traceur.vise : ((contourEnCours() || {}).points || []).length < 3;
  majMarche();
}

// Pendant le tracé : « vous marchez » quand la position suit le sol filmé (le dessin peut glisser un peu).
function majMarche() {
  const info = $("trace-info");
  if (!traceur.actif || info.hidden) return;
  info.classList.toggle("marche", traceur.marche);
}

const arrondiMm = (x) => Math.round(x * 1000) / 1000;

// « ＋ Coin » : le point visé devient un coin ; « ⟲ Fermer la pièce » ; « ✓ Placer ici » (le coin touché, corrigé).
function fermerContour() {
  const c = contourEnCours(), vise = traceur.vise;
  if (!c || c.points.length < 3) return;
  const premier = c.points[0];
  // En visant le premier coin (à moins de 2 m de là où le dessin le croit), on le revoit : la dérive du suivi depuis le
  // début de la pièce est mesurée, le dessin se recale et le serveur répartit l'écart sur les coins de la pièce.
  const ecart = vise && Math.hypot(vise[0] - premier[0], vise[1] - premier[1]) < 2 ? recaler(premier, vise) : null;
  envoyerJson({ type: "trace", action: "fermer", t: Math.round(maintenant() * 1000) / 1000,
                ...(ecart ? { ecart: [arrondiMm(-ecart[0]), arrondiMm(-ecart[1])] } : {}) });
  bip();
}

function validerCoin() {
  const vise = traceur.vise;
  if (traceur.pres && !traceur.selection) {
    fermerContour();
    return;
  }
  if (!vise) return;
  if (traceur.selection) {
    const { cle, index } = traceur.selection;
    envoyerJson({ type: "trace", action: "deplacer", cle, index, x: arrondiMm(vise[0]), y: arrondiMm(vise[1]) });
    const p = traceur.pieces.find((q) => q.cle === cle);
    if (p && p.points[index]) p.points[index] = [vise[0], vise[1]];
    traceur.selection = null;
  } else {
    const pose = capteurs.pose || {};
    envoyerJson({ type: "trace", action: "point", x: arrondiMm(vise[0]), y: arrondiMm(vise[1]), t: Math.round(maintenant() * 1000) / 1000,
                  direction: capteurs.lacet != null ? capteurs.lacet : capteurs.cap, elevation: pose.elevation });
    const c = contourEnCours();
    if (c) c.points.push([vise[0], vise[1]]); // tout de suite à l'écran ; le serveur confirme
    else {
      traceur.pieces.push({ cle: "_nouveau", nom: "Pièce", ferme: false, points: [[vise[0], vise[1]]] });
      traceur.courant = "_nouveau";
    }
  }
  bip();
  majInfoTrace();
}

// Toucher un coin dessiné le choisit (pour le corriger) ; toucher ailleurs, ou de nouveau, le lâche.
function toucherTrace(e) {
  const r = $("trace-toile").getBoundingClientRect();
  const x = e.clientX - r.left, y = e.clientY - r.top;
  let proche = null, meilleur = 36;
  for (const p of traceur.ecran) {
    const d = Math.hypot(p.x - x, p.y - y);
    if (d < meilleur) { meilleur = d; proche = p; }
  }
  const deja = proche && traceur.selection && traceur.selection.cle === proche.cle && traceur.selection.index === proche.index;
  traceur.selection = proche && !deja ? { cle: proche.cle, index: proche.index } : null;
  majInfoTrace();
  majBoutonCoin();
}

// Le message d'ouverture de la liaison (et de chaque reconnexion) : la mission part avec lui.
function messageDebut(coupures) {
  return { type: "debut", session: etat.session, piece: $("piece").value, mission: etat.mission || "dpe", appareil: navigator.userAgent, coupures };
}

function maintenant() {
  return (performance.now() - etat.debut) / 1000;
}

function secondes(s) {
  return `${s.toFixed(1).replace(".", ",")} s`;
}

function horodatage(t) {
  const s = Math.max(0, Math.round(t));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// --- Statut du serveur (avant de démarrer) ---------------------------------------------------

async function chargerStatut() {
  try {
    const r = await fetch("/api/statut");
    const s = await r.json();
    $("statut-serveur").textContent = `Serveur prêt. Cerveau : ${s.cerveau}. Transcription : ${s.transcription}.`;
    if (s.version_page && s.version_page !== VERSION_PAGE) {
      $("statut-serveur").textContent = "Nouvelle version de l'assistant : rechargez la page (tirez vers le bas) avant de commencer. "
        + "Si ce message reste après le rechargement, il faut relancer le serveur sur le PC.";
      $("statut-serveur").classList.add("a-recharger");
    }
    $("ligne-code").hidden = !s.code_requis;
    if (s.boussole) etat.reglagesBoussole = s.boussole;
    if (s.options) etat.options = s.options;
  } catch {
    serveurInjoignable($("statut-serveur"));
  }
}

// Le serveur ne répond pas. Le plus souvent (même Wi-Fi que le PC) : le téléphone a oublié le certificat du serveur,
// accepté une fois, et cette page, gardée sur le téléphone, s'affiche sans montrer l'avertissement qui permet de
// l'accepter de nouveau. L'adresse /api/statut n'est jamais gardée : l'ouvrir fait réapparaître cet avertissement.
function serveurInjoignable(element) {
  const lien = Object.assign(document.createElement("a"), { href: "/api/statut", textContent: "toucher ici" });
  element.replaceChildren(
    "Serveur injoignable depuis ce téléphone. 1) Le téléphone doit être sur le même Wi-Fi que le PC (pas la 4G). " +
    "2) Accepter de nouveau le certificat du serveur : ",
    lien,
    ", puis « Afficher les détails » et « visiter ce site web » ; revenir ensuite sur cette page et la recharger.",
  );
}

// --- Voix de l'assistant ------------------------------------------------------------------------

function choisirVoix() {
  const voix = speechSynthesis.getVoices().filter((v) => v.lang && v.lang.toLowerCase().startsWith("fr"));
  etat.voix = voix.find((v) => v.lang === "fr-FR" && v.localService) || voix.find((v) => v.lang === "fr-FR") || voix[0] || null;
}

function debloquerVoix() {
  // iPhone : la synthèse vocale doit être lancée une première fois par un geste de l'utilisateur.
  if (!("speechSynthesis" in window)) return;
  choisirVoix();
  speechSynthesis.onvoiceschanged = choisirVoix;
  const u = new SpeechSynthesisUtterance(" ");
  u.volume = 0;
  speechSynthesis.speak(u);
}

function parler(texte, id, suite = false) {
  if (!("speechSynthesis" in window)) return;
  if (!suite) speechSynthesis.cancel(); // la suite d'une réponse (phrase par phrase) se met en file, sans couper
  const u = new SpeechSynthesisUtterance(texte);
  u.lang = "fr-FR";
  if (etat.voix) u.voice = etat.voix;
  u.rate = 1.2; // questions courtes, dites vite (retour de Noah : trop lent)
  let commence = false;
  u.onstart = () => {
    commence = true;
    envoyerJson({ type: "tts", etat: "debut", id }, false);
  };
  u.onend = u.onerror = () => envoyerJson({ type: "tts", etat: "fin", id }, false);
  speechSynthesis.speak(u);
  // Certains Android ne signalent pas le début de la voix : on le signale nous-mêmes.
  setTimeout(() => { if (!commence && speechSynthesis.speaking) envoyerJson({ type: "tts", etat: "debut", id }, false); }, 1500);
}

function couperVoix() {
  if ("speechSynthesis" in window && speechSynthesis.speaking) {
    speechSynthesis.cancel();
    envoyerJson({ type: "tts", etat: "fin" }, false);
  }
}

function bip() {
  const ctx = etat.contexteAudio;
  if (navigator.vibrate) navigator.vibrate(40);
  if (!ctx || etat.muet) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = 880;
  gain.gain.setValueAtTime(0.15, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
  osc.connect(gain).connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + 0.16);
}

// --- Liaison avec le serveur ----------------------------------------------------------------

// `garder` : envoyé dès le retour de la liaison s'il ne peut pas partir maintenant (son, images, capteurs, phrases) ;
// sinon abandonné (état de la voix, qui n'a plus de sens plus tard).
function envoyerJson(message, garder = true) {
  if (etat.liaison) etat.liaison.envoyerJson(message, garder);
}

function envoyerBinaire(type, t, donnees, garder = true) {
  if (!etat.liaison) return;
  const entete = new ArrayBuffer(9);
  const vue = new DataView(entete);
  vue.setUint8(0, type);
  vue.setFloat64(1, t, true);
  etat.liaison.envoyer(new Blob([entete, donnees]), garder);
}

// Étape 10 : « Hors réseau » seulement si le serveur est vraiment injoignable (3 battements de 2 s sans réponse, ou
// reconnexion impossible depuis 6 s). Une coupure brève (écran verrouillé, serveur redémarré) se répare en silence.
function connecter() {
  const protocole = location.protocol === "https:" ? "wss://" : "ws://";
  const code = etat.code ? `?code=${encodeURIComponent(etat.code)}` : "";
  etat.liaison = new Liaison({
    creerSocket: () => {
      const ws = new WebSocket(`${protocole}${location.host}/ws${code}`);
      ws.binaryType = "arraybuffer";
      return ws;
    },
    debut: messageDebut,
    surMessage: recevoir,
    surEtat: afficherLiaison,
  });
  etat.liaison.demarrer();
  document.addEventListener("visibilitychange", () => etat.liaison && etat.liaison.pageCachee(document.hidden));
  window.addEventListener("online", () => etat.liaison && etat.liaison.reconnecterVite());
}

function afficherLiaison(e) {
  const pastilles = { connecte: "pastille ok", lent: "pastille", hors_reseau: "pastille ko", refuse: "pastille ko" };
  $("connexion").className = pastilles[e] || "pastille";
  $("connexion").title = { connecte: "Connecté", lent: "Réseau lent", reconnexion: "Reconnexion…", pause: "En pause (page cachée)",
                           hors_reseau: "Hors réseau", refuse: "Code d'accès incorrect", connexion: "Connexion…" }[e] || e;
  if (e === "connecte" || e === "lent") etat.dejaConnecte = true;
  if (e === "refuse") return alerte("Code d'accès incorrect.");
  // Jamais connecté depuis le début : ce n'est pas une coupure. Le serveur est sur le PC : le téléphone doit être sur le
  // même Wi-Fi que lui (en 4G, même avec un très bon signal, il ne peut pas le joindre).
  if (e === "hors_reseau" && !etat.dejaConnecte) {
    alerte("");
    $("alerte").hidden = false;
    return serveurInjoignable($("alerte"));
  }
  if (e === "hors_reseau") return alerte("Hors réseau : l'enregistrement continue, l'assistant reprendra au retour du réseau.");
  if (e === "connecte" && $("alerte").textContent.startsWith("Hors réseau")) {
    alerte("Réseau revenu : l'assistant rattrape ce qui a été dit.");
    setTimeout(() => { if ($("alerte").textContent.startsWith("Réseau revenu")) alerte(""); }, 4000);
  }
}

// Claude réfléchit (rien n'est dit 3 s après la phrase) : ce n'est pas une coupure, on le montre.
function attendreReponse() {
  clearTimeout(etat.attenteReponse);
  etat.attenteReponse = setTimeout(() => ($("latence").textContent = "L'assistant réfléchit…"), 3000);
}

function alerte(texte) {
  $("alerte").textContent = texte;
  $("alerte").hidden = !texte;
}

function recevoir(m) {
  switch (m.type) {
    case "statut":
      etat.session = m.session;
      if (m.options) etat.options = m.options;
      alerte("");
      // Serveur pas relancé après une mise à jour : il ignore la mission choisie (premier essai de Noah du 23/10).
      if (etat.mission && (m.mission || "dpe") !== etat.mission) alerte("Le serveur du PC n'a pas pris la mission choisie : il faut le relancer.");
      $("infos").textContent = `Visite ${m.session}${m.reprise ? " (reprise)" : ""} — cerveau : ${m.cerveau} — transcription : ${m.transcription}`;
      break;
    case "parole_debut":
      couperVoix(); // le diagnostiqueur reparle : l'assistant se tait aussitôt
      break;
    case "transcription":
      $("vous").textContent = `Vous (${horodatage(m.t)}) : « ${m.texte} »`;
      attendreReponse();
      break;
    case "dire":
      clearTimeout(etat.attenteReponse);
      // Réponse de Claude lue phrase par phrase (étape 7) : les phrases « suite » s'ajoutent à la précédente.
      $("question").textContent = m.suite ? `${$("question").textContent} ${m.texte}` : m.texte;
      // Vignette de l'élément concerné (« le mur affiché ») : l'image filmée quand il a été décrit.
      if (!m.suite || m.image) $("vignette").hidden = !m.image;
      if (m.image) $("vignette").src = m.image + (etat.code ? `?code=${encodeURIComponent(etat.code)}` : "");
      $("question").classList.toggle("muet", m.muet || etat.muet);
      $("question").hidden = false;
      // Amiante, plomb : une annonce (« Nouvelle pièce : … ») n'efface pas l'indication « touchez le croquis pour corriger ».
      if (!m.suite && (m.latence_s != null || !croquisSeul())) {
        $("latence").textContent = m.latence_s != null ? `Réponse ${secondes(m.latence_s)} après la fin de votre phrase` : "";
      }
      if (m.cible !== undefined) afficherChoix(m.cible, m.options || []);
      if (!m.muet && !etat.muet) parler(m.texte, m.id, m.suite);
      break;
    case "bip":
      clearTimeout(etat.attenteReponse);
      bip();
      if (m.latence_s != null) $("latence").textContent = `✓ Noté ${secondes(m.latence_s)} après la fin de votre phrase`;
      break;
    case "etat":
      majEtat(m);
      etat.dernierEtat = m;
      if (!$("fiche").hidden) afficherFiche();
      afficherCroquis(m.checklist && m.checklist.croquis);
      break;
    case "actions":
      majActions(m.resultats);
      break;
    case "erreur":
      alerte(m.message);
      setTimeout(() => alerte(""), 6000);
      break;
    case "piece_reconnue":
      $("latence").textContent = `📷 Pièce : ${m.nom}${m.nouvelle ? " (nouvelle)" : ""}. Touchez le croquis pour corriger.`;
      break;
    case "trace": {
      // Les contours gardés par le serveur (ils remplacent ce qui a été ajouté à l'écran en attendant).
      const fermes = traceur.pieces.filter((p) => p.ferme).length;
      traceur.pieces = m.pieces || [];
      traceur.courant = m.courant;
      const s = traceur.selection;
      if (s && !traceur.pieces.some((p) => p.cle === s.cle && p.points.length > s.index)) traceur.selection = null;
      if (!!m.ouvert !== traceur.actif) afficherTrace(!!m.ouvert);
      const ferme = traceur.pieces.filter((p) => p.ferme).length > fermes && traceur.pieces.find((p) => p.cle === m.courant && p.ferme);
      majInfoTrace(ferme ? `✓ ${ferme.nom} : ${ferme.points.length} murs. Pièce suivante : nommez-la, puis visez son premier coin.` : undefined);
      break;
    }
    case "tour":
      // Le serveur a vu un tour de la pièce complet (assistant/tour.py) : un bip dans l'oreillette, sans regarder l'écran.
      bip();
      $("latence").textContent = `🔄 Tour de la pièce enregistré (${Math.round(Math.abs(m.rotation))}° en ${String(m.duree_s).replace(".", ",")} s)`;
      break;
    case "proposition":
      proposerDapresImage(m);
      break;
    case "bilan":
      etat.bilan = m; // l'arrêt reste décidé par le 2e appui sur « Terminer »
      break;
  }
}

// Étape 13 : le DPE décrit le logement (ses côtés, ses équipements), pas une pièce ; la pièce dite n'est qu'un repère.
function majEtat(m) {
  if (croquisSeul()) {
    const n = (m.checklist && m.checklist.pieces || []).length;
    $("piece-courante").textContent = `${MISSIONS[etat.mission].titre} · ${n} pièce${n > 1 ? "s" : ""}${m.piece ? ` · ${m.piece}` : ""}`;
    return;
  }
  $("piece-courante").textContent = `DPE du logement : ${Math.round((m.taux || 0) * 100)} %${m.piece ? ` · ${m.piece}` : ""}`;
  $("taux").style.width = `${Math.round((m.taux || 0) * 100)}%`;
  const liste = $("manques");
  liste.replaceChildren(...m.manques.map((texte) => Object.assign(document.createElement("li"), { textContent: texte })));
  $("manques-titre").textContent = `Manques pour le DPE (${m.nb_manques_visite})`;
}

// --- Questionnaire en direct ---------------------------------------------------------------------------------
// Chaque question arrive avec ses réponses en boutons ; un appui vaut une réponse dite (le serveur l'applique et pose
// aussitôt la question suivante). La fiche montre le DPE du logement par côté, à compléter ou corriger d'un appui.

function boutonsReponse(conteneur, options, envoyer) {
  conteneur.replaceChildren(...options.map((o) => {
    if (o.saisie) return saisieAutre(o, envoyer);
    const bouton = Object.assign(document.createElement("button"), { type: "button", textContent: o.libelle });
    bouton.dataset.valeur = o.valeur;
    bouton.onclick = () => {
      conteneur.querySelectorAll("button").forEach((b) => b.classList.toggle("choisi", b === bouton));
      couperVoix(); // il a répondu : la question en cours n'est plus lue
      envoyer(o);
      $("latence").textContent = `✓ Coché : ${o.libelle}`;
    };
    return bouton;
  }));
  conteneur.hidden = !options.length;
}

// « Autre… » (Noah, 23/10) : une mesure en cm qui n'est pas dans les boutons. Il a l'air d'un bouton comme les autres ;
// un appui ouvre le clavier chiffres (c'est une case de saisie déguisée : sur iPhone, le clavier ne s'ouvre que si l'on
// touche la case elle-même), puis « OK » envoie la valeur, vérifiée et mise en forme par le serveur (« 23 » → « 23 cm »).
function saisieAutre(o, envoyer) {
  const ligne = Object.assign(document.createElement("form"), { className: "autre" });
  const champ = Object.assign(document.createElement("input"), {
    type: "text", placeholder: o.libelle, inputMode: "decimal", enterKeyHint: "done", autocomplete: "off" });
  const unite = Object.assign(document.createElement("span"), { textContent: o.unite || "" });
  const ok = Object.assign(document.createElement("button"), { type: "button", textContent: "OK" });
  ligne.append(champ, unite, ok);
  // Ouverte (case, unité, « OK ») dès qu'on la touche, et tant qu'elle contient un chiffre. Test du 23/10 : « OK »
  // n'était visible que pendant que la case avait la main ; sur iPhone, toucher « OK » la lui retire d'abord, et le
  // bouton disparaissait sous le doigt : rien ne partait.
  const ouvrir = () => ligne.classList.add("ouverte");
  champ.onfocus = () => { ouvrir(); champ.placeholder = o.unite ? `en ${o.unite}` : ""; };
  champ.oninput = ouvrir;
  champ.onblur = () => {
    if (champ.value.trim()) return;
    ligne.classList.remove("ouverte");
    champ.placeholder = o.libelle;
  };
  const valider = () => {
    const valeur = champ.value.trim().replace(/\s+/g, "");
    if (!/^[0-9]+([,.][0-9]+)?$/.test(valeur)) {
      $("latence").textContent = "Tapez un nombre (par exemple 23).";
      return;
    }
    couperVoix();
    envoyer({ ...o, valeur, libelle: `${valeur}${o.unite ? " " + o.unite : ""}` });
    $("latence").textContent = `✓ Noté : ${valeur}${o.unite ? " " + o.unite : ""}`;
    champ.value = "";
    ligne.classList.remove("ouverte");
    champ.blur();
  };
  ok.addEventListener("pointerdown", (e) => e.preventDefault()); // la case garde la main : le bouton reste sous le doigt
  ok.onclick = valider;
  ligne.onsubmit = (e) => { e.preventDefault(); valider(); }; // touche « OK » du clavier
  return ligne;
}

// L'image propose la réponse (assistant/regard.py) : le bouton vu sur l'image s'allume ; un appui confirme. Rien n'est
// noté sans lui.
function proposerDapresImage(m) {
  if (etat.cibleAffichee !== m.cible) return; // la question a changé entre-temps
  const bouton = [...$("choix").querySelectorAll("button")].find((b) => b.dataset.valeur === m.valeur);
  if (!bouton) return;
  bouton.classList.add("vu");
  bouton.textContent = `📷 ${m.libelle}`;
  $("latence").textContent = `📷 Sur l'image : ${m.libelle}${m.raison ? ` (${m.raison})` : ""}. Touchez pour confirmer.`;
}

function afficherChoix(cible, options) {
  etat.cibleAffichee = cible;
  boutonsReponse($("choix"), options, (o) => envoyerJson({ type: "reponse", cible, valeur: o.valeur, libelle: o.libelle, saisie: o.saisie, t: maintenant() }));
}

// --- Croquis du logement (assistant/croquis.py) ------------------------------------------------------------
// Sans mesures : chaque pièce est une case ; portes entre pièces, fenêtres et portes du logement sur leur mur ; murs A à D.
const TYPES_PIECES = ["Entrée", "Séjour", "Salle à manger", "Cuisine", "Chambre", "Salle de bains", "Salle d'eau", "WC", "Couloir",
  "Dégagement", "Bureau", "Buanderie", "Cellier", "Garage", "Escalier", "Palier", "Cave", "Grenier", "Combles", "Sous-sol",
  "Véranda", "Placard", "Dressing", "Débarras", "Chaufferie", "Mezzanine"];
const SVG = "http://www.w3.org/2000/svg";

function dessinerCroquis(svg, c, grand) {
  const largeur = svg.clientWidth || 132, hauteur = svg.clientHeight || 132;
  svg.setAttribute("viewBox", `0 0 ${largeur} ${hauteur}`);
  svg.replaceChildren();
  const xs = c.pieces.map((p) => p.x), ys = c.pieces.map((p) => p.y);
  const [x0, y0] = [Math.min(...xs), Math.min(...ys)];
  const colonnes = Math.max(...xs) - x0 + 1, lignes = Math.max(...ys) - y0 + 1;
  const marge = grand ? 24 : 8;
  const case_ = Math.min((largeur - 2 * marge) / colonnes, (hauteur - 2 * marge) / lignes);
  const ox = (largeur - case_ * colonnes) / 2, oy = (hauteur - case_ * lignes) / 2;
  const el = (nom, attributs, texte) => {
    const e = document.createElementNS(SVG, nom);
    for (const [k, v] of Object.entries(attributs)) e.setAttribute(k, v);
    if (texte != null) e.textContent = texte;
    svg.append(e);
    return e;
  };
  const coin = (p) => [ox + (p.x - x0) * case_, oy + (p.y - y0) * case_];
  // Segment du milieu d'un mur (un tiers de sa longueur), pour une porte ou une fenêtre.
  const milieu = (p, cote, part = 1 / 3) => {
    const [x, y] = coin(p);
    const debut = case_ * (0.5 - part / 2), fin = case_ * (0.5 + part / 2);
    return { nord: [x + debut, y, x + fin, y], sud: [x + debut, y + case_, x + fin, y + case_],
             ouest: [x, y + debut, x, y + fin], est: [x + case_, y + debut, x + case_, y + fin] }[cote];
  };
  for (const p of c.pieces) {
    const [x, y] = coin(p);
    el("rect", { x, y, width: case_, height: case_, fill: p.cle === c.courante ? "#d6ebff" : "#fafafa", stroke: "#222",
                 "stroke-width": grand ? 3 : 2, "stroke-dasharray": p.source === "image" ? "6 3" : "" });
    el("text", { x: x + case_ / 2, y: y + case_ / 2, "text-anchor": "middle", "dominant-baseline": "middle",
                 "font-size": grand ? Math.min(16, case_ / 6) : Math.max(8, Math.min(11, case_ / 5)), "font-weight": "700" },
       grand || case_ > 40 ? p.nom : p.nom.slice(0, 3));
    if (grand) {
      for (const [cote, lettre] of Object.entries(p.murs)) {
        const d = 12;
        const pos = { nord: [x + case_ / 2, y + d], sud: [x + case_ / 2, y + case_ - d / 2], ouest: [x + d / 1.5, y + case_ / 2],
                      est: [x + case_ - d / 1.5, y + case_ / 2] }[cote];
        el("text", { x: pos[0], y: pos[1], "text-anchor": "middle", "dominant-baseline": "middle", "font-size": 12, fill: "#b00" }, lettre);
      }
    }
  }
  const parCle = Object.fromEntries(c.pieces.map((p) => [p.cle, p]));
  for (const porte of c.portes) {  // une ouverture dans le mur commun
    const [a, b, c2, d] = milieu(parCle[porte.a], porte.cote);
    el("line", { x1: a, y1: b, x2: c2, y2: d, stroke: "#fafafa", "stroke-width": grand ? 6 : 4 });
    el("line", { x1: a, y1: b, x2: c2, y2: d, stroke: "#c0782a", "stroke-width": 1.5 });
  }
  for (const o of c.ouvertures) {  // fenêtre en bleu, porte du logement en marron
    const p = parCle[o.piece];
    if (!p) continue;
    const [a, b, c2, d] = milieu(p, o.cote, 0.5);
    el("line", { x1: a, y1: b, x2: c2, y2: d, stroke: o.type === "fenetre" ? "#1a73e8" : "#8b4513", "stroke-width": grand ? 6 : 4 });
  }
  if (c.oriente) el("text", { x: largeur - 10, y: 12, "text-anchor": "end", "font-size": grand ? 14 : 9, fill: "#b00", "font-weight": "700" }, "N ↑");
}

// Amiante, plomb : le croquis en grand, toujours visible (vide : ce qu'il faut faire). DPE : pas de croquis.
// Plan dans un repère commun (assistant/plan.py, Noah 23/10) : les pièces là où l'on a marché, les portes là où l'on est
// passé, le trajet en pointillés, et « vous êtes ici » avec une flèche qui suit la caméra. Nord en haut quand il est connu.
function dessinerPlan(svg, plan, grand) {
  const largeur = svg.clientWidth || 132, hauteur = svg.clientHeight || 132;
  svg.setAttribute("viewBox", `0 0 ${largeur} ${hauteur}`);
  svg.replaceChildren();
  // Dessiné comme un croquis à la main, dans le sens de la marche (2e test de Noah, 23/10 : nord en haut, en marchant vers
  // le sud, tout paraissait « dans le mauvais sens ») : en direct, la dernière marche vers le haut (ce qui est devant est
  // en haut, ce qui est à gauche à gauche) ; en grand, la première marche vers le haut (l'entrée en bas).
  const sens = (grand ? plan.sens_entree : plan.sens_marche) ?? plan.sens_marche ?? 0;
  const r = (-sens * Math.PI) / 180;
  const tourne = ([x, y]) => [x * Math.cos(r) + y * Math.sin(r), -x * Math.sin(r) + y * Math.cos(r)];
  plan = { ...plan, pieces: plan.pieces.map((p) => ({ ...p, polygone: p.polygone.map(tourne) })),
           trajet: plan.trajet.map(tourne), position: tourne(plan.position), coins: (plan.coins || []).map(tourne),
           portes: plan.portes.map((d) => { const [x, y] = tourne([d.x, d.y]); return { ...d, x, y }; }) };
  const points = [...plan.pieces.flatMap((p) => p.polygone), ...plan.trajet, plan.position, ...plan.coins];
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const marge = grand ? 18 : 8;
  const k = Math.min((largeur - 2 * marge) / Math.max(x1 - x0, 1), (hauteur - 2 * marge) / Math.max(y1 - y0, 1));
  const ox = (largeur - k * (x1 - x0)) / 2, oy = (hauteur - k * (y1 - y0)) / 2;
  const P = ([x, y]) => [ox + (x - x0) * k, oy + (y1 - y) * k]; // nord (ou lacet 0) en haut
  const creer = (nom, attributs, texte) => {
    const e = document.createElementNS(SVG, nom);
    for (const [cle, v] of Object.entries(attributs)) e.setAttribute(cle, v);
    if (texte != null) e.textContent = texte;
    return e;
  };
  const el = (nom, attributs, texte) => svg.appendChild(creer(nom, attributs, texte));
  for (const p of plan.pieces) {  // les pièces d'abord, leurs textes ensuite : un fond ne cache jamais un texte voisin
    el("polygon", { points: p.polygone.map(P).map((q) => q.join(",")).join(" "), fill: p.cle === plan.courante ? "#d6ebff" : "#fafafa",
                    stroke: "#222", "stroke-width": grand ? 3 : 2, "stroke-dasharray": p.source === "image" && !p.mesuree ? "6 3" : "" });
  }
  for (const p of plan.pieces) {
    const pts = p.polygone.map(P);
    const cx = pts.reduce((s, q) => s + q[0], 0) / pts.length, cy = pts.reduce((s, q) => s + q[1], 0) / pts.length;
    const petit = Math.min(...pts.map((q) => Math.hypot(q[0] - cx, q[1] - cy))) < 30;
    // Pièce étroite (couloir) : son nom écrit dans sa longueur.
    const largeurP = Math.max(...pts.map((q) => q[0])) - Math.min(...pts.map((q) => q[0]));
    const hauteurP = Math.max(...pts.map((q) => q[1])) - Math.min(...pts.map((q) => q[1]));
    const debout = largeurP < 70 && hauteurP > 1.6 * largeurP;
    el("text", { x: cx, y: cy, "text-anchor": "middle", "dominant-baseline": "middle", "font-weight": "700",
                 "font-size": grand ? 14 : 10, ...(debout ? { transform: `rotate(-90 ${cx.toFixed(1)} ${cy.toFixed(1)})` } : {}) },
       grand || !petit ? p.nom : p.nom.slice(0, 3));
    if (grand && p.depuis_la_porte) {  // regardée depuis sa porte (pièce occupée…) : à dire dans le repérage
      el("text", { x: cx, y: cy + 16, "text-anchor": "middle", "font-size": 11, fill: "#555" }, "vue depuis la porte");
    }
    if (grand && p.lettres) {
      pts.forEach((a, i) => {
        const b = pts[(i + 1) % pts.length];
        const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
        const d = Math.hypot(cx - mx, cy - my) || 1;
        el("text", { x: mx + (cx - mx) / d * 12, y: my + (cy - my) / d * 12, "text-anchor": "middle", "dominant-baseline": "middle",
                     "font-size": 12, fill: "#b00" }, p.lettres[i] || "");
        // Murs relevés : leur longueur (estimée ; le Carrez reste au laser), le long du mur, à l'intérieur de la pièce.
        if (p.murs && p.murs[i] != null) {
          let angle = (Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI;
          if (angle > 90) angle -= 180;
          if (angle < -90) angle += 180;
          const recul = d > 45 ? 25 : -10; // pièce étroite : la longueur à l'extérieur, le nom garde la place
          const lx = mx + (cx - mx) / d * recul, ly = my + (cy - my) / d * recul;
          el("text", { x: lx, y: ly, "text-anchor": "middle", "dominant-baseline": "middle", "font-size": 10, fill: "#333",
                       class: "longueur", transform: `rotate(${angle.toFixed(1)} ${lx.toFixed(1)} ${ly.toFixed(1)})` },
             `${p.murs[i].toFixed(2).replace(".", ",")} m`);
        }
      });
    }
  }
  for (const d of plan.portes) {
    const [px, py] = P([d.x, d.y]);
    el("circle", { cx: px, cy: py, r: grand ? 6 : 3.5, fill: "#c0782a", stroke: "#fff", "stroke-width": 1.5 });
  }
  for (const c of plan.coins) {  // les coins du relevé en cours, au fur et à mesure
    const [qx, qy] = P(c);
    el("circle", { class: "coin", cx: qx, cy: qy, r: grand ? 5 : 3, fill: "#ff8f00", stroke: "#fff", "stroke-width": 1.5 });
  }
  if (plan.trajet.length > 1) {
    el("polyline", { points: plan.trajet.map(P).map((q) => q.join(",")).join(" "), fill: "none", stroke: "#1a73e8",
                     "stroke-width": 1.5, "stroke-dasharray": "3 3", opacity: 0.8 });
  }
  const [vx, vy] = P(plan.position);
  const ici = el("g", { class: "vous-ici", "data-x": vx, "data-y": vy, "data-sens": sens, transform: `translate(${vx},${vy})` });
  ici.append(creer("circle", { r: grand ? 6 : 4.5, fill: "#1a73e8", stroke: "#fff", "stroke-width": 2 }),
             creer("polygon", { points: grand ? "0,-17 6,-7 -6,-7" : "0,-12 4,-5 -4,-5", fill: "#1a73e8" }));
  tournerVousIci();
  if (plan.oriente) {  // le nord, là où il est sur ce dessin tourné
    const nord = el("g", { transform: `translate(${largeur - 14},${16}) rotate(${-sens})` });
    nord.append(creer("polygon", { points: "0,-9 4,3 -4,3", fill: "#b00" }),
                creer("text", { x: 0, y: 14, "text-anchor": "middle", "font-size": grand ? 11 : 8, fill: "#b00", "font-weight": "700" }, "N"));
  }
}

// La flèche « vous êtes ici » suit la caméra : cap si le plan est orienté au nord, sinon lacet du gyroscope (le repère du plan).
function tournerVousIci() {
  const plan = etat.croquis && etat.croquis.plan;
  const direction = plan && plan.oriente ? capteurs.cap : capteurs.lacet;
  document.querySelectorAll(".vous-ici").forEach((g) => {
    const angle = direction != null ? direction - (Number(g.dataset.sens) || 0) : null; // chaque dessin a son propre sens
    g.setAttribute("transform", `translate(${g.dataset.x},${g.dataset.y})${angle != null ? ` rotate(${angle})` : ""}`);
  });
}

function afficherCroquis(c) {
  if (c) etat.croquis = c;
  c = etat.croquis;
  const vide = !c || !c.pieces.length;
  $("croquis").hidden = !croquisSeul();
  $("croquis-aide").hidden = !vide;
  if ($("croquis").hidden) return;
  if (vide) {
    // Rien encore (ou une nouvelle visite) : le plan ouvert dit quoi faire, au lieu d'un grand rectangle blanc.
    $("croquis-petit").replaceChildren();
    $("croquis-grand").replaceChildren();
    $("plan-pieces").replaceChildren(Object.assign(document.createElement("p"), { className: "petit", textContent: $("croquis-aide").textContent }));
    return;
  }
  const avecPlan = c.plan && c.plan.pieces.length;
  if (avecPlan) dessinerPlan($("croquis-petit"), c.plan, false);
  else dessinerCroquis($("croquis-petit"), c, true);
  if ($("plan").hidden) return;
  if (avecPlan) dessinerPlan($("croquis-grand"), c.plan, true);
  else dessinerCroquis($("croquis-grand"), c, true);
  // Corriger une pièce : un autre nom, « c'est la même pièce que… » (reconnue à tort), ou la déplacer d'une case.
  $("plan-pieces").replaceChildren(...c.pieces.map((p) => {
    const bloc = Object.assign(document.createElement("div"), { className: "bloc-piece" });
    const ligne = Object.assign(document.createElement("div"), { className: "ligne-piece" });
    const choix = document.createElement("select");
    choix.append(new Option(p.source === "image" ? "📷 reconnue : corriger ?" : "Renommer", ""),
                 ...TYPES_PIECES.map((t) => new Option(t, t)));
    choix.onchange = () => { if (choix.value) envoyerJson({ type: "renommer_piece", cle: p.cle, nom: choix.value }); };
    ligne.append(Object.assign(document.createElement("span"), { textContent: p.nom }), choix);
    const outils = Object.assign(document.createElement("div"), { className: "ligne-piece" });
    const meme = document.createElement("select");
    meme.append(new Option("Même pièce que…", ""), ...c.pieces.filter((q) => q.cle !== p.cle).map((q) => new Option(q.nom, q.cle)));
    meme.onchange = () => { if (meme.value) envoyerJson({ type: "fusionner_pieces", cle: p.cle, dans: meme.value }); };
    // Les flèches déplacent une case du croquis en grille ; le plan, lui, suit la trajectoire.
    outils.append(meme, ...(avecPlan ? [] : [["←", "ouest"], ["↑", "nord"], ["↓", "sud"], ["→", "est"]]).map(([fleche, vers]) => {
      const b = Object.assign(document.createElement("button"), { type: "button", className: "fleche", textContent: fleche,
                                                                 title: `Déplacer ${p.nom}` });
      b.onclick = () => envoyerJson({ type: "deplacer_piece", cle: p.cle, vers });
      return b;
    }));
    bloc.append(ligne, outils);
    return bloc;
  }));
}

function afficherFiche() {
  const m = etat.dernierEtat;
  const contenu = $("fiche-contenu");
  if (!m || !m.checklist) return contenu.replaceChildren("La fiche apparaît dès que la visite a commencé.");
  $("fiche-piece").textContent = "DPE du logement";
  const blocs = [];
  const ajouterElements = (titre, elements) => {
    const utiles = (elements || []).filter((e) => Object.values(e.champs || {}).some((c) => c.utile));
    if (!utiles.length) return;
    blocs.push(Object.assign(document.createElement("h3"), { textContent: titre }));
    for (const e of utiles) {
      const nombre = e.nombre > 1 ? ` (${e.nombre})` : "";
      blocs.push(Object.assign(document.createElement("div"), { className: "petit", textContent: `${e.nom || e.description}${nombre}` }));
      for (const [champ, c] of Object.entries(e.champs)) {
        if (!c.utile) continue;
        const valeur = c.valeur ? c.valeur.valeur : "";
        const ligne = Object.assign(document.createElement("button"), { type: "button", className: `champ${valeur ? "" : " manque"}` });
        ligne.append(Object.assign(document.createElement("span"), { textContent: c.libelle }),
                     Object.assign(document.createElement("span"), { className: "valeur", textContent: valeur || "à remplir" }));
        const choix = Object.assign(document.createElement("div"), { className: "choix", hidden: true });
        const options = etat.options[`${e.type}.${champ}`] || [];
        ligne.onclick = () => {
          if (!options.length) return;
          boutonsReponse(choix, options, (o) => envoyerJson({ type: "reponse", element: e.id, champ, valeur: o.valeur, libelle: o.libelle, saisie: o.saisie, t: maintenant() }));
        };
        blocs.push(ligne, choix);
      }
    }
  };
  // Chaque côté : ses murs (et leurs parties), chacun suivi de ses fenêtres et portes.
  const env = m.checklist.enveloppe || {};
  const murs = env.murs || [];
  const ouvertures = env.fenetres || [];
  for (const cote of ["nord", "est", "sud", "ouest", ""]) {
    const ici = murs.filter((e) => ((e.orientation && e.orientation.point) || "") === cote);
    const titre = cote ? `Côté ${cote}` : "Côté à trouver";
    ajouterElements(titre, ici.flatMap((mur) => [mur, ...ouvertures.filter((o) => o.support === mur.id)]));
  }
  const ids = new Set(murs.map((e) => e.id));
  ajouterElements("Fenêtres et portes (mur à préciser)", ouvertures.filter((o) => !ids.has(o.support)));
  ajouterElements("Plafond et plancher", [...(env.plafonds || []), ...(env.planchers || [])]);
  ajouterElements("Équipements", m.checklist.logement ? m.checklist.logement.elements : []);
  if (env.cotes_manquants && env.cotes_manquants.length) {
    blocs.push(Object.assign(document.createElement("div"), { className: "petit", textContent: `Côtés pas encore décrits : ${env.cotes_manquants.join(", ")}` }));
  }
  contenu.replaceChildren(...blocs);
}

function majActions(resultats) {
  const liste = $("actions");
  for (const r of resultats) {
    if (!["enregistrer_reponse", "marquer_sans_objet", "piece_courante", "scinder", "compter", "regle", "exception"].includes(r.outil)) continue;
    const li = document.createElement("li");
    const nombre = r.nombre > 1 ? ` ×${r.nombre}` : "";
    let quoi = `${r.element || ""}${nombre} ${r.champ || ""} = ${r.valeur || "sans objet"}`;
    if (r.outil === "piece_courante") quoi = "pièce";
    // Groupes et exceptions (étape 4) : « séparé : F2 « la fenêtre en bois » », « règle : fenetre ».
    const nom = r.description ? ` « ${r.description} »` : "";
    if (r.outil === "scinder") quoi = `séparé : ${r.element || ""}${nombre}${nom}`;
    if (r.outil === "compter") quoi = `${r.element || ""}${nombre}${nom}`;
    if (r.outil === "regle" || r.outil === "exception") quoi = `${r.outil === "regle" ? "règle" : "exception"} : ${r.type || ""}`;
    li.textContent = r.statut === "accepte" ? `✓ ${quoi}` : `✗ refusé (${r.raison}) : ${quoi}`;
    li.className = r.statut === "accepte" ? "" : "refuse";
    liste.prepend(li);
  }
  while (liste.children.length > 4) liste.lastChild.remove();
}

// --- Capture du son ----------------------------------------------------------------------------

function traiterSon(entree, tauxEntree) {
  // Réduction à 16 kHz par moyenne, puis envoi par blocs de 0,1 s (1600 échantillons).
  const donnees = new Float32Array(etat.reste.length + entree.length);
  donnees.set(etat.reste);
  donnees.set(entree, etat.reste.length);
  const rapport = tauxEntree / TAUX;
  const n = Math.floor(donnees.length / rapport);
  for (let i = 0; i < n; i++) {
    const debut = Math.floor(i * rapport);
    const fin = Math.min(donnees.length, Math.floor((i + 1) * rapport));
    let somme = 0;
    for (let j = debut; j < fin; j++) somme += donnees[j];
    etat.tampon.push(somme / Math.max(1, fin - debut));
  }
  etat.reste = donnees.slice(Math.floor(n * rapport));
  while (etat.tampon.length >= 1600) {
    const bloc = etat.tampon.splice(0, 1600);
    const pcm = new Int16Array(1600);
    for (let i = 0; i < 1600; i++) pcm[i] = Math.max(-32768, Math.min(32767, Math.round(bloc[i] * 32767)));
    const t = etat.debutSon + etat.echantillonsLus / TAUX;
    etat.echantillonsLus += 1600;
    envoyerBinaire(TYPE_SON, t, pcm.buffer); // sans réseau, gardé et envoyé au retour (étape 10)
  }
}

async function demarrerSon() {
  const Contexte = window.AudioContext || window.webkitAudioContext;
  const ctx = new Contexte();
  etat.contexteAudio = ctx;
  await ctx.resume();
  const source = ctx.createMediaStreamSource(new MediaStream(etat.flux.getAudioTracks()));
  etat.debutSon = maintenant();
  if (ctx.audioWorklet) {
    await ctx.audioWorklet.addModule("capture-son.js");
    const noeud = new AudioWorkletNode(ctx, "capture-son");
    noeud.port.onmessage = (e) => traiterSon(e.data, ctx.sampleRate);
    source.connect(noeud);
    etat.noeudAudio = noeud;
  } else {
    // Navigateurs anciens : ancienne interface, toujours disponible.
    const noeud = ctx.createScriptProcessor(4096, 1, 1);
    noeud.onaudioprocess = (e) => traiterSon(e.inputBuffer.getChannelData(0), ctx.sampleRate);
    source.connect(noeud);
    noeud.connect(ctx.destination);
    etat.noeudAudio = noeud;
  }
}

// --- Images (~512 px) : une par seconde, et pendant une rotation une à chaque demi-champ tourné -----------------

// Chaque seconde : la mesure de la boussole (étape 6), et une image si aucune n'est partie depuis 0,7 s.
function chaqueSeconde() {
  envoyerCapteurs(maintenant());
  if (!mouvement.derniereImage || performance.now() - mouvement.derniereImage.quand >= 700) capturerImage("temps", null);
}

// Champ horizontal de la caméra principale (mesuré sur les visites de Noah : ~45° en portrait, ~61° en paysage).
function champHorizontal() {
  const video = $("camera");
  return video.videoHeight > video.videoWidth ? 45 : 61;
}

// À chaque image de la caméra (requestVideoFrameCallback, sinon toutes les 66 ms) : une image clé dès que la caméra a
// tourné d'un demi-champ (~22° en portrait), ou s'est levée ou baissée de 20°, depuis la dernière image envoyée. 8 par
// seconde au plus ; au-delà de 200°/s, on attend un peu une image moins floue (essai du 23/10 : à 360°/s, image inutilisable).
function examinerTrame(meta) {
  const derniere = mouvement.derniereImage;
  if (!derniere || mouvement.deroule == null || !etat.liaison || etat.termine) return;
  const pas = champHorizontal() / 2;
  const tourne = Math.abs(mouvement.deroule - derniere.deroule);
  const pose = capteurs.pose;
  const leve = pose && derniere.elevation != null ? Math.abs(pose.elevation - derniere.elevation) : 0;
  if (tourne < pas && leve < 20) return;
  if (performance.now() - derniere.quand < 125) return;
  if (mouvement.vitesse > 200 && tourne < 1.5 * pas) return;
  capturerImage("rotation", meta);
}

function suivreTrames() {
  const video = $("camera");
  if (video.requestVideoFrameCallback) {
    const surTrame = (_maintenant, meta) => {
      if (etat.termine) return;
      examinerTrame(meta);
      suivrePosition(meta);
      video.requestVideoFrameCallback(surTrame);
    };
    video.requestVideoFrameCallback(surTrame);
  } else {
    etat.minuteries.push(setInterval(() => { examinerTrame(null); suivrePosition(null); }, 66));
  }
}

// La pose de la caméra à l'instant `quand` (ms, horloge de performance.now) : interpolée dans l'anneau des orientations.
function poseA(quand) {
  const a = mouvement.anneau;
  if (!a.length) return {};
  let i = a.findIndex((m) => m.quand >= quand);
  if (i < 0) i = a.length - 1;
  const apres = a[i], avant = a[Math.max(0, i - 1)];
  const k = apres.quand > avant.quand ? Math.min(1, Math.max(0, (quand - avant.quand) / (apres.quand - avant.quand))) : 1;
  const melange = (x, y) => (x == null || y == null ? (y == null ? x : y) : x + k * (y - x));
  const deroule = melange(avant.deroule, apres.deroule);
  const proche = k < 0.5 ? avant : apres;
  // Cap et lacet de l'instant : ceux de l'orientation la plus proche, décalés de la rotation faite depuis.
  const decale = (angle) => (angle == null || deroule == null || proche.deroule == null ? angle : (angle + deroule - proche.deroule + 720) % 360);
  return { deroule, cap: decale(proche.cap), lacet: decale(proche.lacet), elevation: melange(avant.elevation, apres.elevation),
           roulis: proche.roulis };
}

function capturerImage(raison, meta) {
  const video = $("camera");
  if (!video.videoWidth || !etat.liaison) return;
  const quand = performance.now();
  const prise = meta && meta.captureTime ? meta.captureTime : quand - LATENCE_IMAGE_MS;
  const pose = poseA(prise);
  const echelle = 512 / Math.max(video.videoWidth, video.videoHeight);
  const toile = capturerImage.toile || (capturerImage.toile = document.createElement("canvas"));
  toile.width = Math.round(video.videoWidth * echelle);
  toile.height = Math.round(video.videoHeight * echelle);
  toile.getContext("2d").drawImage(video, 0, 0, toile.width, toile.height); // toBlob copie l'image tout de suite
  const t = Math.max(0, (prise - etat.debut) / 1000);
  mouvement.derniereImage = { deroule: pose.deroule != null ? pose.deroule : mouvement.deroule,
                              elevation: pose.elevation != null ? pose.elevation : null, quand };
  // Pendant une coupure, toutes les images d'une rotation sont gardées, et une sur trois des autres.
  const garder = raison === "rotation" || etat.liaison.ouverte() || etat.images++ % 3 === 0;
  const arrondi = (x) => (x == null ? null : Math.round(x * 10) / 10);
  const portrait = toile.height > toile.width;
  const entete = { raison, cap: arrondi(pose.cap), lacet: arrondi(pose.lacet), elevation: arrondi(pose.elevation),
                   roulis: arrondi(pose.roulis), vitesse: Math.round(mouvement.vitesse), precision: arrondi(capteurs.precision),
                   portrait, champ: champHorizontal() };
  toile.toBlob((blob) => blob && envoyerImagePosee(t, entete, blob, garder), "image/jpeg", 0.7);
}

// Message binaire de type 3 : [3][t float64][longueur u16][pose en JSON][JPEG]. Après le son (web/liaison.js).
function envoyerImagePosee(t, pose, blob, garder) {
  if (!etat.liaison) return;
  const json = new TextEncoder().encode(JSON.stringify(pose));
  const entete = new ArrayBuffer(11);
  const vue = new DataView(entete);
  vue.setUint8(0, TYPE_IMAGE_POSEE);
  vue.setFloat64(1, t, true);
  vue.setUint16(9, json.length, true);
  etat.liaison.envoyerImage(new Blob([entete, json, blob]), garder);
}

// Orientation à chaque événement : rotation déroulée, vitesse, et l'anneau qui donne la pose de chaque image.
function suivreRotation() {
  const angle = capteurs.lacet != null ? capteurs.lacet : capteurs.cap;
  const quand = performance.now();
  if (angle == null) return;
  if (mouvement.deroule == null || quand - mouvement.dernierQuand > 500) {
    mouvement.deroule = angle; // début, ou trou (page cachée) : on repart de là
    mouvement.vitesse = 0;
  } else {
    const pas = ((angle - mouvement.dernierAngle + 540) % 360) - 180;
    mouvement.deroule += pas;
    const dt = (quand - mouvement.dernierQuand) / 1000;
    if (dt > 0) mouvement.vitesse += 0.3 * (Math.abs(pas) / dt - mouvement.vitesse);
  }
  mouvement.dernierAngle = angle;
  mouvement.dernierQuand = quand;
  const pose = capteurs.pose || {};
  mouvement.anneau.push({ quand, deroule: mouvement.deroule, cap: capteurs.cap, lacet: capteurs.lacet,
                          elevation: pose.elevation, roulis: pose.roulis });
  while (mouvement.anneau.length && quand - mouvement.anneau[0].quand > 1500) mouvement.anneau.shift();
}

// Pas (accéléromètre, sans la pesanteur) : un pic au-dessus de 1 m/s², au plus un pas toutes les 0,3 s.
function suivrePas(e) {
  if (!etat.debut || etat.termine) return;
  const g = e.accelerationIncludingGravity;
  if (!g || g.x == null) return;
  const norme = Math.hypot(g.x, g.y, g.z) - 9.81;
  mouvement.acc += 0.25 * (norme - mouvement.acc);
  const t = maintenant();
  if (Math.abs(mouvement.acc) > 0.6) traceur.secousse = t;
  if (!mouvement.enHaut && mouvement.acc > 1.0 && t - mouvement.dernierPas > 0.3) {
    mouvement.enHaut = true;
    mouvement.dernierPas = t;
    mouvement.pas.push(Math.round(t * 1000) / 1000);
    if (traceur.odo) traceur.odo.pas(capteurs.lacet != null ? capteurs.lacet : capteurs.cap || 0); // seulement s'il est perdu
  } else if (mouvement.enHaut && mouvement.acc < 0.2) {
    mouvement.enHaut = false;
  }
}

// Toutes les 0,25 s : les mesures et les pas depuis le dernier lot (le serveur y voit les tours de pièce en direct).
function envoyerMouvement() {
  if (!mouvement.lot.length && !mouvement.pas.length) return;
  envoyerJson({ type: "capteurs_lot", mesures: mouvement.lot.splice(0), pas: mouvement.pas.splice(0) });
}

// --- Boussole : direction filmée, pour nommer les murs (« le mur nord ») ---------------------------

// Deux mesures (voir assistant/boussole.py) : le CAP de la caméra (absolu, faussé près du métal) et le LACET du
// gyroscope (cap de la caméra sans nord, mais juste pour les angles entre murs). Tous deux sont calculés par la matrice
// de rotation complète (web/boussole.js) : justes quand le téléphone est tenu droit. iPhone : le nord vient de
// webkitCompassHeading (cap du haut de l'appareil), recalé sur l'alpha relatif. Android récent : cap =
// « deviceorientationabsolute », lacet = « deviceorientation ». Android ancien : « deviceorientation » est absolu, il
// donne le cap seul.
const capteurs = { cap: null, lacet: null, precision: null, inclinaison: null, pose: null, dernierAbsolu: 0, ecarts: [], iphone: null };

function autoriserBoussole() {
  // iPhone : l'accès se demande pendant l'appui sur « Démarrer ». Refusé : l'assistant demandera l'orientation à l'oral.
  if (window.DeviceOrientationEvent && typeof DeviceOrientationEvent.requestPermission === "function") {
    DeviceOrientationEvent.requestPermission().catch(() => {});
  }
  // Le mouvement (pas) : une demande à part sur iPhone, dans le même appui.
  if (window.DeviceMotionEvent && typeof DeviceMotionEvent.requestPermission === "function") {
    DeviceMotionEvent.requestPermission().catch(() => {});
  }
  window.addEventListener("devicemotion", suivrePas);
  window.addEventListener("deviceorientationabsolute", (e) => {
    if (e.alpha == null) return;
    capteurs.cap = Boussole.capCamera(e.alpha, e.beta, e.gamma);
    capteurs.dernierAbsolu = performance.now();
    capteurs.inclinaison = e.beta;
  });
  window.addEventListener("deviceorientation", (e) => {
    if (e.alpha == null) return;
    noterOrientation(e); // le même repère que le lacet
    if (typeof e.webkitCompassHeading === "number" && !Number.isNaN(e.webkitCompassHeading)) {
      // iPhone : webkitCompassHeading suit le haut de l'appareil ; le cap de la caméra vient de la matrice complète.
      capteurs.iphone = capteurs.iphone || new Boussole.CapIphone(etat.reglagesBoussole.iphone.inclinaison_calibrage);
      capteurs.cap = capteurs.iphone.mesurer(e.alpha, e.beta, e.gamma, e.webkitCompassHeading);
      capteurs.precision = typeof e.webkitCompassAccuracy === "number" ? e.webkitCompassAccuracy : null;
      // Le gyroscope, dès le début (alpha relatif) : test du 23/10, iPhone tenu droit, aucun cap pendant 35 s, et rien
      // pour retrouver après coup le côté des murs filmés avant. Le serveur les recale dès que le nord est connu.
      capteurs.lacet = Boussole.capCamera(e.alpha, e.beta, e.gamma);
    } else if (e.absolute !== false && performance.now() - capteurs.dernierAbsolu > 2000) {
      capteurs.cap = Boussole.capCamera(e.alpha, e.beta, e.gamma); // Android ancien : orientation absolue
    }
    if (e.absolute === false) capteurs.lacet = Boussole.capCamera(e.alpha, e.beta, e.gamma); // gyroscope (sans nord)
    capteurs.inclinaison = e.beta;
    if (e.beta != null && e.gamma != null) capteurs.pose = Boussole.poseCamera(e.alpha, e.beta, e.gamma);
    if (etat.debut && !etat.termine) suivreRotation();
    noterCapteurs();
  });
  etat.minuteries.push(setInterval(afficherBoussole, 250));
}

function noterCapteurs() {
  // 20 mesures par seconde au plus, pendant la visite seulement.
  if (!etat.debut || etat.termine) return;
  const t = maintenant();
  const dernier = etat.capteursContinus[etat.capteursContinus.length - 1];
  if (dernier && t - dernier.t < 0.05) return;
  const arrondi = (x) => (x == null ? null : Math.round(x * 10) / 10);
  const pose = capteurs.pose || {};
  const mesure = { t: Math.round(t * 1000) / 1000, cap: arrondi(capteurs.cap), lacet: arrondi(capteurs.lacet),
                   precision: arrondi(capteurs.precision), inclinaison: arrondi(capteurs.inclinaison),
                   elevation: arrondi(pose.elevation), roulis: arrondi(pose.roulis), acc: arrondi(mouvement.acc) };
  const C = croquisSeul() ? positionTrace() : null;
  if (C && etat.xr8) {
    // La position du moteur de 8th Wall, et son état (NORMAL, LIMITED…) pour juger le suivi après la visite.
    Object.assign(mesure, { x: arrondiMm(C[0]), y: arrondiMm(C[1]), xr8: suivi.statut === "NORMAL" ? 1 : 0 });
  } else if (C && traceur.odo) {
    // La position suivie par le sol filmé, et de quoi juger le suivi après la visite (détails suivis, calcul, perdu).
    Object.assign(mesure, { x: arrondiMm(C[0]), y: arrondiMm(C[1]), vo_n: traceur.odo.details.length, vo_fige: traceur.fige ? 1 : 0,
                            vo_ms: Math.round(traceur.dureeMs), vo_perdu: traceur.odo.perdu ? 1 : 0 });
  }
  etat.capteursContinus.push(mesure);
  mouvement.lot.push(mesure); // envoyé en direct, par lots (étape 15)
}

function fiabiliteBoussole() {
  // Même règle que le serveur : précision annoncée (iPhone), sinon stabilité de « cap − lacet » sur les dernières secondes.
  if (capteurs.cap == null) return "absente";
  const r = etat.reglagesBoussole; // seuils de boussole.toml, envoyés par le serveur
  if (capteurs.precision != null) {
    return capteurs.precision < 0 || capteurs.precision > r.precision.faible ? "faible" : capteurs.precision > r.precision.bonne ? "moyenne" : "bonne";
  }
  if (capteurs.ecarts.length < 5) return "moyenne";
  const centre = capteurs.ecarts[capteurs.ecarts.length - 1];
  const dispersion = capteurs.ecarts.map((x) => Math.abs(((x - centre + 540) % 360) - 180)).sort((a, b) => a - b)[Math.floor(capteurs.ecarts.length / 2)];
  return dispersion > r.dispersion.faible ? "faible" : dispersion > r.dispersion.bonne ? "moyenne" : "bonne";
}

function afficherBoussole() {
  tournerVousIci();
  const bloc = $("boussole");
  const fiabilite = fiabiliteBoussole();
  bloc.className = `boussole ${fiabilite}`;
  if (capteurs.cap == null) {
    // iPhone : le nord se cale quand le haut du téléphone est presque à plat (webkitCompassHeading).
    $("cap").textContent = capteurs.lacet != null ? "nord : téléphone à plat 1 s" : "pas de boussole";
    $("calibrer").hidden = true;
    return;
  }
  const cap = Math.round(capteurs.cap) % 360;
  const points = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
  $("rose").style.transform = `rotate(${-cap}deg)`; // le N de la rose montre le nord
  $("cap").textContent = `${points[Math.round(cap / 45) % 8]} ${cap}°`;
  $("calibrer").hidden = fiabilite !== "faible";
}

function envoyerCapteurs(t) {
  // Une mesure par seconde, même vide : le serveur sait alors que le téléphone n'a pas de boussole.
  if (capteurs.cap != null && capteurs.lacet != null) capteurs.ecarts = [...capteurs.ecarts, capteurs.cap - capteurs.lacet].slice(-10);
  const arrondi = (x) => (x == null ? null : Math.round(x * 10) / 10);
  envoyerJson({ type: "capteurs", t, cap: arrondi(capteurs.cap), lacet: arrondi(capteurs.lacet), precision: arrondi(capteurs.precision),
                inclinaison: arrondi(capteurs.inclinaison) });
}

// --- Enregistrement local de la vidéo complète ------------------------------------------------

function demarrerEnregistrement(qualite) {
  if (!window.MediaRecorder) return;
  const types = ["video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"];
  etat.typeVideo = types.find((t) => MediaRecorder.isTypeSupported(t)) || "";
  const options = { videoBitsPerSecond: qualite === "1080" ? 8_000_000 : 5_000_000, audioBitsPerSecond: 128_000 };
  if (etat.typeVideo) options.mimeType = etat.typeVideo;
  etat.enregistreur = new MediaRecorder(etat.flux, options);
  etat.morceaux = [];
  etat.enregistreur.ondataavailable = (e) => e.data.size && etat.morceaux.push(e.data);
  etat.enregistreur.start(5000);
}

// --- Démarrage et fin ----------------------------------------------------------------------------

async function demarrer() {
  // Bouton grisé tant que la mission n'est pas choisie ; un second appui pendant l'ouverture de la caméra ne lance pas une
  // seconde visite (relecture du 23/10 : son doublé, caméra jamais éteinte).
  if (!etat.mission || etat.demarrage) return;
  etat.demarrage = true;
  debloquerVoix();
  autoriserBoussole();
  etat.code = $("code").value;
  const qualite = $("qualite").value;
  $("demarrer").disabled = true;
  const micro = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 };
  try {
    if (croquisSeul() && suivi) {
      // Le moteur de 8th Wall ouvre la caméra et dessine l'image ; sa vidéo est enregistrée avec le micro.
      try {
        $("visite").hidden = false;
        $("xr-toile").hidden = false;
        await suivi.demarrer($("xr-toile"), () => (capteurs.lacet != null ? capteurs.lacet : capteurs.cap));
        const son = await navigator.mediaDevices.getUserMedia({ audio: micro });
        etat.flux = new MediaStream([...suivi.flux.getVideoTracks(), ...son.getAudioTracks()]);
        etat.xr8 = true;
        suivi.surImage = () => { if (traceur.actif) dessinerTrace(); };
        $("credit-xr8").hidden = false;
      } catch (e) {
        console.warn("Suivi 8th Wall indisponible :", e);
        suivi.arreter();
        $("xr-toile").hidden = true;
        $("visite").hidden = true;
      }
    }
    if (!etat.xr8) {
      etat.flux = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: qualite === "1080" ? 1920 : 1280 }, height: { ideal: qualite === "1080" ? 1080 : 720 } },
        audio: micro,
      });
    }
  } catch (e) {
    etat.demarrage = false;
    $("demarrer").disabled = false;
    $("statut-serveur").textContent = `Caméra ou micro refusés (${e.name}). La page doit être ouverte en https et l'accès autorisé.`;
    return;
  }
  $("accueil").hidden = true;
  $("visite").hidden = false;
  $("piece-courante").textContent = croquisSeul() ? MISSIONS[etat.mission].titre : "DPE du logement";
  afficherCroquis(null);
  const video = $("camera");
  video.srcObject = etat.flux;
  await video.play().catch(() => {});
  etat.debut = performance.now();
  if ($("enregistrer").checked) demarrerEnregistrement(qualite);
  await demarrerSon();
  connecter();
  etat.minuteries.push(setInterval(chaqueSeconde, 1000));
  etat.minuteries.push(setInterval(envoyerMouvement, 250));
  suivreTrames();
  etat.minuteries.push(setInterval(() => ($("chrono").textContent = horodatage(maintenant())), 1000));
  try { etat.verrouEcran = await navigator.wakeLock.request("screen"); } catch { /* écran : réglage du téléphone */ }
}

function terminer() {
  if (!etat.arretDemande) {
    // 1er appui : l'assistant dit ce qui manque ; 2e appui : arrêt.
    etat.arretDemande = true;
    $("terminer").textContent = "Arrêter vraiment";
    envoyerJson({ type: "fin" });
    setTimeout(() => {
      if (etat.termine) return;
      etat.arretDemande = false;
      $("terminer").textContent = "Terminer";
    }, 20000);
    return;
  }
  arreter();
}

async function arreter() {
  if (etat.termine) return;
  etat.termine = true;
  etat.minuteries.forEach(clearInterval);
  couperVoix();
  if (etat.noeudAudio) etat.noeudAudio.disconnect();
  if (etat.verrouEcran) etat.verrouEcran.release().catch(() => {});
  const videoPrete = new Promise((resolve) => {
    if (!etat.enregistreur || etat.enregistreur.state === "inactive") return resolve();
    etat.enregistreur.onstop = resolve;
    etat.enregistreur.stop();
  });
  await videoPrete;
  etat.flux.getTracks().forEach((piste) => piste.stop());
  if (etat.xr8) suivi.arreter();
  if (etat.contexteAudio) etat.contexteAudio.close();
  let bilan = etat.bilan && etat.bilan.bilan;
  if (etat.session) {
    try {
      const r = await fetch(`/api/sessions/${etat.session}/terminer`, { method: "POST", headers: { "x-code": etat.code } });
      if (r.ok) bilan = await r.json();
    } catch { /* hors réseau : le bilan reste celui reçu en direct */ }
  }
  if (etat.liaison) etat.liaison.arreter();
  afficherFin(bilan);
}

function afficherFin(bilan) {
  $("visite").hidden = true;
  $("fin").hidden = false;
  const resume = $("resume");
  resume.replaceChildren();
  if (bilan && croquisSeul()) {
    // Amiante, plomb : les pièces du croquis (le remplissage du DPE n'a pas de sens ici).
    const noms = (bilan.pieces || []).map((p) => p.nom);
    resume.append(Object.assign(document.createElement("p"), { textContent: `Durée filmée : ${horodatage(bilan.duree_video_s)}.` }),
                  Object.assign(document.createElement("p"), { textContent: noms.length ? `Croquis : ${noms.length} pièce${noms.length > 1 ? "s" : ""} (${noms.join(", ")}).` : "Croquis vide : aucune pièce reconnue." }));
  } else if (bilan) {
    const lignes = [
      `Durée filmée : ${horodatage(bilan.duree_video_s)} — ${bilan.phrases} phrases, ${bilan.questions} questions, ${bilan.acceptees} valeurs notées, ${bilan.refusees} refusées.`,
      ...bilan.pieces.map((p) => `${p.nom} : ${Math.round(p.taux_remplissage * 100)} % rempli`),
    ];
    lignes.forEach((texte) => resume.append(Object.assign(document.createElement("p"), { textContent: texte })));
  }
  const manques = (etat.bilan && etat.bilan.manques) || [];
  $("titre-manques-fin").hidden = croquisSeul();
  $("manques-fin").replaceChildren(...manques.map((m) => Object.assign(document.createElement("li"), { textContent: `${m.piece} : ${m.libelle}` })));
  if (etat.morceaux.length) {
    const blob = new Blob(etat.morceaux, { type: etat.typeVideo || "video/webm" });
    const extension = (etat.typeVideo || "").includes("mp4") ? "mp4" : "webm";
    $("bloc-video").hidden = false;
    $("taille-video").textContent = `${(blob.size / 1e6).toFixed(1)} Mo (${extension}). Ne pas l'envoyer par WhatsApp : elle serait recompressée.`;
    $("telecharger").href = URL.createObjectURL(blob);
    $("telecharger").download = `visite-${etat.session || "locale"}.${extension}`;
    $("envoyer-video").onclick = () => envoyerVideo(blob);
    // Étape 12 : la vidéo complète part toute seule (le serveur en a besoin pour reconnaître les pièces et les murs) ;
    // le bouton reste pour réessayer.
    envoyerCapteursContinus().finally(() => envoyerVideo(blob));
  } else {
    envoyerCapteursContinus();
  }
}

function envoyerCapteursContinus() {
  if (!etat.session || !etat.capteursContinus.length) return Promise.resolve();
  return fetch(`/api/sessions/${etat.session}/capteurs`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-code": etat.code },
    body: JSON.stringify({ mesures: etat.capteursContinus }),
  }).catch(() => {});
}

function envoyerVideo(blob) {
  if (!etat.session) return;
  const xhr = new XMLHttpRequest(); // XMLHttpRequest : pour afficher la progression de l'envoi
  xhr.open("POST", `/api/sessions/${etat.session}/video`);
  xhr.setRequestHeader("content-type", blob.type);
  xhr.setRequestHeader("x-code", etat.code);
  $("progression").hidden = false;
  $("envoyer-video").disabled = true;
  xhr.upload.onprogress = (e) => e.lengthComputable && ($("progression").value = e.loaded / e.total);
  xhr.onload = () => ($("envoyer-video").textContent = xhr.status === 200 ? "Vidéo envoyée ✓" : `Échec (${xhr.status}) : réessayer`, $("envoyer-video").disabled = xhr.status === 200);
  xhr.onerror = () => { $("envoyer-video").textContent = "Échec : réessayer"; $("envoyer-video").disabled = false; };
  xhr.send(blob);
}

// --- Boutons ---------------------------------------------------------------------------------------

$("demarrer").onclick = demarrer;
// La version est revérifiée quand la page revient (Safari réaffiche parfois un onglet gardé en mémoire, sans le recharger).
const revoirStatut = () => { if (!document.hidden && !$("accueil").hidden) chargerStatut(); };
document.addEventListener("visibilitychange", revoirStatut);
window.addEventListener("pageshow", revoirStatut);
// Amiante, plomb : le grand croquis s'arrête au-dessus du bloc du bas (question, boutons), quelle que soit sa hauteur.
if (window.ResizeObserver) {
  const bas = document.querySelector(".bas");
  new ResizeObserver(() => document.body.style.setProperty("--bas", `${bas.offsetHeight}px`)).observe(bas);
}
for (const b of $("missions").querySelectorAll("button")) b.onclick = () => choisirMission(b.dataset.mission);
// Amiante, plomb : le bouton ouvre le plan (croquis en grand, corrections) ; DPE : la fiche du logement.
$("murs").onclick = () => {
  envoyerJson({ type: "trace", action: traceur.actif ? "fin" : "debut" });
  afficherTrace(!traceur.actif);
};
$("trace-point").onclick = validerCoin;
$("trace-annuler").onclick = () => envoyerJson({ type: "trace", action: "annuler" });
$("trace-fermer").onclick = () => {
  if (traceur.selection) {  // « ⇄ Recaler ici » : le coin touché est là où vise la croix ; tout le dessin suit
    const { cle, index } = traceur.selection;
    const p = traceur.pieces.find((q) => q.cle === cle);
    if (p && p.points[index] && traceur.vise) recaler(p.points[index], traceur.vise);
    traceur.selection = null;
    bip();
    majInfoTrace("Dessin recalé sur ce coin.");
    return;
  }
  fermerContour();
};
$("trace-toile").addEventListener("pointerdown", toucherTrace);

$("voir-fiche").onclick = () => {
  if (croquisSeul()) { $("plan").hidden = false; afficherCroquis(etat.croquis); return; }
  $("fiche").hidden = false;
  afficherFiche();
};
$("croquis").onclick = () => { $("plan").hidden = false; afficherCroquis(etat.croquis); };
$("fermer-plan").onclick = () => ($("plan").hidden = true);
$("fermer-fiche").onclick = () => ($("fiche").hidden = true);
$("terminer").onclick = terminer;
$("nouvelle").onclick = () => location.reload();
$("silence").onclick = () => {
  etat.muet = !etat.muet;
  $("silence").textContent = etat.muet ? "🔇 Assistant muet" : "🔈 Assistant actif";
  if (etat.muet) couperVoix();
  envoyerJson({ type: "silence", actif: etat.muet });
};
$("formulaire-texte").onsubmit = (e) => {
  e.preventDefault();
  const texte = $("texte").value.trim();
  if (texte) envoyerJson({ type: "texte", texte });
  $("texte").value = "";
};
window.addEventListener("beforeunload", (e) => { if (!etat.termine && etat.flux) e.preventDefault(); });
// Page cachée (écran verrouillé, autre application) : la caméra et les capteurs s'arrêtent ; le serveur le note.
document.addEventListener("visibilitychange", () => { if (etat.debut && !etat.termine) envoyerJson({ type: "visibilite", cachee: document.hidden }); });
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { /* certificat auto-signé : pas de service worker */ });
chargerStatut();
