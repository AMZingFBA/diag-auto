# Projet DiagAuto — remplir LICIEL automatiquement après la visite

## Contexte métier
- Porteur : Noah (N.Z Consulting / Imodiag, plateforme de diagnostics immobiliers en France). Il parle français, non technique : toute communication finale en français simple.
- Problème : après le rendez-vous, les diagnostiqueurs perdent des heures à ressaisir dans LICIEL DIAGNOSTICS V4 (logiciel de référence du métier) tout ce qu'ils ont noté sur place : croquis/plan du logement, mesures pièce par pièce (lasers), murs/isolation/menuiseries, chauffage/ECS/ventilation (DPE), observations électricité (NF C16-600) et gaz (NF P45-500), repérage amiante (zones homogènes, prélèvements), plomb (CREP, mesures fluo X), termites, Carrez/Boutin, ERP, audit énergétique.
- Objectif : produire AUTOMATIQUEMENT le dossier LICIEL rempli, sans que le diagnostiqueur ne ressaisisse rien. Le diagnostiqueur garde la responsabilité : il valide les données proposées, puis relit dans LICIEL avant d'éditer le rapport.

## Objectif produit (décision de Noah, corrigée le 22/10/2026) — détail dans docs/02-capture-video.md
1. **Données administratives sans saisie** : reprises du devis / dossier client (adresse, propriétaire, maison/appartement, année, surface déclarée) et enrichies automatiquement depuis l'adresse (API RNB, altitude IGN, BDNB, ancien DPE ADEME). Sur place, le diagnostiqueur ne fait que confirmer.
2. **Capture terrain par vidéo sur N'IMPORTE QUEL téléphone**, même ancien (Android ou iPhone, sans LiDAR).
   - **C'est nous qui construisons le système : pas de dépendance à Apple RoomPlan ni au LiDAR.**
   - Une application web (PWA) filme chaque pièce et enregistre la voix et les capteurs (boussole/orientation, gyroscope).
3. **Tout le calcul côté serveur, open source de préférence** :
   - reconstruction 3D depuis la vidéo (COLMAP/GLOMAP, profondeur monoculaire) ;
   - mise à l'échelle par une référence (mesure laser dictée, mire A4, hauteur de porte) ;
   - murs, fenêtres et portes, surfaces, orientation, longueurs de ponts thermiques ;
   - IA vision pour les équipements et la lecture des plaques signalétiques ;
   - transcription de la voix vers les champs invisibles (matériaux, isolation, vitrage, mitoyennetés).
4. **Précision visée ~3–5 %** : suffisante pour le DPE. **Pour le Carrez/Boutin, la mesure laser dictée fait foi** ; la vidéo sert de contrôle et de plan.
5. **Écran de validation** par le diagnostiqueur : chaque valeur proposée montre sa preuve ; une donnée invisible non dite reste vide, l'IA ne la devine jamais.
6. **Sortie vers LICIEL** par génération des tables XML du dossier (paquet `diagauto.liciel_xml`) : pièces + Carrez d'abord, DPE ensuite.

## Documents du projet
- docs/01-cadrage.md : stockage LICIEL, options d'injection, plan de MVP, questions ouvertes.
- docs/02-capture-video.md : parcours terrain, automatique / à confirmer / à dicter, briques techniques, coût serveur, plan de prototype en 3 étapes.
- docs/checklist-dpe.md : données à relever pour un DPE 3CL-2021.

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
