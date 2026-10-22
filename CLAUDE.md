# Projet DiagAuto — remplir LICIEL automatiquement après la visite

## Contexte métier
- Porteur : Noah (N.Z Consulting / Imodiag, plateforme de diagnostics immobiliers en France). Il parle français, non technique : toute communication finale en français simple.
- Problème : après le rendez-vous, les diagnostiqueurs perdent des heures à ressaisir dans LICIEL DIAGNOSTICS V4 (logiciel de référence du métier) tout ce qu'ils ont noté sur place : croquis/plan du logement, mesures pièce par pièce (lasers), murs/isolation/menuiseries, chauffage/ECS/ventilation (DPE), observations électricité (NF C16-600) et gaz (NF P45-500), repérage amiante (zones homogènes, prélèvements), plomb (CREP, mesures fluo X), termites, Carrez/Boutin, ERP, audit énergétique.
- Objectif : produire AUTOMATIQUEMENT le dossier LICIEL rempli, sans que le diagnostiqueur ne ressaisisse rien. Le diagnostiqueur garde la responsabilité : il valide les données proposées, puis relit dans LICIEL avant d'éditer le rapport.

## Objectif produit (décision de Noah, corrigée le 22/10/2026) — détail dans docs/02-capture-video.md
1. **Données administratives sans saisie** : reprises du devis / dossier client (adresse, propriétaire, maison/appartement, année, surface déclarée) et enrichies automatiquement depuis l'adresse (API RNB, altitude IGN, BDNB, ancien DPE ADEME). Sur place, le diagnostiqueur ne fait que confirmer.
2. **Capture terrain par UNE vidéo continue de tout le logement, sur N'IMPORTE QUEL téléphone**, même ancien (Android ou iPhone, sans LiDAR).
   - **C'est nous qui construisons le système : pas de dépendance à Apple RoomPlan ni au LiDAR.**
   - Application web (PWA) : vidéo + voix + capteurs (boussole/orientation, gyroscope).
   - Le diagnostiqueur se déplace librement, sort d'une pièce et **y revient** : le système reconnaît la même pièce et fusionne, **jamais deux pièces pour le même espace**.
   - Rapide, sans procédure lourde : on entre, on balaie, « tel mur c'est ça », on repasse si oubli. **Pas de mesure dictée obligatoire.**
   - Ne jamais passer par WhatsApp : la vidéo est recompressée et les capteurs sont perdus.
3. **Tout le calcul côté serveur, open source de préférence** :
   - carte 3D unique par SLAM / reconstruction avec reconnaissance de lieu et fermeture de boucle (COLMAP/GLOMAP, DROID-SLAM ; ORB-SLAM3 et MASt3R-SLAM seulement comme références, à cause de leurs licences) ;
   - découpage en pièces **sur la carte**, pas dans le temps ;
   - échelle sans mesure obligatoire : profondeur métrique, objets de taille connue, capteurs ; laser si fourni ;
   - murs, fenêtres et portes, surfaces, orientation, longueurs de ponts thermiques ;
   - **chaque phrase dite est rattachée à l'élément visé à cet instant** (transcription horodatée ↔ position de la caméra ↔ mur au centre de l'image ; gérer « ce mur », « le deuxième mur », « celui-là ») ;
   - IA vision pour les équipements et la lecture des plaques signalétiques.
4. **Assistant vocal en direct pendant le tournage** (docs/02-capture-video.md § 3.6).
   - L'IA voit le flux (1 image/s) et parle au diagnostiqueur, dans une oreillette.
   - Elle pose les questions manquantes et signale les oublis ; elle n'affirme jamais une donnée invisible.
   - Chaque réponse est enregistrée par un outil, avec la citation du diagnostiqueur et l'horodatage.
   - L'état « checklist DPE » est tenu par NOTRE serveur, qui calcule ce qui manque.
   - **Cerveau : Claude (API Anthropic) — décision de Noah, pas de Gemini ni d'OpenAI.** L'API Claude n'a pas de voix ni de vidéo temps réel, d'où une chaîne sur notre serveur :
     - fin de phrase (VAD) ;
     - transcription faster-whisper avec lexique métier ;
     - images de l'instant ;
     - Claude Haiku 5.5 en streaming, avec outils et checklist en cache ;
     - synthèse vocale française open source (Piper fr_FR-siwis ou équivalent) ;
     - oreillette.
   - Latence visée : 2 à 4 s. Un modèle plus fort (Sonnet 5.5, ou Opus 5.5) fait l'analyse finale après le tournage.
   - **Pas de clé API (correction de Noah, 22/10/2026)** : le prototype appelle le Claude Code connecté sur le PC (abonnement Claude Max) en mode headless ; ne jamais lire ANTHROPIC_API_KEY. L'abonnement est prévu pour un usage personnel/développement : l'accès pour un usage commercial à grande échelle sera à revoir plus tard (non décidé).
   - Hors réseau : enregistrement local, puis questions a posteriori.
   - Le rattachement définitif des réponses aux murs et tout le calcul 3D restent faits ensuite sur le serveur.
5. **Précision visée ~3–5 %** : suffisante pour le DPE. **Pour le Carrez/Boutin, la mesure laser fait foi** (télémètre filmé ou dicté) ; la vidéo sert de contrôle et de plan.
6. **Écran de validation** par le diagnostiqueur : chaque valeur proposée montre sa preuve ; une donnée invisible non dite reste vide, l'IA ne la devine jamais.
7. **Sortie vers LICIEL** par génération des tables XML du dossier (paquet `diagauto.liciel_xml`) : pièces + Carrez d'abord, DPE ensuite.

## Documents du projet
- docs/01-cadrage.md : stockage LICIEL, options d'injection, plan de MVP, questions ouvertes.
- docs/02-capture-video.md : parcours terrain, automatique / à confirmer / à dicter, briques techniques, coût serveur, plan de prototype en 3 étapes.
- docs/checklist-dpe.md : données à relever pour un DPE 3CL-2021.
- docs/protocole-tournage.md : fiche d'une page pour tourner les vidéos de test (V1).
- docs/exigences-en-attente.md : nouvelles demandes de Noah transmises par Hermes, à intégrer puis vider (garder l'en-tête).
- samples/ (non versionné) : vidéos de test, ex. samples/video-001 (séjour, 38 s, recompressée par WhatsApp).
- prototype-assistant/ : prototype V1bis de l'assistant vocal en direct (page web + serveur FastAPI + Claude Code) ; mesures et limites dans son README.

## Environnement
- Windows 11, LICIEL installé en local : C:\LICIEL_Programmes\LICIEL Diagnostics (version d'essai : la démo n'enregistre pas les modules Carrez/DPE/Élec). Données : C:\LICIEL_Diagnostics (base LICIEL_Dossiers.mdb + Dossiers_AAAA\<n°>\XML\Table_*.xml).
- Recherches d'Hermes (l'agent qui orchestre) : C:\Users\conta\Documents\liciel\ (guide-0 à guide-3, etude-technique-import.md, dossier-test\).
- Python : environnement local `.venv` (pytest). Ce PC n'a pas de GPU NVIDIA : la reconstruction 3D tourne sur CPU (lent) ou sur un GPU loué à la demande.
- Licences : n'utiliser que des briques compatibles avec un usage commercial (MIT, BSD, Apache-2.0…) ; vérifier chaque modèle (beaucoup de modèles 3D récents sont non commerciaux).

## Règles de travail
- **Aucune écriture sous C:\LICIEL_*** (ni installation ni données) : lecture seule. Les tests d'écriture dans LICIEL sont faits par Hermes sur un dossier jetable.
- Pas de contournement de licence, pas de décompilation, pas de lecture des référentiels chiffrés (DATA_XML_SAV), pas de modification de LICIEL. Seules voies acceptables : imports/exports officiels, génération de fichiers dossier au format que LICIEL lit (interopérabilité de nos propres dossiers), automatisation de l'interface utilisateur.
- Exactitude réglementaire (DPE 3CL-2021, loi Carrez/Boutin, normes NF) : ne rien inventer ; les correspondances incertaines sont marquées « hypothèse ».
- Avancer par petites étapes prouvées de bout en bout (voir plan de MVP dans docs/01-cadrage.md § 3).
- Code dans ce dossier, git sur la branche `main`, commits petits avec messages clairs en français (Hermes relit), README en français.
