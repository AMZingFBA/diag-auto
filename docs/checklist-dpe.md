# Données à relever pour un DPE logement (méthode 3CL-2021) — checklist terrain

**Principe (étape 13, décision de Noah du 22/10/2026)** : le DPE décrit l'**enveloppe du logement** (tout ce qui
l'entoure) et ses équipements, **pas chaque pièce**. On raisonne par **côté** (nord, est, sud, ouest) :
- un « mur ouest » = tous les murs ouest du logement, toutes pièces confondues ; on ne crée pas un mur par pièce ;
- les murs entre deux pièces chauffées du logement ne comptent pas (hypothèse 3CL : paroi sur local chauffé non
  déperditive) ;
- un même côté peut avoir **plusieurs parties** (« mur est : 60 % sur le voisin, 40 % sur l'extérieur »), chacune avec
  sa part ou sa longueur, et les fenêtres sur la bonne partie (une fenêtre ne s'ouvre pas sur un voisin) ;
- les fenêtres et portes sont comptées **mur par mur** ;
- les pièces servent au Carrez/Boutin et au repérage, jamais au DPE : l'assistant ne demande pas dans quelle pièce on est.

## Administratif — récupéré automatiquement à la création du devis/dossier (pas sur place)
- Saisis par le client au devis : adresse, propriétaire/donneur d'ordre, maison/appartement, année de construction (approx.), surface déclarée
- Complétés automatiquement : n° RNB et altitude (API RNB / IGN depuis l'adresse), année de construction et caractéristiques connues (base BDNB / ancien DPE ADEME), département
- À seulement CONFIRMER sur place
- Adresse exacte + identifiant bâtiment RNB, département, altitude
- Propriétaire / donneur d'ordre (nom, adresse, SIREN si pro), consentement
- Type : maison / appartement / immeuble ; année de construction (+ justificatif)
- Ancien DPE éventuel (n° ADEME)

## Dimensions
- Surface habitable (pièce par pièce : c'est le seul usage des pièces, avec le Carrez), hauteur sous plafond moyenne
- Appartement : étage, nb de logements, surface du bâtiment, mitoyennetés (dessus/dessous/côtés chauffés ?)
- Inertie (lourde/légère : matériaux murs/planchers)

## Murs de l'enveloppe (par côté, puis par partie)
- Côté (orientation : boussole du téléphone, ou dit) ; surface, ou part / longueur de chaque partie d'un même côté
- Donne sur : extérieur / local non chauffé (garage, cave, cage d'escalier…) / voisin ou local chauffé (rien d'autre à
  relever)
- Fenêtres et portes sur ce mur (nombre et description, ci-dessous)
- Matériau et épaisseur
- Isolation : non / ITI / ITE / ITR ; épaisseur ou R de l'isolant ou année d'isolation ; justificatif

## Plafonds / toiture (une fois pour le logement ; une partie différente si elle est dite)
- Surface ; donne sur : combles perdus / aménagés / terrasse / local chauffé
- Type de structure ; isolation (épaisseur/R/année)

## Planchers bas (une fois pour le logement ; une partie différente si elle est dite)
- Surface ; donne sur : terre-plein / vide sanitaire / sous-sol / garage / local chauffé
- Périmètre sur l'extérieur ; type ; isolation

## Fenêtres et portes-fenêtres (par type)
- Mur qui les porte (donc leur côté : utile aux apports solaires), dimensions (L × H) et nombre
- Menuiserie (PVC, bois, alu, rupteur…), vitrage (simple/double/triple, lame d'air, gaz), double fenêtre
- Position dans le mur (nu int./tunnel/nu ext.), dormant large, retour d'isolant
- Volets / fermetures ; masques (balcon, bâtiment en face, relief)
- Vérandas/loggias fermées

## Portes d'entrée
- Surface, type (bois, PVC, métal, vitrée, isolée), donne sur extérieur ou palier

## Ponts thermiques
- Longueurs des jonctions : murs/planchers, murs/plafonds, murs/refends, menuiseries/murs

## Chauffage (par installation)
- Individuel ou collectif ; énergie (gaz, fioul, élec, bois, PAC, réseau de chaleur…)
- Générateur : type, marque/modèle, année, puissance (photo de la plaque)
- Émetteurs : radiateurs, plancher chauffant, convecteurs… ; température (basse/haute), année
- Régulation (thermostat, robinets thermostatiques, programmation), réseau isolé ou non
- Chauffage d'appoint, surface chauffée par chaque système

## Eau chaude sanitaire
- Système (chaudière, ballon élec, thermodynamique, solaire…), énergie, année, volume du ballon
- Veilleuse, accumulation, réseau isolé, installation < 5 ans

## Climatisation
- Présence, surface climatisée, type, année (toute PAC air/air = aussi climatisation)

## Ventilation
- Type : naturelle (grilles/conduits), VMC simple flux autoréglable/hygro, double flux…
- Année d'installation (si différente de la construction)

## Production d'énergie
- Panneaux photovoltaïques (surface, orientation), autre production

## Justificatifs et photos
- Photos : façades, chaque mur/isolant, fenêtres, chaudière + plaque, ballon, VMC, compteur
- Factures de travaux, attestations d'isolation, notices des équipements
