# Historique des exigences de Noah (transmises par Hermes)

Demandes reçues dans `docs/exigences-en-attente.md`, intégrées le 22/10/2026, puis retirées de ce fichier.
Où trouver le résultat :

- étapes 2 à 10 : [prototype-assistant/README.md](../prototype-assistant/README.md) (une section par étape) et les rejeux avant/après dans [prototype-assistant/rejeux/](../prototype-assistant/rejeux/) ;
- étape 11 (pont assistant → LICIEL) : [README.md](../README.md), section « Générer le dossier LICIEL d'une visite » ;
- étape 12 (carte des pièces, pièces revisitées, phrase → mur) : [prototype-assistant/README.md](../prototype-assistant/README.md),
  section « Étape 12 », et [prototype-assistant/rejeux/20261022-etape12-carte.md](../prototype-assistant/rejeux/20261022-etape12-carte.md).

---

## Étape 2 — ENVOYÉE à Claude le 22/10 08:03 (vérifier puis envoyer l'étape 3)
<!-- ancien titre : à envoyer quand l'étape 1 (compréhension description libre) est finie et testée -->
- Parcours mur par mur : après chaque mur, demander « Y a-t-il un autre mur dans cette pièce ? » jusqu'à 4+ murs, puis fenêtres/portes restantes, puis pièce suivante.
- Ne poser que les questions UTILES au DPE (priorité aux données qui changent l'étiquette) ; ne pas demander des détails peu utiles si le diagnostiqueur ne sait pas (ex. date des radiateurs).
- « Épaisseur d'une fenêtre » n'a pas de sens : demander menuiserie / vitrage / dimensions.
- Gérer les quantités : « en tout trois fenêtres ».
- Réduire la latence (trop de temps de réponse).

## Étape 3 — ENVOYÉE à Claude le 22/10 (en file après l étape 2)
- Compréhension orale robuste : le diagnostiqueur a dit « eau chaude » (radiateur à eau / électrique), la transcription a donné « Oh ! est chaude » et l'assistant n'a pas compris. Il y a plein de cas comme ça.
- Doit comprendre les gens qui parlent mal, vite, avec accent, qui bégaient : vocabulaire métier injecté dans la transcription (prompt initial Whisper / hotwords), modèle de transcription plus gros ou meilleur pour le français, correction par Claude selon le contexte (question posée = « eau ou électrique ? » → « Oh est chaude » = eau chaude), corpus de tests audio réels avec erreurs.

## Étape 4 (Noah, 22/10) — ENVOYÉE à Claude le 22/10 09:07 (étape 3 vérifiée : 96 + 624 tests OK)
- L'assistant doit S'ADAPTER à toute situation, pas un questionnaire rigide. Exemple : « il y a 9 radiateurs électriques basse température et 1 électrique haute température » → il doit créer 2 groupes d'émetteurs différents (9 + 1), avec leurs attributs propres, et ne pas supposer que tout est identique.
- Plus généralement : modèle de données flexible (groupes/quantités/exceptions pour murs, fenêtres, émetteurs, générateurs…), chaque élément peut différer ; le diagnostiqueur peut corriger ou préciser à tout moment (« sauf celui de la chambre qui est en PVC »).
- Revoir la règle « date / température des radiateurs jamais demandées » : ne pas demander par défaut, mais TOUJOURS enregistrer si le diagnostiqueur le dit, et gérer les exceptions par élément.
- L'IA construit dynamiquement ses questions selon le logement réel et ce que dit le diagnostiqueur (pas de liste figée).
- Tests : au moins 15 scénarios d'exceptions (groupes mixtes, corrections tardives, « tous sauf un », éléments ajoutés après coup).

## Étape 5 (Noah, 22/10) — ENVOYÉE à Claude le 22/10 (étape 4 vérifiée : 133 + 624 tests OK). Analyse Hermes du test réel sessions/20261022-083308-20ef54 (Noah : « trop lent, ne s'adapte pas, je dois répéter, je ne sais pas c'est quel mur 3 / mur 4 »)
Constats (journal.jsonl) :
1. NOMS DE MURS ABSTRAITS : « Le mur 3 est en quoi ? », « le quatrième mur » → le diagnostiqueur ne sait pas lequel. Nommer chaque élément par ce qui est visible/dit : « le mur avec la télé », « le mur des 3 fenêtres », « le mur côté voisin », orientation boussole (« mur nord »), + vignette de l'image sur l'écran. Jamais « mur 3 » à l'oral.
2. PHRASES GLOBALES IGNORÉES : « Il y a juste un mur qui donne sur l'extérieur, le reste donne sur l'intérieur ou les voisins » → doit CLORE la pièce (tous les autres murs = local chauffé / mitoyen, aucune question matériau dessus). Or il a créé M4 puis demandé encore « Ce mur 3, il est en quoi ? ». Gérer « le reste », « tous les autres », « pareil pour… ».
3. QUESTIONS INUTILES : matériau/épaisseur demandés pour des murs sur local chauffé ou mitoyen chauffé.
4. VALEURS ABERRANTES : « donne sur l'extérieur 30 mètres » enregistré longueur = 30 m pour un séjour → contrôle de plausibilité et reformulation (« 3 mètres ? »). Même chose pour contradictions (« plafond isolé » puis « pas isolé ») : garder la dernière, signaler.
5. TRANSCRIPTION = goulot de latence : faster-whisper small CPU médiane 2,45 s, p90 6,2 s ; voix prête médiane 4,7 s, p90 7,5 s. Solutions sans payer : transcription en flux PENDANT que la personne parle (morceaux de 1-2 s, ne transcrire que la fin à l'arrêt), int8, beam_size 1, vocabulaire métier en prompt, VAD plus réactif ; viser < 2 s de bout en bout. Mesurer avant/après sur l'audio de cette session (audio.wav) avec l'outil de rejeu.
6. Mauvaise transcription métier (« combles bleus », « le avec l'aise », « plafonds DPE ») → correction contextuelle (étape 3) à vérifier sur ce rejeu.
Livrable : rejouer cette session réelle avant/après, montrer le dialogue obtenu, tests de non-régression, commit, résumé 5 lignes.

## Étape 6 (Noah, 22/10) — ENVOYÉE à Claude le 22/10 (étape 5 vérifiée : 155/156 + 624, test latence flaky signalé) : BOUSSOLE et murs nommés par orientation
- Dans LICIEL / le DPE, les parois et surtout les fenêtres sont décrites par orientation (Nord, Sud, Est, Ouest) : c'est utilisé pour les apports solaires. Nommer les murs « mur nord », « mur sud »… (en plus du repère visuel : « le mur nord, celui avec la télé »).
- Petite boussole affichée en permanence dans un coin de l'écran vidéo (DeviceOrientationEvent / webkitCompassHeading ; demander l'autorisation sur iPhone ; fonctionner sur Android ancien).
- Orientation automatique : quand la caméra filme un mur de face depuis l'intérieur, l'orientation extérieure du mur = le cap de la caméra. Arrondir aux 4 (ou 8) points cardinaux, enregistrer le cap brut.
- Gestion des imprécisions : boussole perturbée par le métal/l'électrique → indicateur de fiabilité, calibration (geste en 8), cohérence entre murs opposés (nord ↔ sud à 180°), correction orale possible (« non, c'est le mur ouest »).
- Pièces sans capteur fiable : demander à l'oral une seule fois l'orientation de la façade principale et déduire les autres.
- Tests : calcul cap → orientation, murs opposés, correction orale.

## Étape 7 (Noah, 22/10) — ENVOYÉE à Claude le 22/10 (étape 6 vérifiée : 189 + 624 OK) : une VRAIE conversation, pas des listes de mots
- Noah : « il ne faut pas ajouter 3-4 mots de vocabulaire ; il faut qu'il comprenne TOUT, n'importe quelle phrase, comme quand je parle à Claude : je dis "comment ça va" il répond, je demande "comment se construit une maison" il répond ».
- Constat Hermes dans le journal du test : l'« extraction » est faite par des règles locales (extraction_ms ≈ 1 ms = mots-clés/regex) et Claude n'intervient qu'en « complément ». C'est la cause de la rigidité.
- À faire : CLAUDE devient le cerveau principal de CHAQUE phrase (compréhension libre, contexte complet de la visite, images), les règles locales ne servent plus qu'à pré-remplir/accélérer et ne doivent jamais bloquer ni contredire Claude.
- L'assistant doit pouvoir répondre à n'importe quelle question ou remarque hors questionnaire (« c'est quoi un pont thermique ? », « on fait une pause », « reviens au salon », « tu as noté quoi pour la cuisine ? », « comment ça va »), puis reprendre la visite naturellement.
- Conserver la rapidité : réponse de Claude en streaming, voix qui démarre dès la première phrase, file d'attente sans blocage.
- Tests : 30 phrases libres variées (questions générales, hors sujet, ordres de navigation, corrections, récapitulatifs).

## Étape 8 (Noah, 22/10 12:10) — ENVOYÉE à Claude le 22/10 ~12:15 : fluidité, silences, hors sujet, infos mal rangées, phrases globales, changement de pièce auto, murs pointés (voir scratch/msg8.txt)

## Étape 9 (Noah, 22/10) — ENVOYÉE à Claude le 22/10 13:10 (étape 8 vérifiée : 233 + 624 OK)
- NE PAS RÉPÉTER ce que dit le diagnostiqueur : « laine de verre 30 cm » → pas de « OK, c'est noté laine de verre 30 cm ». Accusé de réception très court (« ok », petit bip, ou rien) puis directement la question suivante. Récapitulatif seulement sur demande ou en fin de pièce.
- FAUX DOUBLONS : Noah montre un mur côté couloir (jamais décrit avant) ; l'IA répond « je l'avais déjà noté, c'est un doublon, je le retire » → FAUX. Ne jamais affirmer qu'un élément existe déjà sans preuve (même repère visuel/orientation/description dans l'état) ; en cas de doute, créer l'élément et demander confirmation brève. Ne jamais supprimer un élément de soi-même. (Session 20261022-120410-53ecb1 vers 154-157 s et 268-273 s : « je retire mon doublon ».)
- Tests : 10 cas de nouveaux murs ressemblant à d'anciens, aucune suppression automatique ; mesure du nombre de mots répétés par réponse.

## Étape 10 (Noah, 22/10) — ENVOYÉE le 22/10 (étape 9 vérifiée : 251 + 624 OK) — après l étape 9 : FAUX « hors réseau »
- Noah voit « Hors réseau : l'enregistrement continue, l'assistant répondra au retour du réseau » alors qu'il a bien du réseau.
- Trouver la cause (détection basée sur navigator.onLine ? délai d'un ping/WebSocket trop court ? certificat auto-signé ? Claude lent interprété comme coupure ? reconnexion WebSocket ?) dans le journal de ses dernières sessions.
- Ne déclarer « hors réseau » que si le serveur est vraiment injoignable (plusieurs échecs consécutifs d'un battement de cœur, ex. 3 × 2 s) ; distinguer « serveur lent / Claude réfléchit » de « pas de réseau » ; reconnexion automatique silencieuse ; rattrapage des phrases en attente dès le retour.
- Tests : réseau lent, Claude lent, vraie coupure, reconnexion.

## Étape 11 — ENVOYÉE le 22/10 (étape 10 vérifiée : 263 + 624 OK) : reformulation + pont assistant -> tables LICIEL (pièces + Carrez)
- Reformuler en 10 lignes la compréhension du logiciel DiagAuto.
- Construire le pont assistant -> LICIEL : à partir de l'état d'une visite (sessions/<dernière>/ : pièces, murs, ouvertures, émetteurs), générer les tables LICIEL de notre dossier de test (liste des pièces + Carrez) avec le sérialiseur octet-exact de diagauto/liciel_xml, dans un dossier hors C:\LICIEL_* (ex. sorties/dossier-test). Valider avec diagauto verifier. Tests, README, ce fichier. Ne jamais toucher à C:\LICIEL_*.

## Étape 12 — ENVOYÉE le 22/10 14:36 (étape 11 vérifiée : 264 + 652 OK) : V1 de la vidéo continue, 2 pièces avec allers-retours
- Reformuler en 5 lignes la compréhension.
- Côté serveur, module de reconnaissance des pièces revisitées à partir d'une vidéo continue (suivi continu du mouvement, pas de « photo toutes les 3 s ») : reconnaître qu'on retourne dans une pièce déjà vue (jamais de doublon) ; rattacher chaque phrase dictée (« ce mur c'est brique 30 cm ») au mur visible à cet instant (horodatage + cap boussole/gyro). Tout téléphone, même ancien, sans LiDAR, Claude seul comme IA (pas d'API).
- Rejouer sur la dernière session réelle et sur une vidéo de test ; tests ; limites documentées honnêtement.
- Brancher le résultat sur l'état de l'assistant (pièces/murs nommés par repère + cap) et sur diagauto generer. Commit, puis dire ce qui reste.

## Étape 13 (ENVOYÉE le 22/10 16:35, intégrée le 22/10) — Le DPE se fait de façon GLOBALE, pas pièce par pièce (consigne de Noah, 22/10, à envoyer après l'étape 12)
- Dans le DPE, on décrit l'ENVELOPPE du logement (tout ce qui l'entoure), pas chaque pièce. Les murs entre pièces intérieures ne comptent pas (« on s'en fiche »).
- Donc le système (assistant live + checklist + extraction + pont LICIEL) doit raisonner par ORIENTATION : mur ouest, mur nord, mur sud, mur est. Pour chaque mur extérieur : donne sur la rue / l'extérieur / un voisin / local non chauffé, isolation, nombre de fenêtres et portes sur ce mur.
- Les données sont globales à l'appartement / la maison : un « mur ouest » = tous les murs ouest du logement, toutes pièces confondues. Ne PAS créer un mur par pièce pour le DPE. Les pièces servent pour Carrez et le repérage, pas pour le DPE.
- Cas à gérer : UN MÊME MUR dont une partie donne sur l'extérieur et l'autre partie sur un voisin → il faut pouvoir scinder le mur en segments (ex. « mur est : 60 % sur voisin, 40 % sur extérieur », avec surface/longueur de chaque partie, fenêtres rattachées au bon segment).
- À adapter : checklist-dpe.md, questions de l'assistant (ne pas demander « quels murs dans cette pièce » mais « ce mur donne sur quoi ? »), schéma des données, extraction, rejeux de test, tests pytest, README.
- Noah demande qu'on lui envoie un message quand c'est terminé.
- Précision de Noah pendant l'étape (22/10, message direct) : « quand on veut faire un dpe il nous demande dans quel piece on est mais c pas imprtant pour le dpe puisque on veut savoir quel chose de globale […] qu'on soit dans le sejour ou chambre pour le dpe on s'en fiche » → l'assistant ne demande jamais la pièce.

## Étape 14 (Noah, message direct du 23/10/2026, intégrée le 23/10) — Croquis en direct pour le plomb et l'amiante
- « ok c bon pour le dpe mtn il faut que pour le pllonc et l'amiante il faut faire un plan donc faut que ut trouve un systeme ou on fait le tour le la maison et a fait un plan croquis automatqiuement avceun outil ia au tel et la perosnne uqipeut repondre en diret et entamment une idcution si l'ia a pas torp bine compris et il faut que le croqui se descine en meme temps que le digantqiuer fasse la video sur un coins du tel »
- Choix de Noah (questions posées) : croquis **sans aucune mesure** ; « il faut qu'il reconnaisse lui-même quand on change de pièce et c'est quoi la pièce » ; murs **A = mur de la porte, sens horaire**.


## Choix de la mission (Noah, message direct du 23/10/2026, intégré le 23/10)
- « comment je test le logiciel sur mon tel quan dj'ouvre l'url du logciel ca met uniquemet le dpe fautq ue je chossise avant le bonton ce que je veux faire par ex dpe ca m'envois a lavideo piryur faire le dpe ; ou amiante et ca m'memene au croquis »
- Mis en œuvre : accueil à trois cases (DPE, Amiante, Plomb (CREP)), « Démarrer » grisé tant qu'aucune n'est choisie ; DPE = questions du DPE, sans croquis ; amiante et plomb = croquis en grand, pièces reconnues et annoncées, aucune question du DPE (prototype-assistant/README.md, « Choix de la mission »).

## Étape 15 (Noah, messages directs du 23/10/2026, en cours) — Croquis professionnel : un tour par pièce, étages, géométrie
- « ameliore la creation de croquis faut qu'on filme une grande maison en un efois qu'on puisse passe de une piece a une autre d'un etage a un autr eet il le compren d / juste on arriv edan sune pice eon fait un tour tre srapide avec notre tel de 3 seconde par piec emax et ca re^pere les mur fernetre relief ect ect tpout automatique je veux une logciel de haute porfessionalisme »
- « tu en es ou ? on filme directement en direct sur le lgocirel que tu me creer »
- « il est pas assez performant faut analyser les angle des murs , la taille proportionelel des mur , la frome des piece, que l'image se situe dans l'image ppar rapport aux deplacement du diagnostqiuer »
- Fait (23/10) : capture du tour en direct (images selon la rotation avec leur pose, capteurs par lots, tour repéré et bipé). En cours : forme, angles et proportions (coins vus par Claude + calcul), placement selon les pas, étages (prototype-assistant/README.md, « Étape 15 »).
- Après le test de 11:44 (messages directs du 23/10) : « analyse la video il ne comprend rien du tout le croqui ne ressmenle pas du tout a la maison revosi entierement le systeme » ; « mais il fuat pas regarder par image il faut analyse rl avideo parceque par immage c pas bien » ; puis (texte collé) : « Le logiciel reconnaît les pièces, mais le croquis ne correspond pas à leur disposition réelle : toutes les pièces sont ajoutées en ligne droite, même quand je change de direction. Analyse le code pour identifier comment sont calculées la position du téléphone, son orientation et la position de chaque pièce. Vérifie notamment si les pièces sont simplement placées selon leur ordre de détection. Je veux un croquis fondé sur une reconstruction spatiale : suivre les déplacements du téléphone dans un repère commun, positionner les murs et les portes, puis rattacher les pièces à cette géométrie. Une rotation du téléphone sur place ne doit pas être interprétée comme un déplacement ou un changement de pièce. Vérifie aussi si le moteur de suivi fournit des coordonnées correctes mais que leur conversion vers le plan 2D est erronée. »
- Fait (23/10) : trajectoire par les pas et le gyroscope dans un repère commun, plan rattaché à la trajectoire, rotation sur place ignorée, phrases du croquis comprises par Claude (prototype-assistant/README.md, « Étape 15 (suite) »).
- Après le test de 12:46 (message direct du 23/10) : « regarde la video il se perd complteemnt pas il faut que tuc herche un autre moyen de faire le plan une maniere plus integgient eje nesais pas et qui ets sur qu'il se trompe pas la le lgocile ne se repere pas il fait lez chose dan sle mauvais sens il ne repere pas »
- Fait (23/10) : plan dessiné dans le sens de la marche, relations dites utilisées, correction qui n'efface plus une pièce nommée, pièce montrée puis entrée sans doublon, « ici il y a… » compris comme montré, nom de pièce inventé par Claude refusé, correction qui n'efface jamais une pièce déjà vécue (prototype-assistant/README.md, « Étape 15 (fin) ») ; proposé : reconstruction 3D de la vidéo complète après la visite et questions de fin de visite.
- Après le test de 15:06 (message direct du 23/10) : « ca marche toujours pas je pene que le plus sae ca serai d'ajouter de suivre les mur de la maison tu en penses quoic ca le plus safe »
- Fait (23/10) : relevé des murs (bouton « Murs » ou « les murs » ; chaque coin visé au ras du sol une seconde ; forme exacte et longueurs estimées par la géométrie du téléphone, sans IA ; prototype-assistant/README.md, « Étape 16 »).
- Texte collé par Noah (23/10, après l'étape 16) : « Je veux un système de tracé guidé du plan directement sur la caméra : 1. Une croix de visée reste au centre de l'écran. Je vise un coin de la pièce, à la jonction du mur et du sol, puis j'appuie sur un bouton pour enregistrer ce point. 2. Quand je déplace le téléphone vers le coin suivant, un trait pointillé se dessine entre le dernier point validé et l'endroit que je vise. Cela me permet de suivre le contour du mur. 3. J'appuie pour valider le deuxième coin : le segment devient fixe. Je continue ainsi, coin après coin, pour dessiner le contour de la pièce. 4. Les points et les segments déjà validés restent visibles à leur emplacement réel dans la caméra, même quand je marche, tourne le téléphone ou regarde ailleurs. Cela me permet de voir immédiatement les murs déjà tracés et d'éviter de les refaire. 5. Lorsque je reviens au premier point, l'application propose de fermer le contour. Je dois aussi pouvoir annuler le dernier point ou corriger un coin. Le point essentiel : la croix reste au centre de l'écran, mais les coins et les traits doivent être ancrés dans l'espace réel. Il faut suivre la position et l'orientation du téléphone pour que le tracé reste aligné avec les murs pendant mes déplacements. Le plan 2D doit se construire à partir des points réellement enregistrés, en respectant les changements de direction et les angles entre les murs. »
- Fait (23/10) : tracé guidé sur la caméra (web/trace.js), position suivie par le sol filmé (web/odometrie.js), contours gardés par le serveur et plan fait des points enregistrés avec leurs angles (prototype-assistant/README.md, « Étape 17 »).
- Après l'essai de 17:30 (message direct du 23/10) : « j'ai fait un vrai croqui ca a un pas marche il m'as dit une piece alors que j'ai toute la maison mai sen tout ca je suis arrive au point d'entre et les trait bougent top ameliroer nettemen,t c pas du tout encore pro »
- Fait (23/10) : suivi plus sûr (sol sous les pieds écarté, limite de vitesse), dessin figé à l'arrêt, recalage à la fermeture et « ⇄ Recaler », une pièce à la fois (prototype-assistant/README.md, « Étape 18 ») ; proposé : une application avec ARKit/ARCore pour un tracé pro en marchant.
