"use strict";
// Page du téléphone : filme, enregistre la vidéo complète en local, envoie au serveur le son
// (16 kHz) et une image par seconde, et lit à voix haute les questions de l'assistant.

// Version de la page, comparée à celle du serveur (test du 23/10 : l'iPhone gardait l'ancienne page en mémoire).
const VERSION_PAGE = "2026-10-23-3";
const $ = (id) => document.getElementById(id);
const TAUX = 16000;
const TYPE_SON = 1;
const TYPE_IMAGE = 2;

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
    if (s.version_page && s.version_page !== VERSION_PAGE) {
      $("statut-serveur").textContent = "Nouvelle version de l'assistant : rechargez la page (tirez vers le bas) avant de commencer.";
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
    debut: (coupures) => ({ type: "debut", session: etat.session, piece: $("piece").value, appareil: navigator.userAgent, coupures }),
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
      if (!m.suite) $("latence").textContent = m.latence_s != null ? `Réponse ${secondes(m.latence_s)} après la fin de votre phrase` : "";
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

// Étape 13 : le DPE décrit le logement (ses côtés, ses équipements), pas une pièce ; la pièce dite n'est qu'un repère.
function majEtat(m) {
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

function afficherChoix(cible, options) {
  boutonsReponse($("choix"), options, (o) => envoyerJson({ type: "reponse", cible, valeur: o.valeur, libelle: o.libelle, saisie: o.saisie, t: maintenant() }));
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

// --- Images (1 par seconde, ~512 px) --------------------------------------------------------

function envoyerImage() {
  const video = $("camera");
  if (!video.videoWidth || !etat.liaison) return;
  const echelle = 512 / Math.max(video.videoWidth, video.videoHeight);
  const toile = envoyerImage.toile || (envoyerImage.toile = document.createElement("canvas"));
  toile.width = Math.round(video.videoWidth * echelle);
  toile.height = Math.round(video.videoHeight * echelle);
  toile.getContext("2d").drawImage(video, 0, 0, toile.width, toile.height);
  const t = maintenant();
  // Pendant une coupure, une image sur trois est gardée pour le rattrapage (le son, lui, est gardé en entier).
  const garder = etat.liaison.ouverte() || etat.images++ % 3 === 0;
  toile.toBlob((blob) => blob && envoyerBinaire(TYPE_IMAGE, t, blob, garder), "image/jpeg", 0.7);
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
      // Le gyroscope, dès le début (alpha relatif) : test du 23/10, iPhone tenu droit, aucun cap pendant 35 s, et rien
      // pour retrouver après coup le côté des murs filmés avant. Le serveur les recale dès que le nord est connu.
      capteurs.lacet = Boussole.capCamera(e.alpha, e.beta, e.gamma);
    } else if (e.absolute !== false && performance.now() - capteurs.dernierAbsolu > 2000) {
      capteurs.cap = Boussole.capCamera(e.alpha, e.beta, e.gamma); // Android ancien : orientation absolue
    }
    if (e.absolute === false) capteurs.lacet = Boussole.capCamera(e.alpha, e.beta, e.gamma); // gyroscope (sans nord)
    capteurs.inclinaison = e.beta;
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
  etat.capteursContinus.push({ t: Math.round(t * 1000) / 1000, cap: arrondi(capteurs.cap), lacet: arrondi(capteurs.lacet),
                               precision: arrondi(capteurs.precision), inclinaison: arrondi(capteurs.inclinaison) });
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
  if (etat.liaison) etat.liaison.arreter();
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
$("voir-fiche").onclick = () => { $("fiche").hidden = false; afficherFiche(); };
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
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { /* certificat auto-signé : pas de service worker */ });
chargerStatut();
