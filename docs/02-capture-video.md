# DiagAuto — 02. Capture terrain par vidéo continue (tout téléphone, calcul serveur)

*Version du 22/10/2026 (5e). Elle intègre le retour de Noah sur le 1er test vidéo (`samples/video-001`) et l'assistant vocal en direct avec Claude comme cerveau (§ 3.6). Complète [01-cadrage.md](01-cadrage.md) ; liste des données : [checklist-dpe.md](checklist-dpe.md) ; fiche de tournage : [protocole-tournage.md](protocole-tournage.md).*

## Le principe

1. **Une seule vidéo continue de tout le logement**, sur n'importe quel téléphone, même ancien et sans LiDAR.
   - Le diagnostiqueur se déplace librement : il peut sortir d'une pièce et **y revenir plus tard**.
   - Le système reconnaît que c'est la même pièce et fusionne les informations. **Il ne crée jamais deux pièces pour le même espace.**
2. **Il parle en filmant** (« ce mur, c'est de la brique 30 »). Chaque phrase est **rattachée automatiquement au mur ou à l'élément visé à cet instant**.
3. **Rapide** : on entre, on balaie, on dit « ce mur c'est ça », on tourne, on repasse si on a oublié quelque chose.
   - Pas de procédure par pièce, pas de bouton, **pas de mesure dictée obligatoire** : l'échelle vient de la reconstruction et de références.
   - Exception : le Carrez, où la mesure laser reste la référence légale (§ 4).
4. **Tout le calcul est fait sur notre serveur**, avec des briques open source à licence compatible avec un usage commercial.
5. **Assistant vocal en direct** (demande de Noah, § 3.6) :
   - Pendant le tournage, une IA regarde le flux et parle au diagnostiqueur, dans une oreillette.
   - Elle pose les questions manquantes (« ce mur avec la télé, quelle épaisseur ? ») et signale ce qui manque (« il manque l'isolation d'un mur de la chambre 1 »).
   - Elle **ne fait que poser des questions et noter les réponses**, elle n'affirme rien d'invisible.
   - **Cerveau : Claude (API Anthropic)**, avec nos propres briques voix (transcription et synthèse vocale) sur notre serveur.
   - Le calcul 3D lourd reste fait ensuite sur le serveur.
6. Ensuite viennent, comme avant :
   - les données administratives (devis + API RNB, IGN, BDNB, DPE ADEME) ;
   - l'écran de validation avec preuves ;
   - la sortie vers LICIEL (`diagauto.liciel_xml`).

### Ce que le 1er test (`video-001`) nous apprend

| Constat | Conséquence |
|---|---|
| Vidéo passée par WhatsApp : 576×1024, 1,3 Mbit/s, recompressée | **Ne jamais passer par une messagerie.** Capture par notre application web (ou fichier original de l'appareil photo), au moins 720p et environ 8 Mbit/s. |
| Aucune donnée de capteurs (boussole, gyroscope) dans le fichier | Les capteurs ne seront disponibles qu'avec notre application web. **Le système doit quand même marcher sans eux** (cas V1). |
| Mouvement rapide, caméra penchée | L'inclinaison n'est pas gênante pour la reconstruction ; la **vitesse** l'est (images floues). Prévoir un retour en direct (vibration « plus lentement »). |
| Transcription : « ça se meurt là » (ce mur-là), « parpin » (parpaing), « VMCE » | Lexique métier imposé à la transcription + correction automatique (« parpin » → parpaing) avant l'extraction. |
| Mesures orales confuses (« 80 mètres, 20 mètres, 28 mètres… ») | Confirme qu'il **ne faut pas dépendre des mesures dictées**. Les chiffres dits sont des propositions à confirmer, jamais des vérités. |

## 1. Parcours utilisateur

| Moment | Le diagnostiqueur | Le système |
|---|---|---|
| **Devis** | Rien. | Pré-remplit l'administratif depuis le devis et les API publiques. |
| **Arrivée** (1–2 min) | Ouvre le lien du dossier et confirme adresse, bâtiment, type et année. Lance **une seule** vidéo. | Enregistre vidéo, voix et capteurs. |
| **Visite** (5 à 15 min de film) | Marche dans le logement en balayant les murs, sans s'arrêter. Parle quand il veut : « ici c'est la cuisine », « ce mur parpaing 20, isolé par l'intérieur », « celui-là donne sur le garage », « la chaudière ». S'approche des plaques signalétiques 2 secondes. Repasse dans une pièce s'il a oublié quelque chose. **Répond à voix haute aux questions de l'assistant**, entendues dans l'oreillette. | Le téléphone vibre si le mouvement est trop rapide. **L'assistant en direct** demande les informations manquantes pour la pièce en cours, et rappelle les oublis avant qu'on la quitte (« avant de sortir : le vitrage de la fenêtre ? »). |
| **Fin de visite** | Arrête la vidéo. | Envoi reprenable dès que le réseau est là. |
| **Validation** (5–10 min, sur place ou au bureau) | Vérifie le plan proposé (pièces, murs, ouvertures) et traite les valeurs orange et rouges. Chaque valeur est montrée avec l'image du moment et la phrase dite. | Bloque l'envoi tant qu'une donnée obligatoire manque. Garde la trace des validations. |
| **Au bureau** | Relit dans LICIEL, édite le rapport. | Génère les tables LICIEL. |

## 2. Donnée par donnée

Légende :
- **A** = automatique, affiché pour contrôle ;
- **C** = proposé à confirmer ;
- **D** = dit pendant le film (rattaché à l'élément visé) ;
- **P** = photo ou justificatif.

**Une donnée invisible non dite reste vide : l'IA ne la devine jamais.**

| Donnée (checklist DPE) | Statut | Source |
|---|---|---|
| **Administratif** : adresse, RNB, propriétaire, type, année, ancien DPE | C | Devis + API publiques (BAN, RNB, BDNB, DPE ADEME) |
| Altitude | A | IGN |
| Consentement | C | Case cochée sur place |
| **Pièces** : nombre, contours, noms | A → C | Carte 3D découpée en pièces. Nom dit (« ici la cuisine ») ou reconnu à l'image. |
| Surface par pièce (DPE), hauteur sous plafond | A → C | Reconstruction + échelle (§ 3.3). Rampants à confirmer. |
| **Surface Carrez / Boutin** | **D** (laser) + contrôle A | Mesure laser, référence légale : écran du télémètre filmé 1 s (lecture automatique) ou dicté. La vidéo contrôle la cohérence et fournit le plan. |
| Étage, mitoyennetés (dessus, dessous, côtés chauffés ?) | D | Voix |
| Nb de logements, surface du bâtiment | C | BDNB |
| Inertie | C | Déduite des matériaux dits |
| **Murs** : surface nette, longueur, hauteur | A → C | Reconstruction |
| Orientation | A → C | Boussole si disponible. Sinon, recalage du plan sur l'emprise du bâtiment (RNB / cadastre). Le secteur N/S/E/O suffit. |
| Donne sur extérieur / local non chauffé / local chauffé | A → C + D | Mur commun à deux pièces de la carte = intérieur. Type de local non chauffé : voix. |
| Matériau, épaisseur, isolation | D + P | Voix rattachée au mur (« ce mur brique 30 ») ; épaisseur proposée par la profondeur d'embrasure. |
| **Plafonds, planchers bas** : surfaces, périmètre sur l'extérieur | A | Reconstruction |
| Plafonds, planchers bas : donne sur, structure, isolation | D + P | Voix, images des combles ou du sous-sol |
| **Fenêtres, portes** : nombre, dimensions, mur, orientation | A → C | Détection sur les images + carte 3D |
| Menuiserie, volets, double fenêtre, type de porte | C | Reconnaissance d'image |
| Vitrage, lame d'air, gaz, dormant | C / D | Image si lisible, sinon voix |
| Masques, vérandas | C + D | Vidéo extérieure + voix |
| **Ponts thermiques** : longueurs par type de jonction | A → C | Calcul sur le plan 3D |
| **Chauffage, eau chaude, climatisation, ventilation** : type, marque, modèle, année, puissance, volume | C + P | Plaques filmées de près (lecture du texte + IA), reconnaissance des émetteurs, splits, bouches |
| Régulation, réseau isolé, température, veilleuse, années non lisibles | D / C | Voix, image |
| PAC air/air : aussi comptée en climatisation | A | Règle rappelée dans checklist-dpe.md |
| Photovoltaïque | C / D | Vidéo extérieure, voix |
| **Justificatifs** : photos | A | Images extraites de la vidéo, aux bons instants |

Les conventions de mesure 3CL-2021 sont appliquées par le moteur de conversion d'après le texte officiel, sans approximation maison.

## 3. Architecture

```
Vidéo continue + audio (+ capteurs si application web)
  │
  ├─ 1. Carte 3D globale : SLAM visuel + reconnaissance de lieu + fermeture de boucle
  │        → trajectoire de la caméra à chaque instant + nuage de points / maillage, UN seul repère
  ├─ 2. Mise à l'échelle : profondeur métrique + objets de taille connue + capteurs (+ laser si fourni)
  ├─ 3. Structure : sol / plafonds / murs (plans) → découpage en PIÈCES sur la carte
  │        → ouvertures (portes, fenêtres) projetées sur les murs → plan coté, surfaces, jonctions
  ├─ 4. Voix : transcription horodatée au mot → énoncés (référent + attributs)
  │        → ANCRAGE : instant de la phrase → position caméra → élément visé
  ├─ 5. Vision : équipements, plaques (lecture du texte), menuiseries
  └─ 6. JSON « Dossier terrain v1 » (valeur + source + confiance + preuve) → validation → LICIEL
```

Le traitement est fait **après coup, sur le serveur**, et non en temps réel sur le téléphone. On peut donc utiliser des méthodes lourdes et précises : ajustement global de toute la trajectoire, recherche de toutes les paires d'images qui se ressemblent.

### 3.1 Carte 3D unique, revisites et fermeture de boucle

**Objectif** : une seule carte cohérente, même si le diagnostiqueur sort d'une pièce et y revient 5 minutes plus tard. Il faut donc :
- une **reconnaissance de lieu** : « cette image ressemble à une image déjà vue » ;
- une **fermeture de boucle** : la trajectoire est recalée pour que les deux passages tombent au même endroit.

| Option | Principe | Licence | Usage proposé |
|---|---|---|---|
| **COLMAP / GLOMAP** + recherche d'images similaires (arbre de vocabulaire COLMAP) | Reconstruction hors ligne de toute la vidéo, appariement des images proches dans le temps **et** des images similaires lointaines (revisites), puis ajustement global | BSD | **Point de départ de V1** : le plus simple, très précis quand les images sont nettes et texturées |
| **DROID-SLAM** (et variantes à fermeture de boucle type DPV-SLAM) | SLAM appris, robuste au flou et aux murs peu texturés, exige un GPU | BSD pour DROID-SLAM ; variantes à vérifier | **Alternative robuste**, à comparer en V1 |
| **ORB-SLAM3** | SLAM classique. Gère la perte de suivi en créant plusieurs cartes qu'il **fusionne quand il reconnaît un lieu** (cas exact « je sors et je reviens »). Visuel-inertiel possible avec les capteurs. | GPL v3 : utilisable sur serveur, mais pas dans un produit distribué | **Référence de comparaison** |
| **MASt3R-SLAM** | Très robuste sur scènes difficiles (modèle 3D appris) | Non commerciale (héritée de MASt3R), à confirmer | **Référence de recherche uniquement**, pas pour le produit sans accord de licence |
| Appariement d'images | LightGlue (Apache-2.0) avec des points d'intérêt à licence ouverte | | SuperPoint/SuperGlue sont non commerciaux : **à éviter** |

**Garde-fou contre la « fausse fusion »** : deux chambres identiques peuvent se ressembler.
- Toute fermeture de boucle est **vérifiée géométriquement** et doit être cohérente avec la trajectoire.
- En cas de doute, l'écran de validation pose la question : « Chambre 1 (passage à 2:10) = Chambre 1 (passage à 6:40) ? ».
- Le système préfère **demander** plutôt que fusionner à tort.

### 3.2 Découpage en pièces sur la carte (et non dans le temps)

Une pièce est une **zone de l'espace**, pas un morceau de vidéo. Les revisites tombent donc naturellement dans la même pièce. Étapes :
1. Plan(s) du sol par niveau, puis projection des murs en 2D (carte vue de dessus).
2. Détection des **portes et passages** (images + carte), puis découpage de l'espace libre en zones fermées par les murs et les portes.
3. Contrôle par la trajectoire : chaque passage de porte doit correspondre à un changement de pièce.
4. Nom de la pièce : phrase dite pendant que la caméra y est (« ici la cuisine »), sinon reconnaissance à l'image (évier, lit, baignoire), sinon « Pièce n ».
5. Murs communs à deux pièces = parois intérieures. Les autres murs sont proposés « extérieur ou local non chauffé », à confirmer.

### 3.3 Échelle sans mesure obligatoire

Rappel : une erreur d'échelle de 2 % donne environ 4 % d'erreur sur les surfaces. Plusieurs sources indépendantes sont combinées (médiane robuste) avec un indice de confiance :

| Source | Remarque |
|---|---|
| **Profondeur métrique** estimée image par image, moyennée sur des centaines d'images | Modèles à licence à vérifier un par un (Depth Anything V2 Small est en Apache-2.0 ; d'autres sont non commerciaux) |
| **Objets de taille connue** | Hauteur des portes standard, plaques d'interrupteurs et de prises, carrelage, éventuelle feuille A4 posée là. On prend la médiane sur tous les objets trouvés. |
| **Capteurs du téléphone** (accéléromètre + gyroscope via l'application web) | Donnent l'échelle par calcul visuel-inertiel. Imprécis dans un navigateur, mais utile en complément. |
| **Mesure laser** (si filmée ou dite) | Facultative pour le DPE. Utilisée si présente, et **demandée seulement si la confiance est trop basse**. |

**On ne sait pas encore si l'on atteint 3 à 5 % sans aucune mesure : c'est précisément ce que V1 doit mesurer.**

### 3.4 Rattacher chaque phrase au bon élément (ancrage)

1. **Transcription** horodatée au mot (faster-whisper, MIT), avec lexique métier imposé (parpaing, VMC, ITE, laine de verre, hygro B…) et correction des confusions connues (« ce meurt-là » → « ce mur-là »).
2. **Découpage en énoncés** par un modèle de langage avec schéma imposé : *référent* + *attributs* + *instant du mot qui désigne*. Exemple : « celui-ci du bois de 20 cm » donne référent = « celui-ci » (type mur, déduit du contexte) ; matériau = bois ; épaisseur = 20 cm ; instant = 0:14,2.
3. **Résolution géométrique** : à l'instant du mot désignant (± 0,5 s), on connaît la position de la caméra et donc les éléments visibles. Chaque candidat reçoit une note qui combine :
   - sa position au centre de l'image ;
   - la durée pendant laquelle il est visé ;
   - la compatibilité de type (une « fenêtre » ne peut pas être un mur).

   Selon la façon dont l'élément est désigné :

   | Désignation | Règle |
   |---|---|
   | « ce mur », « celui-ci », « celui-là » | L'élément le plus central à l'instant du mot. |
   | « le deuxième mur » | Ordre de balayage depuis l'entrée dans la pièce. Si c'est ambigu : **orange**. |
   | « à gauche », « à droite », « en face », « au fond » | Par rapport à la direction de la caméra. |
   | « pareil pour celui-là » | Recopie les attributs de l'énoncé précédent. |
   | « la chaudière », « la fenêtre » | L'élément de ce type le plus proche dans l'image. |

4. **Fusion entre passages** : ce qui est dit lors d'une revisite s'ajoute au même élément. Une **contradiction** (brique 30 au 1er passage, parpaing 40 au 2e, sur le même mur) passe **en rouge** à trancher.
5. **Preuve** : sur l'écran de validation, chaque attribut affiche l'image de l'instant avec l'élément surligné et l'extrait audio. Le diagnostiqueur corrige d'un geste.

### 3.5 Autres briques (inchangées)

| Brique | Choix |
|---|---|
| **Capture** | PWA : `MediaRecorder` (au moins 720p, environ 8 Mbit/s), `DeviceOrientation` / `DeviceMotion` horodatés, stockage local, envoi reprenable (tus). Retour en direct : vibration si trop rapide. |
| **Fenêtres et portes** | Grounding DINO ou OWLv2 + SAM 2 (Apache-2.0), projetés sur les murs de la carte. |
| **Plans** | Open3D (MIT) : plans RANSAC, hypothèse d'angles droits quand elle est plausible, plan coté SVG/PDF. |
| **Plaques** | PaddleOCR (Apache-2.0), puis modèle vision-langage (ouvert ou API selon Q3). |
| **Serveur** | Python (FastAPI) + file de tâches + GPU à la demande + stockage objet, hébergé en France ou dans l'UE. |
| **Format intermédiaire** | JSON « Dossier terrain v1 » : chaque valeur avec source, confiance, statut et preuve (instant vidéo, élément, extrait audio). |

### 3.6 Assistant vocal en direct pendant le tournage

**Rôle.** L'assistant voit le flux, à 1 image par seconde, et entend le diagnostiqueur. Il :
- **pose les questions manquantes** sur ce qui est filmé, une à la fois et brièvement, sans couper la parole ;
- **note les réponses** (« 10 cm ») avec leur horodatage ;
- **signale les oublis** de la pièce en cours avant qu'on la quitte, et ceux du logement avant d'arrêter le film.

Il **n'affirme jamais** une donnée invisible (« ce mur fait 20 cm ») : il demande. Les réponses restent des valeurs « proposées », avec l'extrait audio comme preuve, et passent par l'écran de validation.

**Décision de Noah (22/10/2026) : le cerveau est Claude (API Anthropic).** Pas de Gemini ni d'OpenAI. L'API Claude n'a pas de mode voix ou vidéo temps réel : elle reçoit du texte et des images, et répond en texte, en continu (« streaming »). On construit donc **une chaîne** : nos briques voix (open source, sur notre serveur) + Claude pour comprendre et décider.

**Architecture temps réel en chaîne**

```
Téléphone (PWA)
 ├─ Enregistrement LOCAL haute qualité (1080p + audio + capteurs) ──► envoi après coup ──► chaîne 3D serveur (§ 3.1–3.5)
 └─ Flux LIVE léger vers NOTRE serveur (WebSocket, ou WebRTC en V2) : audio 16 kHz en continu + 1 image/s (JPEG ~500 px)
        ▼
 NOTRE serveur (France ou UE)
   1. Détection de fin de phrase (VAD)
   2. Transcription de la phrase (faster-whisper, lexique métier)
   3. Images : celle de l'instant de la phrase + 1 ou 2 images précédentes, parmi les images reçues à 1 par seconde
   4. Claude Haiku 5.5, en streaming : vision + transcription + état checklist (préfixe en cache)
         ├─ outils → « état checklist » du dossier (enregistrer_reponse, piece_courante…)
         └─ texte court (question suivante)
   5. Synthèse vocale française de la 1re phrase dès qu'elle est écrite (Piper ou autre, sur notre serveur)
        ▼
 Oreillette du diagnostiqueur
```

Deux types d'appels à Claude :

| Appel | Quand | Ce que fait Claude |
|---|---|---|
| **Réponse** | Juste après une phrase du diagnostiqueur | Enregistre les valeurs dites (outil, avec citation). Pose éventuellement **une** question courte. Une confirmation « noté » est rendue par un **bip**, pas par une phrase, pour gagner du temps. |
| **Veille** | En tâche de fond, toutes les ~10 s et à chaque changement de pièce | Regarde les dernières images et ce qui manque, et **met une question en attente**. Elle est posée au prochain silence, jamais en coupant la parole. |

**Analyse finale** (après envoi de la vidéo complète) : un modèle plus fort, **Claude Sonnet 5.5** (ou **Opus 5.5** pour les cas difficiles), consolide la transcription complète, les images clés et l'ancrage 3D. Il prépare l'écran de validation et les questions a posteriori. Ce traitement n'est pas urgent : l'API par lots (−50 %) est possible.

**Briques voix recommandées** (licences vérifiées sur les pages officielles le 22/10/2026)

| Brique | Choix | Licence / remarque |
|---|---|---|
| Orchestration de la chaîne | **Pipecat** (open source, a déjà des modules VAD, Whisper, Anthropic, Piper) ou code maison léger pour V1bis | Licence à confirmer avant usage commercial |
| Fin de phrase (VAD) | **Silero VAD** (< 1 ms par segment de 30 ms sur un cœur de processeur) | Fichier LICENSE : MIT ; mais le badge du README indique CC BY-NC : **à lever avant usage commercial**. Alternative : VAD de WebRTC. |
| Transcription | **faster-whisper** (MIT) + modèle **whisper-large-v3-turbo** (MIT, bien plus rapide que large-v3, qualité légèrement moindre). Transcription phrase par phrase, découpée par la VAD. | Alternative française : **Voxtral Mini 3B** (Mistral, Apache-2.0, environ 9,5 Go de GPU). |
| Synthèse vocale française | **Piper** avec la voix **fr_FR-siwis** (données CC BY 4.0, attribution). Rapide sur processeur. | Le moteur MIT d'origine est archivé ; la suite est sous GPL-3.0 (utilisable sur notre serveur, pas dans une app distribuée). Éviter fr_FR-tom (AGPLv3). Alternatives : **Kokoro** (Apache-2.0, une seule voix française), **MeloTTS** (code MIT, licence des voix à vérifier). |
| Cerveau live | **Claude Haiku 5.5** (`claude-haiku-5-5`), le plus rapide de la gamme, avec vision et outils | |
| Cerveau analyse finale | **Claude Sonnet 5.5** (`claude-sonnet-5-5`), ou **Opus 5.5** (`claude-opus-5-5`) | |

**Atout pour la confidentialité** : la **voix ne quitte pas notre serveur**, puisque la transcription est faite chez nous. Seuls du texte et des images réduites sont envoyés à Anthropic.

**Budget de latence** (objectif : **2 à 4 s** entre la fin de la phrase et le début de la réponse ; ce sont des estimations à **mesurer en V1bis**, aucun chiffre officiel)

| Étape | Estimation | Comment réduire |
|---|---|---|
| Détection de la fin de phrase | 0,5 à 0,8 s de silence | Seuil réglable. Trop court, l'IA coupe la parole. |
| Envoi de l'audio | 0,1 à 0,3 s | Audio envoyé en continu pendant que le diagnostiqueur parle. |
| Transcription d'une phrase de 2 à 5 s | GPU : ~0,2 à 0,5 s ; processeur seul : ~1 à 3 s | Modèle turbo, calcul en int8, lexique métier. |
| Claude Haiku 5.5 : premiers mots | ~0,5 à 1,5 s | Préfixe en cache. Images petites et préparées à l'avance. Réponse courte, en streaming. |
| Synthèse de la 1re phrase + lecture | ~0,2 à 0,6 s | Synthèse phrase par phrase pendant que Claude continue d'écrire. |
| **Total** | **≈ 1,5 à 3,5 s avec GPU ; ≈ 3 à 6 s sur processeur seul** | |

Les questions de « veille » sont préparées à l'avance : elles ne subissent pas cette latence. Si le diagnostiqueur reparle pendant que l'IA parle, la voix de l'IA s'arrête aussitôt.

**La checklist DPE comme état partagé**

| Règle | Détail |
|---|---|
| **C'est notre serveur qui sait ce qui manque, pas l'IA** | Moteur déterministe : à partir de la checklist (docs/checklist-dpe.md) et de l'état courant, il calcule les champs manquants pour la pièce en cours, par priorité. |
| Outils exposés à l'IA | `piece_courante(nom)`, `enregistrer_reponse(element_decrit, champ, valeur, citation)`, `champs_manquants(piece)`, `marquer_sans_objet(champ)`. |
| Rôle de l'IA | Formuler la question suivante naturellement (« et ce mur avec la télé, il fait quelle épaisseur ? ») et appeler `enregistrer_reponse` avec la citation exacte. |
| Garde-fous dans les consignes | Une question à la fois. Ne pas couper la parole. Nombre maximal de questions par minute. **Jamais de valeur sans citation du diagnostiqueur.** |

**Cohabitation avec le traitement 3D**

| Sujet | Fonctionnement |
|---|---|
| Ce que l'assistant comprend en direct | Il ne connaît que ce qu'on lui **dit** et ce qu'il **voit** : la pièce (« chambre 1 ») et une description de l'élément (« le mur avec la télé »). Il n'a **pas** de carte 3D. |
| Rattachement définitif | Chaque réponse est enregistrée **avec son horodatage**. Après coup, l'ancrage du § 3.4 la rattache au **vrai mur de la carte 3D**, comme une phrase spontanée. Si la description de l'assistant et l'ancrage géométrique ne concordent pas : **orange**. |
| Ce qui reste au serveur | Couverture géométrique (« 2 murs non vus »), surfaces, plan : le serveur, après coup. En direct, l'assistant ne vérifie que la **complétude des informations** (checklist). |
| Voix de l'IA dans l'enregistrement | Elle risque de polluer la transcription. Parade : oreillette conseillée, annulation d'écho du navigateur, et retrait des phrases de l'IA (dont on connaît le texte et l'horodatage) avant la transcription finale. |

**Mode hors réseau** (cave, combles, zone blanche)

| Moment | Fonctionnement |
|---|---|
| Pendant le tournage | L'enregistrement local continue, rien n'est perdu. L'assistant se tait et reprend au retour du réseau avec l'état à jour. |
| Après envoi | Le serveur calcule les manques sur la vidéo complète. Il produit une **liste de questions a posteriori**, chacune avec l'image concernée. Le diagnostiqueur y répond à la voix ou au doigt sur l'écran de validation, ou retourne filmer s'il est encore sur place. |

## 4. Précision et risques

| Sujet | Risque | Parade |
|---|---|---|
| **Carrez / Boutin** | Une erreur de plus de 5 % ouvre droit à une baisse du prix. La vidéo seule (3–5 %) ne suffit pas. | Mesure laser = référence : écran du télémètre filmé (lecture automatique, rattaché à la pièce par l'ancrage) ou dicté. La vidéo fournit le plan et le contrôle de cohérence. |
| **DPE** | Peu sensible à quelques %, très sensible aux erreurs de classement. | Invisible = dit, jamais deviné. Preuve visible. Validation explicite. |
| Perte de suivi (mouvement rapide, flou, murs blancs, miroirs, pièce sombre) | Carte morcelée. | SLAM robuste (DROID-SLAM), fusion des cartes partielles par reconnaissance de lieu. Vibration « plus lentement ». Lumières allumées. Une pièce non reconstruite est **signalée** (à refilmer), jamais inventée. |
| **Fausse fusion** de deux pièces semblables | Deux chambres fusionnées en une. | Vérification géométrique et temporelle, question posée en cas de doute. |
| **Pièce comptée deux fois** (boucle non fermée) | Doublon. | Détection des doublons probables (ressemblance + dimensions + trajectoire), question posée, **jamais de création silencieuse**. |
| **Mauvais rattachement d'une phrase** | Attribut posé sur le mauvais mur. | Note de confiance, orange si ambigu, image et audio montrés à la validation. Mesuré en V1. |
| Transcription | Erreurs de mots métier et de chiffres (cf. video-001). | Lexique imposé, correction, chiffres toujours « à confirmer ». |
| Échelle sans mesure | Précision non prouvée. | Plusieurs sources combinées, confiance affichée, mesure demandée seulement si nécessaire. **Mesuré en V1.** |
| Messagerie (WhatsApp) | Vidéo dégradée, capteurs perdus. | Envoi uniquement par notre application ou en fichier original. |
| Calcul | Vidéo de 10 min traitée en plusieurs dizaines de minutes. | GPU à la demande. Résultats disponibles pour la validation au bureau si besoin. |
| Licences | Plusieurs briques de pointe sont non commerciales (MASt3R-SLAM, SuperGlue…) ou GPL (ORB-SLAM3). | Liste blanche (MIT, BSD, Apache-2.0). Les briques GPL ou non commerciales servent seulement de comparaison. |
| Vie privée (RGPD) | Vidéo continue d'un logement habité. | Floutage des visages, conservation limitée, hébergement en France ou dans l'UE. |
| Sortie DPE vers LICIEL | Injection non prouvée. | Fiche DPE pré-remplie en attendant (01-cadrage.md). |
| **Assistant live : réseau** | Cave, combles, zone blanche. | Mode hors réseau (§ 3.6) : enregistrement local et questions a posteriori. |
| **Assistant live : latence** | La chaîne a 5 étapes (fin de phrase, transcription, Claude, synthèse, lecture) qui s'additionnent. **2 à 4 s n'est atteignable qu'avec un GPU pour la transcription** ; sur processeur seul, plutôt 3 à 6 s. Le réseau mobile ajoute de l'incertitude. | Streaming à chaque étape. Préfixe Claude en cache. Images petites. Questions de veille préparées à l'avance. Bip au lieu de « c'est noté ». Le diagnostiqueur n'attend jamais l'IA pour continuer à filmer. **Chaque étape est mesurée en V1bis.** |
| **Assistant live : seuil de fin de phrase** | Trop court, l'IA coupe la parole ; trop long, elle paraît lente. | Seuil réglable, testé avec Noah. Interruption immédiate de la voix de l'IA si le diagnostiqueur reparle. |
| **Assistant live : serveur voix** | Transcription et synthèse doivent tourner pendant les heures de visite. Un GPU permanent est un coût fixe. | Un GPU partagé entre plusieurs visites simultanées, ou transcription sur processeur si la latence mesurée reste acceptable. |
| **Assistant live : l'IA invente** | Elle « voit » un mur de 20 cm et l'affirme. | Consigne : questions seulement. Enregistrement **uniquement** par outil, avec citation du diagnostiqueur. Contrôle a posteriori : toute valeur sans citation est rejetée. |
| **Assistant live : trop bavard** | Fatigue, distraction. | Plafond de questions par minute. Questions regroupées à la sortie de la pièce. Mode « silencieux » possible. |
| **Assistant live : dépendance à Anthropic** | Panne, limites de débit, évolution des modèles. | La chaîne reste en mode hors réseau (§ 3.6) si Claude ne répond pas. Le modèle est un simple paramètre, et les modèles 5.5 restent disponibles au moins jusqu'en septembre–octobre 2027 (dates de retrait publiées). |
| **Assistant live : confidentialité** | Images d'un logement habité envoyées en direct à Anthropic (entreprise américaine). Traitement « global » ou « US » seulement : **aucune option UE indiquée**. | La voix reste sur notre serveur, seuls texte et images réduites partent. D'après la documentation, les données API ne sont pas conservées par défaut et pas utilisées pour l'entraînement sans accord ; la « conservation zéro » est possible sur demande. Contrat de traitement des données (transfert hors UE) à vérifier par Hermes. Information du propriétaire. Floutage des visages avant envoi. |
| **Assistant live : téléphone ancien** | Enregistrement 1080p + flux live + son en même temps : chauffe, batterie, saccades. | Testé en V1bis sur un téléphone ancien. Si besoin, enregistrement en 720p. |

## 5. Coût serveur approximatif par dossier

Ordres de grandeur **à mesurer en V1**. Hypothèse : 10 min de vidéo continue, logement de 8 pièces.

| Poste | Estimation | Coût |
|---|---|---|
| Carte 3D (SLAM ou reconstruction + ajustement global) + profondeur + structure + détection | 20 à 60 min de GPU, loué 0,5 à 2 €/h | 0,20 à 2 € |
| Transcription + ancrage + extraction | Quelques minutes de GPU ou API | < 0,20 € |
| Plaques et équipements | Modèle ouvert ou API | 0,05 à 1 € |
| Stockage (90 jours, 0,5 à 1 Go) | | < 0,10 € |
| **Total variable** | | **≈ 0,50 à 3 € par dossier** |

Coûts fixes : petit serveur d'application, quelques dizaines d'euros par mois. GPU loués à la demande au démarrage.

**Assistant vocal en direct : coût par minute de tournage**

Ce sont des estimations, à mesurer en V1bis. Les prix de catalogue sous-estiment souvent le coût réel, parce que le contexte de la conversation peut être refacturé à chaque échange.

| Option | Calcul | Par minute | Visite de 15 min |
|---|---|---|---|
Tarifs Anthropic officiels (22/10/2026, en dollars par million de tokens) :

| Modèle | Entrée | Sortie | Lecture de cache |
|---|---|---|---|
| Claude Haiku 5.5 (prompts ≤ 100 000 tokens) | 0,10 $ | 0,50 $ | 0,01 $ |
| Claude Sonnet 5.5 | 2 $ | 10 $ | 0,10 $ |
| Claude Opus 5.5 | 4 $ | 20 $ | 0,20 $ |

Une image coûte ⌈largeur/28⌉ × ⌈hauteur/28⌉ tokens : environ 350 à 600 tokens pour une image de 400×700 à 500×900 px. L'API par lots coûte 50 % moins cher.

Hypothèse : environ 10 appels Haiku par minute (5 réponses + 5 veilles). Chaque appel comprend ~5 000 tokens en cache (consignes + checklist), ~3 000 tokens variables (état de la pièce, historique récent, 2 à 3 images) et ~150 tokens de sortie, soit environ 0,0004 $ par appel.

| Poste | Calcul | Par minute | Visite de 15 min |
|---|---|---|---|
| **Claude Haiku 5.5 en direct** | ~10 appels × ~0,0004 $ | **≈ 0,003 à 0,01 $** | ≈ 0,05 à 0,15 $ |
| (pour comparaison : Sonnet 5.5 en direct) | environ 20 fois plus cher, et plus lent | ≈ 0,08 à 0,20 $ | ≈ 1,2 à 3 $ — *non retenu pour le direct* |
| **Analyse finale Claude Sonnet 5.5** | ~100 000 à 200 000 tokens en entrée (transcription + 100 à 200 images clés) + 10 000 à 20 000 en sortie | — | **≈ 0,30 à 0,60 $** par dossier (moitié avec l'API par lots ; environ double avec Opus 5.5) |
| **Transcription + synthèse vocale** (notre serveur) | GPU partagé pendant les heures de visite (0,5 à 2 €/h × ~220 h/mois ≈ 110 à 440 €/mois), ou processeur seul (quelques dizaines d'€/mois, latence plus forte) | — | **Coût fixe** : ≈ 1 à 4 € par dossier à 100 dossiers/mois ; ≈ 0,2 à 0,9 € à 500 dossiers/mois |

**Bilan** :
- Claude coûte très peu, **moins de 1 $ par dossier** en tout (direct + analyse finale).
- Le vrai poste est le **serveur voix** (transcription et synthèse), à dimensionner selon le volume.
- Le total par dossier (chaîne 3D + assistant + analyse) reste de l'ordre de **1 à 5 €** au début, puis baisse avec le volume.

Sources :
- Anthropic : [tarifs](https://platform.claude.com/docs/en/about-claude/pricing), [modèles](https://platform.claude.com/docs/en/about-claude/models/overview), [vision](https://platform.claude.com/docs/en/build-with-claude/vision), [cache de prompt](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [streaming](https://platform.claude.com/docs/en/build-with-claude/streaming), [résidence des données](https://platform.claude.com/docs/en/manage-claude/data-residency), [conservation des données](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention) ;
- briques voix : [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo), [Silero VAD](https://github.com/snakers4/silero-vad), [Piper (suite GPL)](https://github.com/OHF-Voice/piper1-gpl), [voix Piper](https://huggingface.co/rhasspy/piper-voices), [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), [MeloTTS](https://github.com/myshell-ai/MeloTTS), [Voxtral Mini](https://huggingface.co/mistralai/Voxtral-Mini-3B-2507).

## 6. Plan de prototype

| Étape | Contenu | Critère de réussite |
|---|---|---|
| **V1. Preuve : vidéo continue de 2 pièces avec aller-retour** | **Entrée** : 3 à 5 vidéos tournées selon [protocole-tournage.md](protocole-tournage.md) (pièce A → pièce B → retour en A → retour en B), avec 2 ou 3 téléphones, en fichier original. Le diagnostiqueur parle des murs pendant le film. Mesures laser et croquis numéroté relevés **à part**, comme vérité terrain. **Traitement** (script serveur, sans application) : carte 3D unique avec fermeture de boucle → découpage en pièces → plan coté + surfaces (échelle sans mesure dictée) → transcription → rattachement de chaque phrase à un mur. `video-001` sert de premier cas, dégradé. | **2 pièces reconnues, jamais 3 ou 4**, sur toutes les vidéos exploitables ; une vidéo trop dégradée doit être **signalée**, pas mal interprétée. **≥ 80 % des phrases rattachées au bon mur** ; les erreurs restantes signalées en orange. **Écart de surface ≤ 5 %** (objectif 3 %) sans mesure dictée. Temps et coût de calcul mesurés. Décision « on continue / on ajuste » avec Noah. |
| **V1bis. Assistant vocal en direct sur une pièce** (rapide, **sans SLAM**, en parallèle de V1) | Page web (HTTPS, obligatoire pour la caméra) : caméra + micro → notre petit serveur Python. Chaîne : VAD Silero → faster-whisper (turbo) → **Claude Haiku 5.5** en streaming (image de l'instant + état checklist en cache + outils `enregistrer_reponse` / `champs_manquants` / `piece_courante`) → synthèse Piper (voix fr_FR-siwis) → oreillette. État checklist d'**une pièce** : murs (matériau, épaisseur, isolation, donne sur), fenêtres (menuiserie, vitrage, volets), émetteurs. Enregistrement local de la vidéo en parallèle. Test par Noah dans 2 ou 3 pièces, dont un téléphone ancien. **Deux configurations comparées** : transcription sur le processeur de ce PC, puis sur un GPU loué à l'heure. | **Zéro valeur inventée** : toute valeur a une citation. ≥ 80 % des champs de la pièce remplis à la sortie de la pièce. **Latence mesurée étape par étape**, objectif 2 à 4 s. Coût par minute mesuré. Effet de la voix de l'IA sur l'enregistrement mesuré. Avis de Noah : « utile ou gênant ? ». |
| **V2. Logement complet** | Application web de capture (vidéo + voix + capteurs, retour en direct, **assistant live via relais serveur** si V1bis est concluant). Logement entier en une vidéo. Fenêtres et portes, orientation, ponts thermiques, plaques, Carrez par télémètre filmé. JSON « Dossier terrain v1 ». | Sur 3 logements : pièces correctes, part des champs de la checklist correctement pré-remplis, zéro valeur sans preuve, coût et temps mesurés. |
| **V3. De bout en bout** | Administratif depuis le devis + API publiques, écran de validation, génération LICIEL (pièces + Carrez) via `diagauto.liciel_xml`, fiche DPE pré-remplie. Pilote sur 2–3 vraies visites, chronométrées. | Aucune ressaisie des pièces ni du Carrez. Temps total mesuré avant et après. |

## 7. Questions ouvertes

- **Q1 — Vidéos V1.** Noah peut-il tourner 3 à 5 vidéos selon la fiche de tournage, avec 2 ou 3 téléphones dont un ancien, et nous envoyer les **fichiers originaux** (pas WhatsApp) ?
- **Q2 — Devis.** Sous quelle forme arrivent les données du devis Imodiag ?
- **Q3 — IA et hébergement.** Tout open source auto-hébergé, ou API commerciale acceptée pour la lecture des plaques ? Hébergement en France ou dans l'UE ?
- **Q4 — GPU.** Peut-on louer un GPU à l'heure pour V1, pour quelques euros ? Ce PC n'en a pas.
- **Q5 — Sortie DPE.** Une fiche DPE pré-remplie à recopier est-elle acceptable pendant le prototype ?
- **Q6 — BDNB.** Conditions d'accès à vérifier (Hermes).
- **Q7 — Clé API Anthropic.**
  - Il faut une **clé API Anthropic**, à créer sur la Console Claude (platform.claude.com) avec des crédits. Elle est **facturée à l'usage, séparément de l'abonnement Claude Max** : l'abonnement ne donne pas accès à l'API.
  - Qui crée le compte et la clé ? Quel plafond de dépense pour le prototype ? Quelques dollars suffisent pour V1bis.
  - La clé reste sur notre serveur, jamais dans le téléphone.
- **Q7 bis — Données.**
  - Accepte-t-on d'envoyer à Anthropic des images réduites et du texte ? La voix, elle, reste chez nous.
  - Le traitement se fait hors UE, puisque seules les options « global » et « US » existent.
  - Hermes peut-il vérifier le contrat de traitement des données et la « conservation zéro » ?
- **Q9 — Serveur voix.** Pour atteindre 2 à 4 s de délai, la transcription doit sans doute tourner sur un GPU. Accepte-t-on de louer un GPU à l'heure pour les tests, puis un GPU partagé pendant les heures de visite (de l'ordre de 100 à 450 € par mois) ?
- **Q8 — Oreillette.** Les diagnostiqueurs acceptent-ils de porter une oreillette (filaire ou Bluetooth) pendant la visite ? Sinon, l'IA parle par le haut-parleur, avec plus d'écho dans l'enregistrement.
