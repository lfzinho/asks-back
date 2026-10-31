// Student follow-up: a short written conversation about a few answers from the exam.
// One question at a time, short replies, a time window that starts when the student presses Start.
import { auth, db, usingEmulator, app } from "./fb.js";
import { h, authGate, toast } from "./ui.js";
import {
  collection, doc, addDoc, updateDoc, query, where, onSnapshot, serverTimestamp,
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js";
import {
  signInWithEmailAndPassword, createUserWithEmailAndPassword, signOut,
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";

const MAX_CHARS = 600;
let main;
let user;
let sessions = [];
let stopSession = null;
let ticker = null;

const root = document.getElementById("app");
if (usingEmulator && !auth.currentUser) demoSignIn(root);

authGate(root, {
  app: "follow-up",
  subtitle: "Use the Google account (or email) your teacher has for you, usually your school account.",
  requireVerified: true,
  onUser: (u, m) => {
    user = u;
    main = m;
    main.classList.add("narrow");
    onSnapshot(query(collection(db, "sessions"), where("studentEmail", "==", u.email.toLowerCase())), (snap) => {
      sessions = snap.docs.map((d) => ({ id: d.id, ...d.data() }))
        .sort((a, b) => (b.openedAt || 0) - (a.openedAt || 0));
      route();
    }, (e) => main.replaceChildren(h("div", { class: "card" }, `Could not load your follow-ups: ${e.message}`)));
    window.addEventListener("hashchange", route);
  },
});

function route() {
  const id = location.hash.replace(/^#\/?/, "");
  const open = sessions.filter((s) => s.status === "open");
  const pick = sessions.find((s) => s.id === id) || (open.length === 1 && !id ? open[0] : null);
  if (pick) showSession(pick.id);
  else showList();
}

function showList() {
  stopSession?.(); stopSession = null;
  main.replaceChildren(
    h("h1", {}, "Your follow-ups"),
    sessions.length
      ? h("div", { class: "col", style: "margin-top:16px" }, sessions.map((s) => h("a", { class: "card fu-link", href: `#${s.id}` },
        h("div", {}, h("b", {}, s.examName), h("div", { class: "muted small" }, `${s.items.length} short question${s.items.length > 1 ? "s" : ""}`)),
        h("span", { class: `chip ${s.status === "open" ? "ok" : ""}` }, s.status === "open" ? "open" : "finished"))))
      : h("div", { class: "card", style: "margin-top:16px" },
        h("p", { class: "muted", style: "margin-top:0" }, "Nothing to answer. When a teacher wants to hear more about one of your exam answers, it appears here."),
        h("p", { class: "small" }, "You are signed in as ", h("b", {}, user.email),
          ". If your teacher has a different email for you (your school account, for example), sign out and sign in with that one."),
        h("button", { onclick: () => signOut(auth).then(() => location.reload()) }, "Switch account")));
}

// ---------------------------------------------------------------- one session

function showSession(id) {
  stopSession?.();
  clearInterval(ticker);
  const view = h("div", { class: "fu" });
  main.replaceChildren(view);
  let pending = null; // {item, count}: a reply sent, waiting for the next message
  let draft = "";
  let lastKey = "";
  stopSession = onSnapshot(doc(db, "sessions", id), (snap) => {
    const s = { id, ...snap.data() };
    const item = s.items[s.current];
    if (pending && (!item || s.current !== pending.item || item.messages.length > pending.count)) pending = null;
    const key = JSON.stringify([s.status, s.current, s.startedAt?.seconds, item?.messages.length, !!pending]);
    if (key === lastKey) return;
    lastKey = key;
    render(s);
  });

  function render(s) {
    clearInterval(ticker);
    if (!s.startedAt && s.status === "open") return view.replaceChildren(intro(s));
    if (s.status !== "open") return view.replaceChildren(finished(s));
    const deadline = s.startedAt.toDate().getTime() + s.windowMinutes * 60000;
    const item = s.items[s.current];
    const clock = h("span", { class: "fu-clock" });
    const head = h("div", { class: "fu-head" },
      h("div", { class: "fu-steps" }, s.items.map((it, i) => h("span", {
        class: `fu-step ${i < s.current ? "done" : i === s.current ? "now" : ""}`, title: `Question ${i + 1}` }))),
      h("span", { class: "muted small" }, `Question ${s.current + 1} of ${s.items.length}`),
      h("span", { class: "spacer" }), clock);
    const thread = h("div", { class: "fu-thread" },
      h("div", { class: "fu-context" },
        h("div", { class: "fu-kind" }, item.kind),
        h("div", { class: "fu-prompt" }, item.prompt),
        item.answer ? h("blockquote", {}, h("span", { class: "muted small" }, "You wrote on the exam"), h("div", {}, item.answer)) : null),
      item.messages.map(bubble),
      pending ? h("div", { class: "bubble tutor typing" }, h("i"), h("i"), h("i")) : null);
    const box = h("textarea", { rows: 3, maxlength: MAX_CHARS, placeholder: "Write your answer in a sentence or two…",
      disabled: !!pending, oninput: () => { draft = box.value; count.textContent = `${box.value.length}/${MAX_CHARS}`; },
      onkeydown: (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } } });
    box.value = draft;
    const count = h("span", { class: "muted small" }, `${draft.length}/${MAX_CHARS}`);
    const soft = h("span", { class: "muted small fu-soft" });
    const sendBtn = h("button", { class: "primary", disabled: !!pending, onclick: send }, pending ? "…" : "Send");
    const composer = h("div", { class: "fu-composer" }, box,
      h("div", { class: "row" }, soft, h("span", { class: "spacer" }), count, sendBtn));
    view.replaceChildren(head, thread, composer);
    thread.lastElementChild?.scrollIntoView({ block: "end", behavior: "smooth" });
    if (!pending) box.focus();

    const lastTutor = [...item.messages].reverse().find((m) => m.role === "tutor");
    const askedAt = Date.now();
    const tick = () => {
      const left = Math.max(0, deadline - Date.now());
      clock.textContent = `${Math.floor(left / 60000)}:${String(Math.floor(left / 1000) % 60).padStart(2, "0")} left`;
      clock.classList.toggle("low", left < 120000);
      const since = (Date.now() - askedAt) / 1000;
      soft.textContent = lastTutor && since > (s.softSeconds || 180) ? "Take your time, a short answer is fine." : "";
      if (left <= 0) { clearInterval(ticker); box.disabled = true; sendBtn.disabled = true; clock.textContent = "time is up"; }
    };
    tick();
    ticker = setInterval(tick, 1000);

    async function send() {
      const text = box.value.trim();
      if (!text || pending) return;
      pending = { item: s.current, count: item.messages.length + 1 };
      draft = "";
      item.messages.push({ role: "student", text, kind: "reply" });
      render(s);
      try {
        await addDoc(collection(db, "replies"), { sessionId: s.id, item: s.current, text, uid: user.uid, status: "new",
          createdAt: serverTimestamp() });
      } catch (e) {
        item.messages.pop();
        pending = null;
        draft = text;
        render(s);
        toast(e.code === "permission-denied" ? "This follow-up is closed." : `Could not send: ${e.message}`, "error");
      }
    }
  }
}

function bubble(m) {
  if (m.role === "student") return h("div", { class: "bubble me" }, m.text);
  const tag = { hint: "Hint", transfer: "One more, on your own" }[m.kind];
  return h("div", { class: `bubble tutor ${m.kind}` }, tag ? h("div", { class: "tag" }, tag) : null, m.text);
}

function intro(s) {
  const n = s.items.length;
  return h("div", { class: "card fu-intro" },
    h("div", { class: "fu-badge" }, "💬"),
    h("h1", {}, `Hi ${(s.studentName || "").split(" ")[0] || "there"}, a few quick questions`),
    h("p", {}, `Your teacher read your exam “${s.examName}”. For ${n === 1 ? "one answer" : `${n} answers`}, the paper didn't show everything you know, so we'd like to hear a bit more.`),
    h("ul", { class: "fu-rules" },
      h("li", {}, h("b", {}, "This is not a new test."), " Short written replies, one question at a time."),
      h("li", {}, h("b", {}, "If you get stuck, that's fine."), " You'll get a hint and can try again."),
      h("li", {}, h("b", {}, `${s.windowMinutes} minutes`), " in total, starting when you press Start. Stay on this page and answer in your own words.")),
    h("button", { class: "primary big", onclick: async (e) => {
      e.target.disabled = true;
      try { await updateDoc(doc(db, "sessions", s.id), { startedAt: serverTimestamp() }); }
      catch (err) { e.target.disabled = false; toast(`Could not start: ${err.message}`, "error"); }
    } }, "Start"));
}

function finished(s) {
  return h("div", { class: "card fu-intro" },
    h("div", { class: "fu-badge" }, s.status === "expired" ? "⏱" : "✓"),
    h("h1", {}, s.status === "expired" ? "Time is up" : "All done, thank you!"),
    h("p", {}, "Your teacher will read this conversation together with your exam. You don't need to do anything else."),
    h("details", {}, h("summary", { class: "muted small" }, "See the conversation"),
      s.items.map((it, i) => h("div", { class: "fu-review" },
        h("div", { class: "fu-kind" }, `Question ${i + 1} · ${it.prompt}`), it.messages.map(bubble)))),
    sessions.length > 1 ? h("p", {}, h("a", { href: "#" }, "← All follow-ups")) : null);
}

// ---------------------------------------------------------------- local demo only

/** On the local emulator: one click signs in as a demo student, with the email already verified. */
async function demoSignIn(rootEl) {
  const demo = await fetch("/demo/exam.json").then((r) => r.json()).catch(() => null);
  if (!demo) return;
  const scanned = demo.roster.slice(0, 5);
  const panel = h("div", { class: "card demo-panel" },
    h("b", {}, "Local demo"), h("span", { class: "muted small" }, " sign in as a student of the demo class:"),
    h("div", { class: "row", style: "margin-top:8px; flex-wrap:wrap" }, scanned.map((r) => h("button", { onclick: () => asStudent(r.email) }, r.name))));
  const place = () => { if (!auth.currentUser && !rootEl.querySelector(".demo-panel")) rootEl.querySelector(".wrap")?.prepend(panel); };
  new MutationObserver(place).observe(rootEl, { childList: true, subtree: true });
  place();
}

async function asStudent(email) {
  const password = "demo-student";
  const cred = await signInWithEmailAndPassword(auth, email, password)
    .catch(() => createUserWithEmailAndPassword(auth, email, password));
  if (!cred.user.emailVerified) {
    const project = app.options.projectId;
    await fetch(`http://127.0.0.1:9098/identitytoolkit.googleapis.com/v1/projects/${project}/accounts:update`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer owner" },
      body: JSON.stringify({ localId: cred.user.uid, emailVerified: true }),
    });
    await cred.user.reload();
    await cred.user.getIdToken(true);
  }
  location.reload();
}
