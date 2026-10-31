// Finds a sheet of paper in a small grayscale camera frame, fast enough to run several times a second.
// Paper is the brightest large object on the table: split the frame into bright / dark (Otsu),
// keep the largest bright blob, and take its four extreme points as the page corners.

const MIN_SHARE = 0.08; // the page must cover at least this much of the frame
const MIN_CONTRAST = 28; // gray levels between table and paper
const MIN_FILL = 0.72; // blob area / corner quad area (text and handwriting make holes)
const BORDER_TOUCH = 0.04; // share of the frame border covered by the blob = page cut off

/**
 * @param {Uint8Array} gray  w*h luminance
 * @returns {{state: "none"|"partial"|"page", quad: number[][]|null, share: number, fill: number, reason: string}}
 *   reason: why there is no page ("empty", "bright", "small") or why it is partial ("cut", "shape").
 *   quad: [tl, tr, br, bl] as [x, y] in 0..1 frame coordinates.
 */
export function findPage(gray, w, h) {
  const n = w * h;
  const none = (reason) => ({ state: "none", quad: null, share: 0, fill: 0, reason });

  // Otsu threshold
  const hist = new Uint32Array(256);
  let sum = 0;
  for (let i = 0; i < n; i++) { hist[gray[i]]++; sum += gray[i]; }
  let sumB = 0, wB = 0, best = -1, t = 128, m0 = 0, m1 = 0;
  for (let v = 0; v < 256; v++) {
    wB += hist[v];
    if (!wB) continue;
    const wF = n - wB;
    if (!wF) break;
    sumB += v * hist[v];
    const mB = sumB / wB, mF = (sum - sumB) / wF;
    const between = wB * wF * (mB - mF) * (mB - mF);
    if (between > best) { best = between; t = v; m0 = mB; m1 = mF; }
  }
  // flat frame: an empty table, or white paper on a white table ("bright")
  if (m1 - m0 < MIN_CONTRAST) return none(sum / n > 170 ? "bright" : "empty");

  // largest bright connected component (4-connectivity)
  const label = new Int32Array(n);
  const stack = new Int32Array(n);
  let bestLabel = 0, bestSize = 0, next = 0;
  for (let i = 0; i < n; i++) {
    if (label[i] || gray[i] <= t) continue;
    next++;
    let top = 0, size = 0;
    stack[top++] = i;
    label[i] = next;
    while (top) {
      const p = stack[--top];
      size++;
      const x = p % w;
      if (x > 0 && !label[p - 1] && gray[p - 1] > t) { label[p - 1] = next; stack[top++] = p - 1; }
      if (x < w - 1 && !label[p + 1] && gray[p + 1] > t) { label[p + 1] = next; stack[top++] = p + 1; }
      if (p >= w && !label[p - w] && gray[p - w] > t) { label[p - w] = next; stack[top++] = p - w; }
      if (p < n - w && !label[p + w] && gray[p + w] > t) { label[p + w] = next; stack[top++] = p + w; }
    }
    if (size > bestSize) { bestSize = size; bestLabel = next; }
  }
  const share = bestSize / n;
  if (share < MIN_SHARE) return none("small");

  // corners = extreme points along the diagonals; count blob pixels on the frame border
  let tl = [0, 0], tr = [0, 0], br = [0, 0], bl = [0, 0];
  let sMin = Infinity, sMax = -Infinity, dMin = Infinity, dMax = -Infinity, border = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (label[y * w + x] !== bestLabel) continue;
      const s = x + y, d = x - y;
      if (s < sMin) { sMin = s; tl = [x, y]; }
      if (s > sMax) { sMax = s; br = [x, y]; }
      if (d > dMax) { dMax = d; tr = [x, y]; }
      if (d < dMin) { dMin = d; bl = [x, y]; }
      if (x === 0 || y === 0 || x === w - 1 || y === h - 1) border++;
    }
  }
  const quad = [tl, tr, br, bl];
  let area = 0;
  for (let i = 0; i < 4; i++) {
    const [x1, y1] = quad[i], [x2, y2] = quad[(i + 1) % 4];
    area += x1 * y2 - x2 * y1;
  }
  area = Math.abs(area) / 2;
  const fill = area ? Math.min(1, bestSize / area) : 0;
  const norm = quad.map(([x, y]) => [(x + 0.5) / w, (y + 0.5) / h]);

  if (border / (2 * (w + h)) > BORDER_TOUCH) return { state: "partial", quad: norm, share, fill, reason: "cut" };
  if (fill < MIN_FILL) return { state: "partial", quad: norm, share, fill, reason: "shape" };
  return { state: "page", quad: norm, share, fill, reason: "" };
}

// ---------- stillness ----------
// Phone cameras are never perfectly still: sensor noise, auto-exposure and a slightly wobbly tripod
// all change the picture a little. So frames are compared after blurring (noise averages out) and
// after removing the overall brightness change (auto-exposure). A hand shows up differently from
// noise: one connected patch changes a lot. A frame that is neither calm nor clearly moving only
// takes the count one step back instead of starting over.

const BLOCK = 4; // compare 4x4 pixel block averages
const CALM_MOTION = 5.5; // mean block change below this = calm
const SHAKE_MOTION = 10; // above this something is really moving: start over
const BIG_CHANGE = 30; // a block changed this much = something new is there (hand, page)
const CALM_PATCH = 0.015; // largest connected patch of big changes, share of the frame: calm below this
const SHAKE_PATCH = 0.04; // ... start over above this
const CALM_JITTER = 0.025; // page corners may move up to 2.5% of the frame width per frame

function blockMean(gray, w, h) {
  const bw = Math.floor(w / BLOCK), bh = Math.floor(h / BLOCK);
  const out = new Float32Array(bw * bh);
  for (let by = 0; by < bh; by++) {
    for (let bx = 0; bx < bw; bx++) {
      let s = 0;
      for (let y = by * BLOCK; y < (by + 1) * BLOCK; y++) {
        const row = y * w;
        for (let x = bx * BLOCK; x < (bx + 1) * BLOCK; x++) s += gray[row + x];
      }
      out[by * bw + bx] = s / (BLOCK * BLOCK);
    }
  }
  return { data: out, bw, bh };
}

/** Mean change and largest connected patch of big changes between two block images. */
function change(a, b) {
  const n = a.data.length;
  const d = new Float32Array(n);
  for (let i = 0; i < n; i++) d[i] = a.data[i] - b.data[i];
  const offset = Float32Array.from(d).sort()[n >> 1]; // overall brightness change
  let mean = 0;
  const big = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const v = Math.abs(d[i] - offset);
    mean += v;
    big[i] = v > BIG_CHANGE ? 1 : 0;
  }
  let patch = 0;
  const stack = [];
  for (let i = 0; i < n; i++) {
    if (big[i] !== 1) continue;
    let size = 0;
    big[i] = 2;
    stack.push(i);
    while (stack.length) {
      const p = stack.pop();
      size++;
      const x = p % a.bw, y = (p / a.bw) | 0;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const X = x + dx, Y = y + dy, q = Y * a.bw + X;
          if (X >= 0 && Y >= 0 && X < a.bw && Y < a.bh && big[q] === 1) { big[q] = 2; stack.push(q); }
        }
      }
    }
    patch = Math.max(patch, size);
  }
  return { mean: mean / n, patch: patch / n };
}

/** Counts how long the page has been (nearly) still. update() returns 0..1; 1 = capture now. */
export function stillMeter(frames = 6) {
  let prevBlocks = null, prevQuad = null, count = 0;
  return {
    reset() { count = 0; },
    update(gray, w, h, quad) {
      const blocks = blockMean(gray, w, h);
      const c = prevBlocks && prevBlocks.data.length === blocks.data.length
        ? change(blocks, prevBlocks) : { mean: 99, patch: 1 };
      const jitter = quad && prevQuad
        ? Math.max(...quad.map(([x, y], i) => Math.hypot(x - prevQuad[i][0], (y - prevQuad[i][1]) * h / w)))
        : 1;
      prevBlocks = blocks;
      prevQuad = quad;
      if (c.mean > SHAKE_MOTION || c.patch > SHAKE_PATCH) count = 0;
      else if (c.mean < CALM_MOTION && c.patch < CALM_PATCH && jitter < CALM_JITTER) count++;
      else count = Math.max(0, count - 1);
      return Math.min(1, count / frames);
    },
  };
}
