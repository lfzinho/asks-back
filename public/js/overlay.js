// A page image with boxes drawn over it (SVG in page-pixel coordinates).
import { h } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  return el;
}

/**
 * pageView({src, width, height, regions, annotations, selected, editable, onDraw, onSelect})
 *  regions:     [{box:[x,y,w,h], kind:"region"|"option"|"statement", label, active}]
 *  annotations: [{key, box, kind, label}]   kind: error|note|correct|wrong|expected|flag
 *  editable:    drag on the page to draw a box -> onDraw([x,y,w,h])
 */
export function pageView({ src, width, height, regions = [], annotations = [], selected = null,
  editable = false, onDraw = null, onSelect = null }) {
  const img = h("img", { src, alt: "page", draggable: "false" });
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none" });
  const font = Math.max(14, Math.round(width / 55));

  for (const r of regions) {
    const [x, y, w, hh] = r.box;
    svg.append(svgEl("rect", { x, y, width: w, height: hh, class: `region ${r.kind || ""} ${r.active ? "active" : ""}` }));
    if (r.label) {
      const t = svgEl("text", { x: x + 4, y: y - 6, "font-size": font * 0.8, fill: "#2357d9" });
      t.textContent = r.label;
      svg.append(t);
    }
  }
  for (const a of annotations) {
    const [x, y, w, hh] = a.box;
    const pad = 4;
    const rect = svgEl("rect", {
      x: x - pad, y: y - pad, width: w + 2 * pad, height: hh + 2 * pad, rx: 4,
      class: `ann ${a.kind} ${selected === a.key ? "selected" : ""}`,
    });
    if (onSelect) rect.addEventListener("pointerdown", (e) => { e.stopPropagation(); onSelect(a.key); });
    svg.append(rect);
    if (a.label) {
      const color = { error: "#d32f2f", wrong: "#d32f2f", correct: "#2e9d3a", flag: "#8e44ad" }[a.kind] || "#e67e22";
      const t = svgEl("text", { x: x + w + pad + 3, y: y + font * 0.4, "font-size": font, fill: color });
      t.textContent = a.label;
      svg.append(t);
    }
  }

  const wrap = h("div", { class: `pageview ${editable ? "editable" : ""}` }, img);
  wrap.append(svg);

  if (editable && onDraw) {
    let start = null;
    let draft = null;
    const toPage = (e) => {
      const r = svg.getBoundingClientRect();
      return [(e.clientX - r.left) * (width / r.width), (e.clientY - r.top) * (height / r.height)];
    };
    svg.addEventListener("pointerdown", (e) => {
      start = toPage(e);
      draft = svgEl("rect", { class: "draft", x: start[0], y: start[1], width: 0, height: 0 });
      svg.append(draft);
      svg.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    svg.addEventListener("pointermove", (e) => {
      if (!start) return;
      const [px, py] = toPage(e);
      draft.setAttribute("x", Math.min(px, start[0]));
      draft.setAttribute("y", Math.min(py, start[1]));
      draft.setAttribute("width", Math.abs(px - start[0]));
      draft.setAttribute("height", Math.abs(py - start[1]));
    });
    svg.addEventListener("pointerup", (e) => {
      if (!start) return;
      const [px, py] = toPage(e);
      const box = [Math.min(px, start[0]), Math.min(py, start[1]), Math.abs(px - start[0]), Math.abs(py - start[1])]
        .map(Math.round);
      start = null;
      draft.remove();
      if (box[2] > 6 && box[3] > 6) onDraw(box);
    });
  }
  return wrap;
}
