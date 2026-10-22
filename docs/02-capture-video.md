# DiagAuto — 02. Capture terrain par vidéo (tout téléphone, calcul serveur)

*Version du 22/10/2026, qui remplace la version « iPhone LiDAR / RoomPlan » suite à la correction de Noah. Complète [01-cadrage.md](01-cadrage.md) ; liste des données : [checklist-dpe.md](checklist-dpe.md).*

## Le principe

1. **N'importe quel téléphone**, même ancien (Android ou iPhone, sans LiDAR). Une **application web** (PWA, rien à installer depuis un store) filme chaque pièce et enregistre la voix et les capteurs (boussole, gyroscope).
2. **Tout le calcul se fait sur notre serveur**, avec des briques open source de préférence :
   - reconstruction 3D à partir de la vidéo, mise à l'échelle par une mesure de référence ;
   - murs, fenêtres et portes, surfaces, hauteurs, orientation, longueurs de ponts thermiques ;
   - reconnaissance des équipements et lecture des plaques signalétiques ;
   - transcription de la voix vers les champs invisibles (matériaux, isolation, vitrage, mitoyennetés).
3. **Données administratives** : reprises du devis et complétées par les API publiques (RNB, IGN, BDNB, DPE ADEME).
4. **Écran de validation** : le diagnostiqueur confirme ou corrige. Chaque valeur montre sa preuve, et une donnée invisible non dite reste vide.
5. **Précision visée : environ 3 à 5 %.** C'est suffisant pour le DPE. **Pour le Carrez, la mesure laser reste la mesure** ; la vidéo sert de contrôle de cohérence et de plan.
6. Sortie vers LICIEL par la chaîne `diagauto.liciel_xml` (01-cadrage.md) : pièces + Carrez d'abord, DPE ensuite.

## 1. Parcours utilisateur

| Moment | Le diagnostiqueur | Le système |
|---|---|---|
| **Devis** | Rien. | Reprend les données du devis et interroge les API publiques à partir de l'adresse. Prépare une fiche « à confirmer ». |
| **Arrivée** (2 min) | Ouvre le lien du dossier sur son téléphone. Confirme l'adresse et le bâtiment sur la carte, le type de bien et l'année. Fait cocher le consentement. | Affiche chaque valeur avec sa source (« BDNB : 1974 »). |
| **Extérieur** (2–3 min) | Filme les façades en faisant le tour, dicte les mitoyennetés et ce qu'il voit des murs. | Enregistre la boussole pour l'orientation des façades. |
| **Chaque pièce** (environ 1 min) | 1. Pose la **mire** (feuille A4 imprimée) au sol. 2. Mesure au laser et **dicte** la longueur et la largeur de la pièce. 3. Filme un tour lent de la pièce (murs, angles, sol et plafond) en commentant : « mur nord sur l'extérieur, parpaing, isolé par l'intérieur, dix centimètres ». 4. Filme de près les plaques d'équipements. | Envoie la vidéo pendant qu'on passe à la pièce suivante, si le réseau le permet. Le serveur traite la pièce en 5 à 15 min ; les résultats arrivent au fil de la visite. |
| **Équipements, combles, sous-sol** (5 min) | Chaudière, ballon, VMC, compteur : vidéo ou photo + plaque. Épaisseur d'isolant dictée. | Lecture des plaques, classement des équipements. |
| **Fin de visite ou au bureau** (5–10 min) | Écran de validation : traite les valeurs **rouges** (manquantes) et **orange** (proposées), puis signe. | Bloque l'envoi tant qu'une donnée obligatoire manque, et garde la trace des validations. S'il n'y a pas de réseau sur place, la validation se fait au bureau. |
| **Au bureau** | Ouvre LICIEL, relit, édite le rapport. | Génère les tables LICIEL (pièces, Carrez, puis DPE). |

## 2. Donnée par donnée

Légende :
- **A** = automatique, calculé et affiché pour contrôle ;
- **C** = proposé à confirmer (API, devis ou reconnaissance d'image) ;
- **D** = à dicter, ou mesure laser dictée ;
- **P** = photo ou justificatif.

**Une valeur D non dite reste vide : l'IA ne la devine jamais.**

| Donnée (checklist DPE) | Statut | Source |
|---|---|---|
| **Administratif** | | |
| Adresse, département | C | Devis + géocodage BAN |
| Identifiant RNB | C | API RNB (choix sur carte si plusieurs bâtiments) |
| Altitude | A | Altimétrie IGN |
| Propriétaire / donneur d'ordre, SIREN | C | Devis (+ annuaire des entreprises) |
| Consentement | C | Case cochée sur place |
| Maison / appartement / immeuble | C | Devis + BDNB |
| Année de construction | C + P | Devis, BDNB, ancien DPE (estimation, justificatif si disponible) |
| Ancien DPE | C | Données ouvertes DPE de l'ADEME (vérifier que c'est le même logement) |
| **Dimensions** | | |
| Surface par pièce (DPE) | A → C | Reconstruction vidéo, mise à l'échelle par la mesure laser dictée |
| **Surface Carrez / Boutin** | **D** + contrôle A | **Mesures laser dictées** (la mesure qui fait foi) ; la vidéo vérifie la forme et la cohérence. Les zones < 1,80 m et les annexes sont désignées par le diagnostiqueur. |
| Hauteur sous plafond | A → C | Plans du sol et du plafond reconstruits ; rampants à confirmer |
| Étage, mitoyennetés (dessus, dessous, côtés chauffés ?) | D | Voix |
| Nb de logements, surface du bâtiment | C | BDNB |
| Inertie | C | Déduite des matériaux dictés |
| **Murs** | | |
| Surface (nette des ouvertures) | A → C | Reconstruction |
| Orientation | A → C | Boussole + reconstruction, recoupées avec l'emprise du bâtiment (secteur N/S/E/O suffisant) |
| Donne sur extérieur / local non chauffé / local chauffé | C + D | Proposition (murs de façade) + voix pour le type de local non chauffé |
| Matériau, isolation (type, épaisseur ou R, année) | D + P | Voix, photo, justificatif |
| Épaisseur | C | Profondeur d'embrasure mesurée sur la reconstruction |
| **Plafonds et planchers bas** | | |
| Surfaces | A | Reconstruction |
| Périmètre du plancher sur l'extérieur | A → C | Géométrie |
| Donne sur, structure, isolation | D + P | Voix, photo des combles ou du sous-sol |
| **Fenêtres, portes-fenêtres, portes** | | |
| Nombre, dimensions, mur concerné, orientation | A → C | Détection sur les images + reconstruction |
| Menuiserie, type de porte, volets, double fenêtre | C | Reconnaissance d'image |
| Vitrage, lame d'air, gaz, dormant, retour d'isolant | C / D | Image si lisible, sinon voix |
| Position dans le mur | C | Profondeur d'embrasure |
| Masques, vérandas, loggias | C + D | Vidéo extérieure + voix |
| **Ponts thermiques** | | |
| Longueurs mur/plancher, mur/plafond, mur/refend, menuiserie/mur | A → C | Calcul géométrique ; le type de liaison dépend de l'isolation dictée |
| **Chauffage, eau chaude, climatisation** | | |
| Générateur : type, énergie, marque, modèle, année, puissance | C + P | Plaque lue par l'IA (année jamais déduite d'un n° de série sans confirmation) |
| Individuel / collectif | C | Devis + voix |
| Émetteurs, robinets thermostatiques, thermostat, splits | C | Reconnaissance d'image |
| Température (basse/haute), programmation, réseau isolé, appoint, surface chauffée par système | D / C | Voix |
| Ballon : volume, énergie, année | C + P | Plaque |
| Veilleuse, installation de moins de 5 ans | D | Voix |
| PAC air/air : aussi comptée en climatisation | A | Règle rappelée dans checklist-dpe.md |
| **Ventilation, production d'énergie** | | |
| Type de ventilation (bouches, entrées d'air, caisson) | C + D | Image + voix |
| Année de la ventilation | D | Voix |
| Panneaux photovoltaïques : présence, orientation, surface | C / D | Vidéo extérieure, boussole, voix |
| **Justificatifs** | | |
| Photos (façades, murs, équipements, compteur) | A | Images extraites des vidéos |
| Factures, attestations | P → C | Photo du document + lecture du texte |

Les conventions de mesure de la méthode 3CL-2021 seront appliquées par le moteur de conversion d'après le texte officiel, sans approximation maison :
- dimensions intérieures ou extérieures ;
- déduction des baies ;
- découpage par type de paroi.

## 3. Briques techniques et choix recommandés

| Brique | Choix recommandé | Remarques |
|---|---|---|
| **Capture** | **PWA** (navigateur) :<br>- `MediaRecorder` : vidéo + audio, débit réglé autour de 8 Mbit/s en 1080p ;<br>- `DeviceOrientation` / `DeviceMotion` : boussole et gyroscope horodatés ;<br>- stockage local (IndexedDB) ;<br>- envoi par morceaux, reprenable (protocole tus). | Sur iPhone, l'accès à la boussole demande une autorisation explicite. Le stockage local de Safari est limité, d'où l'envoi pièce par pièce dès que le réseau est là. Guidage à l'écran : tour lent, angles visibles, contrôle de netteté. |
| **Mise à l'échelle** | 1) **Mesure laser dictée** par pièce (sert aussi au Carrez). 2) **Mire imprimée** : feuille A4 à marqueurs ArUco, détectée par OpenCV. 3) Secours : hauteur de porte standard. | **Point critique** : une erreur d'échelle de 2 % donne environ 4 % d'erreur sur les surfaces. |
| **Reconstruction 3D** | Extraction d'images (ffmpeg), puis **COLMAP** ou **GLOMAP** (open source, licence BSD) pour les positions de caméra et le nuage de points. Profondeur monoculaire (ex. **Depth Anything V2 Small**, Apache-2.0) pour densifier les murs peu texturés. | Les modèles 3D appris récents (DUSt3R, MASt3R…) sont plus robustes sur les murs blancs, mais **leurs licences sont souvent non commerciales** : à vérifier avant tout usage. |
| **Plan de la pièce** | Détection de plans (sol, plafond, murs) dans le nuage de points (**Open3D**, MIT, méthode RANSAC), hypothèse d'angles droits quand elle est plausible. On obtient le contour au sol, les longueurs, la hauteur, les surfaces et un **plan coté** (SVG/PDF). | Variante de secours : un panorama 360° pris du centre de la pièce, analysé par un modèle d'agencement de pièce (type HorizonNet). Licence à vérifier. |
| **Fenêtres et portes** | Détection « à vocabulaire ouvert » (**Grounding DINO** ou **OWLv2**, Apache-2.0) + segmentation (**SAM 2**, Apache-2.0), projetées sur le plan du mur pour obtenir les dimensions et la profondeur d'embrasure. | Éviter les briques sous licence AGPL (ex. YOLO d'Ultralytics) sans licence commerciale. |
| **Orientation** | Cap de la boussole pendant le film + positions de caméra → azimut de chaque mur, corrigé de la déclinaison magnétique. Recoupement avec l'emprise du bâtiment (RNB / cadastre). | |
| **Plusieurs pièces** | Prototype : pièce par pièce. Les liens entre pièces (mur commun = intérieur) sont confirmés à la voix ou à l'écran. Plus tard : assemblage automatique en filmant le passage des portes. | |
| **Voix** | **faster-whisper** (Whisper large-v3, licence MIT) avec horodatage des mots, recalé sur la vidéo pour savoir quelle pièce et quel mur sont concernés. | Vocabulaire métier (« VMC hygro B », « ITE », « R = 5 ») à tester sur de vrais enregistrements. |
| **Voix → champs** | Modèle de langage ouvert (ex. Mistral Small, Apache-2.0) ou API, avec **schéma JSON imposé** : il ne remplit que ce qui est explicitement dit et cite l'extrait de parole. | |
| **Plaques et équipements** | Lecture de texte : **PaddleOCR** (Apache-2.0). Interprétation (type d'appareil, marque, modèle, puissance) : modèle vision-langage ouvert (licence à vérifier selon le modèle) ou API commerciale si la qualité l'exige. | |
| **Données administratives** | Service Python : géocodage BAN (Géoplateforme IGN), API RNB, altimétrie IGN, BDNB, DPE ADEME en données ouvertes. Mise en cache avec source et date. | Accès BDNB (clé, conditions) à vérifier. |
| **Serveur** | Python (FastAPI) + file de tâches + un ou plusieurs serveurs GPU **à la demande** + stockage objet. **Hébergement en France ou dans l'UE** (ex. OVHcloud, Scaleway) pour le RGPD. | Ce PC n'a pas de GPU NVIDIA : l'étape 1 tourne sur CPU (plus lent) ou sur un GPU loué à l'heure. |
| **Format intermédiaire** | JSON « Dossier terrain v1 » : chaque valeur porte **source, confiance, statut** (proposé / confirmé / modifié / manquant) **et preuve** (image, extrait audio). | Indépendant de LICIEL. Conversion via `diagauto.liciel_xml`. |

## 4. Précision et risques

| Sujet | Risque | Parade |
|---|---|---|
| **Carrez / Boutin** | Une erreur de plus de 5 % ouvre droit à une baisse du prix. Une précision vidéo de 3 à 5 % ne suffit donc pas. | **Mesure laser dictée = mesure officielle.** La vidéo sert au contrôle (« la pièce mesure 4,12 × 3,60 au laser, la vidéo trouve 4,05 × 3,58 : cohérent »), au plan et aux déductions à signaler. |
| **DPE** | Peu sensible à quelques % de surface. **Très sensible aux erreurs de classement** (isolation, matériau, système). | Invisible = dicté, jamais deviné. Preuve affichée pour chaque valeur. Validation explicite. |
| Échelle | Une erreur d'échelle se répercute au double sur les surfaces. | Mesure laser par pièce, ou mire A4. Contrôle croisé entre les deux quand ils sont disponibles. |
| Murs blancs, miroirs, vitres, pièces sombres ou encombrées | La reconstruction échoue ou reste incomplète. | Guidage pendant le film. Profondeur monoculaire et hypothèse d'angles droits. Le système **signale** les pièces douteuses (alors : saisie des cotes laser). |
| Téléphones anciens | Vidéo de moindre qualité, déformation des images en mouvement rapide, boussole imprécise. | Débit et résolution adaptés. Tour lent guidé. Orientation recoupée avec l'emprise du bâtiment. |
| Réseau sur place | Pas d'envoi pendant la visite (1 à 1,5 Go de vidéo par logement). | Stockage local, puis envoi au bureau. Les résultats arrivent alors après la visite et la validation se fait au bureau. |
| Délai de calcul | 5 à 15 min par pièce sur serveur. | Traitement pièce par pièce pendant la visite. |
| Vie privée (RGPD) | Vidéos de logements habités (personnes, documents). | Floutage des visages, durée de conservation limitée (ex. 90 jours), hébergement en France ou dans l'UE, information du propriétaire. |
| Licences | Plusieurs modèles récents interdisent l'usage commercial. | Liste blanche de licences (MIT, BSD, Apache-2.0), vérifiée brique par brique. |
| Sortie DPE vers LICIEL | Injection des tables DPE non prouvée (codes internes LICIEL). | En attendant, **fiche de saisie DPE pré-remplie** ; pistes XML ADEME et `.LDossier` (01-cadrage.md). |

## 5. Coût serveur approximatif par dossier

Ce sont des **ordres de grandeur à mesurer dès l'étape 1**. Hypothèse : un logement de 8 pièces, environ 1 min de vidéo par pièce, 1 à 1,5 Go de vidéo au total.

| Poste | Estimation | Coût |
|---|---|---|
| Reconstruction + détection (GPU) | 15 à 40 min de GPU, loué 0,5 à 2 €/h selon la carte et le fournisseur | 0,15 à 1,30 € |
| Transcription (10–15 min d'audio) | Moins de 1 min de GPU | < 0,05 € |
| Plaques et équipements (50 à 150 images) | Modèle ouvert sur notre GPU, ou API commerciale | 0,05 à 1 € |
| Extraction voix → champs | Quelques milliers de mots | < 0,05 € |
| Stockage des vidéos (90 jours) | 1,5 Go | < 0,10 € |
| **Total variable** | | **≈ 0,50 à 2,50 € par dossier** |

Coûts fixes : un petit serveur d'application + base de données, quelques dizaines d'euros par mois. Au démarrage, les GPU sont loués **à la demande**. Un serveur GPU permanent (plusieurs centaines d'euros par mois) ne se justifie qu'à partir de plusieurs centaines de dossiers par mois.

## 6. Plan de prototype en 3 étapes

| Étape | Contenu | Critère de réussite |
|---|---|---|
| **V1. Preuve : vidéo d'une pièce → plan coté + surfaces** | Pas encore d'app : vidéos tournées avec 2 ou 3 téléphones, dont un Android ancien, sur 5 à 10 pièces réelles, avec mire A4 et mesures laser de référence. Script serveur (`diagauto reconstruire video.mp4 --echelle …`) : images → COLMAP/GLOMAP → plans des murs → mise à l'échelle → **plan coté (SVG/PDF), surfaces du sol et des murs, hauteur**. Rapport d'écart avec le laser, et temps et coût de calcul mesurés. | Écart de surface ≤ 5 % (objectif 3 %) sur au moins 80 % des pièces. Les cas d'échec sont expliqués. Coût et temps par pièce connus. **Décision « on continue / on ajuste » avec Noah.** |
| **V2. Capture complète d'un logement** | PWA (vidéo + voix + boussole par pièce, envoi reprenable). Détection des fenêtres et portes avec leurs dimensions, orientation des murs, longueurs de ponts thermiques. Transcription et extraction des champs invisibles. Lecture des plaques. JSON « Dossier terrain v1 ». | Sur 3 logements réels : part des champs de la checklist correctement pré-remplis (mesurée), **zéro valeur sans preuve**, temps et coût par dossier mesurés. |
| **V3. De bout en bout** | Données administratives depuis le devis + API publiques. Écran de validation. Génération LICIEL des pièces + Carrez (mesures laser) via `diagauto.liciel_xml` ; fiche DPE pré-remplie. Pilote sur 2 à 3 vraies visites, chronométrées. | Aucune ressaisie des pièces ni du Carrez. Temps de visite + saisie mesuré avant et après. Liste des irritants. |

## 7. Questions nouvelles

- **Q1 — Vidéos de test pour l'étape 1.** Qui filme 5 à 10 pièces réelles, avec quels téléphones ? Il faut aussi les mesures laser de référence ; un protocole de tournage d'une page sera fourni.
- **Q2 — Devis.** Sous quelle forme arrivent les données du devis Imodiag : API, export, e-mail ? Quels champs ?
- **Q3 — IA et hébergement.** Les vidéos et l'audio peuvent-ils être traités sur un serveur loué en France ou dans l'UE ? Préfère-t-on 100 % open source auto-hébergé, ou accepte-t-on une API commerciale pour la lecture des plaques si elle est nettement meilleure ? (Prolonge N9.)
- **Q4 — Calcul.** Peut-on louer un GPU à l'heure pour l'étape 1, pour quelques euros ? Ce PC n'a pas de GPU NVIDIA.
- **Q5 — Sortie DPE.** Pendant le prototype, une fiche DPE pré-remplie à recopier dans LICIEL est-elle acceptable, le temps de prouver l'injection automatique ?
- **Q6 — BDNB.** Faut-il demander un accès (clé, offre) ? Hermes peut-il vérifier les conditions d'usage ?
