# Prototype V1bis — assistant vocal en direct pendant le tournage

Le diagnostiqueur filme le logement avec son téléphone et parle normalement. Un assistant lui pose dans l'oreillette les questions qui manquent pour le DPE (« Le mur avec la commode, il est isolé ? ») et note ses réponses.

Ce prototype correspond à l'étape **V1bis** du plan ([docs/02-capture-video.md](../docs/02-capture-video.md), § 3.6 et § 6).

## Comment ça marche

1. Le **téléphone** (une page web, sans application à installer) :
   - filme et garde la vidéo complète en mémoire ;
   - envoie au serveur le son et **une image par seconde**.
2. Le **serveur** (ce PC) :
   - repère la fin de chaque phrase ;
   - la transcrit sur place : **la voix ne quitte pas le PC** ;
   - envoie à **Claude** la phrase, 1 à 3 images réduites et l'état de la checklist DPE.
3. **Claude** répond par la question suivante, s'il y en a une, et par les valeurs à noter.
4. **Le serveur vérifie chaque valeur** : elle n'est notée que si sa citation se retrouve dans ce que le diagnostiqueur a réellement dit. Sinon, elle est refusée.
5. Le **téléphone** lit la question à voix haute (voix du navigateur) :
   - il se tait dès que le diagnostiqueur reparle ;
   - il fait un **bip** quand une valeur est notée sans question à poser.

C'est **notre serveur** qui tient la checklist et calcule ce qui manque, pas l'IA. L'IA ne fait que poser des questions et proposer ce qu'elle a entendu. Une donnée qui n'a pas été dite reste vide.

Périmètre de la checklist dans ce prototype (tiré de [docs/checklist-dpe.md](../docs/checklist-dpe.md)) :
- **par pièce** : murs (matériau, épaisseur, isolation, donne sur), fenêtres (menuiserie, vitrage, volets), émetteurs de chauffage (type, température, année) ;
- **pour le logement** : chauffage, eau chaude, ventilation.

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
5. Filmez en parlant normalement :
   - « ici c'est la cuisine » ;
   - « ce mur-là, brique, 30 cm, il donne dehors » ;
   - « la fenêtre, PVC double vitrage, volets roulants » ;
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

Un « cerveau » simple, à base de règles, reconnaît quelques mots du métier (brique, PVC, double vitrage, radiateur…) et pose la question suivante de la checklist. Il ne voit pas les images.

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

**Comportement observé** sur la vidéo de test :
- **ce qui marche** :
  - les valeurs dites sont notées avec leur citation : M1 brique 30 cm, M2 parpaing 40 cm ;
  - les questions désignent ce qui est filmé (« Le mur avec la commode, il est isolé ? ») ;
  - quand c'est ambigu (deux « celui-ci » dans la même phrase), l'assistant demande au lieu de deviner.
- **l'erreur corrigée** :
  - une phrase mal transcrite avait d'abord produit une isolation inventée ;
  - la consigne demande maintenant de faire répéter une phrase douteuse : c'est ce que fait l'assistant depuis.
- **à régler avec Noah** : sur une parole décousue, l'assistant demande souvent des précisions.

## Réglages (variables d'environnement)

| Variable | Défaut | Rôle |
|---|---|---|
| `DIAGAUTO_CERVEAU` | `auto` | `claude`, `simulation`, ou `auto` (Claude Code s'il est trouvé, sinon simulation). |
| `DIAGAUTO_MODELE` | `claude-haiku-5-5` | Modèle Claude utilisé. |
| `DIAGAUTO_EFFORT` | `low` | Effort de Claude (`low` à `max`). |
| `DIAGAUTO_IMAGES` | `message` | `message` (le plus rapide) ou `fichiers` (Claude ouvre les images avec son outil de lecture). |
| `DIAGAUTO_CLAUDE` | trouvé automatiquement | Chemin de `claude.exe`. |
| `DIAGAUTO_TRANSCRIPTION` | `auto` | `whisper`, `simulation`, ou `auto`. |
| `DIAGAUTO_WHISPER_MODELE` | `auto` | `auto` = `large-v3-turbo` avec carte graphique, `small` sinon. |
| `DIAGAUTO_FIN_SILENCE` | `0.7` | Silence (en secondes) qui termine une phrase. Trop court, l'assistant coupe la parole ; trop long, il paraît lent. |
| `DIAGAUTO_VEILLE_S` | `10` | Pendant un silence, l'assistant regarde les images toutes les N secondes et peut poser une question. |
| `DIAGAUTO_QUESTIONS_MINUTE` | `6` | Nombre maximal de questions par minute. |
| `DIAGAUTO_CODE` | aucun | Code d'accès demandé par la page. **Obligatoire si le serveur est joignable depuis Internet** (tunnel). |

## Limites connues de ce prototype

- **Pas encore testé sur un vrai téléphone** (Android récent, Android ancien, iPhone) : c'est le prochain test, avec Noah.
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
  - **Pas d'« outils » au sens de l'API** : Claude répond en JSON (question + actions), et le serveur applique les actions après vérification. Les actions sont `piece_courante`, `signaler_element`, `enregistrer_reponse` et `marquer_sans_objet`.
  - **`champs_manquants` n'existe plus** : la liste des manques est envoyée à chaque message, ce qui évite un aller-retour.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `assistant/checklist.py` | La checklist DPE et le calcul de ce qui manque. |
| `assistant/citations.py`, `assistant/actions.py` | Vérification des citations ; application des actions proposées. |
| `assistant/lexique.py` | Lexique métier pour la transcription, corrections connues (« parpin » → parpaing). |
| `assistant/vad.py`, `assistant/transcription.py` | Fin de phrase ; transcription faster-whisper. |
| `assistant/cerveau.py` | Claude via Claude Code : consignes, messages, processus gardé ouvert. |
| `assistant/simulation.py` | Cerveau de simulation, sans Claude. |
| `assistant/session.py` | Une visite : chaîne son → texte → Claude → voix, veille, journal, bilan. |
| `assistant/serveur.py`, `assistant/__main__.py` | Serveur web et lancement. |
| `assistant/rejouer.py` | Rejouer une vidéo de test. |
| `web/` | La page du téléphone. |

Tests (sans Claude ni réseau ; Claude Code y est remplacé par un faux programme) :

```
.venv\Scripts\python -m pytest prototype-assistant\tests
```
