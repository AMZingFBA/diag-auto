# Étape 8 : plus fluide (test de Noah du 22/10/2026 après l'étape 7)

Visite d'origine : `sessions/20261022-120410-53ecb1` (iPhone, séjour puis cuisine, 5 min 48). Retour de Noah : « pas assez fluide, il s'arrête de parler, il répète, il ne prend pas toutes les infos, il ne comprend pas quand je change de pièce, il ne repère pas bien les murs, il parle des lampes ».

## Ce que montre le journal de la visite

- **Silences (« tu parles pas ? » à 190 s et 231 s)** : juste après chaque phrase de l'assistant, un claquement de 0,1 à 0,3 s arrive dans le micro (le téléphone qui bascule sa sortie son ; visible sur `audio.wav` à 222,1 s, 287,3 s, 322,8 s, 340,4 s…). Le serveur le prenait pour une prise de parole : il coupait la voix du téléphone et abandonnait la suite de la réponse. À 222 s et 287 s, la réponse n'a jamais été entendue (aucun début de voix dans le journal).
- **Phrases « . »** : un bruit transcrit « . » partait au second avis de Whisper (2 à 3 s de calcul qui bloquaient la phrase suivante), puis à Claude. Au début, Whisper a inventé « Laine de verre. » sur ce bruit, et Claude, sans vraie phrase à traiter, a décrit l'image : « un rideau blanc, une lampe, un climatiseur mobile ».
- **File bloquée 8 s** (68 s et 77 s) : une phrase finie par « fait » ou « est du » était tenue pour inachevée ; le serveur attendait la suite jusqu'à 8 s avant même de noter, pendant que Noah continuait de parler.
- **Valeurs perdues** : quand Claude doutait (« certitude probable »), sa valeur n'était pas notée ; d'où « laine de verre 20 cm » dit puis « il est isolé ? », et « une autre maison derrière, mais c'est pas la mienne » redemandé deux fois.
- **Valeur mal rangée** : « l'isolant est de la laine de verre 30 cm », dit en décrivant le mur, a été rangé sur le plafond, objet de la dernière question posée (les questions suivantes avaient été abandonnées).
- **Changement de pièce** : « on en a fini dans le séjour, après là il y a un couloir » a créé un « mur côté couloir ».
- **« Ce mur, ce mur et ce mur »** (transcrit « cemur, cemur et cemur ») : deux murs devinés sur une seule image.
- **Temps** : Claude réfléchit avant d'écrire (première phrase en 1,9 s en médiane, jusqu'à 4,7 s) ; voix à 3,1 s en médiane après la fin de phrase détectée.

## Rejeu de la visite, avant et après

```
python -m assistant.rejouer sessions\20261022-120410-53ecb1 --piece Séjour
```

Son et images d'origine, au rythme réel, avec Claude Code et la transcription sur ce PC. Les réponses de Noah sont celles du test : quand les questions changent, certains échanges ne se répondent plus. Le rejeu ne reproduit pas le téléphone (il signale le début de la voix dès qu'une phrase est reçue) : il mesure le serveur. Le temps indiqué est celui entre la fin de phrase détectée et la première chose dite (il faut ajouter 0,7 s de silence de fin de phrase et le démarrage de la voix du téléphone, ~0,3 s).

| | Test de Noah (étape 7) | Rejeu avant (étape 7) | Rejeu après (étape 8) |
|---|---|---|---|
| Fin de phrase → première chose dite, médiane | 2,68 s | 2,57 s | 0,89 s |
| Fin de phrase → première chose dite, 90 % des phrases | 4,5 s | 3,87 s | 1,41 s |
| Fin de phrase → première chose dite, pire cas | 4,91 s | 3,9 s | 3,51 s |
| Début de la voix, médiane (rejeu : voix simulée dès réception) | 3,13 s | 2,57 s | 0,89 s |
| Phrase bloquée dans la file, pire cas | 8,146 s | 8,179 s | 0,0 s |
| Seconds avis de Whisper (2 à 3 s chacun) | 7 | 7 | 0 |
| Phrases de réponse abandonnées | 30 | 28 | 10 |
| Réponses redites après un bruit | — | — | 0 |
| Remplissage à la fin | Séjour 74 %, Cuisine 41 % | Séjour 71 %, Cuisine 41 % | Séjour 68 %, Couloir 0 %, Cuisine 50 % |
| Informations manquantes à la fin | 18 | 18 | 23 |

Le remplissage et les manques ne se comparent pas directement : les réponses rejouées sont celles du test, qui ne répondent plus aux nouvelles questions ; et « après là il y a un couloir » ouvre maintenant une pièce « Couloir » (au lieu d'un faux « mur côté couloir »), dont le plafond et le plancher comptent comme manques.

Ce qui a changé (étape 8) :

- la voix n'est coupée que par une parole confirmée (0,35 s, 0,6 s quand l'assistant parle) : plus par un claquement ;
- une réponse coupée par un bruit (transcrit vide) est redite ;
- « . » n'est plus envoyé ni à Whisper ni à Claude ; plus de second avis de Whisper en conversation ;
- « Noté. » dit tout de suite quand les règles ont noté quelque chose (la contradiction relevée, s'il y en a une) ;
  sinon « Alors… » si rien n'est dit 1,4 s après la fin de phrase ; Claude enchaîne sans redire « noté » ;
- une phrase inachevée ne bloque plus le pré-remplissage : Claude seul attend la suite (2,5 s au plus) ;
- Claude : une image par phrase et un processus renouvelé toutes les 12 phrases (au lieu de 30) : moins à relire,
  réponse plus rapide ;
- consignes : ne parler que du DPE (jamais de décoration), ignorer les débris, ranger chaque information sur
  l'élément en cours, ne jamais redemander ce qui a été dit, noter l'interprétation probable (« à vérifier ») ;
- règles : élément en cours, « tous les murs de la maison », « là c'est la cuisine », « après il y a un couloir »,
  « ce mur, ce mur et ce mur » (un mur par désignation, avec l'image et la boussole de son instant), mots collés ;
- pièce reconnue sur les images : « On est dans la cuisine ? », puis changement sur « oui ».

### Rejeu avant (étape 7 ; visite `20261022-121817-060bff`)

- **Noah** (5 s) : « . »
- **Noah** (9 s) : « C un mur? »
  - **Assistant** : « Oui, je vois une fenêtre avec des rideaux blancs et un mur à côté. Décrivez le premier mur, celui que vous voulez noter en premier. » — 2,1 s
- **Noah** (28 s) : « Mais derrière un rideau, il y a toujours un un mur, fallay Sii- sii, je te mont comme ça, c'est qu'un mur. »
  - **Assistant** : « D'accord, il y a bien un mur derrière le rideau, je le note. Ce mur derrière le rideau, il est en quoi ? » — 3,08 s
- **Noah** (45 s) : « Là déjà vo plus, mais il y a aussi une fenêtre ici, une fenêtre ici, une fenêtre aussi là- bas. »
- **Noah** (60 s) : « Donc, en fait, il y a dans le même mur, il y a trois fenêtres ces trois ces trois fenêtres y sont en PVC on quai PVC les murs y font le mur déjà de longueur fait »
  - *(bip « noté » : 8,448 s)*
- **Noah** (68 s) : « mètres d'épaisseur le mur fait trois centimètres de vingt centimètres et l'isolant, est du »
  - *(bip « noté » : 8,419 s)*
- **Noah** (78 s) : « L'isolence est due la laine de verre trente centimètres voilà il y a également deux radiateurs ici. »
  - *(bip « noté » : 0,177 s)*
  - **Assistant** : « Noté, laine de verre de trente centimètres, et deux radiateurs ici. Ce mur donne sur quoi ? » — 3,4 s
- **Noah** (89 s) : « Il donne sur la rue? »
  - *(bip « noté » : 0,115 s)*
- **Noah** (90 s) : « Extérieur? »
  - **Assistant** : « Oui, extérieur, c'est noté. Ce mur, il est en quoi ? » — 3,21 s
- **Noah** (101 s) : « En brique? »
  - *(bip « noté » : 0,057 s)*
- **Noah** (112 s) : « Il est en brique. »
  - **Assistant** : « Oui, brique, c'est bien noté. Et pour l'épaisseur, vingt centimètres, c'est bien ça ? » — 1,27 s
- **Noah** (126 s) : « Je Djadi au préalable, trente centimètres d'épaisseur de laine de verre et le mur fait quinze centimètres. »
  - *(bip « noté » : 0,517 s)*
- **Noah** (135 s) : « Qu'i faut quoi doute? »
  - **Assistant** : « Il me manque encore le plafond, le plancher et le vitrage des trois fenêtres. Un autre mur dans cette pièce ? » — 2,14 s
- **Noah** (143 s) : « Bg sûr qu'il y a cemur, cemur et cemur. »
  - **Assistant** : « D'accord, je note deux autres murs, celui avec le tableau et celui avec le miroir. Le mur avec le tableau, il donne sur quoi ? » — 2,86 s
- **Noah** (154 s) : « Le mur du tableau donne derrière sur les toilettes, d'ox de l'intérieur. »
  - *(bip « noté » : 0,091 s)*
  - **Assistant** : « Ce mur donne donc sur les toilettes, à l'intérieur. Ce mur du tableau, il est en quoi ? » — 1,71 s
- **Noah** (166 s) : « Ici. »
  - **Assistant** : « J'ai compris, vous désignez le mur avec le miroir. Ce mur donne sur quoi ? » — 3,9 s
- **Noah** (179 s) : « Sur une haute maison derrière. »
  - *(bip « noté » : 0,271 s)*
- **Noah** (180 s) : « Mais c'est pas la mienne. »
  - **Assistant** : « D'accord, ce n'est pas le vôtre, donc c'est bien un voisin, je garde ça. Un autre mur dans cette pièce ? » — 1,1 s
- **Noah** (186 s) : « . »
- **Noah** (188 s) : « Alors tu parles pas? »
  - **Assistant** : « Si, je vous entends, je suis là. Y a-t-il un autre mur dans cette pièce ? » — 2,62 s
- **Noah** (201 s) : « Il est en brique. »
  - *(bip « noté » : 0,09 s)*
- **Noah** (202 s) : « . »
- **Noah** (207 s) : « Tous les murs de la maison sont en briques. »
  - *(bip « noté » : 0,156 s)*
- **Noah** (211 s) : « Pour rien. »
- **Noah** (220 s) : « Il te veut quoi d'ôte? »
- **Noah** (226 s) : « Oui. »
  - **Assistant** : « D'accord, il y a un autre mur. Lequel, celui avec la lampe et le petit meuble, ou un autre ? » — 2,39 s
- **Noah** (231 s) : « Mais tu parles plus à l'orel? »
  - **Assistant** : « Si, je vous parle toujours, je vous entends bien. Le mur en question, c'est celui avec la lampe et le petit meuble, ou un autre ? » — 1,53 s
- **Noah** (237 s) : « Qu. »
- **Noah** (240 s) : « Sur le voisin. »
  - *(bip « noté » : 0,54 s)*
  - **Assistant** : « D'accord, sur le voisin. Est-ce le mur avec le miroir, ou le mur avec la lampe ? » — 2,58 s
- **Noah** (249 s) : « Est- cequ'on a fait ce mot au ce mur, je me rappelle plus. »
  - **Assistant** : « Vous avez trois murs notés : le mur derrière le rideau, donnant sur l'extérieur, le mur du tableau, donnant sur les toilettes, et le mur du miroir, donnant sur le voisin. Il reste le plafond et le plancher. Au-dessus du plafond, il y a quoi : des combles, une terrasse ou un logement ? » — 1,86 s
- **Noah** (258 s) : « Sur un autre voisin. »
  - **Assistant** : « Un autre voisin, c'est pour le mur avec la lampe, ou pour le plafond, avec un logement au-dessus ? » — 2,57 s
- **Noah** (268 s) : « Nant alors dans ce- jour si' fini, après là il y a un couloir. »
- **Noah** (272 s) : « S'il y a un couloir? »
  - **Assistant** : « Oui, je vois bien un couloir avec un escalier, derrière. Au-dessus du plafond : combles, terrasse ou logement ? » — 1,85 s
- **Noah** (285 s) : « Mais non, mais là, on a changé de pièce, là. »
- **Noah** (297 s) : « a ya. un morici. un mici un novicie. »
- **Noah** (302 s) : « Ce premier mur- là »
- **Noah** (305 s) : « Voilà qui ce que je te dis qui donne sur l'extérieur? »
  - *(bip « noté » : 0,241 s)*
- **Noah** (317 s) : « Il y fait trente centimètres de lar,'il est en brique avec des isolants laine de verre La laine de verre fait vingt centimètres il y a aussi une fenêtre, cette fenêtre en bois »
  - *(bip « noté » : 0,187 s)*
  - **Assistant** : « Noté, mur en brique, 30 cm, avec 20 cm de laine de verre, et la fenêtre en bois est déjà notée. Et le plafond de la cuisine, il donne sur quoi ? » — 3,87 s
- **Noah** (336 s) : « P à la cuisine c'est un plafond basique ainsi exactement tout même que le salon d'ailleurs, tu m'as peu posé la question pour le salon. »
  - **Assistant** : « D'accord, le plafond de la cuisine est copié sur celui du séjour. Ce mur, quelle épaisseur ? » — 3,83 s
  - **Assistant** : « Avant d'arrêter, il manque 18 informations. Cuisine, le mur 4 : épaisseur ; Cuisine, le plafond : donne sur ; Cuisine, le plancher : donne sur ; et 15 autres, à l'écran. »

### Rejeu après (étape 8 ; visite `20261022-125841-1a0cff`)

- **Noah** (9 s) : « C un mur? »
  - **Assistant** : « Je ne vois qu'une fenêtre avec des rideaux, pas encore de mur bien cadré. Décrivez le premier mur. » — 0,78 s
- **Noah** (28 s) : « Mais derrière un rideau, il y a toujours un un mur, fallay Sii- sii, je te mont comme ça, c'est qu'un mur. »
  - **Assistant** : « D'accord, il y a bien un mur derrière le rideau. Je le note. Décrivez-le maintenant : il donne sur quoi, il est en quoi ? » — 0,96 s
- **Noah** (45 s) : « Là déjà vo plus, mais il y a aussi une fenêtre ici, une fenêtre ici, une fenêtre aussi là- bas. »
- **Noah** (60 s) : « Donc, en fait, il y a dans le même mur, il y a trois fenêtres ces trois ces trois fenêtres y sont en PVC on quai PVC les murs y font le mur déjà de longueur fait »
  - **Assistant** : « Noté. Les trois fenêtres sont bien sur le même mur, en PVC. Le mur derrière le rideau donne sur quoi ? » — 0,25 s
- **Noah** (68 s) : « mètres d'épaisseur le mur fait trois centimètres de vingt centimètres et l'isolant, est du »
  - **Assistant** : « C'est noté. J'ai compris 30 cm d'épaisseur pour ce mur, c'est bien ça ? » — 0,62 s
- **Noah** (76 s) : « L'isolence est due la laine de verre trente centimètres. »
  - **Assistant** : « D'accord, noté. » — 0,09 s
- **Noah** (78 s) : « Voilà il y a également deux radiateurs ici. »
  - **Assistant** : « Noté. Deux radiateurs à eau. Le mur derrière le rideau est en quoi ? » — 0,11 s
- **Noah** (89 s) : « Il donne sur la rue? »
  - **Assistant** : « C'est noté. Oui, il donne sur l'extérieur. Le mur derrière le rideau est en quoi ? » — 0,14 s
- **Noah** (90 s) : « Extérieur. »
  - **Assistant** : « D'accord, noté. Au-dessus du plafond : combles, terrasse ou logement ? » — 0,04 s
- **Noah** (101 s) : « En brique? »
  - **Assistant** : « Le mur est en brique, c'est noté. Au-dessus du plafond : combles, terrasse ou logement ? » — 1,07 s
- **Noah** (112 s) : « Il est en brique. »
  - **Assistant** : « Noté. Y a-t-il un autre mur dans cette pièce ? » — 0,07 s
- **Noah** (126 s) : « Je Djadi au préalable, trente centimètres d'épaisseur de laine de verre et le mur fait quinze centimètres. »
  - **Assistant** : « C'est noté. Laine de verre 30 centimètres. Ce mur donne sur quoi ? » — 0,2 s
- **Noah** (135 s) : « Qu'i faut quoi doute? »
  - **Assistant** : « Alors… Il me faut pour ce mur, celui affiché à l'écran, ce qu'il y a de l'autre côté, puis son matériau. Ce mur donne sur quoi ? » — 1,4 s
- **Noah** (143 s) : « Bra sur y a semur, semurure et semure. »
  - **Assistant** : « Voyons… Ce mur donne sur quoi ? » — 1,41 s
- **Noah** (154 s) : « Le mur du tableau donne derrière sur les toilettes, d'ox de l'intérieur. »
  - **Assistant** : « D'accord, noté. Ce mur donne sur les toilettes, à l'intérieur. Un autre mur dans cette pièce ? » — 0,14 s
- **Noah** (166 s) : « Ici. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 1,55 s
- **Noah** (179 s) : « Sur une haute maison derrière. »
  - **Assistant** : « Noté. » — 0,15 s
- **Noah** (180 s) : « Mais c'est pas la mienne. »
  - **Assistant** : « Alors… Oui, c'est le logement voisin, je le garde comme tel. Un autre mur dans cette pièce ? » — 1,41 s
- **Noah** (188 s) : « Alors tu parles pas? »
  - **Assistant** : « Si, je vous écoute, je suis là. Un autre mur dans cette pièce ? » — 1,34 s
- **Noah** (201 s) : « Il est en brique. »
  - **Assistant** : « C'est noté. Brique. Ce mur donne sur quoi ? » — 0,09 s
- **Noah** (207 s) : « Tous les murs de la maison sont en briques. »
  - **Assistant** : « Voyons… Noté, tous les murs en brique. Ce mur donne sur quoi ? » — 1,4 s
- **Noah** (211 s) : « Pour rien. »
  - **Assistant** : « Ce mur donne sur quoi ? » — 1,17 s
- **Noah** (220 s) : « il te faut quoi d'autre? »
  - **Assistant** : « Il me faut encore pour le mur affiché : sur quoi il donne, son épaisseur et son isolation. Ce mur donne sur quoi ? » — 0,89 s
- **Noah** (226 s) : « Oui. »
  - **Assistant** : « Ce mur donne sur quoi ? » — 0,82 s
- **Noah** (231 s) : « Mais tu parles plus à l'orel? »
  - **Assistant** : « Si, je vous entends. Je reste à l'écoute. Ce mur donne sur quoi ? » — 1,0 s
- **Noah** (237 s) : « Qu. »
- **Noah** (240 s) : « Sur le voisin. »
  - **Assistant** : « D'accord, noté. Un autre mur dans cette pièce ? » — 0,09 s
- **Noah** (249 s) : « Est- cequ'on a fait ce mot au ce mur, je me rappelle plus. »
  - **Assistant** : « Vous demandez si on a fait le tour des murs du séjour ? » — 0,9 s
- **Noah** (258 s) : « Sur un autre voisin. »
  - **Assistant** : « Noté. Un autre mur dans cette pièce ? » — 0,11 s
- **Noah** (268 s) : « Nant alors dans ce- jour si' fini, après là il y a un couloir. »
  - **Assistant** : « Alors… D'accord, on passe au couloir. Quel est le premier mur ici ? » — 1,4 s
- **Noah** (272 s) : « S'il y a un couloir? »
  - **Assistant** : « Voyons… Oui, c'est bien le couloir. Le premier mur, celui de gauche le long de l'escalier, il est à décrire ? » — 1,4 s
- **Noah** (285 s) : « Mais non, mais là, on a changé de pièce, là. »
  - **Assistant** : « Alors… On est dans la cuisine. Quel est le premier mur ici ? » — 1,41 s
- **Noah** (297 s) : « a ya. un morici. un mici un novicie. »
  - **Assistant** : « Voyons… » — 1,41 s
- **Noah** (302 s) : « Ce premier mur- là »
  - **Assistant** : « D'accord, ce mur. Il donne sur quoi ? » — 3,51 s
- **Noah** (305 s) : « Voilà qui ce que je te dis qui donne sur l'extérieur? »
  - **Assistant** : « C'est noté. » — 0,33 s
- **Noah** (317 s) : « Il y fait trente centimètres de lar,'il est en brique avec des isolants laine de verre La laine de verre fait vingt centimètres il y a aussi une fenêtre, cette fenêtre en bois »
  - **Assistant** : « D'accord, noté. D'accord, la laine de verre fait 20 cm, et cette fenêtre en bois est la seule. Un autre mur dans cette pièce ? » — 0,38 s
- **Noah** (336 s) : « P à la cuisine c'est un plafond basique ainsi exactement tout même que le salon d'ailleurs, tu m'as peu posé la question pour le salon. »
  - **Assistant** : « Alors… D'accord, le plafond de la cuisine est comme celui du séjour. Vous avez raison, je n'ai pas posé la question pour le séjour. Un autre mur dans cette pièce ? » — 1,4 s
  - **Assistant** : « Avant d'arrêter, il manque 23 informations. Cuisine, le plafond : donne sur ; Cuisine, le plafond : isolation ; Cuisine, le plancher : donne sur ; et 20 autres, à l'écran. »
