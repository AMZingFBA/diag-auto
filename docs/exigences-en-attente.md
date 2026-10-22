# Exigences en attente (à transmettre à Claude au prochain lancement)

*(Les étapes 2 à 12 de Noah du 22/10/2026 sont intégrées ; leur texte est gardé dans [historique-exigences.md](historique-exigences.md). Reste l'étape 13.)*

## Étape 13 (ENVOYÉE le 22/10 16:35) — Le DPE se fait de façon GLOBALE, pas pièce par pièce (consigne de Noah, 22/10, à envoyer après l'étape 12)
- Dans le DPE, on décrit l'ENVELOPPE du logement (tout ce qui l'entoure), pas chaque pièce. Les murs entre pièces intérieures ne comptent pas (« on s'en fiche »).
- Donc le système (assistant live + checklist + extraction + pont LICIEL) doit raisonner par ORIENTATION : mur ouest, mur nord, mur sud, mur est. Pour chaque mur extérieur : donne sur la rue / l'extérieur / un voisin / local non chauffé, isolation, nombre de fenêtres et portes sur ce mur.
- Les données sont globales à l'appartement / la maison : un « mur ouest » = tous les murs ouest du logement, toutes pièces confondues. Ne PAS créer un mur par pièce pour le DPE. Les pièces servent pour Carrez et le repérage, pas pour le DPE.
- Cas à gérer : UN MÊME MUR dont une partie donne sur l'extérieur et l'autre partie sur un voisin → il faut pouvoir scinder le mur en segments (ex. « mur est : 60 % sur voisin, 40 % sur extérieur », avec surface/longueur de chaque partie, fenêtres rattachées au bon segment).
- À adapter : checklist-dpe.md, questions de l'assistant (ne pas demander « quels murs dans cette pièce » mais « ce mur donne sur quoi ? »), schéma des données, extraction, rejeux de test, tests pytest, README.
- Noah demande qu'on lui envoie un message quand c'est terminé.
