# Moteur de 8th Wall (binaire distribué)

Copie, sans aucune modification, du paquet npm `@8thwall/engine-binary` version **1.0.0** (janvier 2026) : `xr.js`,
`xr-slam.js` et `resources/` (le moteur de visage `xr-face.js` n'est pas copié). Il donne la position et l'orientation
du téléphone en 3D, en mètres (SLAM), dans Safari sur iPhone, qui n'a pas de réalité augmentée. Utilisé par
`web/suivi-xr8.js` pour le tracé guidé du plan (amiante, plomb).

**Licence : propriétaire, pas libre** (`LICENSE`, « XR Engine License Agreement », Niantic Spatial, Inc.). Choisi par Noah
le 25/10/2026 (option 1). Points à retenir :

- gratuit ; distribution permise seulement sous sa forme d'origine ; ni modification, ni décompilation, ni ingénierie
  inverse (§ 1.2) ;
- exclus : un produit ou service payant dont la valeur vient « entièrement ou essentiellement » du moteur (§ 1.2).
  **Hypothèse** : le croquis n'est qu'une partie de DiagAuto, ce qui devrait le permettre ; **à faire confirmer par un
  juriste avant tout usage commercial** ;
- attribution visible obligatoire (§ 1.3) : la mention « Suivi : 8th Wall © Niantic Spatial, Inc. — licence » est
  affichée pendant la visite, avec un lien vers ce fichier ;
- licence révocable (préavis de 5 jours, § 7), sans garantie, préversion dont l'interface peut changer : si elle
  disparaît, l'application revient à son propre suivi par le sol filmé (`web/odometrie.js`).

Source : https://www.npmjs.com/package/@8thwall/engine-binary ; documentation : https://8thwall.org/docs/engine/overview.
