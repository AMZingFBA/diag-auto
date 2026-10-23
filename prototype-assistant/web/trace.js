"use strict";
// Tracé guidé du plan sur la caméra (Noah, 23/10) : la croix au centre de l'écran vise un coin au ras du sol ; les coins
// validés et les murs tracés restent dessinés à leur place réelle dans l'image, même quand le téléphone tourne ou avance.
//
// Repère du monde : x et y à l'horizontale (ceux de l'orientation du téléphone : x vers la direction 90°, y vers la
// direction 0°, comme le lacet), z vers le haut ; le sol est le plan z = 0 et la caméra est à la hauteur h au-dessus.
// Orientation : la matrice R de web/boussole.js (axes du téléphone → axes du monde) ; la caméra arrière vise -z du
// téléphone. Un point de l'image est donné par (u, v) : son écart au centre de l'image divisé par la focale (u vers la
// droite, v vers le haut) ; son rayon, dans les axes du téléphone, est (u, v, -1).
// Fichier chargé par la page, et testé par tests/test_trace_js.py (Node).

(function (racine) {
  const RAD = Math.PI / 180;
  const PRES = 0.05; // un point à moins de 5 cm devant l'objectif n'est pas dessiné (derrière la caméra)

  function appliquer(R, v) {
    return R.map((ligne) => ligne[0] * v[0] + ligne[1] * v[1] + ligne[2] * v[2]);
  }

  function appliquerInverse(R, v) {
    return [0, 1, 2].map((j) => R[0][j] * v[0] + R[1][j] * v[1] + R[2][j] * v[2]);
  }

  // Direction dans le monde du point (u, v) de l'image.
  function rayon(R, u = 0, v = 0) {
    const d = appliquer(R, [u, v, -1]);
    const n = Math.hypot(d[0], d[1], d[2]);
    return [d[0] / n, d[1] / n, d[2] / n];
  }

  // Le point du sol touché par le rayon d parti de la caméra (C = sa position à l'horizontale, h = sa hauteur) ; null si
  // le rayon ne descend pas assez (au-delà de `portee` mètres, ou au-dessus de l'horizon).
  function auSol(C, h, d, portee = 15) {
    if (d[2] >= 0) return null;
    const t = h / -d[2];
    const x = C[0] + t * d[0], y = C[1] + t * d[1];
    return Math.hypot(x - C[0], y - C[1]) > portee ? null : [x, y];
  }

  // Le point (u, v) de l'image où se voit le point du sol P ; null s'il est derrière la caméra.
  function projeter(R, C, h, P) {
    const c = appliquerInverse(R, [P[0] - C[0], P[1] - C[1], -h]);
    if (c[2] > -PRES) return null;
    return [c[0] / -c[2], c[1] / -c[2]];
  }

  // Le mur P1 → P2 dans l'image : la partie devant la caméra (coupée au plan à 5 cm devant l'objectif), projetée.
  function segment(R, C, h, P1, P2) {
    let a = appliquerInverse(R, [P1[0] - C[0], P1[1] - C[1], -h]);
    let b = appliquerInverse(R, [P2[0] - C[0], P2[1] - C[1], -h]);
    if (a[2] > -PRES && b[2] > -PRES) return null;
    const couper = (p, q) => {  // p derrière, q devant : le point du segment sur le plan z = -PRES
      const k = (-PRES - p[2]) / (q[2] - p[2]);
      return [p[0] + k * (q[0] - p[0]), p[1] + k * (q[1] - p[1]), -PRES];
    };
    if (a[2] > -PRES) a = couper(a, b);
    else if (b[2] > -PRES) b = couper(b, a);
    return [[a[0] / -a[2], a[1] / -a[2]], [b[0] / -b[2], b[1] / -b[2]]];
  }

  // La vidéo remplit l'écran (« object-fit: cover ») : sa focale en pixels de l'écran. `champ` : champ horizontal de
  // l'image de la caméra (degrés), `largeurVideo` × `hauteurVideo` : sa taille, `largeur` × `hauteur` : celle de l'écran.
  function focaleEcran(champ, largeurVideo, hauteurVideo, largeur, hauteur) {
    const focaleVideo = largeurVideo / 2 / Math.tan((champ / 2) * RAD);
    return focaleVideo * Math.max(largeur / largeurVideo, hauteur / hauteurVideo);
  }

  // Point (u, v) de l'image → pixels de l'écran : le centre de l'image est au centre de l'écran (sous la croix).
  function versEcran(uv, focale, largeur, hauteur) {
    return [largeur / 2 + focale * uv[0], hauteur / 2 - focale * uv[1]];
  }

  // Pixels de l'écran → point (u, v) de l'image.
  function depuisEcran(xy, focale, largeur, hauteur) {
    return [(xy[0] - largeur / 2) / focale, (hauteur / 2 - xy[1]) / focale];
  }

  const exporte = { appliquer, appliquerInverse, rayon, auSol, projeter, segment, focaleEcran, versEcran, depuisEcran };
  if (typeof module !== "undefined" && module.exports) module.exports = exporte;
  else racine.Trace = exporte;
})(this);
