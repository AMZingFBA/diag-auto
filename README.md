# DiagAuto

Remplir LICIEL Diagnostics automatiquement à partir des données saisies sur le terrain (pièces, mesures, photos, dictée…), pour que le diagnostiqueur n'ait plus rien à ressaisir. Le diagnostiqueur garde la main : il relit et valide dans LICIEL avant d'éditer le rapport.

Le cadrage complet (stockage LICIEL, architecture, plan du MVP, questions ouvertes) est dans [docs/01-cadrage.md](docs/01-cadrage.md).

## État actuel : étape E1 terminée

Le module `diagauto.liciel_xml` sait **lire et réécrire à l'identique, octet pour octet**, les tables d'un dossier LICIEL (`XML\Table_*.xml`) :

- testé sur les 296 tables des dossiers de référence copiés dans `tests/fixtures/` ;
- vérifié en lecture seule sur les 1 614 tables présentes sur le poste (cas tests DPE de LICIEL, dossiers de démonstration, dossier de test) : 1 614 identiques.

Rien n'est encore écrit dans LICIEL : les deux commandes ci-dessous sont en lecture seule.

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

- **Ne jamais modifier** l'installation LICIEL (`C:\LICIEL_Programmes`). Pour l'instant, **aucune écriture non plus sous `C:\LICIEL_Diagnostics`** : les essais d'écriture seront faits par Hermes sur un dossier jetable.
- On travaille sur l'interopérabilité de **nos propres dossiers**, c'est-à-dire la lecture et l'écriture de fichiers de données. Pas de décompilation, pas de contournement de protection, pas de lecture des référentiels chiffrés (`DATA_XML_SAV`).
- Exactitude réglementaire : rien n'est inventé. Les correspondances encore incertaines sont marquées « hypothèse » dans le code et dans `docs/01-cadrage.md`.

## Organisation du dépôt

```
diagauto/liciel_xml/table.py     lecture/écriture fidèle d'une table (Table, FragmentXml)
diagauto/liciel_xml/dossier.py   lecture d'un dossier complet : pièces, Carrez, modules, mission
diagauto/liciel_xml/valeurs.py   conversions (nombres à virgule, Vrai/Faux)
diagauto/cli.py                  commandes « diagauto inspect » et « diagauto verifier »
tests/fixtures/                  4 dossiers de démonstration LICIEL + 5 cas tests DPE (données fictives)
docs/01-cadrage.md               cadrage du projet
```
