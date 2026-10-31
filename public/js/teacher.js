// Teacher app: the class view (profiles, three scores, demo metrics), each student's flagged
// answers and follow-up transcripts, and the teacher's own judgment, which always has the last word.
import { db, storage, fileUrl } from "./fb.js";
import { h, toast, fmt, authGate, watchWorker, shortId, setChildren } from "./ui.js";
import { pageView } from "./overlay.js";
import {
  collection, doc, addDoc, setDoc, getDoc, updateDoc, deleteDoc, query, where, onSnapshot, serverTimestamp,
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js";
import { ref, uploadBytes } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-storage.js";

let user;
let main;
let cleanups = [];
let generation = 0; // views that load before rendering check it, so a newer route wins

export const PROFILES = {
  mastered: { label: "Mastered", action: "Move on", color: "#1f7a3d" },
  almost: { label: "Almost there", action: "Short review", color: "#3355e0" },
  building: { label: "Building", action: "Guided reteaching", color: "#c27c0e" },
  not_reached: { label: "Not reached", action: "Reteach the concept", color: "#c0352b" },
  verify: { label: "Verify understanding", action: "Talk with the student", color: "#7c3aad" },
};
const TRIGGERS = {
  G1: "Correct, no justification", G2: "Partial answer", G3: "Ambiguity", G4: "Known misconception", G5: "Uncertain authorship",
};
const LEVELS = { 0: "N0 · no help", 1: "N1 · implicit hint", 2: "N2 · conceptual hint", 3: "N3 · explicit hint", transfer: "Transfer" };

authGate(document.getElementById("app"), {
  app: "teacher",
  onUser: (u, m) => {
    user = u;
    main = m;
    watchWorker();
    if (!main.dataset.routed) window.addEventListener("hashchange", route);
    main.dataset.routed = "1";
    route();
  },
});

function route() {
  cleanups.forEach((f) => f());
  cleanups = [];
  generation += 1;
  main.replaceChildren();
  const [view, id] = location.hash.replace(/^#\/?/, "").split("/");
  if (view === "exam") classView(id);
  else if (view === "sub") studentView(id);
  else examList();
}

const append = (el, ...c) => el.append(...c.flat(Infinity).filter((x) => x != null && x !== false));
const guarded = (fn) => async (...args) => {
  try { await fn(...args); } catch (e) { console.error(e); toast(e.message || String(e), "error"); }
};
const pct = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const job = (data) => addDoc(collection(db, "jobs"), { ...data, ownerUid: user.uid, status: "pending", createdAt: serverTimestamp() });
const profileChip = (key, label) => key
  ? h("span", { class: "chip profile", style: `--c:${PROFILES[key].color}` }, PROFILES[key].label)
  : h("span", { class: "chip" }, label || "waiting");

// ======================================================================
// Exam list
// ======================================================================

const SETUP = { setting_up: ["warn", "uploading…"], reading: ["warn", "reading the exam…"], error: ["bad", "could not read the exam"] };

function examList() {
  const list = h("div", { class: "grid" });
  const form = h("div");
  append(main, 
    h("div", { class: "page-head" }, h("h1", {}, "Your classes"), h("span", { class: "spacer" }),
      h("button", { onclick: guarded(createDemoClass), title: "An everyday-science quiz with a class of 20 (15 simulated)" }, "＋ Demo class"),
      h("button", { class: "primary", onclick: () => setChildren(form, newExamForm()) }, "＋ New exam")),
    h("p", { class: "lead" }, "Each exam is graded from the paper. Only where an answer is not enough evidence does the student get a short written follow-up, and you get how far they got and how much help they needed."),
    form, list);
  cleanups.push(onSnapshot(query(collection(db, "exams"), where("ownerUid", "==", user.uid)), (snap) => {
    const exams = snap.docs.map((d) => ({ id: d.id, ...d.data() }))
      .sort((a, b) => (b.createdAt?.seconds || 0) - (a.createdAt?.seconds || 0));
    setChildren(list, exams.length ? exams.map((e) => {
      const st = SETUP[e.status];
      return h("div", { class: "card" },
        h("h2", {}, e.name),
        st ? h("span", { class: `chip ${st[0]}` }, st[1])
          : h("p", { class: "muted small" }, `${(e.questions || []).length} questions · ${(e.roster || []).length} students on the roster`),
        h("div", { class: "row", style: "margin-top:8px" },
          h("a", { class: "btn primary", href: `#/exam/${e.id}` }, "Open class"),
          st ? null : h("a", { class: "btn", href: `/capture?exam=${e.id}` }, "Scan papers")));
    }) : h("div", { class: "card muted" }, "No exams yet. Try the demo class, or upload your own exam."));
  }));
}

function newExamForm() {
  const test = h("input", { type: "file", accept: "application/pdf,image/*", multiple: true });
  const key = h("input", { type: "file", accept: "application/pdf,image/*", multiple: true });
  const style = h("textarea", { placeholder: "e.g. Reasoning points need the reasoning on paper. Ignore spelling." });
  const go = h("button", { class: "primary big", onclick: guarded(async () => {
    if (!test.files.length) { toast("Choose the exam file first.", "error"); return; }
    go.disabled = true;
    go.textContent = "Uploading…";
    await createFromFiles([...test.files], [...key.files], style.value.trim());
  }) }, "Create exam");
  return h("div", { class: "card col", style: "max-width:640px" },
    h("h2", {}, "New exam"),
    h("label", {}, h("b", {}, "Your exam"), " — the PDF, or a photo of each page, blank."), test,
    h("label", {}, h("b", {}, "Answer key"), " (optional) — a copy with the correct options marked."), key,
    h("label", {}, h("b", {}, "How you grade"), " (optional) — in your own words."), style,
    h("p", { class: "muted small" }, "The worker reads the exam and finds the questions, answer boxes and points. The rubric marks which criteria are the answer and which are the reasoning, so a bare answer can be followed up."),
    h("div", { class: "row" }, go));
}

async function createFromFiles(testFiles, keyFiles, gradingStyle) {
  const r = await addDoc(collection(db, "exams"), {
    ownerUid: user.uid, name: (testFiles[0].name || "Exam").replace(/\.[^.]+$/, ""), nameFromFile: true, language: "English",
    grading_style: gradingStyle, pages: [], questions: [], roster: [], uploads: [], status: "setting_up", createdAt: serverTimestamp(),
  });
  const uploads = [];
  for (const [kind, files] of [["test", testFiles], ["key", keyFiles]]) {
    for (const f of files) {
      const pdf = f.type === "application/pdf";
      const path = `uploads/${user.uid}/${r.id}/${kind}-${uploads.length + 1}-${shortId()}.${pdf ? "pdf" : "jpg"}`;
      await uploadBytes(ref(storage, path), f, { contentType: pdf ? "application/pdf" : f.type || "image/jpeg" });
      uploads.push({ path, contentType: pdf ? "application/pdf" : "image/jpeg", kind });
    }
  }
  await updateDoc(r, { uploads });
  await job({ type: "setup", examId: r.id });
  location.hash = `#/exam/${r.id}`;
}

async function createDemoClass() {
  toast("Setting up the demo class…");
  const demo = await (await fetch("/demo/exam.json")).json();
  const r = doc(collection(db, "exams"));
  const pages = [];
  for (const [i, p] of demo.pages.entries()) {
    const blob = await (await fetch(p.demo)).blob();
    const path = `masters/${user.uid}/${r.id}/page${i + 1}.png`;
    await uploadBytes(ref(storage, path), blob, { contentType: "image/png" });
    pages.push({ path, width: p.width, height: p.height });
  }
  await setDoc(r, { ...demo, pages, ownerUid: user.uid, status: "ready", demo: true, createdAt: serverTimestamp() });
  await job({ type: "demo_class", examId: r.id });
  location.hash = `#/exam/${r.id}`;
}

// ======================================================================
// Class view
// ======================================================================

async function classView(id) {
  const gen = generation;
  const exam = { id, ...(await getDoc(doc(db, "exams", id))).data() };
  if (gen !== generation) return;
  const hero = h("div");
  const students = h("div");
  const bank = h("div");
  const side = h("div");
  let subs = [];
  let ins = null;
  append(main, 
    h("div", { class: "page-head" }, h("a", { class: "back", href: "#/" }, "← Classes"), h("span", { class: "spacer" }),
      h("a", { class: "btn", href: `/capture?exam=${id}` }, "Scan papers"),
      exam.demo ? h("button", { onclick: guarded(async () => {
        const bruno = subs.find((x) => x.studentName === "Bruno Lima" && x.followup?.items?.length)
          || subs.find((x) => !x.simulated && x.followup?.items?.length);
        if (!bruno) { toast("Scan the demo papers first."); return; }
        await answerYourself(bruno);
      }), title: "Sends Bruno's airplane question to your own account and opens the student chat, so you can answer it live" }, "Answer as Bruno") : null,
      exam.demo ? h("button", { onclick: guarded(async () => { await job({ type: "play_scripts", examId: id }); toast("Playing the scripted replies of the scanned students…"); }),
        title: "Answers the open follow-ups of the scanned demo students from their scripts" }, "Play scripted replies") : null,
      h("button", { onclick: guarded(async () => { await job({ type: "open_followups", examId: id }); toast("Follow-ups sent to every named student."); }) }, "Send follow-ups"),
      h("button", { onclick: guarded(async () => { await job({ type: "insights", examId: id }); toast("Grouping the class's misconceptions…"); }) }, "Update misconception bank")),
    h("h1", {}, exam.name),
    exam.status && exam.status !== "ready" ? h("p", {}, h("span", { class: `chip ${SETUP[exam.status]?.[0] || ""}` }, SETUP[exam.status]?.[1] || exam.status)) : null,
    hero, h("div", { class: "split wide-left" }, students, side));
  append(side, bank, settingsCard(exam));

  const render = () => {
    renderHero(hero, subs, ins);
    renderStudents(students, exam, subs);
    renderBank(bank, exam, ins);
  };
  cleanups.push(onSnapshot(query(collection(db, "submissions"), where("ownerUid", "==", user.uid), where("examId", "==", id)), (snap) => {
    subs = snap.docs.map((d) => ({ id: d.id, ...d.data() }));
    render();
  }));
  cleanups.push(onSnapshot(doc(db, "insights", id), (snap) => { ins = snap.data() || null; render(); }));
  if (exam.course) {
    cleanups.push(onSnapshot(doc(db, "banks", `${user.uid}_${exam.course}`), (snap) => { exam.bank = snap.data()?.entries || []; render(); }));
  }
}

function renderHero(box, subs, ins) {
  const done = subs.filter((s) => s.scores?.profile);
  const counts = Object.fromEntries(Object.keys(PROFILES).map((k) => [k, done.filter((s) => s.scores.profile === k).length]));
  const low = done.filter((s) => s.scores.adjustedReal < 0.7 * s.scores.max);
  const judged = done.filter((s) => s.teacherProfile);
  const agree = judged.filter((s) => s.teacherProfile === s.scores.profile).length;
  const open = subs.filter((s) => ["open", "ready"].includes(s.followup?.status)).length;
  if (!subs.length) {
    setChildren(box, h("div", { class: "card empty-state" }, h("h2", {}, "No papers yet"),
      h("p", { class: "muted" }, "Scan the students' papers with the phone (Scan papers). The demo class fills in by itself in a few seconds.")));
    return;
  }
  const total = done.length || 1;
  setChildren(box, 
    h("div", { class: "hero-metric card" },
      h("div", { class: "big" }, done.length ? pct(counts.almost / done.length) : "–"),
      h("div", {},
        h("div", { class: "headline" }, "of the class was ", h("b", {}, "Almost there"), " behind a low grade"),
        h("div", { class: "muted" }, `${counts.almost} of the ${low.length} students with a low written score got most of the missing points back with little or no help. A grade alone would have put them with the rest.`))),
    h("div", { class: "ins-hero" },
      stat(`${done.length}/${subs.length}`, "students profiled", open ? `${open} follow-up${open > 1 ? "s" : ""} still open` : ""),
      stat(subs.filter((s) => s.followup?.items?.length).length, "had a follow-up", "the others: the paper was enough"),
      stat(judged.length ? pct(agree / judged.length) : "–", "agree with your judgment", judged.length ? `${agree} of ${judged.length} you rated` : "rate students to measure it"),
      stat(Object.entries(ins?.triggers || {}).filter(([, n]) => n).map(([t, n]) => `${t}·${n}`).join("  ") || "–", "follow-ups by trigger", "")),
    h("div", { class: "card" },
      h("div", { class: "profile-bar" }, Object.entries(PROFILES).map(([k, p]) => counts[k]
        ? h("div", { style: `flex:${counts[k]};background:${p.color}`, title: `${p.label}: ${counts[k]}` }, String(counts[k])) : null)),
      h("div", { class: "profile-legend" }, Object.entries(PROFILES).map(([k, p]) => h("div", {},
        h("i", { style: `background:${p.color}` }), h("b", {}, p.label), h("span", { class: "muted" }, ` ${counts[k]} · ${p.action}`))))));
  if (done.length && total) box.querySelector(".big").title = `${counts.almost} of ${done.length} profiled students`;
}

function stat(v, k, sub) {
  return h("div", { class: "stat" }, h("div", { class: "v" }, String(v)), h("div", { class: "k" }, k), sub ? h("div", { class: "muted small" }, sub) : null);
}

function renderStudents(box, exam, subs) {
  const order = { almost: 0, verify: 1, building: 2, not_reached: 3, mastered: 4 };
  const rows = [...subs].sort((a, b) => (order[a.scores?.profile] ?? -1) - (order[b.scores?.profile] ?? -1)
    || (a.studentName || "~").localeCompare(b.studentName || "~"));
  setChildren(box, h("div", { class: "card table-card" },
    h("h2", {}, "Students"),
    h("div", { class: "table-scroll" }, h("table", { class: "students" },
      h("thead", {}, h("tr", {}, ["Student", "Real", "Mediated", "Potential", "Profile", "Follow-up"].map((t) => h("th", {}, t)))),
      h("tbody", {}, rows.map((s) => {
        const sc = s.scores;
        const items = s.followup?.items || [];
        return h("tr", { onclick: () => { location.hash = `#/sub/${s.id}`; } },
          h("td", {}, h("b", {}, s.studentName || "Unnamed paper"), s.simulated ? h("span", { class: "chip tiny" }, "simulated") : null,
            s.status !== "graded" ? h("div", { class: "muted small" }, s.status) : null),
          h("td", { class: "num" }, sc ? `${fmt(sc.adjustedReal)}/${fmt(sc.max)}` : "–"),
          h("td", { class: "num" }, sc && items.length ? fmt(sc.mediated) : "–"),
          h("td", { class: "num" }, sc && items.length ? pct(sc.potential) : "–"),
          h("td", {}, sc ? profileChip(sc.profile, sc.profileLabel) : null,
            s.teacherProfile && s.teacherProfile !== sc?.profile ? h("div", { class: "muted small" }, `you: ${PROFILES[s.teacherProfile].label}`) : null),
          h("td", {}, items.length
            ? h("div", { class: "trig-list" }, items.map((i) => h("span", { class: `chip tiny trig ${i.phase === "done" ? "" : "live"}`, title: i.reason },
              `${i.question.toUpperCase()} ${i.trigger}${i.reached != null ? ` ✓N${i.reached}` : i.phase === "done" ? " ✗" : ""}`)))
            : h("span", { class: "muted small" }, s.followup ? "not needed" : "")));
      }))))));
}

function renderBank(box, exam, ins) {
  const entries = exam.bank || [];
  const added = new Set(ins?.bankAdded || []);
  setChildren(box, h("div", { class: "card" },
    h("h2", {}, "Misconception bank", exam.course ? h("span", { class: "muted small" }, ` · ${exam.course}`) : null),
    h("p", { class: "muted small" }, "What earlier classes got wrong. An answer that matches one gets a follow-up that confronts it (G4). Each exam adds what its class got wrong."),
    entries.length ? h("ul", { class: "bank" }, entries.map((e) => h("li", {},
      h("span", { class: "q" }, (e.question || "").toUpperCase()), " ", e.title,
      added.has(e.id) ? h("span", { class: "chip tiny ok" }, "new from this class") : null))) : h("p", { class: "muted small" }, "Empty."),
    ins?.misconceptions?.length ? h("details", {}, h("summary", { class: "small" }, `This class's mistakes (${ins.ai || ""})`),
      h("ul", { class: "bank" }, ins.misconceptions.slice(0, 8).map((m) => h("li", {}, h("span", { class: "q" }, m.question.toUpperCase()), " ", m.title,
        h("span", { class: "muted small" }, ` · ${m.count}`))))) : null));
}

function settingsCard(exam) {
  const f = exam.followup || {};
  const w = { 0: 1, 1: 0.75, 2: 0.5, 3: 0.25, ...(f.weights || {}) };
  const inputs = [0, 1, 2, 3].map((k) => h("input", { type: "number", min: 0, max: 100, step: 5, value: Math.round(w[k] * 100), style: "width:64px" }));
  const minutes = h("input", { type: "number", min: 3, max: 120, value: f.window_minutes || 15, style: "width:64px" });
  return h("details", { class: "card" },
    h("summary", {}, h("b", {}, "Weights and time")),
    h("p", { class: "muted small" }, "Credit for points recovered at each help level. These are design choices to calibrate with your own judgment, not values from the literature."),
    h("div", { class: "weights" }, inputs.map((inp, k) => h("label", {}, `N${k}`, inp, "%"))),
    h("label", { class: "small" }, "Reply window ", minutes, " minutes"),
    h("div", { class: "row", style: "margin-top:8px" }, h("button", { onclick: guarded(async () => {
      const weights = Object.fromEntries(inputs.map((inp, k) => [String(k), Number(inp.value) / 100]));
      await updateDoc(doc(db, "exams", exam.id), { followup: { ...f, weights, window_minutes: Number(minutes.value) } });
      await job({ type: "insights", examId: exam.id });
      toast("Saved. The class is being rescored with these weights.");
    }) }, "Save")));
}

// ======================================================================
// One student
// ======================================================================

async function studentView(subId) {
  const box = h("div");
  append(main, box);
  let exam = null;
  cleanups.push(onSnapshot(doc(db, "submissions", subId), async (snap) => {
    if (!snap.exists()) { setChildren(box, h("p", {}, "Not found.")); return; }
    const s = { id: subId, ...snap.data() };
    exam ||= { id: s.examId, ...(await getDoc(doc(db, "exams", s.examId))).data() };
    renderStudent(box, exam, s);
  }));
}

function renderStudent(box, exam, s) {
  const sc = s.scores || {};
  const items = s.followup?.items || [];
  const byQ = Object.fromEntries(items.map((i) => [i.question, i]));
  const others = (s.followup?.candidates || []).filter((c) => byQ[c.question]?.trigger !== c.trigger);
  const hasFollowup = items.length > 0;
  setChildren(box, 
    h("div", { class: "page-head" }, h("a", { class: "back", href: `#/exam/${s.examId}` }, `← ${exam.name}`)),
    h("div", { class: "row", style: "align-items:baseline" }, h("h1", {}, s.studentName || "Unnamed paper"),
      s.simulated ? h("span", { class: "chip" }, "simulated classmate") : null,
      s.nameRead ? h("span", { class: "chip", title: "Read from the name box on the paper" }, "name read from the paper") : null),
    s.studentEmail ? null : assignStudent(exam, s),
    exam.demo && hasFollowup && !s.simulated ? h("div", { class: "card row" },
      h("span", {}, `Demo class: answer ${s.studentName ? `${s.studentName.split(" ")[0]}'s` : "this"} follow-up yourself, with your own account, to show the chat live.`),
      h("button", { class: "primary", onclick: guarded(() => answerYourself(s)) }, "Answer it yourself")) : null,
    h("div", { class: "scores3" },
      score3("Real", sc.adjustedReal, sc.max, sc.adjustedReal !== sc.real ? `written ${fmt(sc.real)}, adjusted by a clarification` : "the written grade"),
      score3("Mediated", hasFollowup ? sc.mediated : null, sc.max, hasFollowup ? "with the help the follow-up gave" : "no follow-up needed"),
      h("div", { class: "s3" }, h("div", { class: "k" }, "Learning potential"), h("div", { class: "v" }, hasFollowup ? pct(sc.potential) : "–"),
        h("div", { class: "muted small" }, "of the missing points recovered"))),
    h("div", { class: "card profile-card", style: sc.profile ? `--c:${PROFILES[sc.profile].color}` : "" },
      h("div", {}, h("div", { class: "k" }, "Profile"), h("div", { class: "pname" }, sc.profileLabel || "–"),
        h("div", {}, sc.why || ""), sc.action ? h("div", { class: "muted" }, `Suggested: ${sc.action}`) : null),
      judgment(s)),
    hasFollowup ? null : h("p", { class: "muted" }, "Every answer on the paper was clear evidence, so this student was not asked anything."),
    items.map((i) => itemCard(exam, s, i)),
    others.length ? h("details", { class: "card" }, h("summary", { class: "small" }, `Other signals found (${others.length}), not asked to keep the follow-up short`),
      h("ul", { class: "small" }, others.map((c) => h("li", {}, `${c.question.toUpperCase()} · ${c.trigger} ${TRIGGERS[c.trigger]}: ${c.reason}`)))) : null,
    h("div", { class: "card" }, h("h2", {}, "All answers"), answersTable(exam, s)),
    pagesCard(exam, s));
}

/** Demo class: restart a scanned student's follow-up, send it to the signed-in teacher and open the student chat. */
async function answerYourself(s) {
  if (!(await user.getIdTokenResult()).claims.email_verified) { await user.reload(); await user.getIdToken(true); }
  if (!user.emailVerified) { toast("Sign in with Google (a verified email) to answer a follow-up yourself."); return; }
  const tab = window.open(`/student#${s.id}`, "_blank");
  await job({ type: "try_followup", submissionId: s.id, email: user.email.toLowerCase() });
  toast(`${s.studentName || "The"} follow-up is on its way to ${user.email}${tab ? ", in the new tab" : ": open /student"}.`);
}

function score3(k, v, max, sub) {
  return h("div", { class: "s3" }, h("div", { class: "k" }, k), h("div", { class: "v" }, v == null ? "–" : fmt(v), h("span", {}, ` / ${fmt(max)}`)),
    h("div", { class: "muted small" }, sub));
}

function judgment(s) {
  const sel = h("select", { onchange: guarded(async () => {
    await updateDoc(doc(db, "submissions", s.id), { teacherProfile: sel.value || null });
    toast("Saved your judgment.");
  }) }, h("option", { value: "" }, "— your judgment —"),
  Object.entries(PROFILES).map(([k, p]) => h("option", { value: k, selected: s.teacherProfile === k }, p.label)));
  return h("div", { class: "judgment" }, h("div", { class: "k" }, "You have the final word"), sel,
    s.teacherProfile ? h("div", { class: "small muted" }, s.teacherProfile === s.scores?.profile ? "Agrees with the generated profile." : "Differs from the generated profile.") : null);
}

function assignStudent(exam, s) {
  const sel = h("select", {}, h("option", { value: "" }, "— pick the student —"),
    (exam.roster || []).map((r) => h("option", { value: r.email }, r.name)));
  return h("div", { class: "card row" }, h("span", {}, "The name on the paper could not be read. Who is it?"), sel,
    h("button", { class: "primary", onclick: guarded(async () => {
      const r = exam.roster.find((x) => x.email === sel.value);
      if (!r) return;
      await updateDoc(doc(db, "submissions", s.id), { studentName: r.name, studentEmail: r.email.toLowerCase() });
      await job({ type: "open_followup", submissionId: s.id });
      toast(`Follow-up sent to ${r.name}.`);
    }) }, "Save and send follow-up"));
}

function itemCard(exam, s, i) {
  const q = exam.questions.find((x) => x.id === i.question) || {};
  const r = s.results?.[i.question] || {};
  const per = s.scores?.perQuestion?.[i.question] || {};
  const outcome = i.phase !== "done" ? h("span", { class: "chip warn" }, "in progress")
    : i.reached == null ? h("span", { class: "chip bad" }, i.expired ? "time ran out" : "not reached")
      : h("span", { class: "chip ok" }, `reached at N${i.reached}`);
  const levelOf = (m) => (m.role === "tutor" ? LEVELS[m.level] : null);
  return h("div", { class: "card item" },
    h("div", { class: "row" }, h("span", { class: "chip trig" }, `${i.trigger} · ${TRIGGERS[i.trigger]}`), h("b", {}, `${i.question.toUpperCase()} ${q.prompt || ""}`),
      h("span", { class: "spacer" }), outcome,
      i.transfer != null ? h("span", { class: `chip ${i.transfer ? "ok" : "bad"}` }, i.transfer ? "transfer ✓" : "transfer ✗") : null),
    h("p", { class: "why" }, i.reason),
    h("blockquote", { class: "written" }, h("span", { class: "muted small" }, `On paper · ${fmt(r.score)}/${fmt(r.maxPoints)}`), h("div", {}, i.answer)),
    h("div", { class: "transcript" }, i.messages.map((m) => h("div", { class: `tline ${m.role}` },
      h("span", { class: "who" }, m.role === "tutor" ? levelOf(m) : "Student"), h("span", {}, m.text),
      m.source === "template" && m.role === "tutor" && s.grader !== "mock" ? h("span", { class: "chip tiny", title: "The model's text failed the quality check; the template was used" }, "template") : null))),
    h("div", { class: "row small muted" },
      `Targets: ${i.targets.map((t) => (q.criteria || []).find((c) => c.id === t)?.description || t).join(" · ")}`),
    h("div", { class: "row small" }, `Real ${fmt(per.adjustedReal)} → mediated ${fmt(per.mediated)} of ${fmt(per.max)}`,
      Object.keys(i.met || {}).length ? h("span", { class: "muted" }, ` (${Object.entries(i.met).map(([c, l]) => `${c} at N${l}`).join(", ")})`) : null));
}

function answersTable(exam, s) {
  return h("div", { class: "table-scroll" }, h("table", { class: "answers" },
    h("tbody", {}, exam.questions.map((q) => {
      const r = s.results?.[q.id] || {};
      const text = q.type === "mcq" ? `option ${r.mcq?.selected || "–"} (key ${q.answer})`
        : (r.transcription || []).map((t) => t.text).join(" ") || "–";
      return h("tr", {}, h("td", {}, h("b", {}, q.id.toUpperCase())), h("td", { class: "num" }, `${fmt(r.score)}/${fmt(q.points)}`),
        h("td", {}, text, r.confidence && r.confidence !== "high" ? h("span", { class: "chip tiny warn" }, `${r.confidence} confidence`) : null));
    }))));
}

function pagesCard(exam, s) {
  const pages = Object.entries(s.pages || {}).sort(([a], [b]) => a - b);
  if (!pages.length) return null;
  const left = h("div");
  const show = async (n) => {
    const p = s.pages[n];
    const regions = exam.questions.filter((q) => q.page === Number(n) && s.followup?.items?.some((i) => i.question === q.id))
      .map((q) => ({ box: q.region, kind: "region", label: q.id.toUpperCase(), active: true }));
    setChildren(left, 
      h("div", { class: "tabs" }, pages.map(([k]) => h("button", { class: k === n ? "active" : "", onclick: () => show(k) }, `Page ${k}`))),
      pageView({ src: await fileUrl(p.path), width: p.width, height: p.height, regions }));
  };
  show(pages[pages.length - 1][0]);
  return h("details", { class: "card" }, h("summary", {}, h("b", {}, "The scanned paper")), left);
}

export { deleteDoc };
