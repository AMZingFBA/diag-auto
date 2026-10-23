"use strict";
// Cap de la caméra arrière (0 = nord, 90 = est), calculé par la matrice de rotation complète du téléphone (étape 7).
//
// Le téléphone donne son orientation par trois angles (alpha, beta, gamma, spécification W3C « DeviceOrientation ») :
// la matrice R = Rz(alpha)·Rx(beta)·Ry(gamma) passe des axes du téléphone (x vers la droite, y vers le haut de l'écran,
// z sortant de l'écran) aux axes de la Terre (x vers l'est, y vers le nord, z vers le haut). La caméra arrière vise
// -z : son cap est la direction, à l'horizontale, du vecteur R·(0, 0, -1). Juste quel que soit le tenu (droit,
// incliné, en paysage).
//
// iPhone : alpha n'a pas d'origine fixe, et webkitCompassHeading donne le cap du HAUT du téléphone (axe y), pas
// celui de la caméra. On mesure donc l'écart entre ce cap et le cap du haut calculé avec l'alpha relatif, quand le
// haut du téléphone est assez horizontal (sinon son cap n'a pas de sens) ; le cap de la caméra est alors son cap
// relatif plus cet écart. L'écart reste valable tant que le gyroscope ne dérive pas (quelques degrés par visite).
// Fichier chargé par la page, et testé par tests/test_boussole_js.py (Node).

(function (racine) {
  const RAD = Math.PI / 180;
  const CAMERA = [0, 0, -1];
  const HAUT = [0, 1, 0];

  function matrice(alpha, beta, gamma) {
    const [ca, sa] = [Math.cos(alpha * RAD), Math.sin(alpha * RAD)];
    const [cb, sb] = [Math.cos(beta * RAD), Math.sin(beta * RAD)];
    const [cg, sg] = [Math.cos(gamma * RAD), Math.sin(gamma * RAD)];
    return [
      [ca * cg - sa * sb * sg, -sa * cb, ca * sg + sa * sb * cg],
      [sa * cg + ca * sb * sg, ca * cb, sa * sg - ca * sb * cg],
      [-cb * sg, sb, cb * cg],
    ];
  }

  function appliquer(R, v) {
    return R.map((ligne) => ligne[0] * v[0] + ligne[1] * v[1] + ligne[2] * v[2]);
  }

  // Cap (0 à 360) de la projection horizontale du vecteur v du téléphone ; null s'il est presque vertical.
  function capVecteur(R, v, horizontaliteMin = 0.05) {
    const [est, nord] = appliquer(R, v);
    if (Math.hypot(est, nord) < horizontaliteMin) return null;
    return (Math.atan2(est, nord) / RAD + 360) % 360;
  }

  // Android (alpha absolu, « deviceorientationabsolute ») : cap de la caméra arrière.
  function capCamera(alpha, beta, gamma) {
    return capVecteur(matrice(alpha, beta, gamma), CAMERA);
  }

  // Élévation de la caméra (0 = horizontale, positive vers le plafond) et roulis de l'image (où se trouve le haut du monde
  // dans l'image, en degrés depuis le haut de l'image vers sa droite : 0 = image droite, ±90 = téléphone en paysage).
  // Justes en portrait comme en paysage (beta seul ne l'est qu'en portrait). Ne dépendent pas d'alpha (iPhone : relatif).
  function poseCamera(alpha, beta, gamma) {
    const R = matrice(alpha, beta, gamma);
    const haut = Math.max(-1, Math.min(1, appliquer(R, CAMERA)[2]));
    return { elevation: Math.asin(haut) / RAD, roulis: Math.atan2(R[2][0], R[2][1]) / RAD };
  }

  // iPhone : recale l'alpha relatif sur le nord grâce à webkitCompassHeading (cap du haut du téléphone).
  function CapIphone(inclinaisonCalibrage = 60) {
    this.horizontaliteMin = Math.cos(inclinaisonCalibrage * RAD); // haut à moins de 60° de l'horizontale
    this.ecart = null;
  }

  CapIphone.prototype.mesurer = function (alphaRelatif, beta, gamma, capDuHaut) {
    const R = matrice(alphaRelatif, beta, gamma);
    const hautRelatif = capVecteur(R, HAUT, this.horizontaliteMin);
    if (capDuHaut != null && hautRelatif != null) {
      const ecart = (capDuHaut - hautRelatif + 360) % 360;
      // Moyenne glissante sur le cercle : un écart isolé (main qui tremble) ne fait pas sauter le nord.
      this.ecart = this.ecart == null ? ecart : (this.ecart + 0.2 * (((ecart - this.ecart + 540) % 360) - 180) + 360) % 360;
    }
    const cameraRelative = capVecteur(R, CAMERA);
    return this.ecart == null || cameraRelative == null ? null : (cameraRelative + this.ecart) % 360;
  };

  const exporte = { matrice, capVecteur, capCamera, poseCamera, CapIphone, CAMERA, HAUT };
  if (typeof module !== "undefined" && module.exports) module.exports = exporte;
  else racine.Boussole = exporte;
})(this);
