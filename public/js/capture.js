// Phone capture app: a full-screen camera that finds the page, outlines it live,
// and auto-captures (with a chime) once the page is fully in view and still.
import { db, storage } from "./fb.js";
import { h, toast, authGate, watchWorker, shortId } from "./ui.js";
import { findPage, stillMeter } from "./pagefind.js";
import {
  collection, doc, setDoc, getDocs, query, where, onSnapshot, serverTimestamp,
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js";
import { ref, uploadBytes } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-storage.js";

const MAX_SIDE = 2200; // uploaded photo size: plenty for alignment, small for Storage
const JPEG_QUALITY = 0.85;
const FRAME_W = 192; // analysis frame width (height follows the camera's aspect ratio)
const TICK_MS = 120;
// Pages of one exam look alike at this size, so "different from the last photo" alone is not
// enough: after each capture we wait to see the swap happen (the page gone, or a hand moving).
const MOTION_SWAP = 6; // frame-to-frame change above this = a hand is moving pages
const CHANGE_MIN = 4; // a new photo must differ from the last one by more than camera noise
const STILL_FRAMES = 6; // ~0.7 s of a (nearly) still, fully visible page before capturing; see stillMeter

const ICON = {
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="26" height="26"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  sound: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/></svg>',
  mute: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10v4h4l5 4V6L8 10z"/><path d="M17 10l4 4M21 10l-4 4"/></svg>',
};
const svg = (markup) => { const t = document.createElement("template"); t.innerHTML = markup; return t.content.firstChild; };

authGate(document.getElementById("app"), {
  app: "capture app",
  subtitle: "Use the same account as the teacher app. Photos go to the exam you pick.",
  onUser: start,
});

async function start(user, main) {
  watchWorker();
  const exams = (await getDocs(query(collection(db, "exams"), where("ownerUid", "==", user.uid))))
    .docs.map((d) => ({ id: d.id, ...d.data() }))
    .filter((e) => (e.pages || []).length);
  if (!exams.length) {
    main.append(h("div", { class: "card capture-start" }, h("h2", {}, "No exam ready yet"),
      h("p", { class: "muted" }, "Create an exam in the ", h("a", { href: "/teacher" }, "teacher app"), " first. Its pages appear here once the exam is read.")));
    return;
  }
  const wanted = new URLSearchParams(location.search).get("exam");
  let examId = exams.some((e) => e.id === wanted) ? wanted : exams[0].id;
  const examName = () => exams.find((e) => e.id === examId)?.name || "";
  const sessionId = `${Date.now().toString(36)}-${shortId()}`;
  let counter = 0;
  const localPreview = new Map();

  // ---------- upload ----------
  async function upload(blob, source) {
    const id = doc(collection(db, "captures")).id;
    const path = `captures/${user.uid}/${examId}/${id}.jpg`;
    localPreview.set(id, URL.createObjectURL(blob));
    await uploadBytes(ref(storage, path), blob, { contentType: "image/jpeg" });
    await setDoc(doc(db, "captures", id), {
      examId, ownerUid: user.uid, sessionId, seq: Date.now() * 1000 + (counter++ % 1000),
      path, status: "uploaded", source, createdAt: serverTimestamp(),
    });
    return id;
  }

  async function shrink(source, w, hgt) {
    const s = Math.min(1, MAX_SIDE / Math.max(w, hgt));
    const c = h("canvas", { width: Math.round(w * s), height: Math.round(hgt * s) });
    c.getContext("2d").drawImage(source, 0, 0, c.width, c.height);
    return new Promise((res) => c.toBlob(res, "image/jpeg", JPEG_QUALITY));
  }

  // ---------- session list (moves between the start screen and the camera's sheet) ----------
  const counts = h("span", { class: "muted small" }, "No photos yet");
  const list = h("div", { class: "thumbs" });
  let caps = [];
  let cam = null;

  onSnapshot(query(collection(db, "captures"), where("sessionId", "==", sessionId), where("ownerUid", "==", user.uid)), (snap) => {
    caps = snap.docs.map((d) => ({ id: d.id, ...d.data() })).sort((a, b) => a.seq - b.seq);
    const done = caps.filter((c) => c.status === "matched").length;
    counts.textContent = caps.length ? `${caps.length} photo(s), ${done} matched to a page` : "No photos yet";
    list.replaceChildren(...caps.map((c) => {
      const chip = { matched: ["ok", `page ${c.page}`], unmatched: ["bad", "no page match"], error: ["bad", "error"],
        processing: ["warn", "processing"], uploaded: ["warn", "waiting for worker"] }[c.status] || ["", c.status];
      return h("div", { class: "thumb", title: c.error || "" },
        localPreview.has(c.id) ? h("img", { src: localPreview.get(c.id), alt: "" }) : null,
        h("span", { class: `chip ${chip[0]}` }, chip[1]));
    }));
    cam?.updateCount();
  });

  // ---------- start screen ----------
  const fileInput = h("input", { type: "file", accept: "image/*", multiple: true, style: "display:none",
    onchange: async () => {
      const files = [...fileInput.files].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      try {
        for (const f of files) {
          const bmp = await createImageBitmap(f, { imageOrientation: "from-image" });
          await upload(await shrink(bmp, bmp.width, bmp.height), "file");
        }
        toast(`Uploaded ${files.length} photo(s)`);
      } catch (e) {
        toast(`Upload failed: ${e.message}`, "error");
      }
      fileInput.value = "";
    } });

  // The quick demo scans Bruno's two pages only; "all five" scans the whole pile.
  async function uploadDemo(all) {
    try {
      const urls = (await (await fetch("/demo/students/list.json")).json()).filter((u) => all || u.includes("/bruno-"));
      toast(all ? `Uploading ${urls.length} demo photos (5 students × 2 pages)…` : "Uploading Bruno's 2 pages…");
      for (const url of urls) await upload(await (await fetch(url)).blob(), "demo");
      toast("Demo photos uploaded");
    } catch (e) {
      toast(`Upload failed: ${e.message}`, "error");
    }
  }

  // Pages are grouped into students per session, so another exam means another session: reload for it.
  const examSelect = h("select", { id: "exam", onchange: (e) => { location.search = `?exam=${encodeURIComponent(e.target.value)}`; } },
    exams.map((e) => h("option", { value: e.id, selected: e.id === examId }, e.name)));
  const teacherLink = h("a", { href: `/teacher#/exam/${examId}`, class: "small" }, "Open this exam in the teacher app →");
  const sessionSlot = h("div", { class: "col" }, list);

  main.append(h("div", { class: "capture-start" },
    h("div", { class: "card" },
      h("div", { class: "hero-icon" }, svg(ICON.camera)),
      h("h1", {}, "Capture pages"),
      h("p", { class: "lead" }, "Point the phone straight down at the table and flip through the pile. Each page is captured on its own."),
      h("div", { class: "field" }, h("label", { for: "exam" }, "Exam"), examSelect),
      h("ol", { class: "how" },
        h("li", {}, h("span", { class: "n" }, "1"), h("div", {}, h("b", {}, "Mount the phone"), " on a tripod or a stack of books, about 40 cm above the table.")),
        h("li", {}, h("span", { class: "n" }, "2"), h("div", {}, h("b", {}, "Put a page down"), " and take your hand away. The outline turns green and it chimes when the page is captured.")),
        h("li", {}, h("span", { class: "n" }, "3"), h("div", {}, h("b", {}, "Go student by student"), ", in page order. The worker groups the pages into students."))),
      h("button", { class: "primary big start", onclick: () => cam.open() }, "Start camera"),
      h("div", { class: "alt" },
        h("button", { onclick: () => fileInput.click() }, "Upload photos…"),
        h("button", { onclick: () => uploadDemo(false), title: "Bruno's two pages, for a quick demo without a camera" }, "Upload demo photos"),
        h("button", { onclick: () => uploadDemo(true), title: "All five students' papers (10 photos)" }, "All 5 students")),
      fileInput),
    h("div", { class: "card" },
      h("div", { class: "row" }, h("h2", { style: "margin:0" }, "This session"), h("span", { class: "spacer" }), counts),
      sessionSlot,
      h("div", { style: "margin-top:12px" }, teacherLink))));

  // ---------- full-screen camera ----------
  cam = camera({
    upload, shrink, examName, list, counts, sessionSlot, getCaps: () => caps, localPreview,
  });
}

function camera({ upload, shrink, examName, list, counts, sessionSlot, getCaps, localPreview }) {
  const video = h("video", { autoplay: true, playsinline: true, muted: true });
  const overlay = h("canvas", { class: "overlay" });
  const octx = overlay.getContext("2d");
  const flash = h("div", { class: "flash" });

  const statusTitle = h("b");
  const statusSub = h("span");
  const status = h("div", { class: "status glass", role: "status", "aria-live": "polite" }, statusTitle, statusSub);

  const workerDot = h("span", { class: "dot" });
  const workerText = h("span", {}, "");
  const titleName = h("b");
  let soundOn = true;
  const soundBtn = h("button", { class: "icon-btn glass", title: "Sound on/off", "aria-label": "Sound on or off",
    onclick: () => { soundOn = !soundOn; soundBtn.replaceChildren(svg(soundOn ? ICON.sound : ICON.mute)); } }, svg(ICON.sound));
  const top = h("div", { class: "top" },
    h("button", { class: "icon-btn glass", title: "Close camera", "aria-label": "Close camera", onclick: () => close() }, svg(ICON.close)),
    h("div", { class: "title" }, titleName, h("span", {}, workerDot, workerText)),
    soundBtn);

  // shutter with a progress ring that fills while the page holds still
  const R = 36, CIRC = 2 * Math.PI * R;
  const ring = svg(`<svg class="ring" viewBox="0 0 78 78"><circle class="track" cx="39" cy="39" r="${R}"/><circle class="progress" cx="39" cy="39" r="${R}" stroke-dasharray="${CIRC}" stroke-dashoffset="${CIRC}"/></svg>`);
  const progress = ring.querySelector(".progress");
  const shutter = h("button", { class: "shutter", title: "Capture now", "aria-label": "Capture now", onclick: () => shoot("manual") },
    ring, h("span", { class: "core" }));

  const lastImg = h("img", { alt: "" });
  const lastCount = h("span", { class: "count" }, "0");
  const lastBtn = h("button", { class: "last", title: "Photos of this session", "aria-label": "Photos of this session",
    onclick: () => sheet.classList.toggle("open") }, lastImg, lastCount);

  let auto = true;
  const autoBtn = h("button", { class: "on", onclick: () => setAuto(true) }, "AUTO");
  const manualBtn = h("button", { onclick: () => setAuto(false) }, "MANUAL");
  const mode = h("div", { class: "mode glass" }, autoBtn, manualBtn);
  const bottom = h("div", { class: "bottom" }, lastBtn, shutter, mode);

  const sheetBody = h("div", { class: "body" });
  const sheet = h("div", { class: "sheet" },
    h("div", { class: "grab" }),
    h("div", { class: "head" }, h("b", {}, "This session"), h("span", { class: "spacer" }),
      h("button", { class: "icon-btn glass", "aria-label": "Close", onclick: () => sheet.classList.remove("open") }, svg(ICON.close))),
    sheetBody);
  const root = h("div", { class: "cam", hidden: true }, video, overlay, flash, top, status, bottom, sheet);
  document.body.append(root);

  let stream = null;
  let audio = null;
  let busy = false;
  let timer = null;
  let raf = null;
  let workerUnsub = null;
  let wakeLock = null;

  // analysis state
  const small = h("canvas");
  const sctx = small.getContext("2d", { willReadFrequently: true });
  let fw = FRAME_W, fh = Math.round(FRAME_W * 0.75);
  let prev = null, lastShot = null, still = 0, armed = true, pageStreak = 0; // still: 0..1
  const meter = stillMeter(STILL_FRAMES);
  let det = { state: "none", quad: null };
  let view = { quad: null, alpha: 0, color: [255, 255, 255], fill: 0 };
  let phase = "search"; // search | partial | steady | captured

  function setAuto(on) {
    auto = on;
    autoBtn.classList.toggle("on", on);
    manualBtn.classList.toggle("on", !on);
    still = 0;
    meter.reset();
  }

  function setStatus(kind, title, sub = "") {
    // big centered card while searching; a small pill above the shutter once a page is in view
    status.className = `status glass${kind === "center" ? "" : ` pill ${kind}`}`;
    if (statusTitle.textContent !== title) statusTitle.textContent = title;
    if (statusSub.textContent !== sub) statusSub.textContent = sub;
  }

  function updateCount() {
    const caps = getCaps();
    lastCount.textContent = String(caps.length);
    const last = [...caps].reverse().find((c) => localPreview.has(c.id));
    if (last && lastImg.src !== localPreview.get(last.id)) lastImg.src = localPreview.get(last.id);
    lastBtn.style.visibility = caps.length ? "visible" : "hidden";
  }

  const grab = () => {
    const vw = video.videoWidth, vh = video.videoHeight;
    const wantH = Math.max(1, Math.round(FRAME_W * vh / vw));
    if (small.width !== FRAME_W || small.height !== wantH) { small.width = fw = FRAME_W; small.height = fh = wantH; }
    sctx.drawImage(video, 0, 0, fw, fh);
    const d = sctx.getImageData(0, 0, fw, fh).data;
    const g = new Uint8Array(fw * fh);
    for (let i = 0; i < g.length; i++) g[i] = (d[4 * i] * 0.299 + d[4 * i + 1] * 0.587 + d[4 * i + 2] * 0.114) | 0;
    return g;
  };
  const diff = (a, b) => {
    if (!a || !b || a.length !== b.length) return 99;
    let s = 0;
    for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]);
    return s / a.length;
  };

  function chime() {
    navigator.vibrate?.(60);
    if (!soundOn || !audio) return;
    try {
      const t0 = audio.currentTime;
      [[1046.5, 0], [1568, 0.09]].forEach(([f, dt]) => {
        const o = audio.createOscillator();
        const g = audio.createGain();
        o.type = "sine";
        o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t0 + dt);
        g.gain.exponentialRampToValueAtTime(0.22, t0 + dt + 0.012);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dt + 0.35);
        o.connect(g).connect(audio.destination);
        o.start(t0 + dt);
        o.stop(t0 + dt + 0.4);
      });
    } catch { /* no audio */ }
  }

  async function shoot(source) {
    if (busy || !stream || video.readyState < 2) return;
    busy = true;
    shutter.classList.add("busy");
    try {
      const blob = await shrink(video, video.videoWidth, video.videoHeight);
      lastShot = grab();
      armed = false;
      still = 0;
      phase = "captured";
      chime();
      flash.classList.remove("go");
      void flash.offsetWidth;
      flash.classList.add("go");
      setStatus("ok", "Captured ✓  Next page");
      const id = await upload(blob, source);
      lastImg.src = localPreview.get(id);
      lastBtn.classList.remove("pop");
      void lastBtn.offsetWidth;
      lastBtn.classList.add("pop");
    } catch (e) {
      toast(`Upload failed: ${e.message}`, "error");
    } finally {
      busy = false;
      shutter.classList.remove("busy");
    }
  }

  function tick() {
    if (!stream || busy || video.readyState < 2 || !video.videoWidth) return;
    const g = grab();
    const motion = diff(g, prev);
    prev = g;
    det = findPage(g, fw, fh);
    const page = det.state !== "none";
    const calm = meter.update(g, fw, fh, det.state === "page" ? det.quad : null);
    pageStreak = det.state === "page" ? pageStreak + 1 : 0;

    if (!page || motion > MOTION_SWAP) armed = true;
    if (!auto) {
      still = 0;
      meter.reset();
      phase = det.state === "page" ? "steady" : det.state;
      if (!page) setStatus("center", "Manual mode", "Press the shutter to take a photo");
      else setStatus(det.state === "page" ? "ok" : "warn", det.state === "page" ? "Page in view" : "Fit the whole page in view");
    } else if (!page) {
      still = 0;
      meter.reset();
      phase = "search";
      setStatus("center", "Looking for a page…", det.reason === "bright"
        ? "Use a darker table or surface than the paper" : "Place a page under the camera");
    } else if (!armed || (lastShot && diff(g, lastShot) < CHANGE_MIN)) {
      still = 0;
      meter.reset();
      phase = "captured";
      setStatus("ok", "Captured ✓  Next page");
    } else if (det.state === "partial") {
      // keep the stillness count: the outline can flicker at the frame edge for a frame or two
      still = 0;
      phase = "partial";
      setStatus("warn", det.reason === "cut" ? "Fit the whole page in view" : "Flatten the page");
    } else {
      still = calm;
      phase = "steady";
      setStatus("glass", "Hold still…");
      if (still >= 1 && pageStreak >= 2) { still = 0; meter.reset(); shoot("auto"); }
    }
    progress.style.strokeDashoffset = String(CIRC * (1 - still));
  }

  // ---------- drawing (every animation frame, easing toward the latest detection) ----------
  function coverMap() {
    const cw = overlay.clientWidth, ch = overlay.clientHeight;
    const vw = video.videoWidth || 1, vh = video.videoHeight || 1;
    const s = Math.max(cw / vw, ch / vh);
    return { s, ox: (cw - vw * s) / 2, oy: (ch - vh * s) / 2, vw, vh };
  }

  function draw() {
    raf = requestAnimationFrame(draw);
    const dpr = window.devicePixelRatio || 1;
    const cw = overlay.clientWidth, ch = overlay.clientHeight;
    if (overlay.width !== Math.round(cw * dpr) || overlay.height !== Math.round(ch * dpr)) {
      overlay.width = Math.round(cw * dpr);
      overlay.height = Math.round(ch * dpr);
    }
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    octx.clearRect(0, 0, cw, ch);

    const target = det.quad;
    const color = { search: [255, 255, 255], partial: [255, 186, 73], steady: [255, 255, 255], captured: [52, 209, 122] }[phase];
    const showFill = phase === "captured" ? 0.22 : phase === "steady" ? 0.1 + 0.14 * still : 0.08;
    if (target) {
      const { s, ox, oy, vw, vh } = coverMap();
      const pts = target.map(([x, y]) => [ox + x * vw * s, oy + y * vh * s]);
      if (!view.quad || view.alpha < 0.05) view.quad = pts;
      else view.quad = view.quad.map(([x, y], i) => [x + (pts[i][0] - x) * 0.35, y + (pts[i][1] - y) * 0.35]);
      view.alpha += (1 - view.alpha) * 0.25;
    } else {
      view.alpha *= 0.8;
    }
    view.color = view.color.map((c, i) => c + (color[i] - c) * 0.2);
    view.fill += (showFill - view.fill) * 0.2;
    if (!view.quad || view.alpha < 0.02) return;

    const [r, g, b] = view.color.map(Math.round);
    const q = view.quad;
    octx.lineJoin = "round";
    octx.lineCap = "round";
    octx.beginPath();
    q.forEach(([x, y], i) => (i ? octx.lineTo(x, y) : octx.moveTo(x, y)));
    octx.closePath();
    octx.fillStyle = `rgba(${r},${g},${b},${view.fill * view.alpha})`;
    octx.fill();
    octx.strokeStyle = `rgba(${r},${g},${b},${0.55 * view.alpha})`;
    octx.lineWidth = 2;
    octx.stroke();

    // corner brackets
    octx.strokeStyle = `rgba(${r},${g},${b},${view.alpha})`;
    octx.lineWidth = 5;
    q.forEach(([x, y], i) => {
      const a = q[(i + 3) % 4], c = q[(i + 1) % 4];
      const toward = ([px, py]) => {
        const dx = px - x, dy = py - y, len = Math.hypot(dx, dy) || 1, L = Math.min(34, len * 0.2);
        return [x + (dx / len) * L, y + (dy / len) * L];
      };
      const [ax, ay] = toward(a), [cx, cy] = toward(c);
      octx.beginPath();
      octx.moveTo(ax, ay);
      octx.lineTo(x, y);
      octx.lineTo(cx, cy);
      octx.stroke();
    });
  }

  // ---------- open / close ----------
  async function open() {
    if (stream) return; // already open (double tap)
    audio ||= new (window.AudioContext || window.webkitAudioContext)();
    audio.resume?.();
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 3840 }, height: { ideal: 2160 } }, audio: false,
      });
    } catch (e) {
      toast(`Camera not available: ${e.message}`, "error");
      return;
    }
    video.srcObject = stream;
    titleName.textContent = examName();
    sheetBody.replaceChildren(h("div", { class: "row", style: "margin-bottom:10px" }, counts), list);
    root.hidden = false;
    document.body.style.overflow = "hidden";
    root.requestFullscreen?.().catch(() => {});
    navigator.wakeLock?.request("screen").then((l) => { wakeLock = l; }, () => {});
    prev = lastShot = null;
    still = 0;
    pageStreak = 0;
    meter.reset();
    armed = true;
    det = { state: "none", quad: null };
    view = { quad: null, alpha: 0, color: [255, 255, 255], fill: 0 };
    setStatus("center", "Looking for a page…", "Place a page under the camera");
    updateCount();
    timer = setInterval(tick, TICK_MS);
    raf = requestAnimationFrame(draw);
    workerUnsub = onSnapshot(doc(db, "workers", "main"), (snap) => {
      const age = (Date.now() - (snap.data()?.lastSeen?.toDate?.()?.getTime() || 0)) / 1000;
      workerDot.className = `dot ${age < 150 ? "on" : "off"}`;
      workerText.textContent = age < 150 ? "Worker online" : "Worker offline";
    }, () => {});
  }

  function close() {
    clearInterval(timer);
    cancelAnimationFrame(raf);
    workerUnsub?.();
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
    wakeLock?.release().catch(() => {});
    wakeLock = null;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    sheet.classList.remove("open");
    root.hidden = true;
    document.body.style.overflow = "";
    sessionSlot.replaceChildren(list);
    counts.isConnected || sessionSlot.closest(".card")?.querySelector(".row")?.append(counts);
  }

  return { open, close, updateCount };
}
