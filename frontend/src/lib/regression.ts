export interface FitPoint {
  x: number;
  y: number;
}

export interface PolyFit {
  degree: number;
  r2: number;
  predict: (x: number) => number;
}

/**
 * Polynom-Fit (kleinste Quadrate) über Normalengleichungen. x wird
 * zentriert/skaliert, damit die Gramsche Matrix auch bei großen
 * Achsenwerten (z. B. Einwohnerzahlen) nicht entartet; Lösung per
 * Gauß-Jordan mit Spaltenpivotierung. null bei n < degree + 2,
 * identischen x, konstantem y oder singulärem System.
 */
export function fitPolynomial(points: FitPoint[], degree: number): PolyFit | null {
  const n = points.length;
  if (degree < 1 || n < degree + 2) return null;

  const mx = points.reduce((s, p) => s + p.x, 0) / n;
  const sx = Math.sqrt(points.reduce((s, p) => s + (p.x - mx) ** 2, 0) / n);
  if (sx === 0) return null;
  const ts = points.map((p) => (p.x - mx) / sx);

  const m = degree + 1;
  const pow = new Array(2 * degree + 1).fill(0);
  for (const t of ts) {
    let acc = 1;
    for (let k = 0; k <= 2 * degree; k++) {
      pow[k] += acc;
      acc *= t;
    }
  }
  const A = Array.from({ length: m }, (_, i) =>
    Array.from({ length: m }, (_, j) => pow[i + j])
  );
  const b = new Array(m).fill(0);
  points.forEach((p, idx) => {
    let acc = 1;
    for (let i = 0; i < m; i++) {
      b[i] += p.y * acc;
      acc *= ts[idx];
    }
  });

  const coeffs = solve(A, b);
  if (!coeffs) return null;

  const predict = (x: number) => {
    const t = (x - mx) / sx;
    let y = 0;
    for (let i = degree; i >= 0; i--) y = y * t + coeffs[i];
    return y;
  };

  const my = points.reduce((s, p) => s + p.y, 0) / n;
  const ssTot = points.reduce((s, p) => s + (p.y - my) ** 2, 0);
  if (ssTot === 0) return null;
  const ssRes = points.reduce((s, p) => s + (p.y - predict(p.x)) ** 2, 0);

  return { degree, r2: 1 - ssRes / ssTot, predict };
}

function solve(A: number[][], b: number[]): number[] | null {
  const m = A.length;
  const M = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < m; col++) {
    let piv = col;
    for (let r = col + 1; r < m; r++) {
      if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r;
    }
    if (Math.abs(M[piv][col]) < 1e-10) return null;
    [M[col], M[piv]] = [M[piv], M[col]];
    for (let r = 0; r < m; r++) {
      if (r === col) continue;
      const f = M[r][col] / M[col][col];
      for (let c = col; c <= m; c++) M[r][c] -= f * M[col][c];
    }
  }
  return M.map((row, i) => row[m] / row[i]);
}
