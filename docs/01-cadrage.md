# DiagAuto — 01. Cadrage

*Rédigé le 21/10/2026. Exploration faite en lecture seule : rien n'a été modifié sous `C:\LICIEL_Programmes` ni sous `C:\LICIEL_Diagnostics`.*

Sources utilisées :
- l'installation LICIEL (`C:\LICIEL_Programmes\LICIEL Diagnostics`) ;
- les données LICIEL (`C:\LICIEL_Diagnostics`), avec les 4 dossiers `Dossiers_DEMO` et notre dossier de test `Dossiers_2026\2610210001` ;
- les ~165 dossiers de cas tests DPE fournis par LICIEL (`Eval_DPE_2020`) ;
- le journal des versions `Historique.txt` ;
- les travaux d'Hermes (`Documents\liciel\guide-0..3`, `etude-technique-import.md`, `dossier-test\README.md`).

---

## En bref (pour Noah)

1. **LICIEL range chaque dossier dans un dossier Windows, sous forme de fichiers texte lisibles.** On trouve une soixantaine de « tables » : une pour les pièces, une pour le Carrez, plusieurs pour le DPE, etc. La liste des missions est gardée à part, dans une petite base de données Access.
2. **On peut donc fabriquer ces fichiers nous-mêmes** à partir de ce que le diagnostiqueur saisit sur place. Ensuite, LICIEL ouvre le dossier comme s'il avait été saisi à la main. Le diagnostiqueur relit, corrige si besoin et édite le rapport comme d'habitude.
3. **On commence petit : la liste des pièces, puis le métrage Carrez/Boutin.** C'est simple, très fréquent et facile à vérifier : la surface est juste ou elle ne l'est pas. Le DPE viendra ensuite. Il est beaucoup plus complexe, et LICIEL y stocke des codes internes.
4. **Deux blocages à lever tout de suite :**
   - Il nous faut une licence LICIEL, ou l'accès à un poste équipé d'une licence. La version d'essai n'enregistre pas les données Carrez, DPE et Élec, donc on ne peut pas prouver le Carrez sans licence.
   - Il faut décider si l'on contacte l'éditeur LICIEL. Il propose de développer des « passerelles d'import » sur devis. Ce serait la voie la plus solide, et cela vaudrait accord écrit.
5. Les questions à trancher sont listées à la fin (section 4).

---

## 1. Comment LICIEL stocke ses données

### 1.1 Deux emplacements bien séparés

| Emplacement | Contenu | Ce qu'on en fait |
|---|---|---|
| `C:\LICIEL_Programmes\LICIEL Diagnostics` | Programmes et référentiels. Le fichier de version admin indique 4.278, celui de la partie terrain 4.277, et une mise à jour a été téléchargée au premier lancement. Application Windows .NET Framework 4.8. | **Lecture seule, jamais modifié.** |
| `C:\LICIEL_Diagnostics` | Données de l'utilisateur : base des missions, dossiers, paramètres société, opérateurs, modèles. | On y **lit** pour comprendre. Plus tard, on **écrira uniquement dans le sous-dossier d'un dossier**, et seulement quand LICIEL est fermé (voir § 2). |

**Programmes principaux** (côté installation) :

| Programme | Rôle |
|---|---|
| `Liciel_Diagnostics.exe` | Partie « gestion » : clients, ordres de mission (ODM), facturation. |
| `Liciel_Terrain_x64.exe` + `Liciel_Terrain_Dll.dll` | Partie « terrain » : saisie d'un dossier (pièces, plan, photos, modules). |
| `LICIEL_Impression.exe` | Génération des rapports, par publipostage Word à partir de `Modeles_sources\*.docx` (A0…D7), puis PDF. |
| `Liciel_DPE_Envoie_ADEME.exe` | Dépôt du DPE à l'ADEME. |
| `Liciel_Ordre_de_Mission.exe`, `Liciel_Operation_Dossiers.exe`, `LICIEL_Liaison_MDB.exe` | Gestion des missions et de la base Access. |
| `Liciel_Synchro_CLOUD.exe`, `Liciel_Synchro_WEBDAV.exe`, `LICIEL_Action_Cloud.exe` | Synchronisation cloud et réseau. |
| `LiciBot\LiciA.exe` | Assistant IA intégré : questions/réponses métier, avec reconnaissance vocale hors ligne (Vosk ou Whisper, français). C'est un chatbot, pas un outil de saisie. On le surveille quand même comme concurrent potentiel. |

**Référentiels chiffrés** : `DATA_XML_SAV\*.dll` contient environ 570 fichiers (listes déroulantes, normes élec/gaz, tables DPE, listes amiante…). Leur contenu est **chiffré**. Conformément aux règles du projet, **on n'y touche pas et on ne cherche pas à les déchiffrer**. Conséquence : quand un champ LICIEL stocke le numéro d'une option de liste (fréquent en DPE), on ne peut connaître ce numéro qu'en **observant des dossiers saisis normalement** (DEMO, cas tests, dossiers que nous saisirons nous-mêmes).

**Corpus d'exemples précieux** : `Eval_DPE_2020\` contient environ 165 dossiers de cas tests DPE (appartements, maisons, immeubles, audits), chacun avec ses tables XML. C'est notre base d'apprentissage pour le futur module DPE.

### 1.2 Côté données : la mission (base Access) et le dossier (fichiers XML)

```
C:\LICIEL_Diagnostics\
├── LICIEL_Dossiers.mdb        ← base Access : registre des missions / ODM
├── Index.txt                  ← compteurs : <dossier>2</dossier><facture>1</facture><devis>1</devis>
├── DATA_SOCIETE_XML\          ← paramètres société (labos, appareils plomb, entreprises…)
├── Operateurs\  Modeles\  Modeles annexes\  Dictionnaires\  logs\
├── Dossiers_DEMO\DEMO_0001 … DEMO_AUDIT_0004   ← dossiers complets fournis par LICIEL
└── Dossiers_2026\2610210001\  ← un dossier = un sous-dossier Windows
    ├── Dossier_Terrain.xml    ← vide (2 octets) dans tous les dossiers observés
    ├── XML\                   ← ★ toutes les données saisies : Table_*.xml
    ├── photos\  plan\  images\
    ├── Version\               ← archive .7z automatique à chaque enregistrement
    └── Travail_en_cours.lock  ← présent pendant l'édition (verrou)
```

- **La mission** est créée dans la partie gestion (« Créer mission » → ODM). Elle est enregistrée dans `LICIEL_Dossiers.mdb`, table `Donnees_Dossiers` d'environ 132 colonnes selon l'étude d'Hermes. Les noms des champs dans le fichier sont en Unicode : nous n'avons pas ouvert la base et nous n'y écrirons pas au début.
- Le **numéro de dossier** a la forme `AAMMJJ` + compteur (`2610210001`).
- **« Démarrer dossier »** crée le sous-dossier `Dossiers_AAAA\<n°>\` et lance la partie terrain.
- Une copie des données de mission est aussi écrite dans le dossier : `XML\Table_Admin_Donnees_Dossiers.xml` (donneur d'ordre, propriétaire, adresse du bien, date de RDV, missions cochées, opérateur…).
- **Export officiel d'un dossier : fichier `.LDossier`.** Exemple : `Eval_DPE_2020\FA4-1\Export_MI6-1.LDossier`. C'est un **ZIP standard, non chiffré** (seule sa liste de contenu a été lue), qui contient :
  - `LICIEL_Dossiers.Donnees_Dossiers.xml` : la fiche mission, en XML ISO-8859-1, avec **les vrais noms de colonnes de la base** (`id`, `Num_dossier`, `dordre_nom`, `bien_adresse`…) ;
  - une mini-base `LICIEL_Dossiers.mdb` ;
  - le dossier complet `Dossiers_2025/MI6-1/` (XML, images, archives `Version`).

  C'est le format d'échange de LICIEL entre postes. **Si LICIEL accepte d'importer un `.LDossier` que nous aurions fabriqué, on crée mission et dossier d'un coup, sans toucher à la base principale** (voir option 1 ter, question H12).

### 1.3 Format des tables `Table_*.xml`

Un fichier par table. Le nom suit le motif `Table_<Domaine>_<Nom>.xml` :
- `Admin_*` : mission, facturation, paiement, géocodage ;
- `General_*` : bien, pièces, description, photos, plan, opérateur ;
- `Z_<Module>_*` : Carrez, DPE_2020, Elec, Gaz, Amiante, CREP, Parasitaire, ERNT, Handicape, Assainissement, Conclusions.

Deux formes existent.

**Table « fiche »** (une seule ligne) :
```xml
<LiTable_Z_Carrez_General>
     <LiColonne_Doc_Remis>Néant</LiColonne_Doc_Remis>
     <LiColonne_Surface_Carrez>284,20</LiColonne_Surface_Carrez>
     ...
</LiTable_Z_Carrez_General>
```

**Table « liste »** (plusieurs lignes ; attention au `table` en minuscules dans `LiItem_table_`) :
```xml
<LiTable_General_Pieces_Toutes>
     <LiItem_table_General_Pieces_Toutes>
          <LiColonne_id_classement_champs>00000</LiColonne_id_classement_champs>
          <LiColonne_ClefComposant>2026_10_21_21_58_39_11306320074286620</LiColonne_ClefComposant>
          <LiColonne_Batiment>Appartement</LiColonne_Batiment>
          <LiColonne_Local>Sejour</LiColonne_Local>
          ...
     </LiItem_table_General_Pieces_Toutes>
</LiTable_General_Pieces_Toutes>
```

**Pièges constatés, que le générateur devra reproduire exactement :**

| Sujet | Constat |
|---|---|
| Ce n'est **pas du XML standard** | Les `&` ne sont pas échappés (ex. `<LiColonne_Annee_Construction>1780 & 1830</…>` dans `Table_Z_Elec_General.xml`). Il faut un lecteur et un écrivain « maison », pas une bibliothèque XML classique. |
| Encodage | Windows-1252, pas UTF-8 (aucun fichier UTF-8 parmi les 1 614 tables du poste). |
| Fins de ligne | Une seule fin de ligne « de structure » par fichier : `CR` (1 610 fichiers) ou `LF` (4 fichiers). Les `CRLF` n'apparaissent qu'*à l'intérieur* des valeurs multi-lignes. Indentation de 5 espaces par niveau. |
| Colonnes en double | Une même colonne peut apparaître deux fois dans une ligne, avec des valeurs différentes (vu une fois, résultats DPE d'un ancien dossier de validation). |
| Fichiers non LiTable | 27 `Table_*.xml` sont des fragments XML libres, sans racine `LiTable_` (ex. `Z_DPE_2020_Details_simulations_ERE_SR01`). |
| Nom de fichier ≠ nom de table | 220 fichiers d'audit : `Table_Z_DPE_2020_Composants_SR01.xml` contient `<LiTable_Z_DPE_2020_Composants>`. On indexe donc par nom de fichier. |
| Nombres | Virgule décimale (`2,6`, `284,20`). On trouve parfois un point (`TxtSurface>10.2`) : il faut fixer une règle par champ. |
| Booléens hétérogènes | `Vrai`/`Faux`, `0`/`1`, `True`/`False` selon les tables. |
| Dates et heures | `05/03/2025`, `18 h 40`, `01 h 00`. |
| Fautes de frappe d'origine (à garder telles quelles) | `Localistion`, `CelfComposant`, `Commantaires`, `Desciption`, `Perfixe`. |
| Clés | `ClefComposant` = horodatage `AAAA_MM_JJ_hh_mm_ss_` + nombre aléatoire. Un ancien format existe aussi (`JJ_MM_AAAA__hh_mm_ss__ms-<md5>`). |
| **Liens entre tables** | **Par le libellé** `Localistion` = « Bâtiment - Local », pas par la clé. Dans DEMO_0001, la même pièce a 3 clés différentes dans `Pieces_Toutes`, `Desciption_Pieces` et `Carrez_Details`. |
| XML imbriqué (DPE) | `LiColonne_XML_Actuel` contient un sous-document mêlant trois types de valeurs (voir plus bas). |
| Valeurs calculées stockées | Totaux Carrez, résultats DPE, textes descriptifs générés. Il faudra savoir si LICIEL les **recalcule à l'ouverture** (question H4). |

Le sous-document XML imbriqué du DPE mélange :
- des numéros d'options LICIEL (`Cmb_Composant=233`, issus des listes chiffrées) ;
- des codes ADEME publics (`enum_materiaux_structure_mur_id=2`, `tv_umur0_id=8`) ;
- des résultats de calcul (`U_calcule=2,05`, `Deperdition_thermique=34,85`).

### 1.4 Tables par module (union des 4 dossiers DEMO)

| Module | Tables |
|---|---|
| Mission / bien | `Admin_Donnees_Dossiers` (+ `_facturation`, `_paiement`, `GeoCodageBan`), `General_Bien`, `General_Bien_conclusions`, `General_Operateurs_General`, `General_Version_logiciel` |
| **Pièces** | `General_Pieces_Toutes` (liste maîtresse), `General_Pieces_Visites`, `General_Pieces_Non_Visites` |
| Description des pièces | `General_Desciption_Pieces` (une ligne par élément : Sol, Mur - A, Mur - B…, avec substrat/revêtement, dégradation et mesure CREP), `_General`, `_OPH`, `_Perval` |
| Photos / plan | `General_Photo`, `General_Photo_General`, `General_Plan`, `General_Plan_General`, `General_Plan_Images` |
| **Carrez / Boutin** | `Z_Carrez_Details`, `Z_Carrez_Resume`, `Z_Carrez_General` |
| DPE 2020 / Audit | `Z_DPE_2020_General`, `_Composants`, `_Zones_homogenes`, `_Justificatifs`, `_Resultats_Calcul`, `_Details_Calcul`, `_Senario_Details`, `_Gestion_Entretien`, `_Ecart_Reperage`, variantes `_SR01/_SR02/_ERE/_RecoN` (audit), plus `Dossier_ADEME.signed.xml` (**signé : on ne le fabrique jamais**) |
| Électricité | `Z_Elec`, `Z_Elec_General`, `Z_Elec_Piece`, `Z_Elec_Reperage_Arrete` |
| Gaz | `Z_Gaz`, `Z_Gaz_Appareil`, `Z_Gaz_General`, `Z_Gaz_General2` |
| Amiante | `Z_Amiante`, `_General`, `_prelevements`, `_doc_remis`, `_Ecart_Norme` |
| Plomb (CREP) | `Z_CREP`, `_General`, `_Etalonnage`, `_Labo`, `_recap_UD`, `_recap_UD_piece` |
| Termites / parasites | `Z_Parasitaire`, `Z_Parasitaire_General` |
| ERP / ERNT | `Z_ERNT_General`, `Z_ERNT_Kinaxia` |
| Conclusions | `Z_Conclusions`, `Z_Conclusions_Details`, `Z_Conclusions_ModuleFilRouge` |

### 1.5 Zoom sur le Carrez (cible du MVP)

Trois tables, avec un **niveau de confiance** pour chaque interprétation :

- **`Z_Carrez_Details`** contient une ligne par **opération de mesure**. Une pièce en a une ou plusieurs.
  - Colonnes : `ClefComposantPiece`, `ClefComposant`, `Localistion`, `Surface_1..4`, `Commantaires`, `Data1..Data12`, `Code_Chk_Habitable`, `Code_Outil_Mesure_Type/Forme/XML`.
  - Exemple « Étage 2 - Comble non habitable 1 » : une ligne `+43,5` (sol, Carrez et habitable), puis une ligne `-21,1` (Carrez et habitable seulement ; `Data1=Faux`, `Data2=Vrai`, `Data4=0`, `Data5=21,1`). On obtient 22,4 m² Carrez pour 43,5 m² au sol, avec le commentaire « Hauteur inférieure à 1,80 m ».
- **`Z_Carrez_Resume`** contient une ligne par **pièce** : surfaces totalisées, `Commantaires`, `Data1` = hauteur sous plafond (2,5 ; 2,7…).
- **`Z_Carrez_General`** contient les totaux du lot : `Surface_Carrez`, `Surface_Habitable`, `Surface_Sol`, `Surface_Ref`, `HSP`, `Doc_Remis`.

| Interprétation | Confiance | Preuve |
|---|---|---|
| `Surface_2` = surface au sol | **Forte** | Somme des `Surface_2` du résumé = `Surface_Sol` (DEMO_0001 : 325,80 ; DEMO_0002 : 100,76). |
| `Surface_1` = Carrez, `Surface_3` = habitable (Boutin) | Moyenne | Les sommes correspondent bien, mais Carrez = habitable dans les 3 démos, donc l'ordre exact n'est pas prouvé. |
| `Surface_4` = surface de référence | Moyenne | Toujours 0 dans les démos. |
| Dans `Details` : `Data1=Vrai` → ajouter, `Data2=Vrai` → retrancher, `Data5` = valeur saisie (positive) | **Forte** | Cohérent avec toutes les lignes des 3 démos (ex. Étage 1 - Pièce 4 : `+9,04` puis `-1,65`). |
| `Data3=1` → la ligne compte en Carrez/habitable, `Data4=1` → elle compte en surface au sol | **Forte** | Garage, véranda, escalier : `Data3=0` et `Data4=1`, donc 0 en Carrez mais compté au sol. Retrait < 1,80 m de DEMO_0001 : `Data3=1` et `Data4=0`, donc déduit du Carrez mais pas du sol. |
| `Resume.Data2 = "OUI"` → pièce annexe, exclue des totaux | Forte | DEMO_0003 : l'écart de 82 m² entre la somme « au sol » (368,87) et `Surface_Sol` (286,87) = Garage - Pièce 1 (50) + Garage - Pièce 2 (32), les deux seules pièces marquées `OUI`. |
| `Resume.Data1` = hauteur sous plafond de la pièce | Forte | 2,5 ; 2,7 ; 2,83… |
| `Code_Outil_Mesure_*` = trace de l'outil de mesure (forme, télémètre) | Faible | Toujours vide dans les démos. |
| `Code_Chk_Habitable` | Inconnue | 1 pour certaines pièces, 0 pour d'autres, sans lien évident. |

Deux constats sur les données de démo :
- Plusieurs nombres de `Details` ont perdu leur virgule (`1183605` pour 11,83605 m²), alors que `Resume` est juste (11,83). Il ne faut donc pas recalculer les surfaces à partir de `Details` sans précaution.
- Dans DEMO_0001, deux lignes Carrez (« RDCH - Pièce 1/2 ») ne correspondent à aucune pièce de la liste.

La commande `diagauto inspect` affiche ces contrôles.

---

## 2. Architecture cible

### 2.1 Vue d'ensemble

```
 SUR PLACE                         AU BUREAU (PC Windows du diagnostiqueur)
┌──────────────────────┐          ┌────────────────────────────────────────────────────────┐
│ ① App terrain        │  JSON    │ ③ Moteur de conversion        ④ Injecteur              │
│  mobile/tablette     │ ───────► │  - validation règles métier   - trouve le dossier       │
│  hors ligne          │ (sync ou │  - mapping modèle → tables       LICIEL n° XXXXXXXXXX   │
│  - pièces, mesures   │  fichier)│    LICIEL (par version)       - refuse si LICIEL ouvert │
│  - dictée vocale     │          │  - écrivain fidèle               (fichier .lock)        │
│  - photos            │          │    (cp1252, CR, virgules)     - sauvegarde avant         │
│  - laser Bluetooth   │          │                               - écrit XML\Table_*.xml    │
└──────────────────────┘          │                               - journal + récap PDF     │
          │                       └───────────────────────────┬────────────────────────────┘
          ▼                                                   ▼
 ② MODÈLE DE DONNÉES COMMUN                        ⑤ LICIEL (inchangé)
   « Dossier terrain » (JSON versionné,              ouvre le dossier → recalcule →
   indépendant de LICIEL)                            le diagnostiqueur RELIT, VALIDE, ÉDITE
```

### 2.2 Les briques

**① App terrain.**
- Application web installable (PWA) qui fonctionne sur iPhone, Android et tablette Windows, **hors ligne** (stockage local, synchronisation au retour du réseau).
- Saisie rapide pensée pour une main : pièces par boutons (Séjour, Chambre n…), mesures, hauteur sous plafond, cases « < 1,80 m », « annexe », photos rattachées à la pièce.
- **Dictée** : la transcription est transformée en champs **proposés**, que le diagnostiqueur valide d'un geste. Jamais de remplissage silencieux. Si une info manque, le champ reste vide et signalé.
- **Télémètre laser** : Web Bluetooth fonctionne sur Android/Chrome mais **pas sur iPhone (Safari)**. Le choix du matériel (question N4) décidera si l'on passe à une app native (Capacitor) pour iOS.

**② Modèle de données commun « Dossier terrain ».**
- Format JSON, versionné, **décrit en termes métier et non en colonnes LICIEL**.
- On peut ainsi changer de cible (autre version de LICIEL, autre logiciel, passerelle officielle) sans toucher à l'app.
- Chaque valeur porte sa **provenance** (saisie, dictée, laser, photo) et un **statut** (à vérifier / validée).

Esquisse pour le MVP :
```json
{
  "version_modele": "0.1",
  "dossier": { "numero_liciel": "2610210001", "date_visite": "2026-10-21", "operateur": "…" },
  "pieces": [
    {
      "id": "p5", "batiment": "Étage 2", "nom": "Comble aménagé", "visitee": true,
      "hauteur_sous_plafond_m": 2.60, "annexe": false, "commentaire": "Hauteur inférieure à 1,80 m",
      "mesures": [
        { "op": "+", "forme": "rectangle", "longueur_m": 7.25, "largeur_m": 6.00, "surface_m2": 43.50,
          "compte_dans": ["carrez", "habitable", "sol"], "source": "laser" },
        { "op": "-", "motif": "hauteur < 1,80 m", "surface_m2": 21.10,
          "compte_dans": ["carrez", "habitable"], "source": "saisie" }
      ]
    }
  ]
}
```

**③ Moteur de conversion** (bibliothèque Python, testée automatiquement).
1. *Lecteur/écrivain fidèle* des `Table_*.xml` : relire puis réécrire un dossier LICIEL **à l'octet près**.
2. *Règles métier* explicites et testées : exclusion < 1,80 m, annexes, lot < 8 m², arrondis. On s'appuie sur les textes (loi Carrez, Code de la construction pour la surface habitable) et on n'invente rien.
3. *Mapping* déclaratif modèle → colonnes, avec un « profil » par version de LICIEL.

**④ Injecteur Windows** : petit programme en ligne de commande, plus tard un bouton.
- N'écrit **que** dans `C:\LICIEL_Diagnostics\Dossiers_AAAA\<n°>\XML\` d'un dossier **déjà créé par LICIEL**.
- Refuse si `Travail_en_cours.lock` existe (dossier ouvert).
- Sauvegarde le dossier avant d'écrire, et produit un **récapitulatif** de ce qui a été injecté, pour faciliter la relecture.

**⑤ LICIEL** reste maître :
- création de la mission ;
- calculs officiels (moteur DPE, totaux) ;
- édition et signature du rapport ;
- dépôt ADEME.

### 2.3 Options d'injection, classées

| Rang | Option | Couverture | Robustesse | Effort | Statut / remarque |
|---|---|---|---|---|---|
| **1** | **Générer les `Table_*.xml` d'un dossier créé par LICIEL**, LICIEL fermé (écriture directe) | Tout ce qui est stocké en XML : pièces, Carrez, description, puis les autres modules | Moyenne : format non documenté, qui peut évoluer à chaque mise à jour. On compense par des tests de non-régression sur les dossiers DEMO et Eval. | Moyen | **Voie principale du MVP.** Les pièces sont testables dès maintenant (la démo enregistre les parties générales). Le Carrez demande une licence. |
| **1 bis** | **Même génération, mais dans un « dossier source » séparé, puis fusion par la fonction officielle « Terrain › Importation »** | Pièces, description, amiante, termites, plomb (cumul possible). DPE et Élec ne se cumulent pas. Carrez : inconnu. | Meilleure : c'est LICIEL qui intègre les données. | Faible en plus du rang 1 | **À tester en parallèle.** Variante plus sûre là où elle s'applique. |
| **1 ter** | **Fabriquer un export `.LDossier`** (ZIP : fiche mission XML + mini-base + dossier avec nos tables), puis l'importer par la fonction officielle d'import de dossier | Mission + toutes les tables | Bonne si LICIEL l'accepte : il crée lui-même la mission et le dossier | Faible en plus du rang 1, sauf si la mini-base `.mdb` doit être fabriquée (inconnu) | **Découvert à l'étape E1, à tester par Hermes (H12).** Pourrait éviter de créer la mission à la main. |
| **2** | **Imports officiels ciblés** | Partielle | Bonne (supportée par l'éditeur) | Variable | Voir le détail sous le tableau. |
| **3** | **Passerelle officielle LICIEL sur devis** (« LOGICIEL Externe » : import d'un format XML/Excel défini par nous) | À définir (idéalement tout) | **Excellente** (maintenue par l'éditeur, vaut accord écrit) | Coût et délai côté LICIEL (analyse 80 € HT + développement) | **À demander dès maintenant, en parallèle** (question N2). Pas d'API publique aujourd'hui. |
| **4** | **Automatisation de l'interface** (piloter les écrans LICIEL comme un humain, via UI Automation / pywinauto) | Tout ce qu'un humain peut saisir | Faible : lent, fragile aux mises à jour et à l'affichage | Élevé | **Dernier recours**, ou « colle » ponctuelle (ex. ouvrir un dossier, cliquer un import officiel). |

Imports officiels utiles (rang 2) :
- **Import d'ODM** générique (Excel/XML/CSV, option à 9 € HT/mois sur demande) pour créer les missions ;
- **XML ADEME** pour le DPE/audit (format public, à évaluer) ;
- imports **plomb** (Excel, appareils Fondis/Niton…) ;
- **plans** DXF/DWG/PDF/images ;
- Carrez : **WinCarrez**, **Measurix v4.3**, **télémètre Bluetooth Leica DISTO** (formats à documenter).

**Exclu** (règles du projet et licence LICIEL) :
- toucher aux fichiers d'installation, aux référentiels chiffrés `DATA_XML_SAV` ou aux exécutables ;
- décompiler ;
- fabriquer des `*.signed.xml`.

**À éviter tant que possible** : écrire dans `LICIEL_Dossiers.mdb`. Ce n'est pas protégé, mais c'est la base de gestion du cabinet et une corruption coûterait cher. La mission est donc créée par LICIEL : à la main au début, puis par l'import d'ODM officiel.

**Point juridique à cadrer.** Les CGV LICIEL interdisent notamment « décompilation, analyse fonctionnelle… dans la limite de ce que permet le Code de la propriété intellectuelle ». Lire et écrire les fichiers de *nos propres dossiers* relève à notre sens de l'interopérabilité, mais ce n'est pas un avis juridique. L'option 3 (demande officielle à LICIEL) règle la question proprement. **Décision à prendre par Noah (N2).**

---

## 3. Plan de MVP en étapes courtes

Chaque étape a un livrable vérifiable. On ne passe à la suivante que si le critère est atteint.

| Étape | Contenu | Livrable / critère de réussite | Prérequis |
|---|---|---|---|
| **E0** ✅ | Cadrage (ce document) | Questions de la section 4 tranchées | — |
| **E1** ✅ | **Lecteur/écrivain fidèle** des `Table_*.xml` (paquet Python `diagauto.liciel_xml`), avec tests automatiques, commandes `diagauto inspect` et `diagauto verifier` | **Atteint le 21/10/2026.** Les 296 tables des fixtures (4 DEMO + 5 Eval) et les 1 614 tables présentes sur le poste sont relues puis réécrites **identiques à l'octet près** ; 624 tests pytest passent. | — |
| **E2** | **Preuve d'injection n°1 : les pièces.** Je génère, dans le dépôt, une version modifiée de `Table_General_Pieces_Toutes` (+ 2 pièces). **Hermes** la pose dans un dossier **jetable**, LICIEL fermé, et vérifie le résultat (H2 : aucune écriture de ma part sous `C:\LICIEL_*`). Variantes à tester par Hermes : 1 bis (« Terrain › Importation ») et 1 ter (import d'un `.LDossier`). | LICIEL ouvre le dossier, les pièces apparaissent, on peut enregistrer et rouvrir sans erreur. On sait aussi s'il faut remplir `Pieces_Visites` nous-mêmes. | Hermes disponible pour le test. La version d'essai suffit. |
| **E3** | **Cartographie Carrez par saisie contrôlée.** Noah ou Hermes saisit dans LICIEL 4 cas : pièce rectangulaire simple ; pièce en L (2 ajouts) ; comble avec retrait < 1,80 m ; cave/balcon annexe. Comparaison des fichiers avant/après. | Chaque colonne de `Z_Carrez_*` documentée (`Surface_1..4`, `Data1..12`, `Code_Chk_Habitable`). On sait si LICIEL **recalcule** `Resume`/`General` à l'ouverture. | **Licence LICIEL** (N1) |
| **E4** | **Générateur Carrez** : modèle JSON → 3 tables Carrez (+ pièces), avec tests unitaires des règles | Pour 3 logements réels, le rapport Carrez édité par LICIEL après injection est **identique** à celui obtenu par saisie manuelle (surfaces, commentaires, totaux). | E1 à E3 |
| **E5** | **Saisie terrain v0 + injecteur.** Page web mobile hors ligne (pièces, mesures, HSP, cases < 1,80 m / annexe, photos), export JSON. Commande `diagauto injecter <n° dossier> <fichier.json>`. | Un diagnostiqueur saisit un logement sur téléphone, puis injecte en moins d'une minute au bureau. | E4, choix du matériel (N4) |
| **E6** | **Pilote réel** : 2–3 visites avec un diagnostiqueur Imodiag | Temps de ressaisie mesuré avant et après, liste des irritants, décision « on continue / on ajuste ». | N10 |

**Après le MVP**, dans cet ordre indicatif, à confirmer avec Noah (N6) :
1. Dictée vocale → champs (avec validation humaine).
2. Télémètre Bluetooth.
3. Description des pièces (sols/murs/plafonds), qui sert ensuite à l'amiante, au CREP et aux termites.
4. **DPE** : évaluer d'abord l'import XML ADEME, sinon la génération des tables en s'appuyant sur le corpus `Eval_DPE_2020`.
5. Électricité, gaz, amiante, plomb.

**Risques principaux et parades :**

| Risque | Parade |
|---|---|
| LICIEL ignore ou écrase nos fichiers (E2 échoue) | Variante 1 bis, passerelle officielle, ou automatisation de l'interface en dernier recours |
| Une mise à jour LICIEL change le format | Tests de non-régression ; profils par version ; détection de version (`Table_General_Version_logiciel.xml`) avant toute injection |
| Erreur réglementaire | Règles métier écrites à partir des textes, testées ; aucun champ inventé ; relecture obligatoire dans LICIEL |
| Pas de licence = pas de preuve Carrez | Bloquant n°1 (N1) |

---

## 4. Questions à trancher

### Pour Noah

- **N1 — Licence.** Peut-on obtenir rapidement une licence LICIEL (même temporaire) pour ce PC, ou l'accès à un poste licencié d'un diagnostiqueur ? La démo **n'enregistre pas** Carrez, DPE et Élec, et elle expire après 10 jours. C'est le **bloquant n°1**.
- **N2 — Relation avec l'éditeur LICIEL.** Êtes-vous d'accord pour contacter LICIEL ? Il s'agirait (a) de demander une passerelle d'import officielle sur devis (analyse 80 € HT) et (b) d'obtenir un accord écrit sur la lecture/écriture des fichiers de nos dossiers. Avez-vous un contact chez eux ? Imodiag a-t-il un poids commercial (nombre de licences) ?
- **N3 — Parc LICIEL des diagnostiqueurs.**
  - Quelle version utilisent-ils, et les mises à jour sont-elles automatiques ?
  - Où sont stockés les dossiers : sur le PC (`C:\LICIEL_Diagnostics`), sur un serveur ou dans le cloud LICIEL ?
  - Saisissent-ils sur tablette Windows sur place, ou tout au bureau après la visite ?
- **N4 — Matériel terrain.**
  - Téléphone iPhone ou Android ? Tablette ?
  - Télémètres laser utilisés (marque et modèle exacts, ex. Leica DISTO D2/D810, Bosch GLM…), avec ou sans Bluetooth ?
  - Y a-t-il du réseau sur place, souvent ou rarement ?
- **N5 — Pratique actuelle du métrage.**
  - Comment mesurent-ils aujourd'hui : croquis papier, magicplan, Measurix, WinCarrez, Bluetooth dans LICIEL ?
  - Comment décomposent-ils une pièce irrégulière ?
  - Qui calcule les retraits < 1,80 m : sur place ou au bureau ?
- **N6 — Priorités.** Confirmez-vous l'ordre pièces + Carrez/Boutin → DPE → élec/gaz → amiante/plomb ? Quel diagnostic coûte le plus de temps de ressaisie aujourd'hui (minutes par dossier, si possible) ?
- **N7 — Ordres de mission.**
  - Comment arrivent-ils : plateforme Imodiag, LiciWeb, e-mail, téléphone ?
  - Veut-on que DiagAuto crée la mission dans LICIEL, ou le diagnostiqueur la crée-t-il toujours lui-même avant la visite ?
- **N8 — Exemples réels.** Pouvez-vous fournir 3 à 5 dossiers LICIEL réels **anonymisés** (dont au moins 2 avec Carrez et 1 avec DPE) **avec les notes de terrain correspondantes** (photos du croquis, carnet, notes) ? C'est indispensable pour concevoir une saisie terrain qui colle aux habitudes.
- **N9 — Données et IA.**
  - Accepte-t-on que photos, adresses et dictées transitent par un serveur (hébergé en UE) et par un service d'IA en ligne pour la transcription ?
  - Ou faut-il du « tout local » ? Cela change le coût et la qualité de la dictée.
- **N10 — Pilote.** Quel(s) diagnostiqueur(s) pour tester, et à partir de quand ?
- **N11 — Forme du produit.** Une application web installable (sans App Store) vous convient-elle pour démarrer ? Y a-t-il un budget d'hébergement, ou une préférence d'outils ?
- **N12 — Outils LICIEL existants.** Les diagnostiqueurs utilisent-ils déjà l'application mobile LiciWeb, LICIEL Cloud, l'assistant vocal LiciA ou la saisie Bluetooth ? Si oui, qu'est-ce qui ne leur suffit pas ? Cela précise ce que DiagAuto doit apporter de plus.

### Pour Hermes

*Réponses reçues le 21/10/2026 :*
- **H1 = oui** : 4 dossiers DEMO et 5 Eval copiés dans `tests/fixtures/` et versionnés.
- **H2** : **aucune écriture de ma part sous `C:\LICIEL_*`**. Hermes fera les tests d'écriture lui-même, plus tard, sur un dossier jetable.
- **H11** : branche `main` ; je commite par petites étapes, Hermes relit.
- **H3 à H10** seront testées progressivement par Hermes.
- Cadre juridique confirmé : interopérabilité de nos dossiers uniquement, pas de décompilation, pas de fichiers chiffrés.

- ~~H1 — Accès.~~ Réglée (voir ci-dessus).
- ~~H2 — Écriture de test.~~ Réglée : c'est Hermes qui écrit.
- **H3 — « Ré-importer dossiers orphelins » / « Terrain › Importation ».**
  - Peux-tu tester si LICIEL accepte un dossier posé sur disque sans entrée dans la base `.mdb` ?
  - Et si « Importation » d'un dossier source ramène bien les pièces, et éventuellement le Carrez ?
- **H4 — Recalcul.** Quand on modifie une table puis qu'on ouvre le dossier, LICIEL recalcule-t-il les totaux (`Z_Carrez_Resume`/`General`, et plus tard les résultats DPE) ? Ou affiche-t-il les valeurs du fichier telles quelles ? À tester dès qu'on a une licence.
- **H5 — Contrôle d'intégrité.**
  - Y a-t-il un contrôle entre `XML\` et les archives `Version\*.7z` (somme de contrôle, restauration automatique) ?
  - LICIEL tolère-t-il une colonne manquante ou une table absente (valeurs par défaut) ?
  - Accepte-t-il `&amp;` ?
- **H6 — Base `.mdb`.**
  - Est-elle protégée par mot de passe ?
  - Quand le dossier change, faut-il mettre à jour quelque chose dans la base (état, surface, conclusion affichée dans la gestion des dossiers) ?
  - Peux-tu exporter, sur une **copie**, la liste des colonnes de `Donnees_Dossiers` ?
- **H7 — Imports Carrez existants.** Où se trouvent exactement « Imports spéciaux › WinCarrez », l'import Measurix et l'« Assistant Télémètre » ? Peut-on en voir la fenêtre ou obtenir un exemple de fichier attendu ? Si l'un de ces formats est simple, c'est un **import officiel** possible pour le Carrez.
- **H8 — Import ODM.**
  - Quels formats le bouton « Importer » de l'ordre de mission accepte-t-il sans l'option payante ?
  - Le modèle Excel « paramétrable » (ligne 1 = noms des champs de la base) est-il disponible dans le wiki ?
- **H9 — XML ADEME.** Le bouton d'import XML ADEME existe-t-il dans le module DPE, ou seulement dans l'Audit ? Accepte-t-il un XML jamais déposé à l'ADEME ? C'est déterminant pour la stratégie DPE.
- **H10 — Libellés des pièces.** Le libellé de liaison est « Bâtiment - Local ». Comment LICIEL construit-il ce libellé quand il y a un numéro automatique ou des adjectifs (balises `{0}{1}{2}{3}`) ? Il faut le reproduire à l'identique, sinon le Carrez ne se rattache pas à la pièce.
- ~~H11 — Git.~~ Réglée : branche `main`.
  - Aucune identité git n'était configurée sur le poste. Les commits utilisent une identité **locale au dépôt** (`DiagAuto` + e-mail du compte), à remplacer si besoin par `git config user.name/user.email`.
- **H12 — Import d'un `.LDossier` (nouveau).**
  - LICIEL sait-il importer un fichier `.LDossier` (menu d'import de dossier ZIP) ?
  - Si oui, la mini-base `LICIEL_Dossiers.mdb` contenue dans le ZIP est-elle indispensable, ou la fiche `LICIEL_Dossiers.Donnees_Dossiers.xml` suffit-elle ?
  - Test proposé : exporter le dossier `2610210001` en `.LDossier`, puis le réimporter sous un autre numéro. Si l'import fonctionne, c'est peut-être la voie d'injection la plus « officielle » sans passerelle payante.

---

*Prochaine action proposée : préparer pour Hermes le fichier de test de l'étape E2 (liste des pièces modifiée, générée par `diagauto.liciel_xml`, livrée dans le dépôt et non dans LICIEL) ; en parallèle, attendre la licence (N1) pour E3.*
