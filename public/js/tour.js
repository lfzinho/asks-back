// Tour (pt-BR): the five-minute pitch as a slideshow. Each demo step explains what to do and links
// to the real screen; signed in as a teacher, the numbers come from your latest class.
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
  document.getElementById("who").textContent = `${slides[i].dataset.who} · ${slides[i].dataset.time}`;
  showNotes();
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
  else if (e.key.toLowerCase() === "n") toggleNotes();
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
// Presenter notes (N)
// ======================================================================

const notesPanel = document.getElementById("notes-panel");
let notesOn = false;
try { notesOn = localStorage.getItem("tour-notes") === "1"; } catch { /* private mode */ }

function showNotes() {
  const slide = slides[current];
  notesPanel.hidden = !notesOn || !slide;
  if (!slide) return;
  document.getElementById("notes-title").textContent = `${slide.dataset.name} · ${slide.dataset.who}`;
  document.getElementById("notes-time").textContent = slide.dataset.time;
  setChildren(document.getElementById("notes-text"),
    (slide.querySelector("template.notes")?.innerHTML.trim() || "").split(/\n\s*\n/).map((p) => h("p", {}, p)));
}
function toggleNotes() {
  notesOn = !notesOn;
  try { localStorage.setItem("tour-notes", notesOn ? "1" : "0"); } catch { /* private mode */ }
  showNotes();
}
document.getElementById("notes-btn").onclick = toggleNotes;
document.getElementById("notes-close").onclick = toggleNotes;

// ======================================================================
// Content
// ======================================================================

fetch("/demo/students/list.json").then((r) => r.json()).then((list) => {
  const firstPages = list.filter((u, i) => list.findIndex((v) => v.split("-")[0] === u.split("-")[0]) === i);
  setChildren(document.getElementById("sample-thumbs"), firstPages.map((u) => {
    const name = u.split("/").pop().split("-")[0];
    return h("figure", {}, h("img", { src: u, alt: `Prova de ${name}`, loading: "lazy" }), name[0].toUpperCase() + name.slice(1));
  }));
}).catch(() => {});

// The five triggers, each with an everyday example.
const TRIGGERS = [
  ["G1", "Certa, sem justificativa", "“Por que sentimos frio ao sair da piscina?” — “Por causa da evaporação.” Está certo, mas não há raciocínio no papel.",
    "Pede o raciocínio: “Você escreveu ‘por causa da evaporação’. Como a evaporação tira calor da sua pele?”"],
  ["G2", "Parcial", "“Por que o gelo flutua? Dê um exemplo na natureza.” — “Porque é menos denso que a água.” Faltou o exemplo.",
    "Pede o que falta, sem dizer o quê: “O que mais a questão pedia?”"],
  ["G3", "Ambígua", "“Por que a panela de pressão cozinha mais rápido?” — “Porque a água ferve mais.” Ferve mais rápido? Ou mais quente?",
    "Pede para esclarecer, uma vez, sem pistas. Se o aluno estava certo, a nota escrita é ajustada."],
  ["G4", "Equívoco conhecido", "“É verão porque a Terra está mais perto do Sol.” Um erro clássico, que já está no banco da disciplina.",
    "Traz a afirmação de um colega: “Um colega disse que no verão a Terra está mais perto do Sol. O que você diria a ele, e por quê?”"],
  ["G5", "Autoria incerta", "Uma explicação de fotossíntese digna de livro-texto, de um aluno cujas outras respostas têm uma linha cada.",
    "Nunca acusa: pede para aplicar a ideia a um caso novo, como “Por que uma planta esquecida num quarto escuro fica amarela?”. O perfil é “Verificar entendimento” e quem decide é o professor."],
];
function pickTrigger(i) {
  const [code, name, example, ask] = TRIGGERS[i];
  [...document.getElementById("trig-pick").children].forEach((b, k) => b.classList.toggle("on", k === i));
  setChildren(document.getElementById("trig-detail"),
    h("div", {}, h("div", { class: "k" }, `${code} · ${name}`), h("p", {}, example)),
    h("div", {}, h("div", { class: "k" }, "O que o sistema pergunta"), h("p", {}, ask)));
}
setChildren(document.getElementById("trig-pick"), TRIGGERS.map(([code, name], i) =>
  h("button", { onclick: () => pickTrigger(i) }, h("b", {}, code), h("span", {}, name))));
pickTrigger(0);

// The verification dialogue from the pitch.
const CHAT = [
  ["ctx", "Questão 3 · Como um avião voa?", "A asa joga o ar para baixo."],
  ["tutor", "Você disse que a asa joga o ar para baixo. Como um avião de acrobacia consegue voar de cabeça para baixo?"],
  ["me", "Ele vai muito rápido, aí não cai."],
  ["hint", "O que faz o ar descer ao passar pela asa?"],
  ["me", "O ar de cima percorre um caminho maior e tem que chegar junto com o de baixo, aí a pressão muda."],
  ["end", "Equívoco clássico (“tempo de trânsito igual”). Resultado: entendimento não confirmado."],
];
let chatTimer = null;

function playChat() {
  const box = document.getElementById("chat-demo");
  clearTimeout(chatTimer);
  const [, prompt, answer] = CHAT[0];
  setChildren(box, h("div", { class: "ctx" }, h("div", { class: "k" }, "Explique seu raciocínio"), h("b", {}, prompt),
    h("blockquote", {}, answer)));
  let i = 1;
  const step = () => {
    if (i >= CHAT.length || !slides[current]?.contains(box)) return;
    const [kind, text] = CHAT[i++];
    const tag = { hint: "Pergunta de apoio", end: "Para o professor" }[kind];
    box.append(h("div", { class: `msg ${kind}` }, tag ? h("div", { class: "tag" }, tag) : null, text));
    box.scrollTop = box.scrollHeight;
    chatTimer = setTimeout(step, kind === "me" ? 1600 : 2400);
  };
  chatTimer = setTimeout(step, 900);
}
document.getElementById("replay-chat").onclick = playChat;

function onSlide(slide) {
  if (slide.querySelector("#chat-demo")) playChat();
}

// Cost calculator.
const BRL = 5.5;
const money = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: v < 1 ? 4 : 2 });
function calc() {
  const n = (id) => Math.max(0, Number(document.getElementById(id).value) || 0);
  const per = ((n("c-in") * 0.15 + n("c-out") * 0.6) / 1e6) * BRL;
  const year = per * n("c-students") * n("c-exams");
  setChildren(document.getElementById("c-out-text"),
    h("div", {}, h("span", {}, "por verificação"), h("b", {}, money(per))),
    h("div", {}, h("span", {}, "por ano, a escola toda"), h("b", {}, money(year))));
}
document.querySelectorAll(".calc input").forEach((i) => i.addEventListener("input", calc));
calc();

// QR code to this site.
if (window.qrcode) {
  const q = window.qrcode(0, "M");
  q.addData(`${location.origin}/teacher`);
  q.make();
  document.getElementById("qr").innerHTML = q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
}

// ======================================================================
// Live numbers for a signed-in teacher
// ======================================================================

const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);

onAuthStateChanged(auth, (user) => {
  const hud = document.getElementById("hud-live");
  if (!user) { setChildren(hud, h("a", { class: "pill", href: "/teacher", target: "_blank" }, "números da demo · entre para ver os seus")); return; }
  onSnapshot(query(collection(db, "insights"), where("ownerUid", "==", user.uid)), (snap) => {
    const all = snap.docs.map((d) => ({ id: d.id, ...d.data() })).filter((x) => x.summary?.profiled)
      .sort((a, b) => (b.updatedAt?.seconds || 0) - (a.updatedAt?.seconds || 0));
    if (!all.length) { setChildren(hud, h("span", { class: "pill" }, "nenhuma turma ainda · números da demo")); return; }
    showLive(all[0].summary);
    setChildren(hud, h("span", { class: "pill on" }, "● ao vivo: sua última turma"));
  }, () => {});
});

function showLive(s) {
  const [almost, verify, agree] = document.querySelectorAll("#live-class .metric");
  const n = s.profiled;
  almost.querySelector(".value").textContent = pct(s.almostShare);
  almost.querySelector(".sub").textContent = `${s.almostBehindLowGrade} de ${n} alunos (${s.almostBehindLowGrade} dos ${s.lowGrade} com nota escrita baixa)`;
  verify.querySelector(".value").textContent = n ? pct((s.counts?.verify || 0) / n) : "–";
  verify.querySelector(".sub").textContent = `${s.counts?.verify || 0} de ${n} alunos`;
  agree.querySelector(".value").textContent = pct(s.agreement);
  agree.querySelector(".sub").textContent = s.teacherJudged ? `nos ${s.teacherJudged} alunos que você avaliou` : "dê seu parecer sobre alunos no painel para medir";
}

const fromHash = () => go((parseInt(location.hash.slice(1), 10) || 1) - 1);
window.addEventListener("hashchange", fromHash);
fromHash();
