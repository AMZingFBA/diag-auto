"use strict";
// Position du téléphone par le sol filmé (Noah, 23/10 : « les coins et les traits doivent être ancrés dans l'espace réel ;
// il faut suivre la position et l'orientation du téléphone pendant mes déplacements »). Safari sur iPhone n'offre pas de
// suivi de position (pas de réalité augmentée WebXR) : il se calcule ici, sans LiDAR, sur n'importe quel téléphone.
//
// L'orientation vient du gyroscope (web/boussole.js). On suit, d'une image à l'autre, de petits détails du sol (méthode de
// Lucas et Kanade, du plus grossier au plus fin, vérifiée à l'aller et au retour). Chaque détail a une place fixe au sol,
// notée la première fois qu'on l'a vu ; son rayon, avec l'orientation et la hauteur du téléphone, dit d'où on le voit
// maintenant. La position du téléphone est la médiane de ce que disent les détails : un détail sur un meuble ou un mur se
// trompe, la médiane l'écarte, et il est oublié. La hauteur du téléphone (1,40 m, hypothèse) donne l'échelle : une erreur
// sur h grandit ou rétrécit tout, le tracé comme les déplacements, et le tracé reste aligné sur l'image.
// Fichier chargé par la page, et testé par tests/test_odometrie_js.py (Node, images de synthèse).

(function (racine) {
  const Trace = racine.Trace || (typeof require !== "undefined" ? require("./trace.js") : null);
  const RAD = Math.PI / 180;
  const SOL_MIN = Math.sin(10 * RAD); // un détail compte s'il est vu à plus de 10° sous l'horizon (à moins de 8 m)
  const SOL_NOUVEAU = Math.sin(15 * RAD); // un nouveau détail se prend à plus de 15° sous l'horizon (à moins de 5 m)
  const ECART_MAX_M = 0.25; // un détail qui place le téléphone à plus de 25 cm des autres n'est pas au sol (ou mal suivi)
  const CANDIDATS_MIN = 6;

  // --- Images en niveaux de gris : { data (Uint8Array), largeur, hauteur } ---------------------------------------------

  function gris(rgba, largeur, hauteur) {
    const g = new Uint8Array(largeur * hauteur);
    for (let i = 0, j = 0; i < g.length; i++, j += 4) g[i] = (rgba[j] * 77 + rgba[j + 1] * 150 + rgba[j + 2] * 29) >> 8;
    return { data: g, largeur, hauteur };
  }

  function reduire(img) {
    const l = img.largeur >> 1, h = img.hauteur >> 1, L = img.largeur, s = img.data, d = new Uint8Array(l * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < l; x++) {
        const i = 2 * y * L + 2 * x;
        d[y * l + x] = (s[i] + s[i + 1] + s[i + L] + s[i + L + 1] + 2) >> 2;
      }
    }
    return { data: d, largeur: l, hauteur: h };
  }

  function pyramide(img, niveaux = 3) {
    const p = [img];
    while (p.length < niveaux && p[p.length - 1].largeur >= 48) p.push(reduire(p[p.length - 1]));
    return p;
  }

  // Valeur en un point non entier (interpolation bilinéaire), bords prolongés.
  function lire(img, x, y) {
    const l = img.largeur, h = img.hauteur, d = img.data;
    x = x < 0 ? 0 : x > l - 1.001 ? l - 1.001 : x;
    y = y < 0 ? 0 : y > h - 1.001 ? h - 1.001 : y;
    const x0 = x | 0, y0 = y | 0, fx = x - x0, fy = y - y0, i = y0 * l + x0;
    return (d[i] * (1 - fx) + d[i + 1] * fx) * (1 - fy) + (d[i + l] * (1 - fx) + d[i + l + 1] * fx) * fy;
  }

  // Coins de Shi et Tomasi (la plus petite valeur propre du tenseur de structure sur 7 × 7) : le meilleur de chaque case
  // d'une grille, là où `garder(x, y)` le permet, et loin des détails déjà suivis.
  function detecter(img, garder, existants, maximum, cote = 14) {
    const l = img.largeur, h = img.hauteur, d = img.data;
    const occupe = new Set(existants.map((p) => `${Math.floor(p[0] / cote)},${Math.floor(p[1] / cote)}`));
    const cases = new Map();
    let meilleurScore = 0;
    for (let y = 5; y < h - 5; y += 2) {
      for (let x = 5; x < l - 5; x += 2) {
        const cle = `${Math.floor(x / cote)},${Math.floor(y / cote)}`;
        if (occupe.has(cle) || !garder(x, y)) continue;
        let sxx = 0, syy = 0, sxy = 0;
        for (let dy = -3; dy <= 3; dy++) {
          for (let dx = -3; dx <= 3; dx++) {
            const i = (y + dy) * l + x + dx;
            const gx = d[i + 1] - d[i - 1], gy = d[i + l] - d[i - l];
            sxx += gx * gx; syy += gy * gy; sxy += gx * gy;
          }
        }
        const score = (sxx + syy - Math.sqrt((sxx - syy) * (sxx - syy) + 4 * sxy * sxy)) / 2;
        const actuel = cases.get(cle);
        if (!actuel || score > actuel[2]) cases.set(cle, [x, y, score]);
        if (score > meilleurScore) meilleurScore = score;
      }
    }
    const seuil = Math.max(2000, 0.05 * meilleurScore); // un sol uni n'a pas de détail à suivre
    return [...cases.values()].filter((c) => c[2] > seuil).sort((a, b) => b[2] - a[2]).slice(0, maximum).map((c) => [c[0], c[1]]);
  }

  // Lucas et Kanade, pyramidal : où est passé chaque point de l'image A dans l'image B (null s'il est perdu).
  function suivre(pa, pb, points, demi = 4, iterations = 12) {
    const n = Math.min(pa.length, pb.length);
    return points.map(([x0, y0]) => {
      let gx = 0, gy = 0, dx = 0, dy = 0;
      for (let niveau = n - 1; niveau >= 0; niveau--) {
        const A = pa[niveau], B = pb[niveau], k = 1 << niveau, px = x0 / k, py = y0 / k;
        const ix = [], iy = [], va = [];
        let sxx = 0, syy = 0, sxy = 0;
        for (let wy = -demi; wy <= demi; wy++) {
          for (let wx = -demi; wx <= demi; wx++) {
            const gxa = (lire(A, px + wx + 1, py + wy) - lire(A, px + wx - 1, py + wy)) / 2;
            const gya = (lire(A, px + wx, py + wy + 1) - lire(A, px + wx, py + wy - 1)) / 2;
            ix.push(gxa); iy.push(gya); va.push(lire(A, px + wx, py + wy));
            sxx += gxa * gxa; syy += gya * gya; sxy += gxa * gya;
          }
        }
        const det = sxx * syy - sxy * sxy;
        const lambdaMin = (sxx + syy - Math.sqrt((sxx - syy) * (sxx - syy) + 4 * sxy * sxy)) / 2;
        if (lambdaMin < 0.5 * ix.length) return null; // pas assez de texture dans la fenêtre : ne se suit pas
        let vx = 0, vy = 0;
        for (let it = 0; it < iterations; it++) {
          let bx = 0, by = 0, j = 0;
          for (let wy = -demi; wy <= demi; wy++) {
            for (let wx = -demi; wx <= demi; wx++, j++) {
              const ecart = va[j] - lire(B, px + gx + vx + wx, py + gy + vy + wy);
              bx += ecart * ix[j]; by += ecart * iy[j];
            }
          }
          const ex = (syy * bx - sxy * by) / det, ey = (sxx * by - sxy * bx) / det;
          vx += ex; vy += ey;
          if (ex * ex + ey * ey < 0.0004) break;
        }
        dx = gx + vx; dy = gy + vy;
        if (niveau > 0) { gx = 2 * dx; gy = 2 * dy; }
      }
      const x = x0 + dx, y = y0 + dy;
      return x < 2 || y < 2 || x > pa[0].largeur - 3 || y > pa[0].hauteur - 3 ? null : [x, y];
    });
  }

  // Suivi vérifié : un point suivi de A vers B puis ramené de B vers A doit retomber à moins d'un pixel de son départ.
  function suivreVerifie(pa, pb, points) {
    const aller = suivre(pa, pb, points);
    const retour = suivre(pb, pa, aller.map((p, i) => p || points[i]));
    return aller.map((p, i) => (p && retour[i] && Math.hypot(retour[i][0] - points[i][0], retour[i][1] - points[i][1]) < 1.0 ? p : null));
  }

  function mediane(valeurs) {
    const v = [...valeurs].sort((a, b) => a - b);
    const m = v.length >> 1;
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  }

  // La position du téléphone (à l'horizontale) d'après des détails du sol de place connue P, vus dans les directions d :
  // chacun la donne (C = P − t·d, t = h / −dz) ; la médiane l'emporte. null s'il y a trop peu de détails au sol.
  function positionDepuis(vus, h) {
    const candidats = [];
    for (const { P, d } of vus) {
      if (d[2] > -SOL_MIN) continue;
      const t = h / -d[2];
      candidats.push([P[0] - t * d[0], P[1] - t * d[1]]);
    }
    if (candidats.length < CANDIDATS_MIN) return null;
    return [mediane(candidats.map((c) => c[0])), mediane(candidats.map((c) => c[1]))];
  }

  // Rotation d'angle |w| autour de l'axe w (formule de Rodrigues), appliquée avant R : la petite correction que l'image
  // apporte au gyroscope (bruit, retard des capteurs sur l'image, lente dérive).
  function tourner(w, R) {
    const a = Math.hypot(w[0], w[1], w[2]);
    if (a < 1e-12) return R;
    const [x, y, z] = [w[0] / a, w[1] / a, w[2] / a], c = Math.cos(a), s = Math.sin(a), t = 1 - c;
    const Q = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
               [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
               [t * x * z - s * y, t * y * z + s * x, t * z * z + c]];
    return Q.map((ligne) => [0, 1, 2].map((j) => ligne[0] * R[0][j] + ligne[1] * R[1][j] + ligne[2] * R[2][j]));
  }

  function resoudre(A, b) {  // petit système linéaire (pivot de Gauss) ; null s'il est singulier
    const n = b.length, M = A.map((ligne, i) => [...ligne, b[i]]);
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let i = c + 1; i < n; i++) if (Math.abs(M[i][c]) > Math.abs(M[p][c])) p = i;
      if (Math.abs(M[p][c]) < 1e-12) return null;
      [M[c], M[p]] = [M[p], M[c]];
      for (let i = 0; i < n; i++) {
        if (i === c) continue;
        const k = M[i][c] / M[c][c];
        for (let j = c; j <= n; j++) M[i][j] -= k * M[c][j];
      }
    }
    return M.map((ligne, i) => ligne[n] / ligne[i]);
  }

  // Position C et correction de l'orientation w qui font le mieux retomber les détails du sol (places P connues) sur
  // leurs points de l'image (xy, pixels) : Gauss-Newton, pondération robuste de Huber (un détail mal suivi pèse peu).
  function affiner(vus, R, C, w, h, f, largeur, hauteur, retenue = 2, lacetSeul = false) {
    const ecarts = (p) => {
      const Rc = tourner([p[2], p[3], p[4]], R), r = [];
      for (const { P, xy } of vus) {
        const uv = Trace.projeter(Rc, [p[0], p[1]], h, P);
        r.push(uv ? [largeur / 2 + f * uv[0] - xy[0], hauteur / 2 - f * uv[1] - xy[1]] : null);
      }
      return r;
    };
    let p = [C[0], C[1], w[0], w[1], w[2]];
    const pas = [0.002, 0.002, 0.0005, 0.0005, 0.0005];
    for (let iteration = 0; iteration < 6; iteration++) {
      const r0 = ecarts(p);
      const J = pas.map((e, j) => ecarts(p.map((v, k) => (k === j ? v + e : v))));
      const A = [0, 1, 2, 3, 4].map(() => [0, 0, 0, 0, 0]), b = [0, 0, 0, 0, 0];
      r0.forEach((r, i) => {
        if (!r || J.some((Jj) => !Jj[i])) return;
        const poids = Math.min(1, 2.0 / (Math.hypot(r[0], r[1]) + 1e-9)); // Huber, à 2 pixels
        for (const c of [0, 1]) {
          const g = J.map((Jj, j) => (Jj[i][c] - r[c]) / pas[j]);
          for (let j = 0; j < 5; j++) {
            b[j] -= poids * g[j] * r[c];
            for (let k = 0; k < 5; k++) A[j][k] += poids * g[j] * g[k];
          }
        }
      });
      for (let j = 2; j < 5; j++) A[j][j] += retenue * f * f; // la correction ne bouge que si l'image l'exige
      if (lacetSeul) for (const j of [2, 3]) { A[j] = A[j].map((_, k) => (k === j ? 1 : 0)); b[j] = 0; }
      const delta = resoudre(A, b);
      if (!delta) return null;
      p = p.map((v, j) => v + delta[j]);
      if (Math.hypot(delta[0], delta[1]) < 1e-4 && Math.hypot(delta[2], delta[3], delta[4]) < 1e-5) break;
    }
    const residus = ecarts(p).map((r) => (r ? Math.hypot(r[0], r[1]) : Infinity));
    return { C: [p[0], p[1]], w: [p[2], p[3], p[4]], residus };
  }

  function Odometrie(options = {}) {
    this.hauteur = options.hauteur || 1.4; // hauteur du téléphone au-dessus du sol (hypothèse)
    this.champ = options.champ || 45; // champ horizontal de l'image (degrés)
    this.maxDetails = options.maxDetails || 60;
    // Le sol à moins de 60 cm du téléphone est sous les pieds : les chaussures et le pantalon y sont souvent dans l'image et
    // bougent avec le téléphone (visite de Noah du 23/10, 17:30, caméra tournée vers ses pieds) : on n'y prend pas de détail.
    this.piedsM = options.piedsM != null ? options.piedsM : 0.6;
    this.affinage = options.affinage != null ? options.affinage : true; // position et orientation affinées ensemble
    this.retenue = options.retenue != null ? options.retenue : 2; // retenue de la correction d'orientation (en « détails »)
    this.lacetSeul = !!options.lacetSeul; // ne corriger que le cap (pas l'inclinaison ni le roulis)
    // Pas plus vite qu'une marche rapide : d'une image à l'autre, un saut plus grand est une erreur du suivi (image floue,
    // meuble pris pour le sol), pas un déplacement (visite de Noah du 23/10 : 96 m de trajet calculé pour ~50 m marchés).
    this.vitesseMax = options.vitesseMax != null ? options.vitesseMax : 1.6;
    this.t = null;
    this.C = [0, 0];
    this.w = [0, 0, 0]; // correction de l'orientation du gyroscope, apprise sur l'image (radians, axes du monde)
    this.details = []; // { xy (pixels de l'image), P (place au sol, mètres) }
    this.precedente = null;
    this.perdu = true;
  }

  // Une image (niveaux de gris, réduite : ~240 pixels de large) et l'orientation R du téléphone à l'instant de sa prise.
  // Renvoie { C, details, perdu }.
  Odometrie.prototype.image = function (img, R, t = null) {
    const f = img.largeur / 2 / Math.tan((this.champ / 2) * RAD);
    let Rc = tourner(this.w, R);
    const direction = (xy) => Trace.rayon(Rc, (xy[0] - img.largeur / 2) / f, (img.hauteur / 2 - xy[1]) / f);
    const pyr = pyramide(img);
    this.douteux = false;
    if (this.precedente && this.precedente[0].largeur === img.largeur && this.details.length) {
      const suivis = suivreVerifie(this.precedente, pyr, this.details.map((d) => d.xy));
      this.details = this.details.map((d, i) => ({ ...d, xy: suivis[i] })).filter((d) => d.xy);
      const vus = this.details.map((d) => ({ P: d.P, xy: d.xy, d: direction(d.xy), detail: d }));
      const C0 = positionDepuis(vus, this.hauteur);
      if (C0) {
        // Les détails qui s'accordent avec la médiane sont au sol : avec eux, position et orientation sont affinées
        // ensemble (le gyroscope a un peu de bruit, et un petit retard sur l'image quand on tourne vite).
        const accord = ({ P, d }) => {
          if (d[2] > -SOL_MIN) return null;
          const t = this.hauteur / -d[2];
          return Math.hypot(P[0] - t * d[0] - C0[0], P[1] - t * d[1] - C0[1]);
        };
        const sol = vus.filter((v) => { const e = accord(v); return e != null && e < ECART_MAX_M; });
        let C = C0, residus = null;
        const affine = this.affinage && sol.length >= 12
          ? affiner(sol, R, C0, this.w, this.hauteur, f, img.largeur, img.hauteur, this.retenue, this.lacetSeul) : null;
        if (affine && Math.hypot(affine.C[0] - C0[0], affine.C[1] - C0[1]) < 0.3 && Math.hypot(...affine.w) < 0.1) {
          C = affine.C;
          this.w = affine.w;
          Rc = tourner(this.w, R);
          residus = new Map(sol.map((v, i) => [v.detail, affine.residus[i]]));
        }
        let douteux = false;
        if (t != null && this.t != null && this.vitesseMax > 0) {
          const dmax = this.vitesseMax * Math.max(0.02, t - this.t) + 0.02, d = Math.hypot(C[0] - this.C[0], C[1] - this.C[1]);
          if (d > dmax) {  // trop loin pour une image : on n'avance que de ce qu'une marche permet
            C = [this.C[0] + ((C[0] - this.C[0]) * dmax) / d, this.C[1] + ((C[1] - this.C[1]) * dmax) / d];
            douteux = true;
          }
        }
        this.douteux = douteux; // position incertaine : pas de nouveau détail placé au sol à partir d'elle
        this.C = C;
        this.perdu = false;
        // Un détail qui ne s'accorde pas avec les autres n'est pas au sol (un meuble, un mur), ou il est mal suivi : oublié.
        this.details = vus.filter((v) => {
          if (residus && residus.has(v.detail)) return residus.get(v.detail) < 3.0;
          const e = accord(v);
          return e == null || e < ECART_MAX_M;
        }).map((v) => v.detail);
      } else {
        this.perdu = true;
      }
    }
    if (t != null) this.t = t;
    if (this.details.length < 0.6 * this.maxDetails && !this.douteux) {
      const garder = (x, y) => {
        const d = direction([x, y]);
        return d[2] < -SOL_NOUVEAU && (this.hauteur / -d[2]) * Math.hypot(d[0], d[1]) >= this.piedsM;
      };
      for (const xy of detecter(img, garder, this.details.map((d) => d.xy), this.maxDetails - this.details.length)) {
        const P = Trace.auSol(this.C, this.hauteur, direction(xy), 6);
        if (P) this.details.push({ xy, P });
      }
    }
    this.precedente = pyr;
    return { C: [...this.C], details: this.details.length, perdu: this.perdu, w: [...this.w] };
  };

  // L'orientation du téléphone corrigée par l'image (pour viser et dessiner au plus juste).
  Odometrie.prototype.orientation = function (R) {
    return tourner(this.w, R);
  };

  // Plus de détail à suivre (sol uni, image floue) : un pas compté par l'accéléromètre avance d'environ 0,6 m.
  Odometrie.prototype.pas = function (direction, longueur = 0.6) {
    if (!this.perdu) return;
    this.C = [this.C[0] + longueur * Math.sin(direction * RAD), this.C[1] + longueur * Math.cos(direction * RAD)];
    this.details = []; // repris au sol depuis la nouvelle position
  };

  const exporte = { gris, reduire, pyramide, lire, detecter, suivre, suivreVerifie, positionDepuis, tourner, affiner, Odometrie };
  if (typeof module !== "undefined" && module.exports) module.exports = exporte;
  else racine.Odometrie = exporte;
})(this);
