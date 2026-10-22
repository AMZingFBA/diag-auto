# DiagAuto

Remplir LICIEL Diagnostics automatiquement à partir des données saisies sur le terrain (pièces, mesures, photos, dictée…), pour que le diagnostiqueur n'ait plus rien à ressaisir. Le diagnostiqueur garde la main : il relit et valide dans LICIEL avant d'éditer le rapport.

Le cadrage complet (stockage LICIEL, architecture, plan du MVP, questions ouvertes) est dans [docs/01-cadrage.md](docs/01-cadrage.md).

## État actuel : étape E1 terminée, pont assistant → LICIEL (pièces + Carrez) en place

Le module `diagauto.liciel_xml` sait **lire et réécrire à l'identique, octet pour octet**, les tables d'un dossier LICIEL (`XML\Table_*.xml`) :

- testé sur les 296 tables des dossiers de référence copiés dans `tests/fixtures/` ;
- vérifié en lecture seule sur les 1 614 tables présentes sur le poste (cas tests DPE de LICIEL, dossiers de démonstration, dossier de test) : 1 614 identiques.

**Étape 11 (22/10/2026)** : le pont `diagauto generer` transforme une visite de l'assistant vocal en tables LICIEL de notre
dossier de test (liste des pièces + les 3 tables Carrez), dans un **nouveau dossier hors de `C:\LICIEL_*`**
(`sorties/dossier-test`). C'est la préparation des étapes E2 (pièces) et E4 (Carrez) du plan. Il reste à Hermes de poser
ces tables dans un dossier LICIEL jetable pour voir si LICIEL les relit (voir plus bas). Rien n'est écrit dans LICIEL.

## Installation (Windows)

```
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Python 3.11 ou plus récent. Aucune dépendance en dehors de `pytest` pour les tests.

## Commandes

Résumé d'un dossier LICIEL (mission, modules présents, pièces, Carrez pièce par pièce) :

```
.venv\Scripts\diagauto inspect C:\LICIEL_Diagnostics\Dossiers_2026\2610210001
.venv\Scripts\diagauto inspect tests\fixtures\Dossiers_DEMO\DEMO_0001
```

Vérifier que toutes les tables d'un ou plusieurs dossiers se relisent et se réécrivent à l'identique. C'est utile après une mise à jour de LICIEL, pour savoir si le format a changé :

```
.venv\Scripts\diagauto verifier C:\LICIEL_Diagnostics
```

### Générer le dossier LICIEL d'une visite (pont assistant → LICIEL)

```
.venv\Scripts\diagauto generer --modele C:\Users\conta\Documents\liciel\dossier-test\etape2-dossier-4pieces
```

- **Visite** : par défaut la plus récente de `prototype-assistant/sessions/` qui a un `etat.json` (autre visite :
  `--visite <dossier>`). On y lit les pièces, et, pour le rapport, les murs, fenêtres, portes et émetteurs.
- **Modèle** : notre dossier de test LICIEL 2610210001 (4 pièces : Sejour, Cuisine, Chambre 1, Salle de bains), ici la
  copie d'Hermes, identique à l'octet au dossier LICIEL. Il est **lu seulement**.
- **Sortie** : `sorties/dossier-test/XML/Table_*.xml` (autre dossier : `--sortie`), plus `diagauto-pont.json` (ce qui a été
  fait, pièces à mesurer, hypothèses). L'écriture est **refusée sous tout dossier `LICIEL_*`**, dans le modèle, et dans un
  dossier existant qui n'a pas été créé par cette commande. `sorties/` n'est pas versionné : on le régénère.
- La commande finit par la vérification `diagauto verifier` du dossier produit. Ensuite, `diagauto inspect sorties\dossier-test`
  montre les pièces et le Carrez rattaché à chaque pièce.

Ce qui est écrit :

| Table | Contenu |
|---|---|
| `General_Pieces_Toutes` | Les pièces déjà dans le dossier gardent leur ligne et leur clé (« Séjour » de la visite = « Sejour » du dossier : accents, majuscules et espaces ignorés). Les nouvelles (ex. « Couloir ») sont ajoutées à la fin, avec une clé au format LICIEL, au bâtiment du dossier (« Appartement » ; `--batiment` s'il y en a plusieurs). Une pièce du dossier non vue pendant la visite reste telle quelle : elle est seulement signalée (c'est au diagnostiqueur de la déclarer non visitée). |
| `Z_Carrez_Resume` | Une ligne par pièce vue ou mesurée : surfaces Carrez, au sol et habitable, hauteur sous plafond, annexe. |
| `Z_Carrez_Details` | Une ligne par mesure : ajout, partie de moins de 1,80 m retirée, pièce comptée au sol seulement. |
| `Z_Carrez_General` | Les totaux du lot (annexes exclues) et la hauteur générale. |
| `General_Pieces_Visites` | Complétée seulement si le modèle l'a déjà (ce n'est pas le cas de notre dossier de test). |
| Autres tables | Copiées du modèle à l'octet près. Aucun fichier signé (`*.signed.xml`) n'est copié ni fabriqué. |

**Aucune surface n'est inventée.** L'assistant ne relève pas encore les surfaces. Dans la visite actuelle, toutes les
pièces sont donc écrites à 0 m² et signalées « À MESURER ». Pour le Carrez, la mesure laser fait foi : les mesures validées
par le diagnostiqueur sont lues dans `mesures.json`, dans le dossier de la visite (ou `--mesures <fichier>`) :

```json
{
  "Séjour": {"surfaces": [18.42], "hsp": 2.5, "source": "laser"},
  "Comble": {"surfaces": [43.5], "moins_1m80": [21.1], "commentaire": "Hauteur inférieure à 1,80 m"},
  "Cave":   {"surfaces": [8.21], "hors_carrez": true},
  "Garage": {"surfaces": [50], "hors_carrez": true, "annexe": true}
}
```

- `surfaces` : mesures en m², ajoutées.
- `moins_1m80` : parties de moins de 1,80 m, retirées du Carrez mais gardées au sol.
- `hors_carrez` : pièce comptée au sol seulement (cave, garage, escalier…).
- `annexe` : pièce hors des totaux.
- `hsp` : hauteur sous plafond, en m.

Une pièce inconnue, une surface négative ou une hauteur aberrante sont refusées, et rien n'est écrit.

Les calculs suivent les dossiers de démonstration. On part des surfaces de chaque pièce de DEMO_0002 et DEMO_0003 (pièces
exclues, annexes, parties de moins de 1,80 m). Nos tables redonnent alors **exactement** les lignes et les totaux calculés
par LICIEL (tests `tests/test_pont.py`).

**Hypothèses à vérifier dans LICIEL** (aussi listées dans `diagauto-pont.json`) :

- lien Carrez → pièce : par le libellé « Bâtiment - Local » (comme dans les démos) et par `ClefComposantPiece` = clé de la
  pièce dans la liste des pièces ;
- `Surface_1` = Carrez et `Surface_3` = habitable (confiance moyenne : identiques dans toutes les démos) ;
- pièce non mesurée écrite à 0 (LICIEL écrit 0 pour une hauteur non saisie) ;
- hauteur générale = moyenne des hauteurs pondérée par la surface au sol (règle retrouvée sur les 3 démos) ;
- `Code_Chk_Habitable` = 0 (sens inconnu) ; `Doc_Remis` laissé vide (à renseigner dans LICIEL) ;
- LICIEL recalcule-t-il `Resume` et `General` à l'ouverture ? Remplit-il seul `General_Pieces_Visites` ? (questions E2 et E3)

**À tester par Hermes** (dossier LICIEL jetable, LICIEL fermé) :

1. Copier `sorties\dossier-test\XML\Table_*.xml` dans le dossier `XML` d'une copie jetable de 2610210001.
2. Ouvrir ce dossier dans LICIEL.
3. Vérifier que le Couloir apparaît dans la liste des pièces.
4. Vérifier que le module Carrez montre les 3 pièces. La version d'essai n'enregistre pas le Carrez, mais elle peut l'afficher.

Les murs, ouvertures et émetteurs relevés ne vont pas encore dans LICIEL : ils figurent dans le rapport
(`diagauto-pont.json`), en attendant l'étape DPE.

Lancer les tests :

```
.venv\Scripts\python -m pytest
```

## Utilisation en Python

```python
from diagauto.liciel_xml import DossierLiciel, lire_table, ecrire_table

table = lire_table(r"...\XML\Table_General_Pieces_Toutes.xml")
for ligne in table.lignes:                       # une ligne = un dict colonne -> valeur (texte brut)
    print(ligne["Batiment"], ligne["Local"])

dossier = DossierLiciel(r"tests\fixtures\Dossiers_DEMO\DEMO_0001")
dossier.pieces()          # liste des pièces (libellé « Bâtiment - Local », visitée ou non)
dossier.carrez()          # Carrez / habitable / au sol / HSP par pièce
dossier.totaux_carrez()   # totaux enregistrés par LICIEL
```

Les valeurs restent du texte, exactement comme dans le fichier : virgule décimale, « Vrai »/« Faux », XML imbriqué. Des conversions sont disponibles dans `diagauto.liciel_xml.valeurs`.

## Ce qu'il faut savoir sur le format LICIEL

Ces fichiers ressemblent à du XML mais n'en sont pas. On ne peut donc pas utiliser une bibliothèque XML standard :

| Particularité | Détail |
|---|---|
| Encodage | Windows-1252 (pas UTF-8). |
| Échappement | `&` et `<` ne sont pas échappés dans les valeurs. |
| Fins de ligne | Une seule par fichier : CR (`\r`) le plus souvent, LF pour quelques fichiers. Les valeurs multi-lignes contiennent souvent des CRLF. |
| Mise en page | Indentation de 5 espaces par niveau. Une table « fiche » finit par une ligne vide, une table « liste » non. |
| Noms | Les fautes de frappe d'origine sont conservées (`Localistion`, `Commantaires`, `CelfComposant`…). |
| Colonnes en double | Une colonne peut apparaître deux fois dans une même ligne (vu une fois). La 2e occurrence est exposée sous la clé `Colonne#2`. |
| Fichiers non LiTable | Quelques `Table_*.xml` sont des fragments XML libres, sans racine `LiTable_` : ils sont conservés tels quels. |

Toute mise en page inattendue lève `FormatNonReconnu` plutôt que d'être « corrigée » en silence.

## Règles du projet

- **Ne jamais modifier** l'installation LICIEL (`C:\LICIEL_Programmes`). Pour l'instant, **aucune écriture non plus sous `C:\LICIEL_Diagnostics`** : les essais d'écriture seront faits par Hermes sur un dossier jetable. `diagauto generer` refuse d'écrire sous tout dossier `LICIEL_*`.
- On travaille sur l'interopérabilité de **nos propres dossiers**, c'est-à-dire la lecture et l'écriture de fichiers de données. Pas de décompilation, pas de contournement de protection, pas de lecture des référentiels chiffrés (`DATA_XML_SAV`).
- Exactitude réglementaire : rien n'est inventé. Les correspondances encore incertaines sont marquées « hypothèse » dans le code et dans `docs/01-cadrage.md`.

## Organisation du dépôt

```
diagauto/liciel_xml/table.py     lecture/écriture fidèle d'une table (Table, FragmentXml)
diagauto/liciel_xml/dossier.py   lecture d'un dossier complet : pièces, Carrez, modules, mission
diagauto/liciel_xml/valeurs.py   conversions (nombres à virgule, Vrai/Faux)
diagauto/pont.py                 pont assistant -> LICIEL : pièces et Carrez d'une visite (« diagauto generer »)
diagauto/cli.py                  commandes « diagauto inspect », « diagauto verifier » et « diagauto generer »
sorties/                         dossiers générés par « diagauto generer » (non versionné)
tests/fixtures/                  4 dossiers de démonstration LICIEL + 5 cas tests DPE (données fictives)
docs/01-cadrage.md               cadrage du projet
prototype-assistant/             prototype V1bis : assistant vocal en direct pendant le tournage (voir son README)
```
