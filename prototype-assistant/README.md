# Prototype V1bis — assistant vocal en direct pendant le tournage

Le diagnostiqueur filme le logement avec son téléphone et parle normalement. Un assistant lui pose dans l'oreillette les questions qui manquent pour le DPE (« Le mur avec la commode, il est isolé ? ») et note ses réponses.

Ce prototype correspond à l'étape **V1bis** du plan ([docs/02-capture-video.md](../docs/02-capture-video.md), § 3.6 et § 6).

## Comment ça marche

1. Le **téléphone** (une page web, sans application à installer) :
   - filme et garde la vidéo complète en mémoire ;
   - envoie au serveur le son et **une image par seconde**.
2. Le **serveur** (ce PC) :
   - repère la fin de chaque phrase, et attend la suite si elle est coupée (« Il est… ») ;
   - la transcrit sur place : **la voix ne quitte pas le PC** ;
   - **note tout de suite**, sans IA, tout ce qu'il reconnaît dans la phrase (quelques millisecondes) ;
   - **pose aussitôt la question suivante du parcours**, sans attendre l'IA (voir « Parcours de la visite » plus bas).
3. **Claude** n'intervient qu'en appui :
   - quand les règles n'ont rien compris à une phrase, il essaie de la comprendre (images comprises) ;
   - il relit en arrière-plan les phrases longues, au cas où les règles auraient manqué une valeur ;
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
2. Un avertissement de sécurité s'affiche, parce que le certificat est fait maison. Touchez « Paramètres avancés », puis « Continuer vers le site ». C'est normal pour ce prototype : le HTTPS est obligatoire pour que le téléphone autorise la caméra et le micro.
3. Branchez une **oreillette**, de préférence. Sans oreillette, la voix de l'assistant passe par le haut-parleur et peut être captée par le micro.
4. Touchez **Démarrer la visite** et autorisez la caméra et le micro.
5. Filmez en parlant normalement, en décrivant librement :
   - « ici c'est la cuisine » ;
   - « ce mur fait 4 m 50 de long, brique 30 cm, isolé par l'intérieur, il donne dehors » ;
   - « il y a trois fenêtres en bois double vitrage, deux radiateurs à eau » ;
   - en réponse à une question, un seul mot suffit : « extérieur », « basse », « roulants » ;
   - « je ne sais pas » ;
   - « pas de radiateur ici ».
6. Les boutons :
   - **Assistant actif / muet** : en mode muet, les questions s'affichent sans être lues.
   - **Terminer** :
     - au 1er appui, l'assistant dit ce qui manque encore ;
     - au 2e appui (« Arrêter vraiment »), la visite s'arrête.
7. À la fin :
   - **Envoyer la vidéo au serveur** : le fichier original, sans recompression ; **jamais par WhatsApp**.
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

Tout fonctionne comme avec Claude : les valeurs sont notées par l'extraction immédiate, et les questions viennent du parcours du serveur. Seule différence : une phrase que les règles n'ont pas comprise reste sans suite, et les images ne sont pas regardées.

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
| **Whisper small** (OpenAI), avec le contexte et le garde-fou : **retenu par défaut** | 2,3 s | bon en général ; quelques erreurs (« Blois » pour « Bois », « Ocean » pour « eau chaude ») | MIT |
| Whisper small français (`bofenghuang/whisper-small-cv11-french`) | 2,4 s | meilleur sur certaines phrases (« Derrière le rideau », « eau chaude ») mais invente davantage sur du silence (« Réalisé par l'Institut… », « Brique, parpaing, basse température. ») ; nombres en lettres | Apache-2.0 (version CTranslate2 publiée par un tiers : à vérifier) |
| **FastConformer français** (NVIDIA, version ONNX) : **en option** | **0,05 s** | souvent juste (« Je ne t'entends plus », « Derrière le rideau », « Bois ») ; parfois abîmé (« de la' prriix » pour brique, « Euxux chaudes ») ; sur du silence, du charabia mais jamais de valeur métier | CC-BY-4.0 (mention de NVIDIA obligatoire ; version ONNX publiée par OpenVoiceOS : à vérifier avant usage commercial) |

Aucun Whisper plus gros ne tient la vitesse sur ce processeur : turbo, medium et les versions françaises « distil » gardent un gros encodeur et prennent 7 à 10 s.

**À essayer avec Noah** : le FastConformer ramènerait la question à **moins de 1 s après la fin de la phrase** (au lieu d'environ 3 s). Ses mots abîmés sont en partie rattrapés par la comparaison phonétique et par Claude. Pour l'essayer :

```
set DIAGAUTO_TRANSCRIPTION=fastconformer
..\.venv\Scripts\python -m assistant
```

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

## Réglages (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `DIAGAUTO_CERVEAU` | `auto` | `claude`, `simulation`, ou `auto` (Claude Code s'il est trouvé, sinon simulation). |
| `DIAGAUTO_MODELE` | `claude-haiku-5-5` | Modèle Claude utilisé. |
| `DIAGAUTO_EFFORT` | `low` | Effort de Claude (`low` à `max`). |
| `DIAGAUTO_IMAGES` | `message` | `message` (le plus rapide) ou `fichiers` (Claude ouvre les images avec son outil de lecture). |
| `DIAGAUTO_CLAUDE` | trouvé automatiquement | Chemin de `claude.exe`. |
| `DIAGAUTO_TRANSCRIPTION` | `auto` | `whisper`, `fastconformer` (option rapide à l'essai, voir « Étape 3 »), `simulation`, ou `auto` (Whisper s'il est installé). |
| `DIAGAUTO_WHISPER_MODELE` | `auto` | `auto` = `large-v3-turbo` avec carte graphique, `small` sinon. |
| `DIAGAUTO_WHISPER_FAISCEAU` | `5` | Largeur de recherche de Whisper. `1` est un peu plus rapide (−0,2 s) mais se trompe davantage sur les mots courts. |
| `DIAGAUTO_FIN_SILENCE` | `0.7` | Silence (en secondes) qui termine une phrase. Trop court, l'assistant coupe la parole ; trop long, il paraît lent. |
| `DIAGAUTO_VEILLE_S` | `10` | Pendant un silence, l'assistant regarde les images toutes les N secondes et peut poser une question. |
| `DIAGAUTO_QUESTIONS_MINUTE` | `20` | Nombre maximal de questions par minute (garde-fou ; c'est le diagnostiqueur qui donne le rythme). |
| `DIAGAUTO_CODE` | aucun | Code d'accès demandé par la page. **Obligatoire si le serveur est joignable depuis Internet** (tunnel). |

## Limites connues de ce prototype

- **Testé une fois sur iPhone par Noah** (version précédente). Restent à tester : Android récent, Android ancien, et cette version corrigée.
- **L'extraction immédiate** ne connaît que le vocabulaire listé dans `assistant/extraction.py`.
  - Le reste est compris par Claude, en relecture de la phrase.
  - Mais la question du parcours part avant cette relecture : un mot inconnu des règles peut donc entraîner une question sur ce qui vient d'être dit. Le vocabulaire est à enrichir au fil des tests.
- **Le parcours suit un ordre** (murs, plafond, plancher, fenêtres, radiateurs). Le diagnostiqueur peut décrire dans l'ordre qu'il veut, tout est noté. Seules les questions suivent cet ordre ; leur contenu s'adapte à ce qui a été dit (étape 4).
- **Hypothèse à faire valider par un diagnostiqueur** : une paroi sur local chauffé n'est pas déperditive en 3CL, donc ses détails ne sont pas demandés.
- **Certificat fait maison** :
  - l'avertissement du navigateur est à accepter à chaque nouveau téléphone ;
  - l'installation de la page comme une application (PWA) ne marche pas avec ce certificat.
  - Pour l'installation, ou pour un test hors du Wi-Fi, il faudra un tunnel HTTPS (par exemple Cloudflare Tunnel), avec un code d'accès.
- La vidéo est gardée **dans la mémoire du téléphone** jusqu'à la fin. Cela convient pour des tests de quelques minutes ; en 1080p, environ 60 Mo par minute.
- La **détection de fin de phrase** se fait sur le volume du son, ce qui est simple. Silero VAD reste à évaluer, une fois sa licence vérifiée.
- La **voix** est celle du navigateur ; Piper (voix fr_FR-siwis, sur le serveur) viendra ensuite.
- Les **capteurs** (boussole, gyroscope) ne sont pas encore enregistrés.
- **Deux processus Claude Code par visite** : un pour les réponses, un pour la veille, pour que la veille ne retarde jamais une réponse.
- Différences avec le plan § 3.6 :
  - **Pas d'« outils » au sens de l'API** : Claude répond en JSON (question + actions), et le serveur applique les actions après vérification. Les actions sont `piece_courante`, `signaler_element`, `enregistrer_reponse`, `marquer_sans_objet`, `cloturer`, `copier`, et depuis l'étape 4 `scinder`, `compter`, `regle` et `exception`.
  - **`champs_manquants` n'existe plus** : la liste des manques est envoyée à chaque message, ce qui évite un aller-retour.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `assistant/checklist.py` | La checklist DPE et le calcul de ce qui manque ; groupes, parties séparées, règles du logement, contradictions. |
| `assistant/groupes.py` | Découpage d'une phrase en groupes, quantités et exceptions (« 9 … et 1 … », « dont une », « tous sauf un »). |
| `assistant/citations.py`, `assistant/actions.py` | Vérification des citations ; application des actions proposées. |
| `assistant/lexique.py` | Lexique métier pour la transcription, corrections connues (« parpin » → parpaing). |
| `assistant/vad.py`, `assistant/transcription.py` | Fin de phrase ; transcription faster-whisper. |
| `assistant/extraction.py` | Extraction immédiate, sans IA, de tout ce qui est dit (description libre, réponse courte, mot mal transcrit deviné, « je ne sais pas »). |
| `assistant/garde.py` | Garde-fous sur les questions : une seule, jamais « répétez », jamais un champ déjà rempli ou déjà demandé. |
| `assistant/cerveau.py` | Claude via Claude Code : consignes, messages, processus gardé ouvert. |
| `assistant/parcours.py` | Le parcours de la visite : quelle question poser maintenant (mur par mur, plafond, plancher…). |
| `assistant/simulation.py` | Cerveau de simulation, sans Claude (règles et parcours seulement). |
| `assistant/evaluer.py` | Évaluation sur une pièce complète à 4 murs, avec la latence de chaque étape. |
| `assistant/session.py` | Une visite : chaîne son → texte → Claude → voix, veille, journal, bilan. |
| `assistant/serveur.py`, `assistant/__main__.py` | Serveur web et lancement. |
| `assistant/rejouer.py` | Rejouer une vidéo de test. |
| `web/` | La page du téléphone. |

Tests (sans Claude ni réseau ; Claude Code y est remplacé par un faux programme) :

```
.venv\Scripts\python -m pytest prototype-assistant\tests
```
