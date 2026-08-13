// Deterministic pseudo-signature SVG generator used by the mock layer so every
// screen is populated with plausible "signature crop" images in preview.
function hash(seed: string) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return () => {
    h ^= h << 13;
    h ^= h >>> 17;
    h ^= h << 5;
    return Math.abs(h % 10000) / 10000;
  };
}

export function signatureDataUrl(seed: string, blank = false) {
  const rnd = hash(seed);
  const w = 220;
  const h = 70;
  let d = "";
  if (!blank) {
    const strokes = 1 + Math.floor(rnd() * 2);
    for (let s = 0; s < strokes; s++) {
      let x = 12 + rnd() * 20;
      let y = 42 + rnd() * 8;
      d += `M${x.toFixed(1)},${y.toFixed(1)}`;
      const points = 5 + Math.floor(rnd() * 4);
      for (let i = 0; i < points; i++) {
        const cx1 = x + 6 + rnd() * 18;
        const cy1 = 12 + rnd() * 44;
        const cx2 = x + 14 + rnd() * 20;
        const cy2 = 12 + rnd() * 44;
        x = x + 20 + rnd() * 22;
        y = 26 + rnd() * 26;
        d += ` C${cx1.toFixed(1)},${cy1.toFixed(1)} ${cx2.toFixed(1)},${cy2.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
        if (x > w - 20) break;
      }
    }
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="${w}" height="${h}" fill="#fdfdfb"/><path d="M8,58 H${w - 8}" stroke="#d8d8d2" stroke-width="1"/>${d ? `<path d="${d}" fill="none" stroke="#1f2d5a" stroke-width="2.1" stroke-linecap="round"/>` : ""}</svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
