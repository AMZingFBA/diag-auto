# Projet DiagAuto — remplir LICIEL automatiquement après la visite

## Contexte métier
- Porteur : Noah (N.Z Consulting / Imodiag, plateforme de diagnostics immobiliers en France). Il parle français, non technique : toute communication finale en français simple.
- Problème : après le rendez-vous, les diagnostiqueurs perdent des heures à ressaisir dans LICIEL DIAGNOSTICS V4 (logiciel de référence du métier) tout ce qu'ils ont noté sur place : croquis/plan du logement, mesures pièce par pièce (lasers), murs/isolation/menuiseries, chauffage/ECS/ventilation (DPE), observations électricité (NF C16-600) et gaz (NF P45-500), repérage amiante (zones homogènes, prélèvements), plomb (CREP, mesures fluo X), termites, Carrez/Boutin, ERP, audit énergétique.
- Objectif : un outil qui prend les données de terrain (saisie mobile rapide, dictée vocale, photos, plan, éventuellement relevés laser) et produit AUTOMATIQUEMENT le dossier LICIEL rempli, sans que le diagnostiqueur ne ressaisisse rien. Le diagnostiqueur garde la responsabilité : il relit et valide dans LICIEL avant d'éditer le rapport.

## Environnement
- Windows 11, LICIEL installé en local : C:\LICIEL_Programmes\LICIEL Diagnostics (version 4.280, données en XML : DATA_XML, DATA_XML_SAV, Data9_General_*.xml, DPE.dll, .NET). Version d'essai (pas de licence) : ne JAMAIS modifier les fichiers d'installation ; travailler sur des copies.
- Recherches en cours (par Hermes, l'agent qui orchestre) — à lire dès qu'ils existent :
  - C:\Users\conta\Documents\liciel\guide-0-general.md (workflow général LICIEL)
  - C:\Users\conta\Documents\liciel\guide-1-dpe-audit.md
  - C:\Users\conta\Documents\liciel\guide-2-amiante-plomb-termites.md
  - C:\Users\conta\Documents\liciel\guide-3-elec-gaz-carrez-erp.md
  - C:\Users\conta\Documents\liciel\etude-technique-import.md (comment injecter des données dans LICIEL : fichiers XML, imports officiels, XML ADEME, automatisation d'interface)
  - Hermes crée aussi un dossier de démonstration dans LICIEL et comparera les fichiers avant/après pour cartographier les champs : résultat dans C:\Users\conta\Documents\liciel\dossier-test\

## Règles de travail
- Pas de contournement de licence, pas de rétro-ingénierie de protection, pas de modification de LICIEL lui-même. Seules voies acceptables : imports/exports officiels, génération de fichiers dossier au format que LICIEL lit, automatisation de l'interface utilisateur.
- Exactitude réglementaire (DPE 3CL-2021, normes NF) : ne rien inventer.
- Commencer petit : un MVP sur UN module (probablement Carrez/Boutin ou dossier + pièces, puis DPE), prouvé de bout en bout.
- Code dans ce dossier, git, README en français.
