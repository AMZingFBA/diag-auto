# Étape 9 : ne pas répéter, jamais de faux doublon (22/10/2026)

Visite : `sessions/20261022-120410-53ecb1` (test de Noah après l'étape 7), rejouée avec la version de l'étape 8 (avant) puis de l'étape 9 (après), son et images au rythme réel :

```
python -m assistant.rejouer sessions\20261022-120410-53ecb1 --piece Séjour
```

## Ce qui s'était passé

- **154-157 s** : Noah dit « le mur du tableau donne derrière sur les toilettes ». Les règles rangent cette phrase sur le mur du miroir (le dernier décrit) ; Claude voit alors deux murs « du tableau » et dit « c'était déjà noté, je retire mon doublon » : il supprime le vrai mur du tableau.
- **268-273 s** : « après là il y a un couloir » crée un faux « mur côté couloir », puis « s'il y a un couloir ? » un second ; Claude dit « c'est le mur côté couloir déjà noté, je retire le doublon » : faux, ce mur n'avait jamais été décrit.
- Au rejeu de l'étape 8, Claude supprimait encore de lui-même une fenêtre de la cuisine (« cette fenêtre en bois est la seule »), créée en double par les règles (« il y a aussi une fenêtre, cette fenêtre en bois »).
- Et l'assistant reprenait ce que Noah venait de dire : « Noté. » puis « Laine de verre 30 centimètres. », « Oui, brique, c'est noté. ».

## Avant / après

| | Test de Noah (étape 7) | Rejeu avant (étape 8) | Rejeu après (étape 9) |
|---|---|---|---|
| Éléments supprimés par l'assistant de lui-même | 2 (annuler M2, annuler M7) | 5 (annuler F3, annuler F2, annuler F1, annuler M6, annuler F5) | 0 |
| « Déjà noté » / « doublon » dit sans preuve | 3 | 1 | 0 |
| Suppressions demandées par Claude et refusées | — | — | 0 |
| « C'est le même mur que… ? » demandé (doute : rien supprimé sans « oui ») | — | — | 1 |
| Fenêtres à la fin (vraies : 3 au séjour, 1 à la cuisine) | Séjour 3, Cuisine 2 | Séjour 3, Cuisine 1 | Séjour 3, Cuisine 1 |
| Mots de sa phrase repris par réponse (descriptions) | 1,25 | 0,59 | 0,15 |
| Réponses qui reprennent au moins un mot | 10 / 16 | 14 / 32 | 3 / 27 |

Mots repris : mots porteurs de sens (pas les articles, ni le nom de l'élément, que la question suivante doit pouvoir dire) de la phrase de Noah qui reviennent dans la réponse de l'assistant à une description (`assistant/repetition.py`). Les réponses à une question posée à l'assistant ne sont pas comptées : y répondre reprend forcément ses mots.

Murs à la fin — test : Séjour : M1 « le mur ouest, celui avec la fenêtre et les rideaux blancs », M3 « le mur nord, celui avec le tableau », M4 « le mur est, celui du miroir et du canapé », M5 « le mur nord, celui avec la télé », M6 « le mur côté couloir » ; Cuisine : M8 « le mur est, celui de la fenêtre au-dessus de l'évier ».

Murs à la fin — avant : Séjour : M1 « le mur extérieur », M2 « le mur affiché », M3 « le mur avec le tableau », M4 « le mur avec les chaises », M5 « le mur avec le miroir » ; Cuisine : M7 « le mur avec le grille-pain ».

Murs à la fin — après : Séjour : M1 « le mur derrière le rideau, face à la fenêtre », M2 « le mur affiché », M3 « le mur avec le tableau », M4 « le mur avec les chaises noires », M5 « le mur avec le grand miroir et le canapé », M6 « le mur avec la télé » ; Cuisine : M7 « le mur avec les placards et le four ».

## Les deux passages, avant et après

### 140 à 175 s

Test de Noah :

- **Noah** (143 s) : « Bra sur qu'il y a cemur, cemur et cemur. »
  - **Assistant** : « Je note le mur du tableau et celui du miroir. Le mur du tableau donne sur quoi ? »
- **Noah** (154 s) : « Le mur du tableau y donne derrière sur les toilettes, d'ox de l'intérieur. »
  - **Assistant** : « D'accord, le mur du tableau donne sur les toilettes, c'était déjà noté, je retire mon doublon. Un autre mur dans cette pièce ? »
- **Noah** (166 s) : « Ici. »
- **Noah** (168 s) : « EC. »
  - **Assistant** : « Je note le mur du miroir, celui du canapé. Il donne sur quoi ? »

Rejeu avant (`20261022-131251-9b72b0`) :

- **Noah** (143 s) : « Bra sur y a ce mur, ce mur et ce mur. »
  - **Assistant** : « Alors… Trois murs de plus, je les ai notés. Ce mur avec le miroir, il donne sur quoi ? »
- **Noah** (154 s) : « Le mur du tableau donne derrière sur les toilettes, d'ox de l'intérieur. »
  - **Assistant** : « D'accord, noté. Le mur du tableau donne sur les WC, je corrige. Le mur avec le miroir, il donne sur quoi ? »
- **Noah** (166 s) : « Ici. »
  - **Assistant** : « Le mur avec le miroir, il donne sur quoi ? »

Rejeu après (`20261022-135155-bf593d`) :

- **Noah** (143 s) : « Bra sur y a ce mur, ce mur et ce mur. »
  - **Assistant** : « Et le mur avec le grand miroir, il donne sur quoi ? »
- **Noah** (154 s) : « Le mur du tableau donne derrière sur les toilettes, d'ox de l'intérieur. »
  - **Assistant** : « Le mur avec le grand miroir et le canapé donne sur quoi ? »
- **Noah** (166 s) : « Ici. »
  - **Assistant** : « Le mur avec le grand miroir et le canapé donne sur quoi ? »

### 260 à 290 s

Test de Noah :

- **Noah** (269 s) : « Onant alors dans ce jour si fini après là, il y a un couloir. »
- **Noah** (272 s) : « S'il y a un couloir? »
  - **Assistant** : « Oui, il y a un couloir, c'est le mur côté couloir déjà noté, je retire le doublon. Un autre mur dans cette pièce ? »
- **Noah** (285 s) : « Mais non est là, on a changé de pièce là. »
  - **Assistant** : « D'accord, on passe dans la cuisine. Décrivez le premier mur. »

Rejeu avant :

- **Noah** (269 s) : « Nant alors dans ce- jour si' fini, après là il y a un couloir. »
  - **Assistant** : « Alors… »
- **Noah** (272 s) : « S'il y a un couloir? »
  - **Assistant** : « Voyons… Oui, on est bien dans le couloir. Décrivez le premier mur. »
- **Noah** (285 s) : « Mais non, mais là, on a changé de pièce, là. »
  - **Assistant** : « Alors… On est dans la cuisine. Décrivez le premier mur. »

Rejeu après :

- **Noah** (269 s) : « Nant alors dans ce- jour si' fini, après là il y a un couloir. »
- **Noah** (272 s) : « S'il y a un couloir? »
  - **Assistant** : « Oui, vous êtes dans le couloir, avec l'escalier. Au-dessus du plafond du couloir, il y a quoi ? »
- **Noah** (285 s) : « Mais non, mais là, on a changé de pièce, là. »
  - **Assistant** : « Voyons… On est dans la cuisine. Décrivez le premier mur. »

## Rejeu après, en entier

- **Noah** (9 s) : « C un mur? »
  - **Assistant** : « Oui, je vois la fenêtre et des rideaux. Décrivez le premier mur, celui qui est face à la fenêtre ou à votre gauche. »
- **Noah** (28 s) : « Mais derrière un rideau, il y a toujours un un mur, fallay Sii- sii, je te mont comme ça, c'est qu'un mur. »
  - **Assistant** : « Il est en quoi, et il donne sur quoi ? »
- **Noah** (45 s) : « Là déjà vo plus, mais il y a aussi une fenêtre ici, une fenêtre ici, une fenêtre aussi là- bas. »
- **Noah** (60 s) : « Donc, en fait, il y a dans le même mur, il y a trois fenêtres ces trois ces trois fenêtres y sont en PVC on quai PVC les murs y font le mur déjà de longueur fait »
  - **Assistant** : « Ce mur donne sur quoi ? »
- **Noah** (69 s) : « mètres d'épaisseur le mur fait trois centimètres de vingt centimètres et l'isolant, est du »
  - **Assistant** : « Le mur ferait 30 cm d'épaisseur, c'est bien ça ? »
- **Noah** (76 s) : « L'isolence est due la laine de verre trente centimètres. »
- **Noah** (78 s) : « Voilà il y a également deux radiateurs ici. »
  - **Assistant** : « Il est en quoi, ce mur ? »
- **Noah** (89 s) : « Il donne sur la rue? »
- **Noah** (91 s) : « Extérieur? »
  - **Assistant** : « Le mur, il est en quoi ? »
- **Noah** (101 s) : « En brique? »
  - **Assistant** : « Y a-t-il un autre mur dans ce séjour ? »
- **Noah** (112 s) : « Il est en brique. »
  - **Assistant** : « C'est le même mur que le mur derrière le rideau, face à la fenêtre ? »
- **Noah** (126 s) : « Je Djadi au préalable trente centimètres d'épaisseur de laine de verre et le mur fait quinze centimètres. »
  - **Assistant** : « Et le mur affiché, il donne sur quoi ? »
- **Noah** (135 s) : « Qu'i faut quoi doute? »
  - **Assistant** : « Il me faut ce que donne le mur affiché, puis le plafond et le plancher. Ce mur donne sur quoi ? »
- **Noah** (143 s) : « Bra sur y a ce mur, ce mur et ce mur. »
  - **Assistant** : « Et le mur avec le grand miroir, il donne sur quoi ? »
- **Noah** (154 s) : « Le mur du tableau donne derrière sur les toilettes, d'ox de l'intérieur. »
  - **Assistant** : « Le mur avec le grand miroir et le canapé donne sur quoi ? »
- **Noah** (166 s) : « Ici. »
  - **Assistant** : « Le mur avec le grand miroir et le canapé donne sur quoi ? »
- **Noah** (179 s) : « Sur une haute maison derrière. »
- **Noah** (181 s) : « Mais c'est pas la mienne. »
  - **Assistant** : « D'accord, c'est chez le voisin. Le mur avec les chaises noires donne sur quoi ? »
- **Noah** (188 s) : « Alors tu parles pas? »
  - **Assistant** : « Si, je vous écoute. Le mur avec les chaises noires donne sur quoi ? »
- **Noah** (201 s) : « Il est en brique. »
- **Noah** (207 s) : « Tous les murs de la maison sont en briques. »
  - **Assistant** : « Le mur avec les chaises noires donne sur quoi ? »
- **Noah** (220 s) : « il te faut quoi d'autre? »
  - **Assistant** : « Pour le mur avec les chaises noires, il me manque sur quoi il donne, son épaisseur et son isolation. Il donne sur quoi ? »
- **Noah** (226 s) : « Oui. »
  - **Assistant** : « Le mur avec les chaises noires donne sur quoi ? »
- **Noah** (231 s) : « Mais tu parles plus à l'orel? »
  - **Assistant** : « Si, je vous entends bien. Le mur avec les chaises noires donne sur quoi ? »
- **Noah** (237 s) : « Qu. »
  - **Assistant** : « Le mur avec les chaises noires donne sur quoi ? »
- **Noah** (240 s) : « Sur le voisin. »
  - **Assistant** : « Au-dessus du plafond, il y a quoi : des combles, une terrasse ou un autre logement ? »
- **Noah** (249 s) : « Est- cequ'on a fait ce mot au ce mur, je me rappelle plus. »
  - **Assistant** : « Alors… Le mur avec la télé n'est pas encore dans mes notes, je l'ajoute. Au-dessus du plafond, il y a quoi : des combles, une terrasse ou un autre logement ? »
- **Noah** (258 s) : « Sur un autre voisin. »
  - **Assistant** : « Le plafond est isolé ? »
- **Noah** (269 s) : « Nant alors dans ce- jour si' fini, après là il y a un couloir. »
- **Noah** (272 s) : « S'il y a un couloir? »
  - **Assistant** : « Oui, vous êtes dans le couloir, avec l'escalier. Au-dessus du plafond du couloir, il y a quoi ? »
- **Noah** (285 s) : « Mais non, mais là, on a changé de pièce, là. »
  - **Assistant** : « Voyons… On est dans la cuisine. Décrivez le premier mur. »
- **Noah** (297 s) : « a ya. un mur ici. un mici un novicie. »
  - **Assistant** : « Alors… »
- **Noah** (302 s) : « Ce premier mur- là »
- **Noah** (306 s) : « Voilà qui ce que je te dis qui donne sur l'extérieur? »
  - **Assistant** : « Ce mur, quelle épaisseur ? »
- **Noah** (309 s) : « Il fait trente centimètres de lar, j'ilai en brique? »
- **Noah** (318 s) : « Avec des isolants laine de verre la laine de verre fait vingt centimètre, il y a aussi une fenêtre, cette fenêtre en bois. »
  - **Assistant** : « Un autre mur dans cette pièce ? »
- **Noah** (336 s) : « P à la cuisine c'est un plafond basique ainsi exactement tout même que le salon d'ailleurs, tu m'as peu posé la question pour le salon. »
  - **Assistant** : « Voyons… D'accord, je reprends le plafond du séjour pour la cuisine. Un autre mur dans cette pièce ? »
