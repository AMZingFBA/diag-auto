# Étape 10 : faux « Hors réseau » (22/10/2026)

Noah voyait « Hors réseau : l'enregistrement continue, l'assistant reprendra au retour du réseau » alors qu'il avait bien
du réseau.

## Causes trouvées

Le journal de ses visites ne contient aucune session postérieure à l'étape 9 sur ce PC : la cause exacte de son dernier
essai ne peut pas y être lue. Le code et les journaux précédents montrent pourquoi ce message apparaissait à tort :

1. **Toute fermeture de la liaison affichait « Hors réseau »**, immédiatement et quelle qu'en soit la raison
   (`ws.onclose` dans `web/app.js`). Il n'y avait ni battement de cœur ni vérification que le serveur était vraiment
   injoignable. `navigator.onLine` n'était pas utilisé ; le certificat auto-signé n'y est pour rien (une fois accepté, la
   liaison s'ouvre).
2. **La page mise en arrière-plan ou l'écran verrouillé** : iOS suspend la page et ferme la liaison, alors que le réseau
   est bon. Visite `sessions/20261022-072246-657b60` : déconnexion à 07:30:27, reconnexion à 07:32:30, et l'horloge de la
   vidéo du téléphone a sauté de 125 s entre les deux (la page était suspendue).
3. **Le serveur redémarré** : chaque redémarrage (il y en a eu plusieurs le 22/10 pendant les rejeux) ferme la liaison.
4. **Une erreur sur un seul message** reçu du téléphone remontait jusqu'à la boucle de la liaison : le serveur la
   fermait, et le téléphone affichait « Hors réseau ».
5. **Claude lent** n'était pas pris pour une coupure par le code (aucun délai de réponse n'était surveillé), mais rien ne
   le montrait : un long silence de l'assistant ressemblait à une panne.
6. Pendant une coupure, **le son, les images et les phrases écrites étaient perdus** pour l'assistant (seule la vidéo
   locale les gardait), et ce que l'assistant disait pendant ce temps n'était jamais remis.

## Ce qui change

**Téléphone** (`web/liaison.js`, testé avec Node et une fausse horloge) :
- un battement de cœur toutes les 2 s ; le serveur répond « pong » tout de suite ;
- **« Hors réseau » seulement si le serveur est vraiment injoignable** : 3 battements sans réponse (6 s), ou une
  reconnexion qui échoue depuis 6 s ;
- un battement en retard (> 1,5 s) donne « réseau lent » : pastille orange, sans alerte ;
- toute fermeture est réparée **en silence** : nouvelle tentative après 0,5 s, puis 1 s, puis toutes les 2 s ;
- page cachée (écran verrouillé, autre application) : aucune alerte ; reconnexion dès que la page revient, ou dès que le
  téléphone signale le retour du réseau ;
- ce qui n'a pas pu partir est **gardé et envoyé au retour, dans l'ordre** : tout le son (le serveur rattrape les
  phrases dites pendant la coupure), une image sur trois, les capteurs, les phrases écrites ; jusqu'à ~12 Mo (2 à 3 min) ;
- « L'assistant réfléchit… » s'affiche si rien n'est dit 3 s après une phrase : Claude lent n'est pas une coupure ;
- au retour : « Réseau revenu : l'assistant rattrape ce qui a été dit. », effacé après 4 s ;
- à chaque reconnexion, le téléphone rapporte au serveur ses coupures (durée, cause, messages gardés ou perdus) : elles
  sont notées au journal de la visite.

**Serveur** (`assistant/serveur.py`, `assistant/session.py`) :
- réponse au battement dans la boucle de la liaison, indépendante de Claude et de la transcription ;
- une erreur sur un message est notée au journal et ne ferme plus la liaison ;
- ce qui est dit pendant une coupure est gardé, et **redit à la reconnexion** s'il date de moins d'une minute ;
- le code de chaque fermeture est noté (« deconnexion », avec son code).

## Mesures

**Scénarios simulés** (`tests/test_liaison_js.py`, fausse horloge, faux serveur) :

| Scénario | Résultat |
|---|---|
| Réseau lent : réponses en 2,5 s pendant 30 s | « réseau lent », jamais « hors réseau », jamais de reconnexion |
| Claude lent : rien d'autre pendant 20 s | toujours « connecté » |
| Vraie coupure de 9 s | « reconnexion » en silence, « hors réseau » à 6 s (pas avant), puis « connecté » ; le son des 8 s rattrapé dans l'ordre |
| Coupure brève (serveur redémarré) | « reconnexion » puis « connecté » en 0,6 s, jamais « hors réseau » |
| Liaison morte sans fermeture (Wi-Fi perdu) | « lent » à 2 s, « hors réseau » à 6 s, reconnexion retentée |
| Écran verrouillé 60 s | « pause », pas d'alerte ; reconnecté dès le retour |
| Coupure trop longue | les messages les plus anciens sont perdus au-delà de la limite ; l'état de la voix n'est pas gardé |
| Code d'accès incorrect | pas de reconnexion |

**Serveur** (`tests/test_liaison.py`) : battement répondu pendant que Claude réfléchit ; message illisible sans coupure ;
reconnexion avec rattrapage de ce qui a été dit pendant la coupure ; son gardé traité au retour.

**Sur le vrai serveur** (ce PC, avec le rejeu de la visite de Noah en parallèle : transcription et vrai Claude) :
- 29 battements sur 29 répondus, en **1 ms** en médiane, **35 ms au pire**, pendant que Claude mettait 3 à 4 s à
  répondre ;
- coupure de 6 s puis reconnexion : la même visite reprend (« reprise »), et les trois phrases dites par l'assistant
  pendant la coupure sont redites au retour.

## Limites

- **À vérifier sur l'iPhone de Noah** : le rejeu ne fait pas tourner la page du téléphone ; le module de liaison est
  testé avec Node et une fausse horloge.
- **Écran verrouillé** : iOS suspend la page ; le son n'est alors plus capté par la page, il n'y a donc rien à rattraper
  pour cette durée (la page garde l'écran allumé pendant la visite quand le téléphone le permet).
- **Serveur redémarré pendant une visite** : la visite en cours est en mémoire ; à la reconnexion, une nouvelle visite
  commence (dans un autre dossier). Ne pas redémarrer le serveur pendant un test.
