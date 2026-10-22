# Étape 13 : rejeu des visites de Noah avec le DPE par côté (22/10/2026)

**Méthode** : les phrases réellement dites par Noah (transcriptions du journal de chaque visite, fautes comprises) sont
rejouées une à une dans une session du nouveau parcours, en mode `rapide` (règles du serveur, **sans Claude**), **sans
boussole** (le rejeu n'envoie pas les capteurs) et sans la pièce de départ. C'est donc le cas le plus défavorable : en
vrai, Claude lit chaque phrase et la boussole range chaque mur de son côté.

Rejeu : chaque phrase du journal (`evenement` « extraction ») passée à `tests/test_dialogue.visite`, comme dans les tests.

## Résultats

| Visite | Phrases | Questions posées | Questions sur la pièce | DPE rempli |
|---|---|---|---|---|
| après-midi (`20261022-153605`) | 80 | 28 (17 différentes) | **0** | 67 % |
| matin (`20261022-120410`) | 40 | 24 (15 différentes) | **0** | 44 % |

**Ce qui va** :
- aucune question sur la pièce ; la première question est « Ce mur donne sur quoi ? » ;
- les murs de la visite de l'après-midi sont reconnus comme avant : « le mur des 3 fenêtres », le mur côté voisin, le mur
  sur la rue en parpaing 30 cm avec sa fenêtre en PVC ; le plancher sur cave est noté une fois pour le logement ;
- « Il te faut quoi d'autre ? » reçoit une réponse précise (« Pour le troisième mur, il me manque… »), puis la question
  reposée.

**Ce qui reste faible (sans Claude ni boussole)** :
- sans boussole, aucun mur n'a de côté : tous sont « côté à trouver », et « Et côtés nord, est et sud… ? » n'arrive
  qu'une fois un côté connu par la parole (« le mur ouest ») ;
- la visite du matin n'a pas dit sa pièce de départ dans le rejeu : les murs sans pièce se nomment par leur rang
  (« le quatrième mur ») ; avec une pièce dite, le rang compte dans la pièce (« le deuxième mur », « le premier mur du
  séjour » vu d'ailleurs) ;
- des phrases ambiguës (« Qui mène sur un voisin », dite pour un autre mur sans le nommer) corrigent le mur de la
  question : avec la vidéo, c'est la caméra qui tranche (« ce mur-là ») ; sans elle, l'assistant le signale (« Je
  remplace extérieur. »).

## Déroulé complet

### Visite 20261022-153605-67f6df : 80 phrases
- « Cquez doncc là c'est la première pièce, c'est le premier mur, tu m'entends? » → Ce mur donne sur quoi ?
- « un mur qui fait quatre mètres il y a trois fenêtres sur le mur, un un mur qui est sur l'ex » → Ce mur donne sur quoi ?
- « ètre de de laine de verre » → Ce mur donne sur quoi ?
- « Je sais passé le mur ouest mais c'est bien extérieur, c'est le même mur. » → Le mur ouest : des fenêtres ou une porte ?
- « Savez dire quoi c'est le même mur que le mur ouest extérieur? » → (rien)
- « L'extérieur, c'est ce que je te dis, la rue. » → (rien)
- « Sur les combes, c'est une chambre là- haut. » → (rien)
- « Non. » → Le premier mur est en quoi ?
- « Le plancher ici donne sur une ce. » → (rien)
- « Le plancher n'est pas isolé. » → Le premier mur est en quoi ?
- « Tu es là? » → (rien)
- « Elles sont en bois, il a y a trois fenêtres sur ce mur. » → Quelle épaisseur ?
- « Je te'ai dit en laine des verres au début, je te l'ai dit. » → Quelle épaisseur ?
- « Oui, il y a ce mur- là. » → (rien)
- « Qui mène sur un voisin. » → Je remplace extérieur. Les 3 fenêtres : PVC, bois ou alu ?
- « Non, c'est un autreôte mur. c'est un autreôt mur. » → (rien)
- « Tu m'as dit Tu m's posé question à cequ'il y a un œuf mur. » → (rien)
- « Sur un voisin. » → J'ai compris bois, c'est bien ça ?
- « Y a ce mur- là. » → (rien)
- « Un voisin. » → Simple ou double vitrage ?
- « Il ré. » → (rien)
- « Heuh y ce mur- là. » → (rien)
- « Exact, oui. » → (rien)
- « Ba. c'est celui- ci qui mène sur l'extérieur. » → Ce mur est en quoi ?
- « Onz parpaing trente centimètres et quinze centimètres de laine de verre. » → Des fenêtres ou une porte sur ce mur ?
- « Il. » → (rien)
- « Mais non, après l'aille à la fenêtre. » → (rien)
- « E Elle est en Pvc. » → Cette fenêtre : simple ou double vitrage ?
- « Double Par contre, les trois sonettees de là- bas y sont simples. » → Des volets ?
- « E oui. » → (rien)
- « Pareille une cave, tout tout le planchers même sur une cave en bas. » → Des volets ?
- « E balin, faites chaussure tournée dans la pièce U. » → (rien)
- « Oui. roulant. En bois. » → Je remplace PVC. Les 3 fenêtres : des volets ?
- « Je t'ai montré là la fenêtre qu' mène sur dans la cuisine. » → (rien)
- « F. » → (rien)
- « All nous. » → (rien)
- « Tu es là? » → (rien)
- « Oui, je t'ai dit qu'il y a là la fenêtre dans la cuisine qui mène sur l'extérieur, on en a » → (rien)
- « Dans dans la pièce une, an. mais dans la cuisine, oui. » → (rien)
- « Oui, il y a-enant deux radiateurs au eau chaude avec de l'eau et à ces basses températures » → Les 3 fenêtres : des volets ?
- « Le gaz. » → (rien)
- « basse température. » → (rien)
- « Oh, dans les deux milles, deux milleines. » → (rien)
- « Avec du gaz. » → (rien)
- « Je t'ai dit ça avec gaz. » → (rien)
- « J'ai dit chaudière, je te l'ai dit. » → Et côtés nord, est et sud, le logement donne sur quoi ?
- « Vaime s. » → (rien)
- « A je t'ai dit vingt pieds. » → (rien)
- « GMC. » → (rien)
- « Simple. » → (rien)
- « Tu m'écoutes pas ou quoi? » → (rien)
- « Il y a cette pièce. » → (rien)
- « Y a sept pièces. » → (rien)
- « Mur vers l'extérieur. » → Ce mur est en quoi ?
- « En bois. partantin. » → Quelle épaisseur ?
- « Qu. » → (rien)
- « Trente centimètres. » → Il est isolé ?
- « Na. » → (rien)
- « Nur. » → (rien)
- « Il n'est pas isolé. » → Des fenêtres ou une porte sur ce mur ?
- « Celui- ci celuilui- ci. » → (rien)
- « Oui oui oui Tu m'entends? » → Cette fenêtre : PVC, bois ou alu ?
- « vaot. » → (rien)
- « Il tu m'entends Al'ô Alô. allô. » → Simple ou double vitrage ?
- « Oui, je t'ai dit celui- ci. » → (rien)
- « Oui, c'est un mur sur la chambre, mais à la différence du premier, c'est que celui- ci mèn » → Simple ou double vitrage ?
- « Elle par su. » → (rien)
- « Non. » → (rien)
- « Oui. » → (rien)
- « P. » → (rien)
- « Oui. » → (rien)
- « Il. » → (rien)
- « Non. » → (rien)
- « Elle n'est pas isolée. » → (rien)
- « A. » → (rien)
- « A. » → (rien)
- « Lour. » → (rien)
- « Unf. » → (rien)
- « Bois. c'est du bois. » → Je remplace alu. Des volets ?
- « Le simple. » → Des volets ?

Questions : 28 ; sur la pièce : 0 ; uniques : 17 ; DPE rempli à 67 %
Enveloppe :
   Enveloppe du logement (DPE : murs par côté, toutes pièces confondues ; murs entre pièces ignorés) :
   - côté nord : rien encore
   - côté est : rien encore
   - côté sud : rien encore
   - côté ouest : M2 mur « le mur ouest » (dit, orienté ouest (dit), vu dans aucune pièce encore) : donne sur = extérieur, matériau = parpaing, épaisseur = 30 cm, isolation = isolé laine de verre
       sur ce mur : aucune fenêtre (dit)
   - côté inconnu (orientation à trouver) : M1 mur « le mur des 3 fenêtres » (dit, vu dans aucune pièce encore) : donne sur = local chauffé (voisin) (déjà demandé, à vérifier plus tard : ne pas redemander), matériau = bois, épaisseur = inutile pour le DPE, isolation = isolé laine, longueur = inutile pour le DPE, part du mur = inutile pour le DPE
       sur ce mur : F1 fenêtre ×3 « les 3 fenêtres » (dit, sur M1, vu dans aucune pièce encore) : menuiserie = ?, vitrage = ?, volets = ?
   - côté inconnu (orientation à trouver) : M3 mur « le mur de la fenêtre en parpaing » (dit, vu dans aucune pièce encore) : donne sur = extérieur, matériau = parpaing, épaisseur = 30 cm, isolation = isolé laine de verre
       sur ce mur : F2 fenêtre « la deuxième fenêtre » (dit, sur M3, vu dans aucune pièce encore) : menuiserie = bois (déjà demandé, à vérifier plus tard : ne pas redemander), vitrage = double, volets = roulants
   - côté inconnu (orientation à trouver) : M4 mur « le mur de la fenêtre en bois » (dit, vu dans aucune pièce encore) : donne sur = extérieur, matériau = bois, épaisseur = 30 cm, isolation = non isolé
       sur ce mur : F3 fenêtre « la troisième fenêtre » (dit, sur M4, vu dans aucune pièce encore) : menuiserie = bois (déjà demandé, à vérifier plus tard : ne pas redemander), vitrage = simple, volets = ?
   - côté inconnu (orientation à trouver) : M6 mur « le sixième mur » (dit, vu dans aucune pièce encore) : donne sur = local chauffé (voisin), matériau = inutile pour le DPE, épaisseur = inutile pour le DPE, isolation = inutile pour le DPE, longueur = inutile pour le DPE, part du mur = inutile pour le DPE
   - plafond : PL1 plafond « le plafond » (toujours présent, vu dans aucune pièce encore) : donne sur = ?, isolation = ?
   - plancher : PB1 plancher « le plancher » (toujours présent, vu dans aucune pièce encore) : donne sur = sous-sol / cave, isolation = non isolé
   Murs entre deux pièces (ignorés pour le DPE) : M5
Pièces notées (repère) : []

### Visite 20261022-120410-53ecb1 : 40 phrases
- « . » → (rien)
- « Laine de verre. » → Ce mur donne sur quoi ?
- « Est- ce un mur? » → (rien)
- « Mais derrière un rideau y a toujours un un mur fallay sii- sii, je mont comme ça, c'est qu » → (rien)
- « Là déjà vo plus mais il y a aussi une fenêtre ici, une fenêtre ici, une fenêtre aussi là-  » → Ce mur donne sur quoi ?
- « Donc, en fait, il y a dans le même mur, il y a trois fenêtres ces trois ces trois fenêtres » → Au-dessus du logement : combles, terrasse ou un autre logement ?
- « mètres d' éppaisseur le mur fait trois centimètres vingtt centimètres et l'isolant, est du » → J'ai compris 3 cm d'épaisseur : plutôt 30 cm ?
- « L'isolence est due la laine de verre trente centimètres voilà il y a également deux radiat » → Ce mur donne sur quoi ?
- « Il donne sur la rue? » → Il est en quoi ?
- « Extérieur? » → Il est en quoi ?
- « Extérieur. » → Les autres côtés du logement donnent sur quoi ?
- « En brique? » → Ce mur donne sur quoi ?
- « Il est en brique. » → Ce mur donne sur quoi ?
- « Je Djaddi au préalable trente centimètres d'épaisseur de laine de verre et le mur fait qui » → Le plafond est isolé ?
- « Qui faut quoi doute? » → Pour le plafond, il me manque sur quoi il donne et l'isolation. Le plafond est isolé ?
- « Bra sur qu'il y a cemur, cemur et cemur. » → Ce mur donne sur quoi ?
- « Le mur du tableau y donne derrière sur les toilettes, d'ox de l'intérieur. » → Le quatrième mur donne sur quoi ?
- « Ici. » → (rien)
- « EC. » → (rien)
- « Sur une haut maison derrière. » → J'ai compris local chauffé : WC, c'est bien ça ?
- « Mais c'est pas la mienne. » → Le troisième mur donne sur quoi ?
- « . » → (rien)
- « . » → (rien)
- « Alors tu parles pas? » → (rien)
- « Il est en brique. » → Ce mur donne sur quoi ?
- « . » → (rien)
- « Tous les murs de la maison sont en briques. » → Quelle épaisseur ?
- « Pourourir. » → (rien)
- « Il te veut quoi d'ôte? » → Pour le troisième mur, il me manque sur quoi il donne, l'épaisseur et l'isolation. Quelle épaisseur ?
- « Mais tu parles plus à l'orel? » → (rien)
- « Sur le voisin. » → Le mur extérieur : des fenêtres ou une porte ?
- « Est- ce qu'on a fait ce mot au ce mur, je me rappelle plus. » → (rien)
- « Sur un autre voisin. » → (rien)
- « Onant alors dans ce jour si fini après là, il y a un couloir. » → Le mur extérieur : des fenêtres ou une porte ?
- « S'il y a un couloir? » → (rien)
- « Mais non est là, on a changé de pièce là. » → (rien)
- « a un murici. un murici et un movicie. » → Ce mur donne sur quoi ?
- « Ce premier mur- là Voilà qui que je te dise qui donne sur l'extérieur? » → Ce mur, quelle épaisseur ?
- « Il il fait trente centimètres de lar, gilé en brique avec des isolants laine de verre La l » → Les 3 fenêtres : simple ou double vitrage ?
- « P à la cuisine c'est un plafond basique ainsi exactement que même que le salon d'ailleurs, » → (rien)

Questions : 24 ; sur la pièce : 0 ; uniques : 15 ; DPE rempli à 44 %
Enveloppe :
   Enveloppe du logement (DPE : murs par côté, toutes pièces confondues ; murs entre pièces ignorés) :
   - côté nord : rien encore
   - côté est : rien encore
   - côté sud : rien encore
   - côté ouest : rien encore
   - côté inconnu (orientation à trouver) : M1 mur « le premier mur » (dit, vu dans aucune pièce encore) : donne sur = extérieur, matériau = brique (règle du logement), épaisseur = 30 cm, isolation = isolé laine de verre 30 cm
   - côté inconnu (orientation à trouver) : M2 mur « le deuxième mur » (dit, vu dans aucune pièce encore) : donne sur = ?, matériau = brique, épaisseur = 15 cm, isolation = isolé laine de verre
   - côté inconnu (orientation à trouver) : M3 mur « le troisième mur » (dit, vu dans aucune pièce encore) : donne sur = local chauffé (voisin), matériau = brique, épaisseur = inutile pour le DPE, isolation = inutile pour le DPE, longueur = inutile pour le DPE, part du mur = inutile pour le DPE
   - côté inconnu (orientation à trouver) : M4 mur « le quatrième mur » (dit, vu dans aucune pièce encore) : donne sur = local chauffé (voisin), matériau = brique (règle du logement), épaisseur = inutile pour le DPE, isolation = inutile pour le DPE, longueur = inutile pour le DPE, part du mur = inutile pour le DPE
   - côté inconnu (orientation à trouver) : M6 mur « le mur des 4 fenêtres » (dit, vu dans Couloir) : donne sur = extérieur, matériau = brique, épaisseur = 30 cm, isolation = isolé laine de verre 20 cm
       sur ce mur : F1 fenêtre ×3 « les 3 fenêtres » (dit, sur M6, vu dans aucune pièce encore) : menuiserie = PVC, vitrage = ?, volets = ?
       sur ce mur : F2 fenêtre « la fenêtre en bois » (dit, sur M6, vu dans Couloir) : menuiserie = bois, vitrage = ?, volets = ?
   - côté inconnu (orientation à trouver) : M7 mur « le deuxième mur » (dit, vu dans Couloir) : donne sur = ?, matériau = brique (règle du logement), épaisseur = ?, isolation = ?
   - côté inconnu (orientation à trouver) : M8 mur « le troisième mur » (dit, vu dans Couloir) : donne sur = ?, matériau = brique (règle du logement), épaisseur = ?, isolation = ?
   - plafond : PL1 plafond « le plafond » (toujours présent, vu dans aucune pièce encore) : donne sur = ?, isolation = ?
   - plancher : PB1 plancher « le plancher » (toujours présent, vu dans aucune pièce encore) : donne sur = ?, isolation = ?
   Murs entre deux pièces (ignorés pour le DPE) : M5
Pièces notées (repère) : ['Couloir']

