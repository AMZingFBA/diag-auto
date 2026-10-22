# Étape 7 : une vraie conversation (22/10/2026)

Claude (Haiku 5.5, via Claude Code et l'abonnement, sans clé API) lit chaque phrase et y répond ; les règles du serveur ne font que pré-remplir. Deux essais : 30 phrases libres, puis la visite réelle de Noah rejouée.

## 1. Trente phrases libres, avec le vrai Claude

```
python -m assistant.evaluer --conversation
```

Une visite est d'abord mise en place (séjour décrit, cuisine commencée), puis 30 phrases que des règles ne peuvent pas prévoir. Phrases écrites (sans transcription). « Première phrase dite » : temps entre la fin de la phrase du diagnostiqueur et la première phrase de la réponse prête à être dite (il faut ajouter 0,7 s de silence de fin de phrase et ~0,05 s de transcription). « Pré-rempli par les règles » : noté tout de suite, avant Claude ; « Claude » : ce que Claude a noté, corrigé ou annulé.

### Mise en place de la visite

- « Ici c'est le séjour. » → « Très bien, on commence par le séjour. Décrivez-moi le premier mur. »
- « Ce mur donne dehors, brique 30 cm, isolé par l'intérieur, il y a deux fenêtres PVC double vitrage dessus. » → « Noté, le mur sur l'extérieur, en brique de 30 cm, isolé par l'intérieur, avec deux fenêtres PVC double vitrage. Il y a un autre mur dans ce séjour ? »
- « Un autre mur donne sur le voisin. » → « Noté, un mur sur le voisin, local chauffé. Il y a encore un autre mur dans ce séjour ? »
- « Pas d'autre mur. » → « Noté, pas d'autre mur dans le séjour. Au-dessus du plafond, c'est quoi : combles, terrasse ou logement ? »
- « Au-dessus, des combles perdus isolés avec 30 cm de laine de verre. » → « Noté, combles perdus isolés en laine de verre 30 cm. Sous le plancher, c'est quoi : terre-plein, vide sanitaire, cave ou logement ? »
- « Terre-plein, pas isolé. » → « Noté, plancher sur terre-plein, non isolé. Les 2 fenêtres, elles ont des volets ? »
- « Volets roulants. » → « Noté, volets roulants. D'autres fenêtres dans ce séjour, ou une porte vers l'extérieur ? »
- « Pas d'autre fenêtre. » → « Noté, pas d'autre fenêtre dans le séjour. Des radiateurs dans cette pièce ? »
- « Deux radiateurs à eau. » → « Noté, deux radiateurs à eau dans le séjour. Quel est le chauffage principal du logement ? »
- « Une chaudière gaz à condensation de 2015. » → « Noté, chaudière gaz à condensation de 2015. Et l'eau chaude, comment est-elle produite ? »
- « On passe dans la cuisine. » → « On passe dans la cuisine. Décrivez-moi le premier mur de cette pièce. »
- « Ce mur donne dehors, parpaing de 20, non isolé. » → « Noté, le mur sur l'extérieur, en parpaing de 20 cm, non isolé. Il y a un autre mur dans cette cuisine ? »

### 30 phrases libres

1. *question générale* — « C'est quoi un pont thermique ? »
   - **Assistant** : « Un pont thermique, c'est un point faible de l'enveloppe où la chaleur fuit plus vite, par exemple à la jonction d'un mur et d'un plancher, ou autour d'une fenêtre. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,19 s, réponse complète de Claude 1,29 s
2. *question générale* — « Comment se construit une maison ? »
   - **Assistant** : « Une maison se construit en général sur des fondations, avec une structure porteuse en béton, parpaing, brique ou bois, puis on pose la charpente et la couverture. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,18 s, réponse complète de Claude 1,27 s
3. *question générale* — « Ça sert à quoi une VMC ? »
   - **Assistant** : « Une VMC, c'est une ventilation mécanique contrôlée : elle renouvelle l'air du logement en continu et évacue l'humidité et les odeurs. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,14 s, réponse complète de Claude 1,24 s
4. *question générale* — « C'est quoi la différence entre une isolation par l'intérieur et par l'extérieur ? »
   - **Assistant** : « L'isolation par l'intérieur se pose côté pièce, c'est plus simple mais on perd un peu de surface et on peut créer des ponts thermiques. L'isolation par l'extérieur se pose sur la façade, elle est plus performante mais plus coûteuse. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,86 s, réponse complète de Claude 2,10 s
5. *question générale* — « Un DPE, c'est valable combien de temps ? »
   - **Assistant** : « Un DPE est valable dix ans. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,23 s, réponse complète de Claude 1,28 s
6. *question générale* — « Pourquoi tu me demandes l'épaisseur des murs ? »
   - **Assistant** : « Parce que l'épaisseur et le matériau du mur entrent dans le calcul des déperditions de chaleur du logement, donc dans la note du DPE. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,38 s, réponse complète de Claude 1,46 s
7. *hors sujet* — « Comment ça va ? »
   - **Assistant** : « Très bien, merci de demander. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,15 s, réponse complète de Claude 1,20 s
8. *hors sujet* — « Tu m'entends bien ? »
   - **Assistant** : « Oui, je vous entends bien. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,66 s, réponse complète de Claude 1,68 s
9. *hors sujet* — « Il fait drôlement chaud dans cette cuisine. »
   - **Assistant** : « Oui, la cuisine est peut-être mal ventilée ou exposée au soleil, c'est une observation utile pour la visite. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,29 s, réponse complète de Claude 1,28 s
10. *hors sujet* — « Tu es qui, toi ? »
   - **Assistant** : « Je suis l'assistant vocal de la visite, je vous aide à noter les éléments pour le DPE. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,77 s, réponse complète de Claude 1,86 s
11. *hors sujet* — « Merci, tu m'aides bien. »
   - **Assistant** : « Avec plaisir. Pour cette cuisine, il y a un autre mur ? »
   - temps : première phrase dite 1,23 s, réponse complète de Claude 1,23 s
12. *navigation* — « On fait une pause, je prends un appel. »
   - **Assistant** : « D'accord, je vous attends. »
   - Claude : pause
   - temps : première phrase dite 1,20 s, réponse complète de Claude 1,14 s — en pause
13. *navigation* — « Tu as noté quoi pour le séjour ? »
   - **Assistant** : « Pour le séjour, j'ai noté deux murs, celui sur l'extérieur en brique de 30 cm isolé par l'intérieur avec les 2 fenêtres PVC double vitrage et volets roulants, et celui sur le voisin. Le plafond est en combles perdus isolés, le plancher sur terre-plein non isolé. Il reste à voir les radiateurs, déjà notés, et le chauffage, c'est la chaudière gaz de 2015. »
   - temps : première phrase dite 1,45 s, réponse complète de Claude 1,78 s — en pause
14. *navigation* — « C'est bon, on reprend. »
   - **Assistant** : « Très bien, on reprend. Pour cette cuisine, il y a un autre mur ? »
   - Claude : reprendre
   - temps : première phrase dite 1,14 s, réponse complète de Claude 1,16 s
15. *navigation* — « Attends, reviens au séjour. »
   - **Assistant** : « On revient au séjour. Ventilation, c'est une VMC ou une ventilation naturelle ? »
   - pré-rempli par les règles : piece_courante
   - Claude : piece_courante
   - temps : première phrase dite 1,76 s, réponse complète de Claude 1,89 s
16. *navigation* — « Bon, on retourne dans la cuisine. »
   - **Assistant** : « On retourne dans la cuisine. Au-dessus du plafond de la cuisine, c'est quoi : combles, terrasse ou logement ? »
   - pré-rempli par les règles : piece_courante
   - Claude : piece_courante
   - temps : première phrase dite 1,10 s, réponse complète de Claude 1,35 s
17. *navigation* — « On a fini la cuisine, on passe à la chambre. »
   - **Assistant** : « On passe à la chambre. Décrivez-moi le premier mur de cette pièce. »
   - pré-rempli par les règles : piece_courante
   - Claude : piece_courante
   - temps : première phrase dite 1,52 s, réponse complète de Claude 1,57 s
18. *correction* — « Non, le premier mur du séjour, c'est du parpaing, pas de la brique. »
   - **Assistant** : « Noté, le mur du séjour est bien en parpaing. Décrivez-moi le premier mur de la chambre. »
   - pré-rempli par les règles : enregistrer_reponse M1 materiau parpaing
   - temps : première phrase dite 3,60 s, réponse complète de Claude 3,62 s
19. *correction* — « Je me suis trompé, il y a trois radiateurs dans le séjour, pas deux. »
   - **Assistant** : « Noté, trois radiateurs dans le séjour. Décrivez-moi le premier mur de la chambre. »
   - pré-rempli par les règles : compter E1 3
   - temps : première phrase dite 1,94 s, réponse complète de Claude 1,92 s
20. *correction* — « En fait, la chaudière date de 2012. »
   - **Assistant** : « Noté, chaudière de 2012. Plafond pareil que dans le séjour ? »
   - pré-rempli par les règles : enregistrer_reponse CH1 annee 2012
   - temps : première phrase dite 1,89 s, réponse complète de Claude 1,90 s
21. *correction* — « Oublie ce que je viens de dire sur la chaudière, c'était bien 2015. »
   - **Assistant** : « D'accord, la chaudière reste à 2015. Plafond pareil que dans le séjour ? »
   - pré-rempli par les règles : enregistrer_reponse CH1 annee 2015
   - temps : première phrase dite 2,35 s, réponse complète de Claude 2,37 s
22. *correction* — « Ce mur de la chambre, il est orienté plein sud. »
   - **Assistant** : « Noté, le mur sud de la chambre. Ce mur donne sur quoi ? »
   - pré-rempli par les règles : signaler_element M4 le mur 4 ; orienter M4 le mur 4
   - temps : première phrase dite 1,98 s, réponse complète de Claude 1,91 s
23. *récapitulatif* — « Où on en est ? »
   - **Assistant** : « Le séjour est complet, et la chaudière gaz de 2015 est notée. La cuisine a son mur extérieur, il reste ses plafond, plancher et fenêtre. Dans la chambre, j'ai le mur sud, il me manque ce qu'il donne, sa matière, son épaisseur et son isolation, puis le plafond et le plancher. Ce mur donne sur quoi ? »
   - temps : première phrase dite 2,23 s, réponse complète de Claude 2,82 s
24. *récapitulatif* — « Il manque quoi dans cette pièce ? »
   - **Assistant** : « Dans la chambre, il me manque tout le mur sud : ce qu'il donne, son matériau, son épaisseur et son isolation. Il me manque aussi le plafond et le plancher, avec ce qu'ils donnent et leur isolation. Et je dois savoir si il y a une fenêtre et un émetteur de chauffage. Ce mur donne sur quoi ? »
   - temps : première phrase dite 3,35 s, réponse complète de Claude 3,73 s
25. *récapitulatif* — « Rappelle-moi ce que j'ai dit sur le chauffage. »
   - **Assistant** : « Vous avez dit une chaudière gaz à condensation de 2015. Dans le séjour, vous avez noté trois radiateurs à eau. Pour la chambre, l'émetteur n'est pas encore noté. Ce mur sud donne sur quoi ? »
   - temps : première phrase dite 1,85 s, réponse complète de Claude 2,13 s
26. *récapitulatif* — « Combien de fenêtres on a vues jusqu'ici ? »
   - **Assistant** : « Jusqu'ici, deux fenêtres, les deux du séjour, en PVC double vitrage avec volets roulants. Pour la cuisine et la chambre, je n'ai pas encore noté de fenêtre. Ce mur sud donne sur quoi ? »
   - temps : première phrase dite 2,18 s, réponse complète de Claude 2,21 s
27. *récapitulatif* — « Tu as noté quoi pour la cuisine ? »
   - **Assistant** : « Pour la cuisine, j'ai le mur extérieur : parpaing de 20 centimètres, non isolé, qui donne sur l'extérieur. Il me manque le plafond et le plancher, avec ce qu'ils donnent et leur isolation, et la présence éventuelle d'une fenêtre. Ce mur sud donne sur quoi ? »
   - temps : première phrase dite 2,08 s, réponse complète de Claude 2,39 s
28. *description libre* — « Bon alors là c'est un mur un peu bizarre, moitié pierre moitié brique, je dirais 50 centimètres, il donne sur la rue. »
   - **Assistant** : « Noté, mur mixte pierre et brique, 50 centimètres, donnant sur l'extérieur. Il est isolé ? »
   - pré-rempli par les règles : enregistrer_reponse M4 materiau brique ; enregistrer_reponse M4 epaisseur 50 cm ; enregistrer_reponse M4 donne_sur extérieur
   - Claude : enregistrer_reponse M4 materiau pierre et brique
   - temps : première phrase dite 3,50 s, réponse complète de Claude 3,32 s
29. *description libre* — « Là il y a une vieille fenêtre en bois, simple vitrage, sans volet, elle ferme mal. »
   - **Assistant** : « Noté, fenêtre en bois, simple vitrage, sans volet, sur le mur sud. Ce mur sud, il est isolé ? »
   - pré-rempli par les règles : signaler_element F2 la fenêtre 2 ; enregistrer_reponse F2 menuiserie bois ; enregistrer_reponse F2 vitrage simple ; enregistrer_reponse F2 volets aucun
   - temps : première phrase dite 1,87 s, réponse complète de Claude 1,85 s
30. *description libre* — « Le radiateur de la chambre est électrique, un vieux grille-pain. »
   - **Assistant** : « Noté, un seul radiateur électrique dans la chambre, j'ai retiré le doublon. Au-dessus du plafond de la chambre : combles, terrasse ou logement ? »
   - pré-rempli par les règles : signaler_element E2 le radiateur électrique ; enregistrer_reponse E2 type radiateur électrique ; signaler_element E3 le radiateur électrique n°2 ; enregistrer_reponse E3 type convecteur électrique
   - Claude : annuler E3
   - temps : première phrase dite 3,98 s, réponse complète de Claude 3,99 s

### Résumé

- réponses non vides : 30/30
- première phrase dite : médiane 1,77 s, pire 3,98 s (après la fin de phrase ; + 0,7 s de silence et ~0,05 s de transcription au téléphone)
- réponse complète de Claude : médiane 1,85 s


## 2. La visite réelle de Noah, rejouée

Visite d'origine : `sessions/20261022-083308-20ef54` (iPhone, séjour, 2 min 29), rejouée au rythme réel, son et images, avec la même version du serveur dans ses deux modes :

```
set DIAGAUTO_CONVERSATION=rapide      (avant : fonctionnement des étapes 5 et 6)
set DIAGAUTO_CONVERSATION=claude      (après : étape 7, par défaut)
python -m assistant.rejouer sessions\20261022-083308-20ef54 --piece Séjour
```

Les réponses de Noah sont celles du test d'origine : quand les questions changent, certains échanges ne se répondent plus, ce qui est normal pour un rejeu. Le temps indiqué après une réponse de l'assistant est celui entre la fin de phrase détectée et sa première phrase prête (ajouter 0,7 s de silence de fin de phrase). Le bip « noté » part dès le pré-remplissage, avant la réponse de Claude.

### Temps de réponse

| | Test d'origine (étape 4) | Rejeu en mode rapide (étapes 5-6) | Rejeu en conversation (étape 7) |
|---|---|---|---|
| Transcription, médiane | 2,45 s | 0,06 s | 0,06 s |
| Fin de phrase → réponse prête, médiane | 3,15 s | 0,1 s | 2,29 s |
| Fin de phrase → réponse prête, 90 % des phrases | 7,13 s | 0,95 s | 4,41 s |
| Fin de phrase → réponse prête, pire cas | 7,63 s | 3,2 s | 4,41 s |
| Bip « noté » (pré-remplissage), médiane | — | — | 0,09 s (11 bips) |
| Séjour rempli à la fin | 65 % | 60 % | 76 % |
| Informations manquantes à la fin | 10 | 11 | 7 |

### Rejeu en mode rapide (avant ; visite `20261022-115147-182aa6`)

- **Noah** (5 s) : « er. »
- **Noah** (23 s) : « Alors c'est le premier mur Ce premier mur y donne sur l'extérieur y fait trente trente mètres il y a trois fenêtres dessus c'est du bois »
  - **Assistant** : « Ce mur est en quoi ? » — 0,44 s
- **Noah** (27 s) : « c'est une laine de verre de trente centimètres et l'. »
  - **Assistant** : « Il est en quoi ? » — 0,08 s
- **Noah** (30 s) : « Et le mur est en brique. »
  - **Assistant** : « Quelle épaisseur ? » — 0,12 s
- **Noah** (32 s) : « Trente centimètres. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 0,07 s
- **Noah** (38 s) : « Au- dessus du plafond, il y a des combles, exactement. »
  - **Assistant** : « Un autre mur dans cette pièce ? » — 0,09 s
- **Noah** (42 s) : « E Wai a se b en face avec l. »
  - *(second avis de Whisper : « Oui, à ce but, enfin, celui avec l'aise. »)*
- **Noah** (45 s) : « Le plafond est isolé dans le plafond est pas isolés. »
  - **Assistant** : « Ce mur donne sur quoi ? » — 3,2 s
  - **Assistant** : « Ce mur donne sur quoi ? » — 0,24 s
- **Noah** (49 s) : « Le plafond'est pas isolé. »
  - **Assistant** : « Il est en quoi ? » — 0,09 s
- **Noah** (58 s) : « Le plafond n'est pas isolé. »
  - **Assistant** : « Il est en quoi ? » — 0,08 s
- **Noah** (62 s) : « Il te faut quoi d'autre comme information sur ce mur? »
  - **Assistant** : « Pour le mur affiché, il me manque sur quoi il donne, le matériau, l'épaisseur et l'isolation. Il est en quoi ? » — 0,06 s
- **Noah** (72 s) : « Un sous- sol. »
  - **Assistant** : « Quelle épaisseur ? » — 0,05 s
- **Noah** (75 s) : « Tout simplement. »
- **Noah** (94 s) : « Et là, le mur que j suis en train de te montrer y donne sur de deux maisons, derrière, d'oxula, et mur qui donnent vers un voisin simplement voilà »
  - **Assistant** : « Le mur côté cave, quelle épaisseur ? » — 0,95 s
- **Noah** (102 s) : « c'est un mur qui donne derrière sur des toilettes par as une chambre, et là, voilà, c'est un mur qui. »
  - **Assistant** : « Le mur côté cave est isolé ? » — 0,18 s
- **Noah** (110 s) : « Ben en fait, ce mur, c c'est cette pièce fait quatre f a quatre murs voilà toute la pièce. »
  - **Assistant** : « Le mur côté cave est isolé ? » — 0,37 s
- **Noah** (115 s) : « Quel mur. »
  - **Assistant** : « Je parle du mur côté cave, affiché à l'écran. Il est isolé ? » — 0,07 s
- **Noah** (129 s) : « Il y a juste un mur dans la pièce qui donne sur l'extérieur le reste donne que sur l'intérieur, de la maison ou sinon un voisin. »
  - **Assistant** : « Sous le plancher : terre-plein, vide sanitaire, cave ou logement ? » — 0,51 s
  - **Assistant** : « Avant d'arrêter, il manque 11 informations. Séjour, le mur 2 : matériau ; Séjour, le mur 2 : épaisseur ; Séjour, le mur 2 : isolation ; et 8 autres, à l'écran. »

### Rejeu en conversation (après ; visite `20261022-114819-a1dc25`)

- **Noah** (5 s) : « er. »
- **Noah** (23 s) : « Alors c'est le premier mur Ce premier mur y donne sur l'extérieur y fait trente trente mètres il y a trois fenêtres dessus c'est du bois »
  - *(bip « noté » : 0,503 s)*
  - **Assistant** : « J'ai noté que ce mur donne sur l'extérieur et que les trois fenêtres sont en bois. Pour la longueur, trente mètres me paraît beaucoup, je ne l'ai pas notée, vous pourrez la vérifier. Ce mur est en quoi ? » — 4,41 s
- **Noah** (27 s) : « c'est une laine de verre de trente centimètres et l'. »
  - *(bip « noté » : 0,089 s)*
- **Noah** (30 s) : « Et le mur est en brique. »
  - *(bip « noté » : 0,114 s)*
- **Noah** (32 s) : « Trente centimètres. »
- **Noah** (38 s) : « Au- dessus du plafond, il y a des combles, exactement. »
  - *(bip « noté » : 0,068 s)*
- **Noah** (42 s) : « E Wai a se b en face avec l. »
- **Noah** (45 s) : « Le plafond est isolé dans le plafond est pas isolés. »
  - *(bip « noté » : 0,056 s)*
  - **Assistant** : « Oui, le plafond n'est pas isolé, c'est bien noté. Y a-t-il un autre mur dans cette pièce ? » — 2,29 s
- **Noah** (49 s) : « Le plafond n desest pas isolés. »
  - *(bip « noté » : 0,046 s)*
- **Noah** (58 s) : « Le plafond n'est pas isolé. »
  - *(bip « noté » : 0,052 s)*
- **Noah** (62 s) : « Il te faut quoi d'autre comme information sur ce mur? »
  - **Assistant** : « Pour le mur des trois fenêtres, j'ai tout. Il reste le plancher : il donne sur quoi ? » — 1,72 s
- **Noah** (69 s) : « Un. »
- **Noah** (72 s) : « Un sous- sol. »
  - *(bip « noté » : 0,212 s)*
  - **Assistant** : « Sous-sol, c'est noté. Le plancher est isolé ? » — 1,05 s
- **Noah** (74 s) : « Tout simplement. »
  - **Assistant** : « Je crois que vous voulez dire que le plancher n'est pas isolé, tout simplement. C'est bien ça ? » — 3,99 s
- **Noah** (94 s) : « Et là, le mur que j suis en train de te montrer y donne sur de deux maisons, derrière, d'oxula, et mur qui donnent vers un voisin simplement voilà »
  - *(bip « noté » : 0,607 s)*
  - **Assistant** : « Y a-t-il encore un autre mur dans cette pièce ? » — 2,95 s
- **Noah** (97 s) : « un haut mur qui donne derrière sur des toilettes »
  - *(bip « noté » : 0,071 s)*
- **Noah** (102 s) : « par elle a su une chambre, et là voilà c'est un mur qui. »
- **Noah** (110 s) : « Ben en fait, ce mur, c c'est cette pièce fait quatre f a quatre murs voilà toute la pièce. »
  - **Assistant** : « D'accord, la pièce a quatre murs, et il m'en manque un. Il donne sur quoi ? » — 2,47 s
- **Noah** (115 s) : « Quel mur. »
  - **Assistant** : « C'est le mur qu'on n'a pas encore décrit, celui avec la télé, en face des fenêtres. Il donne sur quoi ? » — 1,91 s
- **Noah** (129 s) : « Il y a juste un mur dans la pièce qui donne sur l'extérieur le reste donne que sur l'intérieur, de la maison ou sinon un voisin. »
  - *(bip « noté » : 0,152 s)*
  - **Assistant** : « Noté, seul le mur des fenêtres donne sur l'extérieur, les autres sur l'intérieur ou des voisins. Les 3 fenêtres, elles sont en simple ou double vitrage ? » — 2,13 s
  - **Assistant** : « Avant d'arrêter, il manque 7 informations. Séjour, le plancher : isolation ; Séjour, les 3 fenêtres : vitrage ; Séjour, les 3 fenêtres : volets ; et 4 autres, à l'écran. »
