# Test réel de Noah du 22/10/2026, rejoué avant et après l'étape 5

Visite d'origine : `sessions/20261022-083308-20ef54` (iPhone, séjour, 2 min 29). Retour de Noah : « trop lent, ne s'adapte pas, je dois répéter, je ne sais pas c'est quel mur 3 / mur 4 ».

Le son de la visite (`audio.wav`) et ses images ont été rejoués au rythme réel dans le serveur, avec Claude Code et la transcription sur ce PC (sans carte graphique) :

```
python -m assistant.rejouer sessions\20261022-083308-20ef54 --piece Séjour
```

Les réponses de Noah sont celles du test d'origine : quand les questions changent, certains échanges ne se répondent plus, ce qui est normal pour un rejeu. Le temps indiqué après chaque question est celui entre la fin de phrase détectée et la question prête (il faut y ajouter 0,7 s de silence de fin de phrase). Claude n'interprète pas toujours de la même façon les phrases incompréhensibles : deux rejeux peuvent différer un peu. Quand une phrase passe par le second avis de Whisper, la réponse arrive après la phrase suivante dans la sortie du rejeu.

## Temps de réponse

| | Test d'origine | Rejeu avant (étape 4) | Rejeu après (étape 5) |
|---|---|---|---|
| Transcription, médiane | 2,45 s | 2,26 s | 0,07 s |
| Transcription, 90 % des phrases | 6,18 s | 3,54 s | 0,22 s |
| Fin de phrase → question prête, médiane | 3,15 s | 3,12 s | 0,14 s |
| Fin de phrase → question prête, 90 % des phrases | 7,13 s | 5,51 s | 0,94 s |
| Fin de phrase → question prête, pire cas | 7,63 s | 6,07 s | 3,23 s |

## Test d'origine (version du matin)

- **Noah** (23 s) : « Ce premier mur donne sur l'extérieur 30 mètres. Il y a 3 fenêtres dessus, c'est du bois. »
  - **Assistant** : « Le mur 1 est en quoi ? » — 3,15 s
- **Noah** (27 s) : « Laine de verre de 30 cm. »
  - **Assistant** : « Quelle épaisseur ? » — 2,23 s
- **Noah** (30 s) : « Et le mur y en brique. »
  - **Assistant** : « Au-dessus du plafond : combles, terrasse ou logement ? » — 2,06 s
- **Noah** (32 s) : « 30 cm. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 4,15 s
- **Noah** (38 s) : « Au-dessus du plafond, il y a des combles bleus. »
  - **Assistant** : « Le plafond est isolé ? » — 2,48 s
- **Noah** (42 s) : « Oui, à ce mur en face, le avec l'aise. »
- **Noah** (45 s) : « Le plafond isolé dans le plafonds DPE isolé. »
- **Noah** (49 s) : « Le plafond est pas isolé. »
- **Noah** (58 s) : « Le plafond n'est pas isolé. »
- **Noah** (62 s) : « Il te faut quoi d'être comme information sur ce mur ? »
  - **Assistant** : « Le plancher donne sur quoi ? » — 5,2 s
- **Noah** (72 s) : « Un sous-sol. »
- **Noah** (75 s) : « Tout faire plus beau. »
- **Noah** (94 s) : « Et là, le mur que je suis en train de te montrer, il donne sur une autre maison derrière. Donc celui-là, c'est un mur qui donne vers un voisin. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 6,9 s
- **Noah** (102 s) : « C'est un autre mur qui donne derrière sur des toilettes. »
  - **Assistant** : « Ce mur 3, il est en quoi ? » — 7,63 s
- **Noah** (109 s) : « En fait, ce mur, cette pièce fait à 4 murs toute la pièce. »
  - **Assistant** : « Et le quatrième mur, il donne sur quoi ? » — 7,14 s
- **Noah** (115 s) : « Quel mur. »
  - **Assistant** : « Le mur restant, il donne sur quoi ? » — 4,67 s
- **Noah** (129 s) : « Il y a juste un mur dans la pièce qui donne sur l'extérieur. Le reste ne donne que sur l'd'intérieur, de la maison ou ses noms en voisins. »
  - **Assistant** : « Le mur 4 est en quoi ? » — 6,18 s

## Rejeu avant l'étape 5 (version de l'étape 4, visite `20261022-100015-fd1f22`)

- **Noah** (23 s) : « Alors, ça c'est le premier mur. Ce premier mur, il donne, sur l'extérieur, il fait 30 mètres. Il y a trois fenêtres dessus. C'est du bois. »
  - **Assistant** : « Le mur 1 est en quoi ? » — 3,92 s
- **Noah** (27 s) : « Laine de verre de 30 cm. »
  - **Assistant** : « J'ai compris pierre, c'est bien ça ? » — 2,16 s
- **Noah** (30 s) : « Et le mur y embrique. »
- **Noah** (32 s) : « 30 cm. »
  - **Assistant** : « Il fait quelle épaisseur ? » — 5,23 s
  - **Assistant** : « Un autre mur dans cette pièce ? » — 3,12 s
- **Noah** (38 s) : « Au-dessus du plafond, des combles bleus. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 2,85 s
- **Noah** (42 s) : « Oui, à ce but, enfin, celui avec l'aise. »
  - **Assistant** : « Le mur 2 donne sur quoi ? » — 2,62 s
- **Noah** (45 s) : « Le plafond isolé dans le plafonds des pays isolés. »
  - **Assistant** : « Le mur 2 donne sur quoi ? » — 2,43 s
- **Noah** (49 s) : « Le plafond des pays isolés. »
  - **Assistant** : « Il est en quoi ? » — 2,09 s
- **Noah** (58 s) : « Le plafond n'est pas isolé. »
  - **Assistant** : « Noté : non isolé au lieu de isolé. Il est en quoi ? » — 2,21 s
- **Noah** (62 s) : « Il te faut quoi d'être comme information sur ce mur ? »
  - **Assistant** : « Quelle épaisseur ? » — 2,35 s
- **Noah** (72 s) : « Un sous-sol. »
  - **Assistant** : « Quelle épaisseur ? » — 1,94 s
- **Noah** (74 s) : « Tout faire plus beau. »
  - **Assistant** : « Le mur 2, il est isolé ? » — 3,77 s
- **Noah** (94 s) : « Et là, le mur que je suis en train de te montrer, il donne deux teux maisons derrière. Donc celui-là, c'est un mur qui donne vers un voisin. Simplement. Voilà. »
  - **Assistant** : « Noté : local chauffé (voisin) au lieu de local non chauffé : cave. Un autre mur dans cette pièce ? » — 3,67 s
- **Noah** (102 s) : « Le mur sur les toilettes, la sur le chambre. »
  - **Assistant** : « Ce mur donne sur quoi ? » — 5,51 s
- **Noah** (110 s) : « Ce mur, cette pièce fait à quatre murs toute la pièce. »
  - **Assistant** : « Quatre murs en tout, c'est ça ? » — 6,07 s
- **Noah** (115 s) : « Quel mur. »
  - **Assistant** : « Le plancher donne sur quoi ? » — 4,57 s
- **Noah** (129 s) : « Il y a juste un mur dans la pièce qui donne sur l'extérieur. Le reste ne donne que sur l'd'intérieur de la maison ou sinon en voisin. »
  - **Assistant** : « Le mur avec le miroir est en quoi ? » — 3,43 s

## Rejeu après l'étape 5 (visite `20261022-104307-fb28c0`)

- **Noah** (5 s) : « er. »
- **Noah** (23 s) : « Alors c'est le premier mur Ce premier mur y donne sur l'extérieur y fait trente trente mètres il y a trois fenêtres dessus c'est du bois »
  - **Assistant** : « Ce mur est en quoi ? » — 0,46 s
- **Noah** (27 s) : « c'est une laine de verre de trente centimètres et l'. »
  - **Assistant** : « Il est en quoi ? » — 0,08 s
- **Noah** (30 s) : « Et le mur est en brique. »
  - **Assistant** : « Quelle épaisseur ? » — 0,11 s
- **Noah** (32 s) : « Trente centimètres. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 0,06 s
- **Noah** (38 s) : « Au- dessus du plafond, il y a des combles, exactement. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 0,09 s
- **Noah** (42 s) : « E Wai a se b en face avec l. »
  - *(pas comprise ; second avis de Whisper : « Oui, à ce but, enfin, celui avec l'aise. »)*
- **Noah** (45 s) : « Le plafond est isolé dans le plafond est pas isolés. »
  - **Assistant** : « Ce mur donne sur quoi ? » — 3,23 s
  - **Assistant** : « Ce mur donne sur quoi ? » — 0,29 s
- **Noah** (49 s) : « Le plafond'est pas isolé. »
  - **Assistant** : « Il est en quoi ? » — 0,09 s
- **Noah** (58 s) : « Le plafond n'est pas isolé. »
  - **Assistant** : « Il est en quoi ? » — 0,09 s
- **Noah** (62 s) : « Il te faut quoi d'autre comme information sur ce mur? »
  - **Assistant** : « Pour le mur affiché, il me manque sur quoi il donne, le matériau, l'épaisseur et l'isolation. Il est en quoi ? » — 0,43 s
- **Noah** (72 s) : « Un sous- sol. »
  - **Assistant** : « Quelle épaisseur ? » — 0,05 s
- **Noah** (75 s) : « Tout simplement. »
- **Noah** (94 s) : « Et là, le mur que j suis en train de te montrer y donne sur de deux maisons, derrière, d'oxula, et mur qui donnent vers un voisin simplement voilà »
  - **Assistant** : « Le mur côté cave, quelle épaisseur ? » — 0,94 s
- **Noah** (102 s) : « c'est un mur qui donne derrière sur des toilettes par as une chambre, et là, voilà, c'est un mur qui. »
  - **Assistant** : « Le mur côté cave est isolé ? » — 0,18 s
- **Noah** (110 s) : « Ben en fait, ce mur, c c'est cette pièce fait quatre f a quatre murs voilà toute la pièce. »
  - **Assistant** : « Le mur côté cave est isolé ? » — 0,42 s
- **Noah** (115 s) : « Quel mur. »
  - **Assistant** : « Je parle du mur côté cave, affiché à l'écran. Il est isolé ? » — 0,09 s
- **Noah** (129 s) : « Il y a juste un mur dans la pièce qui donne sur l'extérieur le reste donne que sur l'intérieur, de la maison ou sinon un voisin. »
  - **Assistant** : « Sous le plancher : terre-plein, vide sanitaire, cave ou logement ? » — 0,58 s
