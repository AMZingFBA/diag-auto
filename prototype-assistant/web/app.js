"use strict";
// Page du téléphone : filme, enregistre la vidéo complète en local, envoie au serveur le son
// (16 kHz) et une image par seconde, et lit à voix haute les questions de l'assistant.

const $ = (id) => document.getElementById(id);
const TAUX = 16000;
const TYPE_SON = 1;
const TYPE_IMAGE = 2;

const etat = {
  ws: null,
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
  minuteries: [],
  muet: false,
  termine: false,
  arretDemande: false,
  voix: null,
  verrouEcran: null,
  bilan: null,
  // Seuils de la boussole (boussole.toml) ; remplacés par ceux du serveur au chargement.
  reglagesBoussole: { precision: { bonne: 15, faible: 30 }, dispersion: { bonne: 12, faible: 25 }, iphone: { inclinaison_calibrage: 60 } },
};

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
    $("ligne-code").hidden = !s.code_requis;
    if (s.boussole) etat.reglagesBoussole = s.boussole;
  } catch {
    $("statut-serveur").textContent = "Serveur injoignable : vérifiez l'adresse et le Wi-Fi.";
  }
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
    envoyerJson({ type: "tts", etat: "debut", id });
  };
  u.onend = u.onerror = () => envoyerJson({ type: "tts", etat: "fin", id });
  speechSynthesis.speak(u);
  // Certains Android ne signalent pas le début de la voix : on le signale nous-mêmes.
  setTimeout(() => { if (!commence && speechSynthesis.speaking) envoyerJson({ type: "tts", etat: "debut", id }); }, 1500);
}

function couperVoix() {
  if ("speechSynthesis" in window && speechSynthesis.speaking) {
    speechSynthesis.cancel();
    envoyerJson({ type: "tts", etat: "fin" });
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

function envoyerJson(message) {
  if (etat.ws && etat.ws.readyState === WebSocket.OPEN) etat.ws.send(JSON.stringify(message));
}

function envoyerBinaire(type, t, donnees) {
  if (!etat.ws || etat.ws.readyState !== WebSocket.OPEN) return;
  if (etat.ws.bufferedAmount > 2_000_000) return; // réseau saturé : on saute plutôt que d'accumuler du retard
  const entete = new ArrayBuffer(9);
  const vue = new DataView(entete);
  vue.setUint8(0, type);
  vue.setFloat64(1, t, true);
  etat.ws.send(new Blob([entete, donnees]));
}

function connecter() {
  const protocole = location.protocol === "https:" ? "wss://" : "ws://";
  const code = etat.code ? `?code=${encodeURIComponent(etat.code)}` : "";
  const ws = new WebSocket(`${protocole}${location.host}/ws${code}`);
  ws.binaryType = "arraybuffer";
  etat.ws = ws;
  $("connexion").className = "pastille";
  ws.onopen = () => {
    $("connexion").className = "pastille ok";
    ws.send(JSON.stringify({ type: "debut", session: etat.session, piece: $("piece").value, appareil: navigator.userAgent }));
  };
  ws.onmessage = (e) => recevoir(JSON.parse(e.data));
  ws.onclose = (e) => {
    $("connexion").className = "pastille ko";
    if (e.code === 4401) return alerte("Code d'accès incorrect.");
    if (!etat.termine) {
      // Hors réseau : l'enregistrement local continue ; on retente la liaison.
      alerte("Hors réseau : l'enregistrement continue, l'assistant reprendra au retour du réseau.");
      setTimeout(() => { if (!etat.termine) connecter(); }, 2000);
    }
  };
}

function alerte(texte) {
  $("alerte").textContent = texte;
  $("alerte").hidden = !texte;
}

function recevoir(m) {
  switch (m.type) {
    case "statut":
      etat.session = m.session;
      alerte("");
      $("infos").textContent = `Visite ${m.session}${m.reprise ? " (reprise)" : ""} — cerveau : ${m.cerveau} — transcription : ${m.transcription}`;
      break;
    case "parole_debut":
      couperVoix(); // le diagnostiqueur reparle : l'assistant se tait aussitôt
      break;
    case "transcription":
      $("vous").textContent = `Vous (${horodatage(m.t)}) : « ${m.texte} »`;
      break;
    case "dire":
      // Réponse de Claude lue phrase par phrase (étape 7) : les phrases « suite » s'ajoutent à la précédente.
      $("question").textContent = m.suite ? `${$("question").textContent} ${m.texte}` : m.texte;
      // Vignette de l'élément concerné (« le mur affiché ») : l'image filmée quand il a été décrit.
      if (!m.suite || m.image) $("vignette").hidden = !m.image;
      if (m.image) $("vignette").src = m.image + (etat.code ? `?code=${encodeURIComponent(etat.code)}` : "");
      $("question").classList.toggle("muet", m.muet || etat.muet);
      $("question").hidden = false;
      if (!m.suite) $("latence").textContent = m.latence_s != null ? `Réponse ${secondes(m.latence_s)} après la fin de votre phrase` : "";
      if (!m.muet && !etat.muet) parler(m.texte, m.id, m.suite);
      break;
    case "bip":
      bip();
      if (m.latence_s != null) $("latence").textContent = `✓ Noté ${secondes(m.latence_s)} après la fin de votre phrase`;
      break;
    case "etat":
      majEtat(m);
      break;
    case "actions":
      majActions(m.resultats);
      break;
    case "erreur":
      alerte(m.message);
      setTimeout(() => alerte(""), 6000);
      break;
    case "bilan":
      etat.bilan = m; // l'arrêt reste décidé par le 2e appui sur « Terminer »
      break;
  }
}

function majEtat(m) {
  $("piece-courante").textContent = `Pièce : ${m.piece || "—"}`;
  $("taux").style.width = `${Math.round((m.taux || 0) * 100)}%`;
  const liste = $("manques");
  liste.replaceChildren(...m.manques.map((texte) => Object.assign(document.createElement("li"), { textContent: texte })));
  $("manques-titre").textContent = `Manques de la pièce (${m.manques.length}) — visite : ${m.nb_manques_visite}`;
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
    envoyerBinaire(TYPE_SON, t, pcm.buffer); // sans réseau, le bloc est perdu pour l'assistant, pas pour la vidéo
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

// --- Images (1 par seconde, ~512 px) --------------------------------------------------------

function envoyerImage() {
  const video = $("camera");
  if (!video.videoWidth || !etat.ws || etat.ws.readyState !== WebSocket.OPEN) return;
  const echelle = 512 / Math.max(video.videoWidth, video.videoHeight);
  const toile = envoyerImage.toile || (envoyerImage.toile = document.createElement("canvas"));
  toile.width = Math.round(video.videoWidth * echelle);
  toile.height = Math.round(video.videoHeight * echelle);
  toile.getContext("2d").drawImage(video, 0, 0, toile.width, toile.height);
  const t = maintenant();
  toile.toBlob((blob) => blob && envoyerBinaire(TYPE_IMAGE, t, blob), "image/jpeg", 0.7);
  envoyerCapteurs(t);
}

// --- Boussole : direction filmée, pour nommer les murs (« le mur nord ») ---------------------------

// Deux mesures (voir assistant/boussole.py) : le CAP de la caméra (absolu, faussé près du métal) et le LACET du
// gyroscope (cap de la caméra sans nord, mais juste pour les angles entre murs). Tous deux sont calculés par la matrice
// de rotation complète (web/boussole.js) : justes quand le téléphone est tenu droit. iPhone : le nord vient de
// webkitCompassHeading (cap du haut de l'appareil), recalé sur l'alpha relatif. Android récent : cap =
// « deviceorientationabsolute », lacet = « deviceorientation ». Android ancien : « deviceorientation » est absolu, il
// donne le cap seul.
const capteurs = { cap: null, lacet: null, precision: null, inclinaison: null, dernierAbsolu: 0, ecarts: [], iphone: null };

function autoriserBoussole() {
  // iPhone : l'accès se demande pendant l'appui sur « Démarrer ». Refusé : l'assistant demandera l'orientation à l'oral.
  if (window.DeviceOrientationEvent && typeof DeviceOrientationEvent.requestPermission === "function") {
    DeviceOrientationEvent.requestPermission().catch(() => {});
  }
  window.addEventListener("deviceorientationabsolute", (e) => {
    if (e.alpha == null) return;
    capteurs.cap = Boussole.capCamera(e.alpha, e.beta, e.gamma);
    capteurs.dernierAbsolu = performance.now();
    capteurs.inclinaison = e.beta;
  });
  window.addEventListener("deviceorientation", (e) => {
    if (e.alpha == null) return;
    if (typeof e.webkitCompassHeading === "number" && !Number.isNaN(e.webkitCompassHeading)) {
      // iPhone : webkitCompassHeading suit le haut de l'appareil ; le cap de la caméra vient de la matrice complète.
      capteurs.iphone = capteurs.iphone || new Boussole.CapIphone(etat.reglagesBoussole.iphone.inclinaison_calibrage);
      capteurs.cap = capteurs.iphone.mesurer(e.alpha, e.beta, e.gamma, e.webkitCompassHeading);
      capteurs.precision = typeof e.webkitCompassAccuracy === "number" ? e.webkitCompassAccuracy : null;
    } else if (e.absolute !== false && performance.now() - capteurs.dernierAbsolu > 2000) {
      capteurs.cap = Boussole.capCamera(e.alpha, e.beta, e.gamma); // Android ancien : orientation absolue
    }
    if (e.absolute === false) capteurs.lacet = Boussole.capCamera(e.alpha, e.beta, e.gamma); // gyroscope (sans nord)
    capteurs.inclinaison = e.beta;
  });
  etat.minuteries.push(setInterval(afficherBoussole, 250));
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
  const bloc = $("boussole");
  const fiabilite = fiabiliteBoussole();
  bloc.className = `boussole ${fiabilite}`;
  if (capteurs.cap == null) {
    $("cap").textContent = "pas de boussole";
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
  debloquerVoix();
  autoriserBoussole();
  etat.code = $("code").value;
  const qualite = $("qualite").value;
  $("demarrer").disabled = true;
  try {
    etat.flux = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: qualite === "1080" ? 1920 : 1280 }, height: { ideal: qualite === "1080" ? 1080 : 720 } },
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
  } catch (e) {
    $("demarrer").disabled = false;
    $("statut-serveur").textContent = `Caméra ou micro refusés (${e.name}). La page doit être ouverte en https et l'accès autorisé.`;
    return;
  }
  $("accueil").hidden = true;
  $("visite").hidden = false;
  const video = $("camera");
  video.srcObject = etat.flux;
  await video.play().catch(() => {});
  etat.debut = performance.now();
  if ($("enregistrer").checked) demarrerEnregistrement(qualite);
  await demarrerSon();
  connecter();
  etat.minuteries.push(setInterval(envoyerImage, 1000));
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
  if (etat.contexteAudio) etat.contexteAudio.close();
  let bilan = etat.bilan && etat.bilan.bilan;
  if (etat.session) {
    try {
      const r = await fetch(`/api/sessions/${etat.session}/terminer`, { method: "POST", headers: { "x-code": etat.code } });
      if (r.ok) bilan = await r.json();
    } catch { /* hors réseau : le bilan reste celui reçu en direct */ }
  }
  if (etat.ws) etat.ws.close();
  afficherFin(bilan);
}

function afficherFin(bilan) {
  $("visite").hidden = true;
  $("fin").hidden = false;
  const resume = $("resume");
  resume.replaceChildren();
  if (bilan) {
    const lignes = [
      `Durée filmée : ${horodatage(bilan.duree_video_s)} — ${bilan.phrases} phrases, ${bilan.questions} questions, ${bilan.acceptees} valeurs notées, ${bilan.refusees} refusées.`,
      ...bilan.pieces.map((p) => `${p.nom} : ${Math.round(p.taux_remplissage * 100)} % rempli`),
    ];
    lignes.forEach((texte) => resume.append(Object.assign(document.createElement("p"), { textContent: texte })));
  }
  const manques = (etat.bilan && etat.bilan.manques) || [];
  $("manques-fin").replaceChildren(...manques.map((m) => Object.assign(document.createElement("li"), { textContent: `${m.piece} : ${m.libelle}` })));
  if (etat.morceaux.length) {
    const blob = new Blob(etat.morceaux, { type: etat.typeVideo || "video/webm" });
    const extension = (etat.typeVideo || "").includes("mp4") ? "mp4" : "webm";
    $("bloc-video").hidden = false;
    $("taille-video").textContent = `${(blob.size / 1e6).toFixed(1)} Mo (${extension}). Ne pas l'envoyer par WhatsApp : elle serait recompressée.`;
    $("telecharger").href = URL.createObjectURL(blob);
    $("telecharger").download = `visite-${etat.session || "locale"}.${extension}`;
    $("envoyer-video").onclick = () => envoyerVideo(blob);
  }
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
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { /* certificat auto-signé : pas de service worker */ });
chargerStatut();
