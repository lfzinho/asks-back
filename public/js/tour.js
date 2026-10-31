// Tour: the pitch as a keyboard-driven slideshow. Signed in as a teacher, the class slide shows
// the live numbers of your latest exam instead of the demo's.
import { auth, db } from "./fb.js";
import { h, setChildren } from "./ui.js";
import { onAuthStateChanged } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";
import { collection, query, where, onSnapshot } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js";

// ======================================================================
// Slides
// ======================================================================

const slides = [...document.querySelectorAll(".slide")];
const dots = document.getElementById("dots");
const progress = document.getElementById("progress");
let current = -1;

slides.forEach((s, i) => dots.append(h("button", { title: s.dataset.name, "aria-label": s.dataset.name, onclick: () => go(i) })));

function go(i) {
  i = Math.max(0, Math.min(slides.length - 1, i));
  if (i === current) return;
  slides.forEach((s, k) => {
    s.classList.toggle("active", k === i);
    s.classList.toggle("before", k < i);
  });
  [...dots.children].forEach((d, k) => { d.classList.toggle("on", k === i); d.classList.toggle("done", k < i); });
  progress.style.width = `${(i / (slides.length - 1)) * 100}%`;
  document.querySelector('[data-go="prev"].nav-btn').disabled = i === 0;
  document.querySelector('[data-go="next"].nav-btn').disabled = i === slides.length - 1;
  slides[i].scrollTop = 0;
  current = i;
  history.replaceState(null, "", `#${i + 1}`);
  onSlide(slides[i]);
}

const actions = { next: () => go(current + 1), prev: () => go(current - 1), first: () => go(0) };
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-go]");
  if (b) actions[b.dataset.go]();
});
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, select, textarea")) return;
  if (["ArrowRight", "PageDown", " "].includes(e.key)) { e.preventDefault(); actions.next(); }
  else if (["ArrowLeft", "PageUp"].includes(e.key)) { e.preventDefault(); actions.prev(); }
  else if (e.key === "Home") go(0);
  else if (e.key === "End") go(slides.length - 1);
  else if (e.key.toLowerCase() === "f") toggleFullscreen();
});
let touchX = null;
document.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
document.addEventListener("touchend", (e) => {
  if (touchX == null) return;
  const dx = e.changedTouches[0].clientX - touchX;
  if (Math.abs(dx) > 70) (dx < 0 ? actions.next : actions.prev)();
  touchX = null;
});
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen?.();
}
document.getElementById("fullscreen").onclick = toggleFullscreen;

// ======================================================================
// Content
// ======================================================================

fetch("/demo/students/list.json").then((r) => r.json()).then((list) => {
  const firstPages = list.filter((u, i) => list.findIndex((v) => v.split("-")[0] === u.split("-")[0]) === i);
  setChildren(document.getElementById("sample-thumbs"), firstPages.map((u) => {
    const name = u.split("/").pop().split("-")[0];
    return h("figure", {}, h("img", { src: u, alt: `${name}'s paper`, loading: "lazy" }), name[0].toUpperCase() + name.slice(1));
  }));
}).catch(() => {});

// Bruno's real transcript from the demo run (mock mode).
const CHAT = [
  ["ctx", "Q5 · What is the time complexity of binary search, and why?", "It is O(log n)."],
  ["tutor", "You wrote \"It is O(log n)\". What makes that true? Walk me through the reasoning behind it."],
  ["me", "It gets smaller every step."],
  ["hint", "Re-read what you wrote, then look at what one comparison with the middle element tells you."],
  ["me", "Each comparison cuts the interval in half, and that only works because the array is sorted."],
  ["transfer", "What would change in the algorithm if the array were sorted in descending order?"],
  ["me", "I would flip the comparison and go the other way, it is still log n."],
];
let chatTimer = null;

function playChat() {
  const box = document.getElementById("chat-demo");
  clearTimeout(chatTimer);
  box.replaceChildren();
  const [, prompt, answer] = CHAT[0];
  box.append(h("div", { class: "ctx" }, h("div", { class: "k" }, "Explain your reasoning"), h("b", {}, prompt),
    h("blockquote", {}, answer)));
  let i = 1;
  const step = () => {
    if (i >= CHAT.length || !slides[current]?.contains(box)) return;
    const [kind, text] = CHAT[i++];
    const tag = { hint: "Hint", transfer: "One more, on your own" }[kind];
    box.append(h("div", { class: `msg ${kind}` }, tag ? h("div", { class: "tag" }, tag) : null, text));
    box.scrollTop = box.scrollHeight;
    chatTimer = setTimeout(step, kind === "me" ? 1500 : 2300);
  };
  chatTimer = setTimeout(step, 900);
}

function onSlide(slide) {
  if (slide.querySelector("#chat-demo")) playChat();
}

// ======================================================================
// Live numbers for a signed-in teacher
// ======================================================================

const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

onAuthStateChanged(auth, (user) => {
  const hud = document.getElementById("hud-live");
  if (!user) { setChildren(hud, h("a", { class: "pill", href: "/teacher" }, "demo numbers · sign in for yours")); return; }
  onSnapshot(query(collection(db, "insights"), where("ownerUid", "==", user.uid)), (snap) => {
    const all = snap.docs.map((d) => ({ id: d.id, ...d.data() })).filter((x) => x.summary?.profiled)
      .sort((a, b) => (b.updatedAt?.seconds || 0) - (a.updatedAt?.seconds || 0));
    if (!all.length) { setChildren(hud, h("span", { class: "pill" }, "no class yet · demo numbers")); return; }
    showLive(all[0]);
    setChildren(hud, h("span", { class: "pill on" }, "● live: your latest class"));
  }, () => {});
});

function showLive(ins) {
  const s = ins.summary;
  const [almost, agree] = document.querySelectorAll("#live-class .metric");
  almost.querySelector(".value").textContent = pct(s.almostShare);
  almost.querySelector(".sub").textContent = `${s.almostBehindLowGrade} of ${s.profiled} students, ${s.almostBehindLowGrade} of the ${s.lowGrade} with a low written score`;
  agree.querySelector(".value").textContent = pct(s.agreement);
  agree.querySelector(".sub").textContent = s.teacherJudged ? `on the ${s.teacherJudged} students you rated` : "rate students in the teacher app to measure it";
}

const fromHash = () => go((parseInt(location.hash.slice(1), 10) || 1) - 1);
window.addEventListener("hashchange", fromHash);
fromHash();
