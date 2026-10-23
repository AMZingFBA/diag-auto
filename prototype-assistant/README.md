# Prototype V1bis — assistant vocal en direct pendant le tournage

Le diagnostiqueur filme le logement avec son téléphone et parle normalement. Un assistant lui pose dans l'oreillette les questions qui manquent pour le DPE (« Le mur avec la commode, il est isolé ? ») et note ses réponses.

Ce prototype correspond à l'étape **V1bis** du plan ([docs/02-capture-video.md](../docs/02-capture-video.md), § 3.6 et § 6).

## Comment ça marche

1. Le **téléphone** (une page web, sans application à installer) :
   - filme et garde la vidéo complète en mémoire ;
   - envoie au serveur le son et **une image par seconde**.
2. Le **serveur** (ce PC) :
   - repère la fin de chaque phrase, et attend la suite si elle est coupée (« Il est… ») ;
   - la transcrit sur place, en 0,05 s : **la voix ne quitte pas le PC** (voir « Étape 5 ») ;
   - **pré-remplit tout de suite**, sans IA, tout ce qu'il reconnaît dans la phrase, et le confirme par un **bip**, sans répéter ce qui a été dit (étape 9) ;
   - calcule la question suivante du parcours (voir « Parcours de la visite » plus bas).
3. **Claude est le cerveau de chaque phrase** (étape 7) :
   - il comprend n'importe quelle phrase, comme dans une vraie conversation, et y répond : question générale, remarque, ordre (« on fait une pause », « reviens au salon »), correction, récapitulatif ;
   - il vérifie le pré-remplissage du serveur, le corrige ou l'annule si besoin ;
   - puis il reprend la visite avec la question proposée par le parcours ;
   - sa réponse est lue **dès sa première phrase**, pendant qu'il écrit la suite ; s'il tarde, « Alors… » part au bout de 1,4 s ;
   - pendant les silences, il regarde les images et signale les éléments visibles (fenêtre, radiateur…), sans parler.
4. **Le serveur vérifie tout** :
   - une valeur n'est notée que si sa citation se retrouve dans ce que le diagnostiqueur a réellement dit ;
   - une question n'est jamais posée deux fois ;
   - une question est bloquée si elle demande de répéter ou si elle porte sur un champ déjà rempli ;
   - s'il y a deux questions, seule la première est gardée.
5. Le **téléphone** lit la question à voix haute (voix du navigateur), et se tait dès que le diagnostiqueur reparle. Il affiche aussi le temps de réponse.

## Parcours de la visite (étape 2, retour de Noah du 22/10/2026)

C'est le serveur qui décide de la question suivante, dans un ordre fixe, pièce par pièce :

1. **Les murs, un par un.**
   - Pour chaque mur : « donne sur » d'abord, puis matériau, épaisseur, isolation.
   - Quand un mur est fini : « Un autre mur dans cette pièce ? », jusqu'à ce que le diagnostiqueur réponde non.
2. **Le plafond, puis le plancher.** S'ils sont déjà décrits dans une autre pièce, l'assistant propose « Plafond pareil que dans le séjour ? ».
3. **Les fenêtres et portes restantes**, puis « D'autres fenêtres, ou une porte vers l'extérieur ? ».
4. **Les radiateurs** : leur type seulement. Leur date et leur température ne sont jamais demandées, mais toujours notées quand elles sont dites (étape 4).
5. **Une seule fois pour tout le logement** :
   - le chauffage, l'eau chaude et la ventilation ;
   - puis la date du ballon d'eau chaude, s'il y en a un, et plus jamais après « je ne sais pas ».
6. **« Pièce terminée. Quelle est la pièce suivante ? »**

**Seulement les questions utiles au DPE** :
- les questions sont courtes, 10 mots au plus ;
- une question restée sans réponse n'est pas reposée : elle revient dans le rappel de fin de visite. Seule exception : si le diagnostiqueur a parlé d'autre chose (une correction), elle est reposée une fois juste après (étape 4) ;
- **hypothèse à faire valider** : un mur, un plafond ou un plancher qui donne sur un **local chauffé** n'est pas une paroi déperditive en DPE 3CL. On ne demande donc ni son matériau ni son isolation ;
- la date du ballon n'est demandée que s'il y a un ballon ;
- une fenêtre n'a pas d'« épaisseur » : on demande la menuiserie, le vitrage et les volets ;
- « Par la chaudière », pour l'eau chaude : son énergie est celle de la chaudière. Elle est notée comme **déduite**, avec sa source.

**Quantités** : « en tout trois fenêtres, toutes pareilles » ou « oui, deux, à eau » donnent un seul groupe de 3 fenêtres ou de 2 radiateurs, décrits une seule fois.

**Description libre** (retour de Noah après son test du 22/10/2026) : le diagnostiqueur peut tout dire d'un coup, par exemple « ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il y a trois fenêtres en bois double vitrage, deux radiateurs à eau ».
- Tout est noté en une fois : le mur avec ses 4 valeurs, un groupe de **3 fenêtres** identiques, un groupe de **2 radiateurs**.
- Seul ce qui n'a pas été dit est demandé ensuite.

**Pas de « répétez »** :
- un mot mal transcrit est deviné avec le vocabulaire du champ demandé, par exemple « Ictérieur » donne extérieur ou « BESSE » donne basse ;
- la correction est gardée pour l'écran de validation ;
- « je ne sais pas » est noté « inconnu », marqué à vérifier, et l'assistant passe à la suite.

C'est **notre serveur** qui tient la checklist et calcule ce qui manque, pas l'IA. L'IA ne fait que poser des questions et proposer ce qu'elle a entendu. Une donnée qui n'a pas été dite reste vide.

Périmètre de la checklist dans ce prototype (tiré de [docs/checklist-dpe.md](../docs/checklist-dpe.md)) :
- **par pièce** : murs (donne sur, matériau, épaisseur, isolation), plafond et plancher (donne sur, isolation), fenêtres (menuiserie, vitrage, volets), portes vers l'extérieur, radiateurs (type) ;
- **pour le logement** : chauffage, eau chaude, ventilation ; date du ballon.
- **noté s'il est dit, jamais demandé** : date et température des radiateurs, longueur d'un mur, dimensions d'une fenêtre.

## Important : Claude passe par l'abonnement Claude Max, sans clé API

Décision de Noah du 22/10/2026 : **aucune clé API Anthropic**.
- Le serveur utilise le **Claude Code déjà connecté sur ce PC** (abonnement Claude Max). Il le lance en mode « sans écran » et le garde ouvert pendant la visite.
- Il retire de son environnement toute clé API éventuelle, pour être sûr que c'est l'abonnement qui sert.
- Il trouve Claude Code tout seul, par exemple celui installé avec l'extension VS Code.

> **Limite à garder en tête** : l'abonnement Max est prévu pour un usage **personnel et de développement**. Pour un usage commercial à grande échelle (beaucoup de diagnostiqueurs, beaucoup de visites), il faudra revoir ce point plus tard (API Anthropic avec contrat, ou autre). **On n'en décide pas maintenant.** Les limites d'usage de l'abonnement s'appliquent aussi pendant les tests.

## Installation (une seule fois)

Dans un terminal, à la racine du projet `diag-auto` :

```
.venv\Scripts\python -m pip install -r prototype-assistant\requirements.txt
```

Il faut aussi que Claude Code soit installé et connecté sur ce PC, ce qui est le cas avec l'extension VS Code. Si le serveur ne le trouve pas, indiquez son chemin dans la variable `DIAGAUTO_CLAUDE`.

## Lancer le serveur

```
cd prototype-assistant
..\.venv\Scripts\python -m assistant
```

Le serveur affiche deux adresses :
- l'une **pour ce PC** : `https://localhost:8443` ;
- l'autre **pour le téléphone**, par exemple `https://192.168.3.6:8443`.

Il faut que :
- le téléphone soit **sur le même Wi-Fi** que le PC ;
- Windows autorise le serveur : au premier lancement, le pare-feu demande l'autorisation ; cochez « réseaux privés ».

Au premier lancement, le modèle de transcription se télécharge (environ 500 Mo pour « small »).

## Sur le téléphone

1. Ouvrez l'adresse affichée pour le téléphone, dans Chrome (Android) ou Safari (iPhone).
2. Un avertissement de sécurité s'affiche, parce que le certificat est fait maison. Touchez « Paramètres avancés », puis « Continuer vers le site ». C'est normal pour ce prototype : le HTTPS est obligatoire pour que le téléphone autorise la caméra et le micro. Le téléphone oublie parfois ce certificat (« Serveur injoignable » alors que le Wi-Fi est bon) : touchez le lien « toucher ici » de l'accueil, ou ouvrez l'adresse suivie de `/api/statut`, et acceptez de nouveau.
3. Branchez une **oreillette**, de préférence. Sans oreillette, la voix de l'assistant passe par le haut-parleur et peut être captée par le micro.
4. Touchez **Démarrer la visite** et autorisez la caméra et le micro. Sur iPhone, autorisez aussi l'accès à l'**orientation** (boussole) : elle donne l'orientation des murs et des fenêtres (« le mur nord »). Si vous refusez, l'assistant demandera une fois l'orientation d'un mur à l'oral. Une petite boussole reste affichée en haut à droite (voir « Étape 6 »).
5. Filmez en parlant normalement, en décrivant librement :
   - « ici c'est la cuisine » ;
   - « ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il donne dehors » ;
   - « il y a trois fenêtres en bois double vitrage, deux radiateurs à eau » ;
   - en réponse à une question, un seul mot suffit : « extérieur », « basse », « roulants » ;
   - « je ne sais pas » ;
   - « pas de radiateur ici ».
6. À côté de chaque question sur un élément, l'écran montre sa **vignette** : l'image filmée quand il a été décrit. Le diagnostiqueur sait ainsi de quel mur on parle.
7. Sous chaque question, ses **réponses en boutons** : un appui vaut une réponse dite, et la question suivante arrive aussitôt. On peut répondre à l'oral ou au doigt, au choix.
8. Les boutons :
   - **📋 Fiche** : toute la pièce en cours, chaque information avec sa valeur ou « à remplir » ; un appui sur une ligne pour la remplir ou la corriger ;
   - **Assistant actif / muet** : en mode muet, les questions s'affichent sans être lues.
   - **Terminer** :
     - au 1er appui, l'assistant dit ce qui manque encore ;
     - au 2e appui (« Arrêter vraiment »), la visite s'arrête.
9. À la fin :
   - la vidéo complète part toute seule vers le PC (fichier original, sans recompression ; **jamais par WhatsApp**) : rester sur la page jusqu'à « Vidéo envoyée ✓ » ; le bouton **Envoyer la vidéo au serveur** sert à réessayer ;
   - ou **Garder la vidéo sur le téléphone**.

Si le réseau coupe (cave, combles) :
- l'enregistrement de la vidéo continue sur le téléphone ;
- l'assistant se tait ;
- la page se reconnecte toute seule et reprend la même visite.

Le volet **Outils de test** permet d'écrire une phrase au lieu de la dire.

## Mode simulation (sans Claude)

Pour tester la page et la chaîne sans utiliser l'abonnement, lancez le serveur en mode simulation :

```
set DIAGAUTO_CERVEAU=simulation
..\.venv\Scripts\python -m assistant
```

Tout fonctionne comme en mode `rapide` : les valeurs sont notées par l'extraction immédiate, et les questions viennent du parcours du serveur. Différences : pas de conversation (une question ou une phrase que les règles n'ont pas comprise reste sans suite), et les images ne sont pas regardées.

Si faster-whisper n'est pas installé, ou avec `DIAGAUTO_TRANSCRIPTION=simulation`, rien n'est transcrit : on écrit alors les phrases dans « Outils de test ».

## Tester sans téléphone : rejouer une vidéo

L'outil de rejeu envoie une vidéo au serveur comme si un téléphone filmait, au rythme réel. Il affiche les échanges, puis le bilan des latences :

```
cd prototype-assistant
..\.venv\Scripts\python -m assistant --port 8765 --sans-https
```

puis, dans un **autre** terminal :

```
cd prototype-assistant
..\.venv\Scripts\python -m assistant.rejouer ..\samples\video-001\video.mp4 --serveur http://localhost:8765
```

Une **visite déjà enregistrée** se rejoue de la même façon, à partir de son dossier (son `audio.wav` et images) :

```
..\.venv\Scripts\python -m assistant.rejouer sessions\20261022-083308-20ef54 --serveur http://localhost:8765 --piece Séjour
```

## Évaluer sur une pièce complète à 4 murs

Le script joue la visite complète d'un séjour à 4 murs, en 19 phrases de diagnostiqueur (avec des « je ne sais pas »), puis le passage à la cuisine. Depuis l'étape 4, il n'y a plus les deux questions sur la date et la température des radiateurs. Les phrases passent par toute la chaîne : extraction immédiate, parcours, Claude, garde-fous. Pour chaque phrase, il affiche :
- ce qui a été noté ;
- la question posée, comparée à la question attendue ;
- le temps de chaque étape.

```
cd prototype-assistant
..\.venv\Scripts\python -m assistant.evaluer
```

Ajoutez `--simulation` pour l'exécuter sans Claude. Le même parcours est vérifié, question par question, par les tests automatiques (`tests/test_dialogue.py`). Les 10 phrases avec fautes de transcription de l'étape 1 sont vérifiées dans `tests/test_extraction.py`.

`python -m assistant.evaluer --comprehension` joue des réponses difficiles, que les règles ne peuvent pas trancher seules. Il montre comment Claude les interprète par rapport à la question posée (voir « Étape 3 »).

Ces deux évaluations jouent le parcours en mode `rapide` (sans conversation). `python -m assistant.evaluer --conversation` joue une visite en cours, puis **30 phrases libres**, avec le vrai Claude en cerveau de chaque phrase (voir « Étape 7 »). Ajoutez `--sortie fichier.md` pour garder le résultat.

## Ce qui est enregistré

Chaque visite a son dossier `prototype-assistant/sessions/<date-heure-code>/`. Ce dossier n'est pas versionné dans git : il contient des images et du son d'un logement.

| Fichier | Contenu |
|---|---|
| `journal.jsonl` | Tout ce qui s'est passé, horodaté. Pour chaque phrase : le texte transcrit, la réponse brute de Claude, les valeurs acceptées ou refusées (avec la raison), et les mesures de temps de chaque étape. |
| `audio.wav` | Le son reçu, calé sur l'horloge de la vidéo. Un trou de réseau est rempli de silence. |
| `images/` | Les images reçues, une par seconde. Le nom de fichier est l'instant dans la vidéo. |
| `etat.json` | La checklist à la fin : chaque valeur avec sa **citation** et son **instant**, l'historique si elle a été redite autrement (« à vérifier »), et les manques. |
| `bilan.json` | Le résumé : nombre de phrases, de questions, de valeurs, taux de remplissage par pièce, latences (médiane, 90e centile, maximum). |
| `video.mp4` / `video.webm` | La vidéo complète, si elle a été envoyée depuis le téléphone. |

**Données envoyées à Anthropic** (via Claude Code) : le texte des phrases et des images réduites (512 pixels). **La voix reste sur ce PC.**

## Mesures du 22/10/2026

Sur ce PC (12 cœurs, **pas de carte graphique**), avec Claude Haiku 5.5 via Claude Code (effort « bas »).

**1. Façon d'appeler Claude Code** (temps entre l'envoi et la réponse complète)

| Façon | Temps | Décision |
|---|---|---|
| Relancer `claude -p` à chaque phrase | 2,7 à 6,3 s (démarrage ~1,3 s à chaque fois) | non |
| Claude Code **gardé ouvert**, image **dans le message** | 1,8 à 2 s (premiers mots ~1,3 s) | **retenu** |
| Gardé ouvert, image **en fichier**, que Claude doit ouvrir | une étape de plus (~2 s) ; et avec le même nom de fichier, Claude ne rouvre pas l'image | en option (`DIAGAUTO_IMAGES=fichiers`) |
| Réponse en JSON imposée par schéma | même temps, mais la question n'arrive qu'à la fin | non |

**2. La réflexion de Claude**

Claude Code fait **toujours réfléchir** Haiku 5.5 avant de répondre : 400 à 950 jetons, soit 1,4 à 4,3 s selon les phrases. Trois façons de la couper ont été essayées, sans effet :
- le réglage `alwaysThinkingEnabled=false` ;
- la variable `MAX_THINKING_TOKENS=0` ;
- une consigne de rapidité dans les instructions.

C'est la principale limite de l'accès par Claude Code. L'API permettrait de couper cette réflexion.

**3. Transcription sur le processeur** (phrase de 5,7 s)

| Modèle | Temps | Qualité |
|---|---|---|
| **small** (retenu sans carte graphique) | **~2 s** | correcte, avec des erreurs (« La letta ITI » au lieu de « La taille d'ici ») |
| large-v3-turbo (retenu avec carte graphique) | 8 à 10 s | très bonne |
| medium | ~7 s, avec des boucles à plus de 40 s | à écarter |

Utiliser plus de cœurs n'accélère presque pas.

**4. De bout en bout** (vidéo `video-001` rejouée, 38 s, 9 phrases)

| Étape | Médiane | 90 % des cas en dessous de |
|---|---|---|
| Silence attendu pour décider que la phrase est finie | 0,7 s | 0,7 s |
| Transcription | 1,7 s | 2,2 s |
| Claude : premiers mots | 1,4 s | 3,5 s |
| **Fin de phrase détectée → début de la voix** | **4,1 s** | **5,7 s** |

Soit **environ 4,8 s entre la fin de la phrase et le début de la réponse**. L'objectif est de 2 à 4 s. Pour s'en approcher :
- une **carte graphique** pour la transcription (gain attendu : environ 1,5 s, à mesurer) ;
- et, plus tard, un accès sans réflexion forcée.

Claude Code indique aussi ce que la visite aurait coûté au tarif de l'API : environ 0,02 à 0,03 $ pour 40 s de vidéo. **Ce n'est pas facturé avec l'abonnement.** C'est plus que l'estimation du plan, à cause de la réflexion.

## Après le test de Noah sur iPhone (22/10/2026)

**Ce que le test a montré** (7 minutes dans un séjour) : l'assistant comprenait mal et faisait répéter. Le journal en donne trois causes.

1. **Transcription mauvaise sur les réponses courtes** : « Sainte », « Ictérieur », « BESSE », « O, chaudi », parfois 5 à 14 s par phrase.
   - Cause : la détection de phrase ne gardait que 0,3 s de son avant le premier mot ; sur un ou deux mots, Whisper manque de contexte. Il recommençait aussi plusieurs fois quand il hésitait, et partait parfois en boucle.
   - Correction : 1 s de son gardé avant la phrase et 0,5 s après, recherche plus large (faisceau 5), anti-répétition, longueur de texte plafonnée.
   - Vérifié en rejouant l'enregistrement de Noah :
     - « Il est isolé par l'intérieur », « BAS ! », « Eau chaude. » sont maintenant justes ;
     - plus de boucle ;
     - 2,3 s par phrase en médiane (+0,2 s), et le pire cas passe de 5,9 s à 3,6 s.
2. **Phrases coupées pendant les hésitations** (« Il est… » / « Et il fait… » / « 20 mètres 5 »). Le serveur attend maintenant la suite tant que le diagnostiqueur parle encore.
3. **Claude faisait répéter et reposait des questions.** Trois corrections :
   - une extraction immédiate par règles note tout ce qui est reconnu, y compris dans une description libre ;
   - de nouvelles consignes à Claude : tout extraire, deviner, une seule question ;
   - des garde-fous sur les questions, appliqués par le serveur.

**Évaluation sur 10 phrases réalistes avec le vrai Claude** (`python -m assistant.evaluer`) :
- **26 valeurs notées sur 26, aucune refusée** : description libre complète, groupes de 3 fenêtres et 2 radiateurs, « Ictérieur » → extérieur, « BESSE » → basse, « parpin » → parpaing, « je sais pas » → inconnu.
- **0** demande de répétition, **0** question double, **0** question redemandée dans la même pièce.
- Questions courtes et utiles : « Ce mur donne sur l'extérieur ? », « Les 3 fenêtres ont des volets ? », « Les radiateurs sont basse ou haute température ? ».

| Étape (phrase reçue en texte) | Médiane | Plage |
|---|---|---|
| Extraction immédiate (bip « noté ») | **2 ms** | 0,5 à 13 ms |
| Question de Claude prête | **1,5 s** | 0,9 à 2,7 s |

**Sur le téléphone**, il faut ajouter environ 0,7 s de silence de fin de phrase et environ 2,3 s de transcription. Cela donne :
- le bip « noté » environ **3 s** après la fin de la phrase ;
- la question environ **4,5 s** après.

Le temps de réponse est maintenant affiché sous chaque question à l'écran.

## Étape 2 : parcours et temps de réponse (22/10/2026)

**Évaluation sur la pièce à 4 murs avec le vrai Claude** (`python -m assistant.evaluer`) :
- **21 questions sur 21 conformes au parcours**, 31 valeurs notées, séjour rempli à 100 % ;
- 0 demande de répétition, 0 question double, 0 question reposée ;
- **la question part en quelques millisecondes** après la transcription : c'est le serveur qui la pose, sans attendre Claude ;
- Claude n'a eu qu'une relecture à faire en arrière-plan, sans rien changer.

Vérifié aussi avec le vrai Claude :
- une phrase longue avec un mot inconnu des règles (« meulière ») : Claude l'a ajoutée 1,5 s plus tard. Le mot est maintenant dans le vocabulaire, avec d'autres matériaux de mur ;
- « Tu m'entends bien ? » : « Oui, je t'entends. » (2,3 s).

**Temps de réponse sur le téléphone** (ce PC, sans carte graphique) : environ 0,7 s de silence de fin de phrase, plus environ 2,3 s de transcription, plus quelques millisecondes pour le parcours, soit **environ 3 s entre la fin de la phrase et la question**.
- Avant cette étape : environ 4,5 s ; au départ : environ 4,8 s.
- La voix du navigateur parle aussi un peu plus vite.
- Pour aller plus bas, il faut une **carte graphique** pour la transcription. Un essai avec une fenêtre d'analyse plus courte (10 ou 15 s au lieu de 30 s) n'a rien gagné : le moteur la complète de toute façon à 30 s.

## Étape 3 : compréhension orale robuste (22/10/2026)

Cas réel de Noah : il a dit « eau chaude », la transcription a donné « Oh ! est chaude », et l'assistant n'a pas compris. La réponse est maintenant interprétée **par rapport à la dernière question posée**, en quatre couches. Chacune ne sert que si la précédente n'a pas suffi.

1. **Nettoyage de l'oral** :
   - les hésitations disparaissent (« euh », « hum », « bah ») ;
   - les répétitions aussi (« le… le mur », « roulant, roulant ») ;
   - ainsi que les faux départs d'un bégaiement (« pa… parpaing », « dou… double ») ;
   - les points de suspension ne coupent plus la phrase (« le mur il fait… trente » = 30 cm) ;
   - une correction l'emporte (« alu… enfin bois » = bois ; « brique, non, parpaing » = parpaing).
2. **Ressemblance avec les réponses possibles de la question**, par l'orthographe **et par le son**, avec une clé phonétique française :
   - « Oh ! est chaude » se prononce comme « eau chaude » (ressemblance 0,91), ce qui donne radiateur à eau ;
   - de même, « vie de sanitaire » donne vide sanitaire, « comble perdue » combles perdus, « doublevitrage » double, « pévécé » PVC, « condensassion » condensation, « ballon thermo » thermodynamique ;
   - les mots courts doivent se prononcer exactement pareil, sinon « allô » ressemblerait à « agglo ».
3. **Doute** : si plusieurs réponses se ressemblent, si la ressemblance est faible, ou si deux valeurs sont dites (« bois… ou alu ? »), l'assistant **propose l'interprétation la plus probable** : « J'ai compris double, c'est bien ça ? ».
   - « Oui », « c'est ça », « exactement » : la valeur est notée, marquée « confirmé ».
   - « Non, triple » : c'est triple qui est noté.
   - « Non » : rien n'est noté, et l'assistant n'insiste pas.
4. **Claude, avec le contexte**, quand les règles n'ont rien compris :
   - il reçoit la dernière question, ses **valeurs possibles** et les images ;
   - s'il est sûr, il note ;
   - s'il n'est que « probable », le serveur demande confirmation au lieu de noter ;
   - il ne fait jamais répéter.

Ce qui est deviné, déduit, confirmé ou dit avec un doute (« je crois que c'est du béton ») est noté comme tel, pour l'écran de validation.

**Tests** : 31 transcriptions bruitées réalistes (`tests/test_comprehension.py`), chacune avec son interprétation attendue (notée, à confirmer, « je ne sais pas » ou rien à noter). S'y ajoutent les réponses à une confirmation et le cas où Claude n'est que probable.

**Cas difficiles avec le vrai Claude** (`python -m assistant.evaluer --comprehension`) :

| Question | Réponse entendue | Résultat |
|---|---|---|
| Au-dessus du plafond ? | « Au-dessus c'est le voisin, il est chauffé. » | noté : local chauffé (logement au-dessus) |
| Sous le plancher ? | « En dessous y a le parking de l'immeuble. » | « J'ai compris local non chauffé : garage, c'est bien ça ? » (Claude, 1,6 s) |
| Radiateurs à eau ou électriques ? | « Ils sont branchés sur la chaudière. » | « J'ai compris radiateur à eau, c'est bien ça ? » |
| Fenêtres PVC, bois ou alu ? | « Du plastique blanc. » | « J'ai compris PVC, c'est bien ça ? » (Claude, 1,9 s) |
| Le mur est en quoi ? | « Du, euh, comment on dit, du bloc creux. » | noté : parpaing |
| Radiateurs à eau ou électriques ? | « Oh ! » | rien : trop peu pour deviner ; rien n'est inventé, rien n'est redemandé |

**Vocabulaire métier donné à la transcription** (comparé sur l'enregistrement de Noah) :
- **Retenu : un contexte enrichi avec la liste de Noah** (parpaing, PVC, double vitrage, VMC hygro, chaudière à condensation, PAC air/eau, ballon thermodynamique, combles perdus, ITI/ITE, vide sanitaire, terre-plein…).
  - Gains : « eau chaude » au lieu de « Chaude », « Basse » au lieu de « BAS ! », et plus de « 100 cm » inventé.
  - Même vitesse qu'avant.
- **À ne jamais mettre dans ce contexte** : « je ne sais pas », « oui », « non ». Whisper les inventait sur du silence, et un « je ne sais pas » inventé marquerait un champ « inconnu ».
- **Écartés : les « hotwords » de faster-whisper**. Ils sont plus lents (2,9 s au lieu de 2,4 s) et ont **inventé des phrases métier sur du silence** (« Laine de verre, polystyrène, radiateur à condensation. »).
- **Garde-fou** : même avec le contexte retenu, Whisper a recopié « Laine de verre. » deux fois sur des passages sans parole. Une telle invention, en réponse à une question sur l'isolation, deviendrait une valeur.
  - Whisper donne pour chaque passage une probabilité « pas de parole » et une confiance. Sur les 52 phrases de Noah :
    - les inventions sont à 0,39–0,50, avec une confiance de −0,8 à −1,3 ;
    - les vraies réponses sont à 0,09 au plus.
  - Une transcription douteuse, ou recopiée du contexte sur un passage probablement sans parole, est donc écartée.
  - Vérifié sur le son réel : les deux « Laine de verre » disparaissent ; « Extérieur », « eau chaude » et « BASSE » restent.

**Modèles de transcription essayés** (52 phrases de l'enregistrement de Noah, ce PC sans carte graphique) :

| Moteur | Temps par phrase | Qualité observée | Licence |
|---|---|---|---|
| **Whisper small** (OpenAI), avec le contexte et le garde-fou : retenu à l'étape 3, **second avis depuis l'étape 5** | 2,3 s | bon en général ; quelques erreurs (« Blois » pour « Bois », « Ocean » pour « eau chaude ») | MIT |
| Whisper small français (`bofenghuang/whisper-small-cv11-french`) | 2,4 s | meilleur sur certaines phrases (« Derrière le rideau », « eau chaude ») mais invente davantage sur du silence (« Réalisé par l'Institut… », « Brique, parpaing, basse température. ») ; nombres en lettres | Apache-2.0 (version CTranslate2 publiée par un tiers : à vérifier) |
| **FastConformer français** (NVIDIA, version ONNX) : en option à l'étape 3, **par défaut depuis l'étape 5** | **0,05 s** | souvent juste (« Je ne t'entends plus », « Derrière le rideau », « Bois ») ; parfois abîmé (« de la' prriix » pour brique, « Euxux chaudes ») ; sur du silence, du charabia mais jamais de valeur métier | CC-BY-4.0 (mention de NVIDIA obligatoire ; version ONNX publiée par OpenVoiceOS : à vérifier avant usage commercial) |

Aucun Whisper plus gros ne tient la vitesse sur ce processeur : turbo, medium et les versions françaises « distil » gardent un gros encodeur et prennent 7 à 10 s.

**À essayer avec Noah** : le FastConformer ramènerait la question à **moins de 1 s après la fin de la phrase** (au lieu d'environ 3 s). Ses mots abîmés sont en partie rattrapés par la comparaison phonétique et par Claude. C'est fait à l'étape 5 (mode « rapide », par défaut).

## Étape 4 : un assistant qui s'adapte (22/10/2026)

Demande de Noah : un assistant qui s'adapte au logement réel, pas un questionnaire rigide. **Rien n'est supposé identique s'il n'a pas été dit.**

**Groupes et exceptions.**
- Un élément peut regrouper plusieurs objets identiques. Chaque groupe a ses propres valeurs.
- Chaque groupe porte un nom parlant, qui sert dans les questions.

| Ce que dit le diagnostiqueur | Ce qui est noté |
|---|---|
| « Il y a 9 radiateurs électriques basse température et 1 électrique haute température » | 2 groupes : « les 9 radiateurs basse température » et « le radiateur haute température » |
| « 3 radiateurs à eau, 2 en fonte de 1975 et 1 en acier de 2010 » | 2 groupes à eau : « les 2 radiateurs de 1975 » et « le radiateur de 2010 » |
| « Quatre fenêtres en PVC double vitrage, dont une en simple vitrage » | 3 fenêtres en double vitrage et 1 en simple vitrage, toutes en PVC |
| Question « Les 3 fenêtres : PVC, bois ou alu ? », réponse « Deux en PVC et une en bois » | Le groupe est séparé en « les 2 fenêtres en PVC » et « la fenêtre en bois ». Chacun a ensuite sa propre question sur les volets |
| « Toutes sauf une ont des volets roulants » | 2 fenêtres à volets roulants, puis la question « L'autre fenêtre : des volets ? » |
| « Un des radiateurs est électrique » | Ce radiateur est séparé du groupe ; les autres restent à eau |
| « Toutes les fenêtres sont en bois, sauf celle de la chambre qui est en PVC » | Une **règle du logement**. Elle vaut pour les fenêtres déjà décrites et pour celles des pièces visitées ensuite ; la chambre reçoit PVC |
| « Sauf celle de la chambre, qui est en PVC », dit après coup | Exception ajoutée à la règle |
| « Dans la cuisine, il y a aussi un radiateur électrique », dit depuis la chambre | Le radiateur va dans la cuisine ; on reste dans la chambre |
| « Le premier mur, en fait c'est du béton », « Le mur 2 donne sur le garage, pas dehors » | Correction de cet élément-là, même s'il a été décrit bien avant |
| « En fait il y a 3 radiateurs, pas 2 » | Nombre corrigé |

Une partie séparée d'un groupe garde les valeurs déjà dites pour le groupe. À l'écran de validation, elles sont marquées « comme son groupe ».

Une valeur dite pour un élément l'emporte sur celle reprise d'un groupe ou d'une règle. C'est une exception, pas une contradiction.

**Contradictions : la dernière valeur est gardée, et c'est signalé.**
- L'assistant le dit tout de suite, avant sa question suivante : « Noté : béton au lieu de brique. Un autre mur dans cette pièce ? ».
- L'ancienne valeur reste dans l'historique. Le champ est « à vérifier » à l'écran de validation, et la liste des contradictions est dans le bilan de la visite.
- La question restée en attente (ici « Un autre mur ? ») est reposée une fois après la correction.

**Date et température des radiateurs** : jamais demandées, mais toujours notées quand elles sont dites, groupe par groupe. Par exemple : « tous les radiateurs sont en basse température sauf un ».

**Questions construites selon le logement réel** :
- Chaque groupe a ses questions, sous son nom : « La fenêtre en bois : des volets ? ».
- « Pareil » ou « aussi » reprend la valeur du groupe précédent de la pièce. « Toutes » vaut aussi pour les autres fenêtres de la pièce dont on n'a rien dit.
- Ce qui est connu par une règle n'est pas redemandé.
- Pour le chauffage, la question dépend de l'énergie dite :
  - gaz : « Chaudière à condensation, basse température ou standard ? » ;
  - bois : « Poêle, insert ou chaudière ? » ;
  - électricité : « Radiateurs électriques ou pompe à chaleur ? ».
- Une réponse trop générale pour le DPE (« pompe à chaleur », « chaudière ») est notée, puis précisée une fois : « Pompe à chaleur air/eau ou air/air ? ».
- Chauffage à l'électricité et tous les radiateurs électriques :
  - le chauffage est noté « radiateurs électriques (effet Joule) » ;
  - cette valeur est marquée **déduite**, avec sa source ;
  - la date de la « chaudière » n'est pas demandée.
- « Le radiateur sous la fenêtre est électrique » : la fenêtre situe le radiateur, elle ne devient pas un nouvel élément.

**Tests** : `tests/test_groupes.py` contient 27 scénarios et un dialogue complet. Les scénarios couvrent les groupes mixtes, les exceptions, les règles du logement, les ajouts après coup, les corrections tardives et les contradictions. Le prototype compte maintenant 133 tests.

**Limites de cette étape** :
- Les murs restent décrits un par un. « Les deux murs du fond donnent sur les voisins » ou « le reste donne sur l'intérieur » relèvent de l'étape 5.
- « Tous les radiateurs sont électriques » vaut pour la pièce. Pour tout le logement, il faut le dire (« du logement », « partout ») ou excepter une autre pièce.
- Les phrases trop compliquées pour les règles sont confiées à Claude. Il dispose des mêmes outils : séparer un groupe, changer un nombre, poser une règle.

## Étape 5 : le test réel de Noah, rejoué avant et après (22/10/2026)

Retour de Noah sur son test (visite `sessions/20261022-083308-20ef54`) : « trop lent, ne s'adapte pas, je dois répéter, je ne sais pas c'est quel mur 3 / mur 4 ». Le son de cette visite a été **rejoué tel quel** dans le serveur, avant et après les corrections (`python -m assistant.rejouer sessions\20261022-083308-20ef54`). Les deux dialogues complets sont dans [rejeux/20261022-test-reel-noah.md](rejeux/20261022-test-reel-noah.md).

**1. Des noms de murs compréhensibles, jamais « le mur 3 ».**
- Le mur dont on vient de parler est « ce mur ».
- Les autres sont nommés par ce qui a été dit ou vu d'eux :
  - le repère dit : « le mur avec la télé », « le mur du fond » ;
  - ses fenêtres : « le mur des 3 fenêtres », car une fenêtre citée après un mur est rattachée à ce mur ;
  - ce sur quoi il donne : « le mur côté voisin », « le mur côté WC », « le mur extérieur » ;
  - la boussole du téléphone au moment où il a été filmé : « le mur nord ».
- Sans indice, c'est « le mur affiché ». La page montre la **vignette** de l'élément à côté de chaque question.
- « Quel mur ? » : l'assistant répond (« Le mur côté garage. ») et repose sa question.
- Une question de Claude qui dit « mur 3 » ou « le quatrième mur » est refusée.

**2. Les phrases globales sont comprises.**
- « Cette pièce fait 4 murs » : une fois les 4 murs décrits, plus de « Un autre mur ? ». Avant, l'assistant demande « Il reste un mur : il donne sur quoi ? ».
- « Il y a juste un mur qui donne sur l'extérieur, le reste donne sur l'intérieur ou les voisins » :
  - c'est le mur extérieur déjà décrit, pas un mur de plus ;
  - les autres murs donnent sur un local chauffé, sans aucune question de plus ;
  - la liste des murs est close.
- « Pareil pour celui-là » : un nouveau mur avec les valeurs du précédent.
- « Il te faut quoi d'autre ? » : l'assistant dit ce qui manque pour l'élément en cours, puis repose sa question.

**3. Pas de question inutile.**
- « Il donne derrière sur des toilettes », « sur la cuisine » : c'est un local chauffé. Le matériau et l'épaisseur ne sont pas demandés (hypothèse déjà en place : paroi non déperditive).
- Les valeurs libres de Claude (« toilettes ») sont ramenées au vocabulaire du serveur, pour que cette règle s'applique.
- Un mot mal entendu n'est deviné que dans une réponse courte. Ce n'était pas le cas au test réel :
  - « Laine de verre de 30 cm » donnait « J'ai compris pierre ? » ;
  - la question de Noah « Il te faut quoi comme information sur ce mur ? » donnait le matériau « tuffeau ».

**4. Valeurs aberrantes et contradictions.**
- Une valeur invraisemblable n'est jamais notée : « il fait 30 mètres » de long, pour un mur de séjour, donne « J'ai compris 30 m de long : plutôt 3 m ? ».
- Les bornes sont larges, à faire valider (hypothèse) :
  - mur : 0,3 à 15 m de long et 4 à 100 cm d'épaisseur ;
  - isolant : 1 à 40 cm sur un mur et 1 à 60 cm sur un plafond ;
  - année : de 1850 à aujourd'hui ;
  - côté d'une fenêtre : 0,2 à 6 m.
- « Le plafond est isolé… le plafond est pas isolé », dans la même phrase : le diagnostiqueur se reprend, seule la dernière valeur compte.
- D'une phrase à l'autre, une contradiction est gardée et signalée (étape 4).

**5. Temps de réponse : la transcription n'est plus le goulot.**
- Mesuré sur le son de la visite de Noah :
  - Whisper small prend **environ 2 s par phrase sur ce processeur, quelle que soit sa longueur** (même « 30 cm. ») : le modèle traite toujours 30 s de son ;
  - réduire sa recherche (`beam 1`) ne gagne que 0,2 s et le fait inventer davantage (« Le choc est un peu trop épuisé… » sur un bruit).
- Le **FastConformer** de NVIDIA transcrit la même phrase en **0,05 s**. Il a aussi mieux compris Noah :
  - « Et le mur est en brique » (Whisper : « embrique ») ;
  - « Le plafond n'est pas isolé » (Whisper : « des pays isolés ») ;
  - « Il te faut quoi d'autre comme information ? ».
- Il devient le moteur par défaut (mode « rapide ») :
  - Whisper, guidé par le vocabulaire métier, ne donne qu'un **second avis**, et seulement pour une phrase que les règles n'ont pas comprise ;
  - si Whisper n'y entend pas de vraie parole, c'était un bruit, et rien n'est dit ;
  - Claude n'intervient qu'ensuite.
- La transcription « en flux, pendant que la personne parle » n'est donc plus utile : une phrase de 15 s est transcrite en 0,2 s.

| Rejeu du son de la visite de Noah | Avant (étape 4) | Après (étape 5) |
|---|---|---|
| Transcription, médiane | 2,26 s | **0,07 s** |
| Fin de phrase détectée → question prête, médiane | 3,12 s | **0,14 s** |
| Idem, pire 10 % des phrases | 5,51 s | **0,94 s** |
| Plus le silence de fin de phrase | + 0,7 s | + 0,7 s |

Total entre la fin de la phrase et la question : environ **3,8 s avant, 0,85 s après** (médiane), plus le démarrage de la voix du téléphone. Une phrase incomprise reste plus lente (second avis de Whisper ~2 s, puis Claude ~2 à 3 s).

**6. Mots métier mal transcrits** : corrections ajoutées au lexique, d'après ce rejeu :
- « combles bleus » et « comblots » → combles perdus, combles ;
- « y embrique » → est en brique ;
- « des pays isolés », « DPE isolé », « dépa isolés » → est pas isolé.

**Tests** : `tests/test_visite_reelle.py` (23 tests). Il contient la visite de Noah rejouée en texte, phrase par phrase, avec ce qu'elle doit donner. Le prototype compte maintenant 156 tests.

**Limites de cette étape** :
- La boussole d'un téléphone est souvent faussée à l'intérieur. Le nom « le mur nord » n'est qu'un repère, et l'orientation reste à confirmer à l'écran de validation.
- Le FastConformer ne connaît pas le vocabulaire métier. Ses erreurs sont rattrapées par le lexique, la comparaison phonétique, puis le second avis de Whisper. Sa licence (CC-BY-4.0, mention de NVIDIA ; version ONNX publiée par OpenVoiceOS) est à vérifier avant un usage commercial.
- Le rejeu d'une visite garde les réponses d'origine de Noah, alors que les questions ont changé. Certains échanges ne se répondent donc plus, ce qui est normal.

## Étape 6 : boussole, murs et fenêtres orientés (22/10/2026)

Dans LICIEL et en DPE 3CL, les parois et surtout les **fenêtres sont décrites par leur orientation** (nord, est, sud, ouest) : elle sert au calcul des apports solaires. L'assistant la relève maintenant tout seul, et nomme les murs ainsi : « **le mur nord** », « **le mur est, celui avec la télé** ».

**Principe** : quand le diagnostiqueur filme un mur de face, depuis l'intérieur de la pièce, la caméra regarde vers l'extérieur de ce mur. L'orientation du mur est donc le cap de la caméra pendant qu'il le décrit, arrondi au point cardinal le plus proche (4 points, ceux du DPE). Le **cap brut** est gardé (`cap_brut` dans l'état), avec sa preuve pour l'écran de validation (« cap 352° »). Une fenêtre citée avec son mur prend l'orientation de ce mur.

**Sur le téléphone** : une petite boussole reste affichée en haut à droite de la vidéo.
- Elle indique la direction filmée (« SO 223° »).
- Sa bordure indique la fiabilité : verte (bonne), orange (moyenne), rouge (faible), grise (pas de boussole).
- Si elle est perturbée, elle affiche « Faites un 8 avec le téléphone » (calibration), et l'assistant le dit une fois.
- Sur iPhone, l'accès est demandé à l'appui sur « Démarrer ».
- Sur Android récent, elle utilise l'orientation absolue ; sur Android ancien, l'orientation fournie par le navigateur.

**Boussole et gyroscope**. Le téléphone envoie deux mesures chaque seconde :
- le **cap** de la boussole : il donne le nord, mais il est faussé près du métal ou de l'électricité (radiateur en fonte, tableau électrique) ;
- le **lacet** du gyroscope : il ne connaît pas le nord, mais il donne juste l'angle entre deux murs.

La différence entre les deux est la même pour toute la visite. Estimée sur de nombreuses mesures (médiane), elle donne l'orientation de chaque mur par le gyroscope. Résultat :
- un mur filmé près d'un radiateur en fonte reste juste (la boussole perturbée y est notée) ;
- deux murs **face à face sont toujours opposés** (nord ↔ sud).

**Fiabilité** : bonne, moyenne, faible, ou absente (pas de boussole, accès refusé). Elle repose sur la précision annoncée par l'iPhone, sinon sur la stabilité de la différence cap − gyroscope. Les seuils (15° et 30°, 12° et 25°) sont des hypothèses à ajuster sur le terrain : depuis l'étape 7, ils sont dans `boussole.toml`.

**Correction à l'oral**, à tout moment : « Non, c'est le mur ouest », « ce mur est plein sud », « le mur est donne dehors ».
- L'orientation dite l'emporte sur la boussole, et sa preuve est gardée : « dit : non, c'est le mur ouest (la boussole donnait nord) ».
- Elle sert de référence : les autres murs se recalent par le gyroscope.
- Si elle dément la boussole de plus de 45°, la boussole est déclarée peu fiable pour la suite.
- « Le mur est en brique » n'est pas une orientation : « est » y est le verbe.
- « Le mur nord, en fait c'est du béton » vise le mur orienté nord.

**Pièce sans boussole fiable** (absente, faible, ou démentie) : l'assistant demande **une seule fois** « Ce mur est orienté nord, sud, est ou ouest ? », pour le mur extérieur filmé. Une réponse courte suffit : « Plein sud », « À l'est ».
- Avec le gyroscope, tous les autres murs s'en déduisent.
- Sans gyroscope, la question revient une fois par pièce.
- Si le téléphone n'a rien envoyé (essai écrit, rejeu d'une ancienne visite), rien n'est demandé.

**Cohérence** : si deux murs face à face (d'après le gyroscope) ont la même orientation, ou deux murs visés dans la même direction des orientations différentes, c'est signalé : « Attention : le mur nord et le mur ouest sont face à face, l'orientation de l'un des deux est fausse. »

**Tests** : `tests/test_boussole.py` (33 tests) :
- le calcul cap → orientation ;
- la fiabilité, et la visée stable ou balayée ;
- les murs opposés et les fenêtres orientées comme leur mur ;
- la correction orale et sa propagation ;
- la question unique sans boussole ;
- la confusion « le mur est en brique » ;
- les noms par orientation ;
- une visite simulée avec un téléphone qui envoie boussole et gyroscope.

Le prototype compte 189 tests.

**Limites** :
- La boussole n'a pas encore été essayée sur un vrai téléphone ; c'est à faire avec Noah, sur iPhone et sur un Android ancien.
- Le cap de l'iPhone tenu droit : corrigé à l'étape 7 (calcul par la matrice de rotation), à vérifier au test terrain.
- Le gyroscope dérive de quelques degrés sur une longue visite : sans effet sur l'arrondi au point cardinal (± 45°), mais la référence se recale si une orientation est redite.
- Un mur filmé de biais, depuis un coin de la pièce, donne un cap faux : l'orientation reste à confirmer à l'écran de validation, comme toute valeur de capteur.

## Étape 7 : une vraie conversation, Claude cerveau de chaque phrase (22/10/2026)

Demande de Noah : « il ne faut pas ajouter 3-4 mots de vocabulaire. Il faut qu'il comprenne TOUT, n'importe quelle phrase, comme quand je parle à Claude ».

**Ce qui change** :
- **Claude lit chaque phrase**, avec les images de l'instant et l'état complet de la visite. Il répond à tout, puis reprend la visite :
  - question générale : « C'est quoi un pont thermique ? » → « Un pont thermique, c'est un point faible de l'enveloppe où la chaleur s'échappe plus facilement… Un autre mur dans cette cuisine ? » ;
  - hors sujet : « Comment ça va ? » → « Très bien, merci. On continue la cuisine : un autre mur dans cette pièce ? » ;
  - ordre : « On fait une pause, je prends un appel », « reviens au séjour » ;
  - correction : « En fait, la chaudière date de 2012 », « oublie ce que je viens de dire sur la chaudière » ;
  - récapitulatif : « Tu as noté quoi pour la cuisine ? », « Où on en est ? ».
- **Les règles du serveur ne font que pré-remplir**. Ce qu'elles reconnaissent est noté tout de suite (bip), puis envoyé à Claude comme « déjà noté automatiquement », éléments créés compris.
  - Claude le vérifie : il corrige une valeur, ou annule un élément créé à tort (« un vieux grille-pain » n'est pas un deuxième radiateur).
  - Sa valeur remplace celle des règles, sans contradiction signalée, et n'est jamais ramenée à un seul mot du vocabulaire (« pierre et brique » reste « pierre et brique »).
  - Les règles ne bloquent jamais Claude.
- **Une question posée à l'assistant ne pré-remplit rien** : « Ça sert à quoi une VMC ? » ne crée plus de VMC.
- **Le serveur garde la main** sur la question suivante. Le parcours la calcule et la propose à Claude, avec le nom de l'élément (« le mur extérieur »), pour qu'il la nomme après une digression. Les garde-fous restent (une seule question, jamais « répétez », jamais « le mur 3 »), ainsi que la vérification des citations.
- **Une question restée sans réponse** est reposée à la fin de chaque digression, et non plus une seule fois.
- **Pause** : « on fait une pause » arrête les questions du parcours jusqu'à « on reprend ». Ce qui est dit pendant la pause est quand même noté.
- **Nouvelles actions de Claude** : `pause`, `reprendre`, `annuler`. `annuler` sert pour un pré-remplissage faux, ou pour « oublie ce que je viens de dire sur … » : la valeur revient à la précédente, ou l'élément est retiré.
- **Si Claude ne répond pas** (délai, abonnement indisponible), le serveur pose seul la question du parcours, comme avant.

**Rapidité** :
- La réponse de Claude arrive au fil de l'eau. **La voix démarre dès sa première phrase**, et le téléphone enchaîne les phrases suivantes sans couper.
- **File d'attente sans blocage** : pendant que Claude répond, la phrase suivante est déjà transcrite et pré-remplie (bip). Elle passe ensuite à Claude, avec les autres phrases dites entre-temps, en un seul appel.
- Si le diagnostiqueur reparle, la fin de la réponse en cours n'est pas lue.
- Mesuré sur les 30 phrases libres, avec le vrai Claude :
  - première phrase dite entre **1,5 et 1,8 s** (médiane de trois passages) après la fin de la phrase, **4 s au pire** ;
  - à ajouter : 0,7 s de silence pour détecter la fin de phrase, et ~0,05 s de transcription.
- **Le prix d'une vraie conversation** : à l'étape 5, la question du parcours partait en 0,1 s, sans IA. Elle attend maintenant Claude (~1,5 à 2,5 s). Le « noté » (bip) reste immédiat (0,09 s). L'ancien fonctionnement reste disponible : `DIAGAUTO_CONVERSATION=rapide`.

**Essai avec le vrai Claude** : `python -m assistant.evaluer --conversation`. Une visite est d'abord mise en place (séjour décrit, cuisine commencée). Puis viennent 30 phrases libres : 6 questions générales, 5 hors sujet, 6 de navigation, 5 corrections, 5 récapitulatifs et 3 descriptions libres. Résultat complet, phrase par phrase : [rejeux/20261022-etape7-conversation.md](rejeux/20261022-etape7-conversation.md). Les 30 phrases ont reçu une réponse sensée, suivie de la reprise de la visite.

**La visite réelle de Noah, rejouée** (son et images, au rythme réel, même version du serveur dans ses deux modes ; détail dans le même rapport) :

| | Mode rapide (étapes 5-6) | Conversation (étape 7) |
|---|---|---|
| Fin de phrase → réponse prête, médiane | 0,1 s | 2,3 s |
| Fin de phrase → réponse prête, pire cas | 3,2 s | 4,4 s |
| Bip « noté », médiane | — | 0,09 s |
| Séjour rempli à la fin | 60 % | 76 % |
| Informations manquantes à la fin | 11 | 7 |

En mode rapide, la question part tout de suite, mais elle est mécanique : « Il est en quoi ? » quatre fois, et « Un sous-sol » est compris comme un mur côté cave. En conversation, l'assistant comprend mieux :
- « Il te faut quoi d'autre sur ce mur ? » → « Pour le mur des trois fenêtres, j'ai tout. Il reste le plancher : il donne sur quoi ? » ;
- il relève de lui-même que « 30 mètres » est invraisemblable pour ce mur ;
- « Quel mur ? » → « C'est le mur qu'on n'a pas encore décrit, celui avec la télé, en face des fenêtres. ».

Quand Noah enchaîne ses phrases sans s'arrêter, l'assistant se tait : le bip confirme ce qui est noté, et la question vient au premier silence.

**Corrections des règles trouvées par cet essai** (elles faussaient le pré-remplissage) :
- « le premier mur du séjour », « ce mur de la chambre » : c'est la pièce où est le mur, et non « donne sur le séjour » ;
- « la chaudière date de 2012 » : la chaudière déjà décrite (correction signalée), et non une deuxième chaudière ;
- « il fait chaud dans cette cuisine » : la pièce où l'on est n'est jamais une valeur ;
- « reviens au séjour », « on retourne dans la cuisine » : changement de pièce ;
- « Pas d'autre mur. » : la liste des murs est close (n'était pas comprise sans Claude) ;
- Claude omet souvent le type d'un élément qu'il désigne par son identifiant : le serveur le déduit (ces corrections étaient refusées).

**Boussole (réponses d'Hermes à l'étape 6)** :
- **iPhone** : `webkitCompassHeading` donne le cap du haut de l'appareil, pas celui de la caméra.
  - Le cap de la caméra arrière est maintenant calculé par la **matrice de rotation complète** (alpha, bêta, gamma, norme W3C) : juste quand le téléphone est tenu droit, incliné ou en paysage.
  - `webkitCompassHeading` ne sert plus qu'à recaler le nord : on mesure l'écart avec le cap du haut calculé, quand le haut est à moins de 60° de l'horizontale, et on le lisse.
  - Code : [web/boussole.js](web/boussole.js). Il est testé avec Node par `tests/test_boussole_js.py` (11 tests : poses connues, 200 poses au hasard comparées à un calcul Python, recalage de l'iPhone). À vérifier au test terrain de Noah.
- **Seuils** : dans [boussole.toml](boussole.toml) (précision, dispersion, visée, correction, cohérence, iPhone), à ajuster sur le terrain sans toucher au code.

**Tests** :
- `tests/test_conversation.py` (12 tests), avec un faux Claude écrit à l'avance :
  - chaque phrase va à Claude ;
  - réponse lue phrase par phrase, une seule question, à la fin ;
  - question restée sans réponse reposée ;
  - pause et reprise ;
  - « reviens au séjour » ;
  - correction et annulation du pré-remplissage, sans contradiction ;
  - réponse périmée abandonnée, phrase suivante pré-remplie sans attendre ;
  - phrases en attente réunies en un seul appel ;
  - question du parcours si Claude n'en pose pas ;
  - « Décrivez le premier mur » de Claude compté comme sa question (pas de doublon) ;
  - Claude indisponible ;
  - contexte envoyé à Claude ;
  - les 30 phrases libres jouées de bout en bout.
- `tests/test_cerveau.py` : lecture de la réponse phrase par phrase pendant qu'elle s'écrit.
- `tests/test_boussole_js.py` : calcul du cap de la caméra.

Le prototype compte 215 tests.

**Limites** :
- **Réponses aux questions générales** : elles viennent des connaissances de Claude (Haiku), sans vérification par le serveur. Elles sont justes dans l'essai, mais parfois approximatives (validité des anciens DPE). Les consignes lui demandent de dire quand il n'est pas sûr.
- **Récapitulatifs** : justes, mais parfois maladroits (« il reste à voir les radiateurs, déjà notés »).
- **Latence** : environ 1,5 à 2 s de plus qu'à l'étape 5 avant la question. Elle monte à 4 s quand Claude écrit une longue première phrase, au premier message de la visite, ou au remplacement de son processus (tous les 30 messages).
- **Diagnostiqueur qui parle sans pause** : la réponse en cours est abandonnée dès qu'il reparle, pour ne pas lui couper la parole. (Un bruit l'interrompait aussi : corrigé à l'étape 8.)
- **Vouvoiement** : l'assistant vouvoie le diagnostiqueur, comme les questions du parcours. C'est une ligne des consignes, facile à changer.

## Étape 8 : plus fluide (test de Noah du 22/10/2026 après l'étape 7)

Retour de Noah (`sessions/20261022-120410-53ecb1`, séjour puis cuisine, 5 min 48) : « pas assez fluide, il s'arrête de parler, il répète, il ne prend pas toutes les infos, il ne comprend pas quand je change de pièce, il ne repère pas bien les murs, il parle des lampes ». Diagnostic complet, et visite rejouée avant/après : [rejeux/20261022-etape8-fluidite.md](rejeux/20261022-etape8-fluidite.md).

**1. « Il s'arrête de parler »** : la cause principale était un **claquement de 0,1 à 0,3 s** qui arrive dans le micro juste après chaque phrase de l'assistant (le téléphone qui bascule sa sortie son ; visible sur `audio.wav`). Le serveur le prenait pour une prise de parole : il coupait la voix et abandonnait la réponse. À 222 s et 287 s, la réponse n'a jamais été entendue.
- La voix n'est plus coupée que par une **parole confirmée** : 0,35 s de parole, 0,6 s quand l'assistant parle (son écho n'est pas une prise de parole).
- Une réponse coupée par un bruit (transcrit vide) est **redite**.
- Un bruit transcrit « . » ne part plus ni à Whisper ni à Claude. Au début de la visite, Whisper avait inventé « Laine de verre. » sur ce bruit, et Claude s'était mis à décrire l'image.
- Plus de second avis de Whisper en conversation : il coûtait 2 à 3 s et bloquait la phrase suivante.
- Une phrase inachevée (« … et l'isolant est du ») bloquait tout jusqu'à 8 s. Maintenant, elle est notée tout de suite, et seul Claude attend la suite (2,5 s au plus).

**2. Toujours une voix en moins de 2 s** (avant : 3,1 s en médiane, Claude réfléchissant avant d'écrire) :
- « **Noté.** » est dit tout de suite quand les règles ont noté quelque chose. S'il y a une contradiction, c'est elle qui est dite : « Noté : parpaing au lieu de brique. ».
- Sinon, « **Alors…** » ou « Voyons… » est dit si rien n'est encore parti 1,4 s après la fin de phrase, même quand Claude répond encore à la phrase précédente. Rien n'est dit pour un mot isolé (débris, « euh »).
- Claude enchaîne sans redire « noté » : le serveur retire ce mot de sa première phrase.
- Claude reçoit une seule image par phrase (au lieu de trois), et son processus est renouvelé toutes les 12 phrases (au lieu de 30). Il a moins à relire et répond plus vite.
- Rejeu de la visite : première chose dite à **0,9 s** en médiane (2,6 s avant), 1,4 s pour 90 % des phrases (3,9 s avant).

**3. Hors sujet** : les consignes de Claude interdisent de décrire la décoration (rideau, lampe, appareil). Un objet ne sert qu'à nommer un mur (« le mur avec la télé »).

**4. Infos perdues ou mal rangées** :
- **Élément en cours** : une phrase qui ne nomme rien (« l'isolant, c'est de la laine de verre 30 cm ») complète l'élément qu'il est en train de décrire, et non celui de la dernière question. Au test, cette phrase avait été rangée sur le plafond. Cet élément n'est valable que dans sa pièce.
- **Interprétation probable de Claude** : elle est notée, avec la mention « à vérifier » pour l'écran de validation. Avant, elle était perdue puis redemandée (« une autre maison derrière, mais c'est pas la mienne » : demandé deux fois de plus).
- Préciser une valeur (« isolé », puis « isolé laine de verre 30 cm ») n'est plus une contradiction.
- Consigne : ne jamais redemander ce qui a été dit, même mal rangé. Le ranger au lieu de le redemander.

**5. Phrases globales** : « Tous les murs de la maison sont en brique » est une **règle du logement**, comprise aussi par les règles du serveur. Elle vaut pour les murs déjà décrits et à venir, dans toutes les pièces, et le matériau n'est plus demandé.

**6. Changement de pièce** :
- Par la parole : « là c'est la cuisine », « après il y a un couloir », « on retourne dans… ». « On a changé de pièce » sans nom : Claude la reconnaît sur les images.
- Par la vidéo : pendant les silences, Claude regarde les images. S'il voit une autre pièce, l'assistant demande « **On est dans la cuisine ?** », et « oui » change de pièce.
  - Un « nouveau décor » (couleurs de l'image jamais vues dans la pièce, voir `assistant/decor.py`) avance ce coup d'œil.
  - Ce signal ne décide jamais seul : mesuré sur la visite, tourner la caméra dans une même pièce change autant les couleurs que changer de pièce.

**7. « Ce mur, ce mur et ce mur »** : chaque « ce mur » (ou « un mur ici ») désigne le mur filmé à cet instant.
- Un mur est créé pour chacun. Son instant est estimé d'après sa place dans la phrase, et le mur reçoit l'image et la visée de la boussole de cet instant. Il n'est pas créé si la caméra visait un mur déjà connu.
- Claude reçoit ces images et donne à chacun un repère visuel. La question suivante porte sur eux, et non plus « un autre mur ? ».

**8. Transcription** : mots collés corrigés (« cemur », « semur » → « ce mur » ; « murici » → « mur ici » ; « qui faut quoi doute ? » → « il te faut quoi d'autre ? »). Les débris (« Pourourir », « Djaddi ») sont ignorés par Claude.

**Tests** : `tests/test_fluidite.py` (18 tests) reprend chaque constat avec un faux Claude et du son fabriqué :
- claquement sans coupure ;
- réponse redite après un bruit ;
- voix en moins de 2 s ;
- phrase inachevée notée tout de suite ;
- pas de décoration ;
- élément en cours ;
- valeur probable notée ;
- « tous les murs » ;
- changements de pièce (parole et images) ;
- murs montrés un par un (image et boussole de chaque instant) ;
- débris et mots collés.

Le prototype comptait alors 233 tests.

(Depuis l'étape 9, « Noté. » n'est plus dit : un bip le remplace, et la contradiction se dit « Je remplace brique. ».)

**Limites** :
- **Le rejeu ne reproduit pas le téléphone** : la coupure de la voix par le claquement est corrigée côté serveur, à vérifier au prochain test de Noah.
- **La réflexion de Claude** (impossible à couper par Claude Code) reste le plus long : 1 à 5 s avant sa première phrase. « Noté. » et « Alors… » la masquent, mais le contenu de la réponse arrive ensuite.
- **L'instant de chaque « ce mur »** est estimé d'après sa place dans la phrase (pas de minutage mot à mot avec le moteur de transcription rapide) : à une seconde près.
- **« On est dans la cuisine ? »** ne vient que pendant un silence (la veille de Claude) ou si Claude le remarque en répondant.

## Étape 9 : ne pas répéter, jamais de faux doublon (22/10/2026)

Demandes de Noah :
- ne pas répéter ce qu'il dit : à « laine de verre 30 cm », pas de « OK, c'est noté laine de verre 30 cm » ;
- plus de faux doublon : il a montré un mur côté couloir jamais décrit, et l'assistant a répondu « je l'avais déjà noté, c'est un doublon, je le retire ».

Visite rejouée avant et après : [rejeux/20261022-etape9-doublons.md](rejeux/20261022-etape9-doublons.md).

**1. Ne pas répéter** :
- Ce que les règles ont compris est confirmé par un **bip**, sans mots. Puis vient directement la question suivante (de Claude). « Alors… » n'est dit que si rien n'a été compris ni dit au bout de 1,4 s.
- Une contradiction se dit sans répéter la nouvelle valeur : « **Je remplace brique.** » (et pour un nombre : « Je corrige : il y en avait 2. »). Elle n'est dite qu'une fois.
- Le serveur ne laisse pas passer une phrase de Claude qui reprend ce qu'il vient de dire, après une description. Il retire « Noté » ou « c'est noté » ; il supprime une phrase dont la moitié des mots porteurs viennent de la sienne (« Laine de verre 30 centimètres. », « Tous les murs en brique. »).
  - Ce filtre ne s'applique pas à une question posée à l'assistant : y répondre reprend forcément ses mots (« un pont thermique, c'est… »).
- Les consignes de Claude : rien de ce qu'il vient de dire ; un récapitulatif seulement s'il le demande ou en fin de pièce.
- **Mesure** (`assistant/repetition.py`) : nombre de mots porteurs de sa phrase repris dans la réponse à une description.
  - Les articles et le nom de l'élément ne comptent pas : la question doit pouvoir dire « ce mur ».
  - Ce nombre figure dans le bilan de chaque visite (`mots_repetes_par_reponse`) et dans `python -m assistant.evaluer --conversation`.
  - Rejeu de la visite : **0,15 mot par réponse** (3 réponses sur 27), contre 0,59 avant et 1,25 au test de Noah. Avec le vrai Claude, sur 27 descriptions : 0,15 aussi.

**2. Jamais de faux doublon, jamais de suppression de lui-même** :
- **Claude ne peut plus supprimer un élément** de lui-même. Une suppression (ou l'oubli d'une valeur ancienne) n'est acceptée que s'il la demande (« oublie », « annule », « supprime », « c'est le même »). Sinon elle est refusée et notée au journal. Il peut toujours corriger une valeur que les règles ont mal pré-remplie dans la même phrase.
- **Doublon possible** : Claude le signale (action `doublon`), et le serveur demande « **C'est le même mur que le mur côté voisin ?** ».
  - « Oui » réunit les deux : ce qui n'était dit que de l'un passe à l'autre. « Non » les garde.
  - Rien n'est jamais réuni sans son « oui ».
- **Jamais d'affirmation sans preuve** : une phrase de Claude qui dit « déjà noté », « doublon », « je le retire » ou « c'est le même » n'est pas dite. Seule la question passe.
  - La preuve (même repère, même orientation, même description dans l'état) est notée au journal avec la question.
- **Règles corrigées** (elles créaient les faux doublons) :
  - « le mur du tableau » va sur le mur qui porte ce repère. Au test, il allait sur le dernier mur décrit, celui du miroir, et Claude avait alors supprimé le vrai mur du tableau.
  - « une fenêtre, cette fenêtre en bois » et « trois fenêtres, ces trois fenêtres en PVC » : un seul élément.
  - « une fenêtre ici, une fenêtre ici, une fenêtre là-bas » : une seule entrée de 3 fenêtres. Au rejeu de l'étape 8, le séjour finissait avec 9 fenêtres, que Claude « nettoyait » en supprimant. Maintenant il en a 3 sans rien supprimer.
  - « le radiateur est électrique, un vieux grille-pain » : un seul radiateur.
- **Rejeu de la visite** : 0 élément supprimé par l'assistant (5 avant, 2 au test de Noah) et 0 « déjà noté » dit sans preuve (3 au test). Une seule question « C'est le même mur que… ? ».

**Tests** : `tests/test_doublons.py` (18 tests).
- 10 cas de nouveaux murs ressemblant à d'anciens, sans aucune suppression automatique : même « donne sur », même phrase redite, mur côté couloir, mur du tableau, murs montrés un par un, même repère (« non » puis « oui »), doute sans preuve, fenêtre annoncée puis décrite, même orientation.
- La suppression seulement quand il la demande.
- La mesure des mots répétés, avec un « Claude bavard » qui reprend tout ce qu'on lui dit : 0 mot répété.

Le prototype compte 251 tests.

**Limites** :
- Le filtre des reprises est une règle simple (la moitié des mots porteurs) : une reprise courte peut passer (« D'accord, c'est chez le voisin. »), et Claude répète moins de lui-même grâce à ses consignes.
- Sans suppression automatique, un élément créé en trop reste jusqu'à ce que le diagnostiqueur réponde « oui » à « C'est le même… ? », ou jusqu'à l'écran de validation.

## Étape 10 : plus de faux « Hors réseau » (22/10/2026)

Noah voyait « Hors réseau » alors qu'il avait du réseau. Causes, changements et mesures : [rejeux/20261022-etape10-reseau.md](rejeux/20261022-etape10-reseau.md).

**Cause** : **toute** fermeture de la liaison affichait « Hors réseau », tout de suite, sans vérifier que le serveur était injoignable.
- Ces fermetures arrivent avec un bon réseau : page mise en arrière-plan ou écran verrouillé (iOS suspend la page), serveur redémarré, erreur sur un seul message reçu (le serveur fermait la liaison).
- Il n'y avait pas de battement de cœur : une coupure d'une seconde ressemblait à une panne, et une liaison morte n'était pas vue.
- Ce qui était dit pendant une coupure était perdu pour l'assistant.

**Maintenant** :
- **Battement de cœur** toutes les 2 s. Le serveur répond tout de suite, même quand Claude réfléchit : 1 ms en médiane, 35 ms au pire, mesuré pendant le rejeu complet d'une visite avec le vrai Claude.
- **« Hors réseau » seulement si le serveur est vraiment injoignable** : 3 battements sans réponse (6 s), ou une reconnexion qui échoue depuis 6 s.
- Une réponse lente donne « réseau lent » : pastille orange, sans alerte. Claude lent donne « L'assistant réfléchit… ».
- **Reconnexion automatique et silencieuse** : après 0,5 s, 1 s, puis toutes les 2 s. Elle est aussi immédiate quand la page revient ou que le réseau revient.
- Page cachée (écran verrouillé) : aucune alerte.
- **Rattrapage** : le téléphone garde ce qui n'a pas pu partir (tout le son, une image sur trois, les capteurs, les phrases écrites ; jusqu'à 2 à 3 min). Il l'envoie au retour, dans l'ordre, et le serveur traite les phrases dites pendant la coupure.
  - Le serveur redit ce qu'il a dit pendant la coupure (moins d'une minute).
  - Le téléphone rapporte ses coupures (durée, cause), notées au journal avec le code de chaque fermeture.
- Une erreur sur un message est notée au journal et ne ferme plus la liaison.

**Fichiers** : `web/liaison.js` (la liaison du téléphone, testable seule) ; `assistant/serveur.py` (battement, erreurs, journal) ; `assistant/session.py` (rattrapage).

**Tests** :
- `tests/test_liaison_js.py` (8 scénarios, avec Node et une fausse horloge) : réseau lent, Claude lent, vraie coupure, coupure brève, liaison morte, écran verrouillé, coupure trop longue, code incorrect.
- `tests/test_liaison.py` (4 tests du serveur) : battement pendant que Claude réfléchit, message illisible, reconnexion avec rattrapage, son gardé traité au retour.

Le prototype compte 263 tests.

**Limites** :
- À vérifier sur l'iPhone de Noah : le module de liaison est testé avec une fausse horloge, pas encore sur le téléphone.
- Écran verrouillé : iOS suspend la page, et le son n'est plus capté pendant ce temps.
- Serveur redémarré pendant une visite : une nouvelle visite commence à la reconnexion. Ne pas redémarrer le serveur pendant un test.

## Étape 11 : de la visite aux tables LICIEL (22/10/2026)

Le `etat.json` d'une visite (pièces, murs, ouvertures, émetteurs) devient la liste des pièces et le métrage Carrez de notre
dossier de test LICIEL, dans `sorties/dossier-test`, hors de `C:\LICIEL_*`. Depuis la racine du projet :

```
.venv\Scripts\diagauto generer --modele C:\Users\conta\Documents\liciel\dossier-test\etape2-dossier-4pieces
```

Par défaut, la visite prise est la plus récente de `sessions/`. Le détail (tables écrites, mesures, hypothèses, essai à
faire dans LICIEL) est dans le [README du projet](../README.md#générer-le-dossier-liciel-dune-visite-pont-assistant--liciel).

Sur la dernière visite (le rejeu de la visite de Noah avec le code de l'étape 10) :
- **Séjour** et **Cuisine** sont retrouvés dans le dossier (« Séjour » = « Sejour ») et gardent leur clé LICIEL ;
- **Couloir** est ajouté au bâtiment « Appartement » ;
- Chambre 1 et Salle de bains, non vues, restent telles quelles ;
- les 3 pièces sont dans le Carrez, **à mesurer** : l'assistant ne relève pas encore les surfaces, et aucune n'est inventée ;
- `diagauto verifier` : 13 tables sur 13 identiques à la relecture.

**Test** : `tests/test_pont_liciel.py` construit une visite avec la checklist de l'assistant, l'exporte comme la session,
puis vérifie les pièces et le Carrez produits. Le prototype compte 264 tests.

## Test de Noah du 22/10 après-midi : questionnaire en direct, moins de questions

Visite `sessions/20261022-153605-67f6df` (11 min 43, trois pièces). Noah : « il pose trop de questions que je répète, des
fois plus de réponse pendant 2 minutes, il me fait passer à une pièce alors qu'on n'a pas fini celle-là ; un questionnaire
en direct sur le téléphone pour cocher les réponses en même temps qu'à l'oral ». Analyse complète et rejeu avant/après :
[rejeux/20261022-noah-apres-midi.md](rejeux/20261022-noah-apres-midi.md).

**Questionnaire en direct** (`web/app.js`, `assistant/reponses.py`) :
- chaque question arrive sur le téléphone **avec ses réponses en boutons** (« PVC · Bois · Alu · Bois-alu · Métal »,
  « Oui · Non », « Non isolé · Isolé par l'intérieur… ») ; un appui vaut une réponse dite : notée tout de suite (citation
  « coché sur le téléphone »), et la question suivante part aussitôt, sans attendre Claude ;
- le bouton **📋 Fiche** montre toute la pièce en cours (et le chauffage, l'eau chaude, la ventilation) : chaque information
  utile, sa valeur ou « à remplir » en rouge ; un appui sur une ligne montre ses réponses, pour compléter ou corriger ;
- les réponses en boutons sont celles du vocabulaire des règles : une réponse cochée est rangée comme la même réponse dite.

**Moins de questions répétées** :
- **bruits** : la transcription rapide donnait des lettres sur un bruit (« A. », « F. », « Il. ») ; l'assistant y voyait une
  réponse incomprise et reposait sa question (« PVC, bois ou alu ? » 4 fois). Une phrase courte sans aucun mot connu est
  maintenant réécoutée par Whisper : bruit (rien n'est dit), ou vraie réponse ;
- **réponses courtes mal transcrites** : « Vaime s. » (VMC), « Na. » (non) ; Whisper les retrouve, guidé au besoin par les
  réponses attendues à la question posée ;
- **« Un autre mur dans cette pièce ? »** (10 fois) devient « D'autres murs sur l'extérieur ou un local non chauffé ? »,
  une fois par pièce, reposée seulement après un nouveau mur de ce genre (un mur sur un voisin chauffé ne compte pas pour
  le DPE). Claude ne peut plus la reposer sous une autre forme : ses questions ont la même clé que celles du parcours.
  « Pas d'autre mur » peut être dit à tout moment ;
- **« c'est le même mur »** réunit les deux murs, même sans « oui » au début ou transcrit avec un point d'interrogation.

**Plus de longs silences** : une réponse coupée par un bruit n'était reprise que s'il n'y avait eu qu'un seul bruit ; avec
deux bruits de suite (téléphone manipulé), jamais, d'où 30 à 35 s de silence et les « Allô ? ». Elle est reprise dès
qu'aucune vraie phrase n'a été dite depuis.

**Pas de changement de pièce avant la fin de la pièce** : « On est dans la cuisine ? », proposé d'après l'image alors que la
première pièce n'était pas finie, n'est plus proposé tant qu'il manque quelque chose ; Noah peut toujours le dire lui-même.
La première pièce n'est plus nommée « U » (« c'est la première pièce » : « Pièce 1 »).

**« Hors réseau » alors que le réseau est bon** (même jour) : le téléphone avait oublié le certificat du serveur, et la page
gardée en mémoire s'affichait sans montrer l'avertissement. L'accueil affiche maintenant « Serveur injoignable depuis ce
téléphone » avec un lien (« toucher ici ») qui fait réapparaître l'avertissement du certificat.

**Rejeu de la visite** (même son, nouveau code) : « D'autres murs… ? » 2 fois au lieu de 10 ; aucun bruit pris pour une
réponse (17 avant) ; délai de réponse au pire 9,1 s au lieu de 32 s ; un seul mur pour la phrase qui en donnait deux ;
plus de « pièce U » ni de changement de pièce proposé trop tôt. Détails et limites dans le rapport de rejeu.

**Tests** : `tests/test_questionnaire.py` (19), `tests/test_capture.py` (3), scénarios de référence mis à jour. Le prototype
compte 287 tests.

## Étape 12 : carte des pièces de la vidéo, pièces revisitées, phrase → mur (22/10/2026)

Après la visite, sur le serveur (dans `prototype-assistant`) :

```
..\.venv\Scripts\python -m assistant.carte sessions\<visite>
```

Sans dossier : la visite la plus récente qui a des images. `--sans-claude` : ne rien montrer à Claude. La commande écrit
dans le dossier de la visite `carte.md` (à lire), `carte.json` et, si la visite a un état, `etat-consolide.json`, que
`diagauto generer` lit en priorité.

**Ce que fait la carte** (`assistant/carte.py`, `assistant/vision.py` ; OpenCV, licence Apache-2.0 ; sur le processeur) :
1. **suivi continu du mouvement**, image par image (jusqu'à 30 images par seconde) : on sait quand la caméra tourne sur
   place, quand elle avance, quand le suivi décroche ;
2. **images clés** choisies par le mouvement (pas une photo toutes les n secondes), et **stations** : suites d'images où
   le diagnostiqueur tourne sur place, donc dans une seule pièce ;
3. **reconnaissance de lieu** : chaque image clé est comparée aux images qui lui ressemblent le plus (mots visuels), puis
   la ressemblance est vérifiée par la géométrie (au moins 35 points communs cohérents ; un même modèle de porte ou de
   fenêtre dans deux pièces en donne au plus une trentaine) ;
4. **pièces**, dans l'ordre du temps : chaque station rejoint la pièce qu'elle reconnaît, sinon la pièce annoncée, sinon
   reste dans la pièce en cours (on ne change pas de pièce en tournant sur place). Une image clé n'est **ancrée** (sûre)
   que si l'image la relie, de proche en proche, au début de sa pièce ;
5. **Claude** (abonnement, sans clé API) juge les passages non ancrés : une image toutes les 8 s, toutes les 2 s juste
   avant l'annonce d'une pièce, comparée à 6 images ancrées de chaque pièce ; 32 images par appel, 3 appels au plus ;
6. **cap de la caméra** : boussole et gyroscope du téléphone, sinon le suivi de la vidéo (les murs s'appellent alors
   « mur A, B, C, D », jamais nord ou est inventés) ;
7. **phrase → mur** : à l'instant du mot qui désigne (« ce mur »), la pièce reconnue et le cap donnent le mur visé, comparé
   à l'élément choisi par l'assistant pendant la visite.

**Pourquoi « ancrée »** (ce qu'ont montré les visites de Noah) :
- **la voix retarde sur la porte** : la pièce est annoncée jusqu'à 15 s après y être entré. Cuisine filmée dès 3:03,
  annoncée à 3:18 ; sortie de la cuisine vers 4:13, « pièce U » dite à 4:28 ;
- **elle peut se tromper longtemps** : dans le rejeu de la visite de l'après-midi, l'assistant s'est cru dans la cuisine de
  4:18 à 7:09, alors que Noah était revenu dans la première pièce ;
- les images d'un tel passage se reconnaissent entre elles et portent le mauvais nom. Seules les images reliées au début de
  la pièce prouvent quelque chose ; les autres sont montrées à Claude.

**Garde-fous** :
- jamais deux pièces pour le même endroit ;
- pour contredire la pièce annoncée, il faut 4 liens vers des images ancrées. Quelques liens peuvent venir d'une porte :
  depuis la pièce U, on voyait la chambre, et sans cette règle la chambre entière se rangeait dans U ;
- une autre pièce vue par Claude (entrée, escalier) devient une **question**, jamais une pièce créée d'après une image ;
- une pièce est **revisitée** si l'on en est sorti vers une autre pièce, puis revenu. Un coup d'œil de moins de 4 s ou des
  images floues ne comptent pas.

**Branchements** :
- **état de l'assistant** : `etat-consolide.json` contient
  - une seule pièce par endroit (« Pièce 1 » et « Séjour » fusionnées si c'est le même endroit) ;
  - les murs nommés par repère et cap (« le mur nord, celui avec le tableau ») ;
  - les éléments notés dans une pièce mais filmés dans une autre, signalés ;
  - les questions de la carte ;
- **`diagauto generer`** lit `etat-consolide.json` en priorité. Son rapport dit les pièces revisitées et liste les questions,
  par exemple : « les 2 radiateurs (E1) : noté dans « Cuisine », mais filmé dans « Pièce 1 » : dans quelle pièce ? » ;
- **état écrit à chaque changement**, et plus seulement à « Terminer » : la visite de l'après-midi, jamais terminée, n'avait
  pas d'état.

**Mesures** (ce PC, 12 cœurs, sans carte graphique ; vérité relevée image par image) :

| Visite | Ce qu'il fallait trouver | Résultat |
|---|---|---|
| Noah, après-midi (`20261022-153605`, 11 min 43, images à 1 par seconde, boussole) | U, cuisine, U, chambre, U ; la voix en retard à chaque porte | 3 pièces, U revisitée ; **260 images clés justes sur 262** (à plus d'1 s d'une porte) ; 4 questions : entrée, escalier, 2 hésitations de Claude |
| Rejeu de la même visite (`20261022-162157`) | pareil, mais l'assistant s'est cru dans la cuisine de 4:18 à 7:09 (retour non annoncé) | retour trouvé par Claude, **261 sur 262** ; les 2 radiateurs notés « cuisine » signalés |
| Noah, matin (`20261022-120410`, 5 min 47, images à 1 par seconde, sans capteurs) | séjour, couloir, cuisine, retour au séjour à 5:39, non annoncé | séjour revisité **de 5:39 à 5:47** ; le couloir rangé avec la cuisine ; 1 question (escalier) |
| Vidéo de synthèse (tests) | 2 pièces, 2 allers-retours, retour non annoncé | 2 pièces, jamais de doublon ; 5 phrases sur 5 au bon mur avec la boussole ; sans boussole, même lettre pour le même mur |
| video-001 (séjour, 38 s, recompressée par WhatsApp) | 1 pièce | 1 pièce, 3 murs ; suivi tenu sur 97 % des images |

**Temps** : visite de l'après-midi, 17 s de calcul, 55 s avec Claude (3 appels, 82 images) ; video-001 à 30 images par
seconde, 17 s pour 38 s de film.

Détails, avant/après et réponses de Claude : [rejeux/20261022-etape12-carte.md](rejeux/20261022-etape12-carte.md).

**Limites, honnêtement** :
- **Pas de carte 3D métrique** : ni plan, ni surfaces, ni longueurs de murs. C'est une carte des lieux (quelles images
  montrent le même endroit). La suite est la reconstruction 3D (COLMAP/GLOMAP, docs/02-capture-video.md § 3.1).
- **Aucune vidéo complète d'une vraie visite** : les visites de Noah n'ont que les images envoyées en direct (1 par
  seconde) ; la vidéo complète n'est envoyée que depuis le 22/10 après-midi. À 1 image par seconde, le suivi décroche
  souvent et peu d'images se relient : Claude juge alors une grande partie de la visite (82 images sur 11 min). Le suivi
  continu n'est éprouvé que sur la vidéo de synthèse et video-001.
- **Sans Claude**, un retour non annoncé qu'aucune image ne relie au premier passage n'est pas trouvé : il reste dans la
  pièce dite par la voix.
- **Aux portes**, la limite entre deux pièces est juste à 1 ou 2 s près ; un couloir qui mène à une pièce est souvent rangé
  avec elle.
- **Orientation des murs** : l'axe des murs d'une pièce est estimé d'après les caps où la caméra s'attarde. Avec la boussole
  lue une fois par seconde, il a varié de 40° pour la pièce U d'un calcul à l'autre (images retenues différentes). Le
  nord, l'est, le sud ou l'ouest d'un mur est donc à confirmer, en attendant les capteurs à 20 mesures par seconde et une
  estimation par les lignes des murs dans l'image. *Étape 13 : axe du logement, voir plus bas.*
- **Phrase → mur** : « ce mur », « celui-là » (le mur en face) ; pas encore « le deuxième mur » ni « à gauche ». *Fait à l'étape 13.*
- **Pièces identiques** (deux chambres pareilles) : vérification géométrique et questions ; pas encore essayé sur une vraie
  visite.
- Claude varie un peu d'un calcul à l'autre (une hésitation de plus ou de moins) ; ses réponses sont gardées dans
  `carte.md`, tableau « Passages non reconnus ».

**Tests** :
- `tests/test_carte.py` (12) : synthèse ; lecture des réponses de Claude ; consolidation ; visites réelles de Noah et
  video-001 quand elles sont présentes ;
- `tests/scene_synthetique.py` : pièces texturées filmées en tournant et en marchant, boussole simulée, vérité terrain ;
- `tests/test_pont.py` (racine du projet) : état consolidé lu par `diagauto generer`.

Le prototype compte 299 tests.

## Étape 13 : le DPE du logement, par côté (22/10/2026)

**Ce que Noah a demandé** : le DPE décrit l'**enveloppe** du logement (tout ce qui l'entoure), pas chaque pièce. On
raisonne par côté : un « mur ouest », ce sont tous les murs ouest du logement, toutes pièces confondues. Les murs entre
deux pièces ne comptent pas. Et pendant la visite : « qu'on soit dans le séjour ou la chambre, pour le DPE on s'en
fiche » : l'assistant ne doit pas demander la pièce.

**Ce que le diagnostiqueur entend maintenant** (sans jamais une question sur la pièce) :
1. « Ce mur donne sur quoi ? », puis, s'il donne dehors ou sur un local non chauffé, son matériau, son épaisseur, son
   isolation ; un mur sur un voisin ou sur une autre pièce ne demande rien de plus ;
2. « Des fenêtres ou une porte sur ce mur ? », puis leur menuiserie, leur vitrage, leurs volets ; une porte sur un mur qui
   donne dehors ou sur les parties communes donne dehors ou sur le palier : c'est déduit, pas demandé ;
3. « Et côtés nord et sud, le logement donne sur quoi ? » (avec la boussole : seuls les côtés dont rien n'est dit), ou
   « Les autres côtés du logement donnent sur quoi ? » (sans boussole). Bouton « Des voisins » ou « Non, c'est tout » ;
4. le plafond, puis le plancher du logement, **une fois** ;
5. le chauffage, les radiateurs (« à eau ou électriques ? », sauté s'il est déjà clair : radiateurs électriques), l'eau
   chaude, la ventilation, **une fois** ;
6. « C'est complet pour le DPE. »

Il peut tout dire à sa façon, dans l'ordre qu'il veut : « au nord le voisin, à l'est la cage d'escalier », « au sud la
cour, brique 30 cm, avec deux fenêtres en alu », « mur est : 60 % sur le voisin, 40 % dehors », « le mur de gauche donne
sur le voisin ». Une pièce dite (« on passe dans la chambre ») est seulement notée, pour le Carrez et le repérage.

**Comment c'est rangé** (`assistant/checklist.py`) :
- les murs, fenêtres, portes, le plafond et le plancher sont ceux du **logement** (« enveloppe »), avec les pièces où ils
  ont été vus ; les radiateurs, le chauffage, l'eau chaude et la ventilation aussi ;
- un mur filmé ou dit du même côté qu'un mur déjà décrit, et qui donne sur la même chose, **le rejoint** : rien n'est
  redemandé. Dit autrement (le même côté sur un voisin dans la chambre), c'est une **autre partie** de ce côté, avec sa
  part ou sa longueur ; ses fenêtres vont sur la partie qui donne dehors ;
- une fenêtre est **sur un mur** (« sur ce mur : 3 fenêtres ») ; sa boussole l'emporte sur le mur dont on parlait ;
- les murs entre deux pièces sont gardés à part et **ignorés pour le DPE** ;
- l'état (`etat.json`) a une partie `enveloppe` : murs par côté, murs entre pièces, plafond, plancher, fenêtres (chacune
  avec son mur), côtés pas encore décrits ;
- l'écran du téléphone montre la **fiche « DPE du logement »** : chaque côté, ses murs et leurs fenêtres, puis plafond,
  plancher et équipements, à corriger d'un appui.

**Points ouverts de l'étape 12, vérifiés** (`assistant/carte.py`, après la visite) :
- **orientation des murs** : l'axe des murs était estimé pièce par pièce, sur les images prises en balayant ; il variait de
  40° d'un calcul à l'autre pour la pièce U. Désormais :
  - avec la boussole, l'axe est celui du **logement** (les murs des pièces sont parallèles), estimé sur toutes les pièces ;
    une pièce que cet axe explique vraiment mal garde le sien ;
  - le cap de chaque image vient du **suivi de la vidéo**, recalé sur **toutes** les mesures de boussole des images
    reliées entre elles, chaque mesure comparée au cap de son propre instant (avant : une seule mesure, prise jusqu'à
    0,4 s à côté pendant que la caméra tourne) ;
  - les murs désignés pendant la visite (« ce mur ») comptent davantage ;
  - des murs tournés de près de 45° par rapport au nord (côté incertain) deviennent une question ;
  - un côté filmé différent du côté noté par l'assistant devient une question.
- **« le mur de gauche », « sur ma droite », « celui derrière moi », « en face »** : le mur visé est celui de la caméra
  décalé de 90° ou 180°, à l'instant où c'est dit (« ça donne derrière sur les toilettes » n'est pas pris pour « derrière
  moi ») ;
- **« le deuxième mur »** : le deuxième montré dans la pièce (comme pendant la visite) ; à défaut, le deuxième noté par
  l'assistant dans la pièce.

| Essai | Avant | Après |
|---|---|---|
| Vidéo de synthèse, boussole correcte | 5 phrases sur 5 au bon mur | 5 sur 5 |
| Même vidéo, boussole à 1 mesure par seconde, bruitée de ±20° (6 tirages) | 24 sur 30 ; axes des deux pièces écartés jusqu'à 74° | **30 sur 30** ; un seul axe, juste à 12° près |
| « à gauche », « sur ma droite », « derrière moi », « le deuxième mur » (synthèse) | non rattachés | 5 sur 5 |
| Visite de Noah, après-midi (images à 1 par seconde, boussole) | axe de U variable de 40° ; cuisine seule | **un seul axe (67°) pour U, la cuisine et la chambre** |

**Pont LICIEL** (`diagauto/pont.py`) : le rapport de `diagauto generer` (texte et `diagauto-pont.json`, partie `dpe`)
décrit le DPE du logement : chaque côté, ses murs et leurs parties, les fenêtres et portes de chacun, le plafond, le
plancher, les équipements, les côtés pas encore décrits et ce qui reste à renseigner. Une valeur déduite y est marquée
« déduit ». Les pièces restent pour le Carrez, avec ce qui y a été vu. **Ce DPE n'est pas encore écrit dans les tables
LICIEL** : c'est l'étape suivante du plan (docs/01-cadrage.md).

**Relecture** : une relecture indépendante du code a trouvé 9 défauts, tous corrigés et testés (`tests/test_enveloppe.py`) :
« il l'est » pris pour le côté est ; « par l'intérieur » pris pour un mur sur l'intérieur ; la deuxième partie d'un mur
sans côté ; « le reste » d'un mur pris pour « les autres murs » ; la longueur d'une partie recopiée sur l'autre ; une
fenêtre rangée sans tenir compte de sa pièce ; la porte déduite non mise à jour quand son mur est corrigé ; un mur réuni
d'office à un autre puis dit différent, qui écrasait le premier ; et l'évaluation qui plantait. Ont aussi été corrigés :
« radiateur basse » pris pour « radiateur acier » (donc « à eau » inventé), et le chauffage électrique déduit des
radiateurs seulement si les radiateurs étaient dits avant.

**Rejeu des visites de Noah** (phrases réellement dites, sans Claude ni boussole) : voir
[rejeux/20261022-etape13-dpe-par-cote.md](rejeux/20261022-etape13-dpe-par-cote.md). Aucune question sur la pièce ; les
murs de la vraie visite sont reconnus et nommés comme avant (« le mur des 3 fenêtres », « le mur côté voisin »).

**Limites, honnêtement** :
- **Sans boussole**, on ne sait pas de quel côté est un mur : il est rangé « côté à trouver », et l'assistant demande une
  fois « Les autres côtés du logement donnent sur quoi ? ». « C'est tout » clôt la liste des murs.
- Un mur que rien ne distingue (pas de côté, pas de repère, pas de fenêtre) se nomme encore par son rang dans sa pièce
  (« le deuxième mur », « le premier mur du séjour » vu d'ailleurs).
- Les parties d'un mur ont leur part ou leur longueur dite ; leur **surface** n'est pas encore calculée (pas de plan coté).
- **Hypothèses 3CL à faire valider** : un mur sur un voisin ou sur une pièce chauffée n'est pas déperditif (rien d'autre
  n'est demandé) ; l'orientation d'un mur sert à ranger le logement par côté et celle d'une fenêtre aux apports solaires.
- Pas encore testé en vrai par Noah avec ce parcours ; les vraies visites n'ont que des images à 1 par seconde (le suivi
  continu de la vidéo n'est éprouvé que sur la synthèse).

**Tests** : `tests/test_dialogue.py` (visite par côtés sans pièce, question par question), `tests/test_enveloppe.py`,
`tests/test_groupes.py`, `tests/test_carte.py` (« à gauche », « le deuxième mur », boussole bruitée, état par côté),
`tests/test_pont_liciel.py` et, à la racine, `tests/test_pont.py`.

**Retour de Noah le soir même : « quand on lance la vidéo, ça ne parle qu'au bout de 15 secondes »** (visite
`20261022-211918`). Deux causes, corrigées :
- la première question n'était posée qu'après la première phrase traitée. Elle part maintenant **dès que le téléphone est
  relié** (« Ce mur donne sur quoi ? »), posée par le serveur seul, sans attendre Claude (prêt en 9 s environ) ;
- la détection de fin de phrase (`assistant/vad.py`) partait d'un bruit de fond à −60 dB qu'elle n'apprenait que pendant
  les silences. Ce soir-là, le bruit (téléphone manipulé) était à −45 dB dès le lancement, au-dessus du seuil : tout
  passait pour de la parole, et la première phrase n'était coupée de force qu'au bout de 15 s. Le bruit de fond est
  maintenant suivi en continu (les 10 % de moments les plus calmes des 2 dernières secondes : la parole a des creux, pas un
  bruit continu). Sur le son de cette visite, « C'est là ? Que tu m'entends ? » est détecté seul, de 10,0 à 13,2 s, au
  lieu d'un bloc de 0 à 15 s.

**Retour de Noah le 23/10 : les murs un par un.** Après le premier mur, l'assistant demandait « Et côtés nord, est et
sud, le logement donne sur quoi ? », avec deux boutons : « Des voisins » ou « Non, c'est tout ». Chez lui, deux murs
donnaient sur le voisin et un sur la rue : il a répondu « non », ce qui a fermé la liste des murs, et l'assistant n'en a
plus parlé. Maintenant :
- **mur par mur** : « Et le mur sud, il donne sur quoi ? », puis l'est, puis l'ouest (nord, sud, est, ouest, dans cet
  ordre, seulement ceux dont rien n'est dit) ; chaque mur est fini (matériau, isolation, fenêtres) avant le suivant ;
- les boutons de ces questions sont ceux de « donne sur » (extérieur, voisin, parties communes, garage…), plus **« En
  partie voisin, en partie dehors »** : deux parties du même mur, la fenêtre sur la partie qui donne dehors. Il peut aussi
  le dire (« en partie sur le voisin, en partie sur la rue », « 60 % sur le voisin, le reste dehors ») ;
- ensuite, **« Un autre mur autour du logement, à me montrer ? »** (« Oui, un autre » / « Non, c'est tout ») : une maison
  peut avoir cinq murs ou plus. Il montre le mur à la caméra, la boussole donne son côté. La question revient après chaque
  mur de plus ; seul « Non, c'est tout » ferme la liste.

**« Autre… » (Noah, 23/10)** : chaque question à boutons (sauf « donne sur ») a un bouton **« Autre… »** qui ouvre une case
pour taper la valeur, à l'écran de la question comme dans la fiche. Une épaisseur, une longueur ou une année se tapent au
clavier numérique : le serveur la vérifie (épaisseur de 3 à 150 cm, longueur de 0,2 à 100 m, année de 1800 à 2030) et la
met en forme (« 23 » → « 23 cm ») ; une valeur impossible n'est pas notée et c'est dit à l'écran. Le reste (matériau,
isolation…) se tape en texte, ramené au vocabulaire comme une réponse dite. La valeur est notée « tapé sur le
téléphone », et la question suivante part aussitôt.

**Test de Noah du 23/10 au matin (visite `20261023-073730`) : ce qui n'allait pas, et ce qui est corrigé** :
- **les boutons de « Et le mur sud, il donne sur quoi ? » ne faisaient rien** : la question partait vers le téléphone
  avec une mauvaise étiquette (`secondaire:mur.donne_sur` au lieu de `cote:sud`), et la réponse cochée revenait sans
  être comprise. D'où : questions redemandées (« le mur est… » plusieurs fois), réponse lente après « en partie… » (c'est
  Claude qui finissait par répondre à la voix), et « refusé : citation introuvable » (Claude voulait noter le « voisin »
  coché). Corrigé ; une réponse cochée peut aussi être citée par Claude ;
- **le bouton « Voisin chauffé » de « Ce mur donne sur quoi ? » notait « local chauffé »** (une cloison entre deux
  pièces) : le mur sortait du DPE. La valeur exacte d'un bouton est maintenant gardée telle quelle ;
- **toutes les réponses sont vérifiées** (`tests/test_tous_les_boutons.py`) : une visite complète, avec et sans
  boussole, question par question ; à chaque question, l'étiquette envoyée au téléphone redonne la même question, et
  **chaque bouton** (et « Autre… » avec une valeur tapée) est noté et répond à la question. Pareil pour tous les boutons
  de la fiche (plus de 100) ;
- **la boussole** n'avait pas été enlevée, mais sur iPhone le nord ne se cale que quand le haut du téléphone est presque
  à plat ; tenu droit dès le début, il n'a donné aucun cap pendant 35 s, et le gyroscope n'était pas envoyé (rien pour
  retrouver le côté des murs filmés avant). Maintenant : le gyroscope part dès le début ; la boussole affiche « nord :
  téléphone à plat 1 s » et l'assistant le dit une fois ; les murs filmés avant prennent leur côté dès que le nord est
  connu ; l'orientation n'est demandée à l'oral qu'après une minute sans nord ;
- **« Autre… » n'ouvrait pas le clavier** sur iPhone (la case apparaissait après l'appui) : la case « Autre valeur » est
  maintenant affichée directement avec les boutons ; un appui dessus ouvre le clavier chiffres.

**Même jour, 8 h 01** : « dans l'épaisseur, j'ai appuyé sur Autre et rien ne se passe ; l'assistant ne parle plus ».
- **l'assistant se taisait** : répondant vite par boutons, Noah dépassait le plafond de 20 questions par minute, et la
  question suivante était retenue (« question_retenue » au journal). Le plafond ne vaut plus que pour ce que l'assistant
  dit de lui-même ; après une réponse (bouton ou voix), la question suivante part toujours ;
- **« Autre »** : le téléphone affichait encore l'ancienne page (un bouton « Autre… » au lieu de la case) : le serveur
  n'envoyait pas de consigne de cache, et Safari réutilisait la page sans la redemander. Maintenant la page est toujours
  revérifiée (« Cache-Control: no-cache », et le service worker ne passe plus par le cache du navigateur) ; et la page
  compare sa version à celle du serveur : si elle est ancienne, elle affiche « Nouvelle version de l'assistant :
  rechargez la page » avant de commencer.

**« Autre… », version finale (Noah, 23/10)** : seulement pour une mesure en centimètres (l'épaisseur d'un mur), plus
pour le reste. Il a l'air d'un bouton comme les autres ; un appui ouvre le clavier chiffres, la case s'agrandit avec
« cm » et « OK ». (Techniquement, c'est une case de saisie déguisée en bouton : sur iPhone, le clavier ne s'ouvre que si
l'on touche la case elle-même.)

Le prototype compte 321 tests (et le projet, à la racine, 654).

## Réglages (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `DIAGAUTO_CERVEAU` | `auto` | `claude`, `simulation`, ou `auto` (Claude Code s'il est trouvé, sinon simulation). |
| `DIAGAUTO_MODELE` | `claude-haiku-5-5` | Modèle Claude utilisé. |
| `DIAGAUTO_EFFORT` | `low` | Effort de Claude (`low` à `max`). |
| `DIAGAUTO_IMAGES` | `message` | `message` (le plus rapide) ou `fichiers` (Claude ouvre les images avec son outil de lecture). |
| `DIAGAUTO_CLAUDE` | trouvé automatiquement | Chemin de `claude.exe`. |
| `DIAGAUTO_CONVERSATION` | `claude` | `claude` : Claude lit et répond à chaque phrase (étape 7). `rapide` : le serveur pose seul la question du parcours, Claude n'intervient que pour une phrase non comprise (étape 5, plus rapide mais sans conversation). |
| `DIAGAUTO_TRANSCRIPTION` | `auto` | `rapide` (FastConformer, Whisper en second avis : voir « Étape 5 »), `whisper`, `fastconformer`, `simulation`, ou `auto` (`rapide` si les deux moteurs sont installés, sinon Whisper). |
| `DIAGAUTO_WHISPER_MODELE` | `auto` | `auto` = `large-v3-turbo` avec carte graphique, `small` sinon. |
| `DIAGAUTO_WHISPER_FAISCEAU` | `5` | Largeur de recherche de Whisper. `1` est un peu plus rapide (−0,2 s) mais se trompe davantage sur les mots courts. |
| `DIAGAUTO_FIN_SILENCE` | `0.7` | Silence (en secondes) qui termine une phrase. Trop court, l'assistant coupe la parole ; trop long, il paraît lent. |
| `DIAGAUTO_VEILLE_S` | `10` | Pendant un silence, l'assistant regarde les images toutes les N secondes et peut poser une question. |
| `DIAGAUTO_QUESTIONS_MINUTE` | `20` | Nombre maximal de questions par minute (garde-fou ; c'est le diagnostiqueur qui donne le rythme). |
| `DIAGAUTO_CODE` | aucun | Code d'accès demandé par la page. **Obligatoire si le serveur est joignable depuis Internet** (tunnel). |

## Limites connues de ce prototype

- **Testé une fois sur iPhone par Noah** (version précédente). Restent à tester : Android récent, Android ancien, et cette version corrigée.
- **L'extraction immédiate** ne connaît que le vocabulaire listé dans `assistant/extraction.py`. Depuis l'étape 7, ce n'est plus un frein : Claude lit chaque phrase et comprend le reste. En mode `rapide`, en revanche, la question du parcours part avant Claude.
- **Le parcours suit un ordre** (étape 13 : chaque mur et ses fenêtres, les côtés qui manquent, plafond, plancher, équipements). Le diagnostiqueur peut décrire dans l'ordre qu'il veut, tout est noté. Seules les questions suivent cet ordre ; leur contenu s'adapte à ce qui a été dit (étape 4).
- **Hypothèse à faire valider par un diagnostiqueur** : une paroi sur local chauffé n'est pas déperditive en 3CL, donc ses détails ne sont pas demandés.
- **Certificat fait maison** :
  - l'avertissement du navigateur est à accepter à chaque nouveau téléphone ;
  - l'installation de la page comme une application (PWA) ne marche pas avec ce certificat.
  - Pour l'installation, ou pour un test hors du Wi-Fi, il faudra un tunnel HTTPS (par exemple Cloudflare Tunnel), avec un code d'accès.
- La vidéo est gardée **dans la mémoire du téléphone** jusqu'à la fin. Cela convient pour des tests de quelques minutes ; en 1080p, environ 60 Mo par minute.
- La **détection de fin de phrase** se fait sur le volume du son, ce qui est simple. Silero VAD reste à évaluer, une fois sa licence vérifiée. Depuis l'étape 8, une prise de parole doit durer 0,35 s (0,6 s pendant que l'assistant parle) pour couper la voix.
- La **voix** est celle du navigateur ; Piper (voix fr_FR-siwis, sur le serveur) viendra ensuite.
- La **boussole** et le **gyroscope** du téléphone sont enregistrés (une mesure par seconde) : voir « Étape 6 ». La boussole n'a pas encore été essayée sur un vrai téléphone ; le cap de la caméra de l'iPhone tenu droit (étape 7) est à vérifier au test terrain.
- **Deux processus Claude Code par visite** : un pour les réponses, un pour la veille, pour que la veille ne retarde jamais une réponse.
- Différences avec le plan § 3.6 :
  - **Pas d'« outils » au sens de l'API** : Claude répond en JSON (question + actions), et le serveur applique les actions après vérification. Les actions sont `piece_courante`, `signaler_element`, `enregistrer_reponse`, `marquer_sans_objet`, `cloturer`, `copier`, depuis l'étape 4 `scinder`, `compter`, `regle` et `exception`, depuis l'étape 6 `orienter`, depuis l'étape 7 `pause`, `reprendre` et `annuler` (depuis l'étape 9, `annuler` un élément seulement à sa demande), et depuis l'étape 9 `doublon` (une question ; « oui » donne `fusionner`).
  - **`champs_manquants` n'existe plus** : la liste des manques est envoyée à chaque message, ce qui évite un aller-retour.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `assistant/checklist.py` | La checklist DPE et le calcul de ce qui manque ; groupes, parties séparées, règles du logement, contradictions. |
| `assistant/groupes.py` | Découpage d'une phrase en groupes, quantités et exceptions (« 9 … et 1 … », « dont une », « tous sauf un »). |
| `assistant/noms.py` | Noms parlants à l'oral : « ce mur », « le mur côté voisin », « le mur nord », jamais « le mur 3 ». |
| `assistant/plausibilite.py` | Contrôle des valeurs invraisemblables (un mur de 30 m de long) avant de les noter. |
| `assistant/repetition.py` | Mots de sa phrase repris dans une réponse : mesure, et reconnaissance d'une simple reprise (étape 9). |
| `assistant/decor.py` | Nouveau décor filmé : avance le coup d'œil de Claude sur la pièce (étape 8). |
| `assistant/boussole.py`, `boussole.toml` | Boussole et gyroscope du téléphone : orientation des murs et des fenêtres, fiabilité ; seuils réglables. |
| `assistant/citations.py`, `assistant/actions.py` | Vérification des citations ; application des actions proposées. |
| `assistant/lexique.py` | Lexique métier pour la transcription, corrections connues (« parpin » → parpaing). |
| `assistant/vad.py`, `assistant/transcription.py` | Fin de phrase ; transcription (FastConformer, Whisper en second avis). |
| `assistant/extraction.py` | Extraction immédiate, sans IA, de tout ce qui est dit (description libre, réponse courte, mot mal transcrit deviné, « je ne sais pas »). |
| `assistant/garde.py` | Garde-fous sur les questions : une seule, jamais « répétez », jamais un champ déjà rempli ou déjà demandé. |
| `assistant/cerveau.py` | Claude via Claude Code : consignes de conversation, messages, processus gardé ouvert, réponse lue phrase par phrase. |
| `assistant/parcours.py` | Le parcours de la visite : quelle question poser maintenant (mur par mur, plafond, plancher…). |
| `assistant/simulation.py` | Cerveau de simulation, sans Claude (règles et parcours seulement). |
| `assistant/evaluer.py` | Évaluations : pièce complète à 4 murs, réponses difficiles, 30 phrases libres en conversation. |
| `assistant/session.py` | Une visite : chaîne son → texte → pré-remplissage → Claude → voix (trois postes en file, sans blocage), pause, veille, journal, bilan. |
| `assistant/serveur.py`, `assistant/__main__.py` | Serveur web et lancement. |
| `assistant/rejouer.py` | Rejouer une vidéo de test. |
| `assistant/vision.py` | Images de la visite (vidéo ou images reçues) : suivi du mouvement, points ORB, mots visuels, liens vérifiés par la géométrie (étape 12). |
| `assistant/carte.py` | Carte des pièces après la visite : stations, pièces revisitées, ancrage, arbitrage par Claude, murs et cap, phrase → mur, état consolidé (étape 12). |
| `web/` | La page du téléphone ; `web/boussole.js` : cap de la caméra par la matrice de rotation ; `web/liaison.js` : liaison avec le serveur (battement de cœur, reconnexion, rattrapage). |

Tests (sans Claude ni réseau ; Claude Code y est remplacé par un faux programme) :

```
.venv\Scripts\python -m pytest prototype-assistant\tests
```
