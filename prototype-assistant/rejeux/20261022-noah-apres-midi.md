# Test de Noah du 22/10 après-midi : questions répétées, silences, pièce changée trop tôt

Visite `sessions/20261022-153605-67f6df` : 11 min 43, iPhone, trois pièces (« pièce U », cuisine, chambre). Ce que dit Noah :
« il pose trop de questions que je répète ; des fois plus de réponse pendant 2 minutes ; il me fait passer à une pièce
alors qu'on n'a pas fini celle-là, et après on retourne sur la pièce ; c'est trop long avec toutes les questions ; ce serait
bien qu'un questionnaire apparaisse sur le téléphone en même temps qu'à l'oral, pour cocher les réponses ».

## Ce que montre le journal (visite entière)

| Mesure | Valeur |
|---|---|
| Phrases de Noah | 80 |
| Questions posées | 62, dont **18 répétitions** |
| « Un autre mur dans cette pièce ? » | **10 fois** |
| « La fenêtre de la chambre, côté rue : PVC, bois ou alu ? » | 4 fois |
| « Ventilation : VMC ou naturelle ? » | 3 fois |
| Silences de 20 s ou plus alors qu'il parlait | 6 (26, 32, 23, 25, 35 et 22 s) |
| Réponses de l'assistant coupées / reprises | 25 / 3 |
| Phrases douteuses traitées comme des réponses | 17 |
| Pièces | « U » (!), Cuisine, Chambre |
| Changements de pièce proposés d'après l'image | 2, dont un alors que la première pièce n'était pas finie |

## Causes

1. **Des bruits pris pour des réponses.** La transcription rapide donne quelques lettres sur un bruit (téléphone manipulé,
   pas) : « A. », « F. », « P. », « Il. », « Lour. », « Unf. ». Réécoutés par Whisper, ces passages ne contiennent aucune
   parole (Whisper n'entend rien, ou invente « Sous-titres réalisés par la communauté d'Amara.org », typique d'un passage
   sans voix). L'assistant y voyait une réponse incomprise et reposait sa question : c'est l'essentiel des répétitions de
   « PVC, bois ou alu ? ».
2. **Des réponses courtes mal transcrites.** « VMC » transcrit « Vaime s. » puis « GMC. » ; « non » transcrit « Na. »,
   « Nur. ». Whisper, guidé par les réponses attendues à la question, retrouve « VMC » (2 fois sur 2) et « Non » (2 sur 2).
   En conversation, le second avis de Whisper était coupé depuis l'étape 8 (lent, et il inventait sur le bruit).
3. **« Un autre mur dans cette pièce ? » 10 fois.** Le parcours la posait après chaque mur (demande de l'étape 2). Claude
   la reposait aussi de lui-même, sous une autre clé : le garde-fou contre les répétitions ne la reconnaissait pas.
4. **Les silences de 30 à 35 s.** Un bruit coupe la réponse de l'assistant (il croit que Noah parle). La reprise de la
   réponse coupée n'avait lieu qu'après un seul bruit ; avec deux bruits de suite, jamais. À 4:49 et à 9:55, l'assistant
   s'est tu ; Noah a fini par dire « Allô ? », « Tu es là ? ».
5. **Le mur décrit en une phrase compté deux fois** (M1, M2) ; « c'est le même mur » n'a pas été compris (la phrase ne
   commençait pas par « oui ») : les deux murs sont restés, d'où des questions déjà répondues (« je te l'ai dit au début »).
6. **La pièce changée trop tôt** : à 3:07, « On est dans la cuisine ? » d'après l'image, alors que la première pièce
   n'était pas finie ; il a fallu y revenir pour les volets et les radiateurs.
7. **« La pièce U »** : Claude a nommé « U » la « première pièce », et ce nom d'une lettre a été accepté.

## Ce qui change

Voir le README, « Test de Noah du 22/10 après-midi ». En bref : questionnaire en direct sur le téléphone (réponses en
boutons et fiche de la pièce) ; réécoute par Whisper des phrases courtes sans mot connu ; reprise de la réponse coupée
quel que soit le nombre de bruits ; « D'autres murs sur l'extérieur ou un local non chauffé ? » une fois par pièce, sous
une seule clé ; « c'est le même mur » compris ; pas de changement de pièce proposé avant la fin de la pièce ; « Pièce 1 ».

## Rejeu de la même visite avec le nouveau code

Même son et mêmes images (`python -m assistant.rejouer sessions/20261022-153605-67f6df`), vrai Claude, sur une copie du
serveur (port 8444) : visite rejouée `sessions/20261022-162157-9d0845`.

| Mesure | Avant (visite réelle) | Après (rejeu) |
|---|---|---|
| « Un autre mur ? » / « D'autres murs… ? » | 10 | **2** |
| Bruits pris pour des réponses | 17 | **0** (8 bruits écartés, 5 réponses retrouvées par Whisper) |
| Délai de réponse après une phrase : médiane / pire | 1,8 s / 32 s | 1,6 s / **9,1 s** |
| Réponses coupées / reprises | 25 / 3 | 16 / 5 |
| Mur décrit en une phrase | 2 murs (M1 et M2) | **1 mur** |
| Pièces | « U », Cuisine, Chambre | Pièce 1, Cuisine, Chambre 1 |
| Changement de pièce proposé avant la fin de la pièce | 2 | **0** (2 reportés) |

**À lire avec prudence** : le rejeu fait entendre les réponses enregistrées de Noah, qui répondaient aux anciennes
questions. Quand le nouvel assistant pose une autre question, la réponse enregistrée ne lui correspond pas (« Oui. »,
« Non. », « Simple. ») et la question revient : c'est ce qui donne, dans le rejeu, « Ce radiateur, il est à eau ou
électrique ? » 6 fois et « Quelle est la pièce suivante ? » 3 fois. De même, les longs passages sans parole de
l'enregistrement (Noah attendait l'ancien assistant, resté muet) apparaissent comme des silences ; le bon indicateur est le
délai de réponse après une vraie phrase : 9,1 s au pire (une réponse coupée par un bruit, puis la réécoute de « Allô ? »).
Le questionnaire du téléphone (boutons, fiche) ne peut pas être rejoué : il est vérifié par les tests et dans une vraie
page (jsdom).

**Corrigé après le rejeu** : « V'aime ça. » (VMC) n'était pas réécouté, « ça » étant un mot connu. Une réponse de trois
mots au plus, à une question qui attend des réponses précises, que les règles ne comprennent pas, est maintenant réécoutée
elle aussi ; une réponse comprise telle quelle ne l'est jamais (aucune seconde perdue).

**Limite** : la réécoute par Whisper prend 2,5 à 4 s sur ce PC (sans carte graphique). Elle ne concerne que les phrases
courtes douteuses (13 sur 71 dans le rejeu), surtout des bruits, auxquels rien n'est répondu.
