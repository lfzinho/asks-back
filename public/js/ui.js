// Small DOM helpers, sign-in card and worker status shared by the apps.
import { auth, db, usingEmulator } from "./fb.js";
import {
  onAuthStateChanged, signInWithPopup, signInWithRedirect, getRedirectResult, GoogleAuthProvider,
  signInWithEmailAndPassword, createUserWithEmailAndPassword, sendEmailVerification, signOut,
} from "https://www.gstatic.com/firebasejs/12.4.0/firebase-auth.js";
import { doc, onSnapshot } from "https://www.gstatic.com/firebasejs/12.4.0/firebase-firestore.js";

/** h("div", {class: "x", onclick: fn}, child, [children], "text") */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

/** Replace an element's children; accepts nested arrays and skips null/false. */
export function setChildren(el, ...children) {
  el.replaceChildren(...children.flat(Infinity).filter((c) => c != null && c !== false));
}

let toastTimer;
export function toast(message, kind = "info") {
  document.querySelector(".toast")?.remove();
  const el = h("div", { class: `toast ${kind}` }, message);
  document.body.append(el);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.remove(), kind === "error" ? 6000 : 3000);
}

export function fmt(v) {
  return v == null ? "–" : Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

export function shortId() {
  return Math.random().toString(36).slice(2, 10);
}

function authErrorText(e) {
  const code = (e && e.code) || "";
  if (code.includes("popup-closed-by-user") || code.includes("cancelled-popup-request")) return "";
  if (code.includes("account-exists-with-different-credential"))
    return "This email already has an account with a password. Sign in with email and password below.";
  if (code.includes("unauthorized-domain")) return `This address (${location.host}) is not allowed to sign in yet.`;
  if (code.includes("network-request-failed")) return "No connection to Google. Check the internet and try again.";
  if (code.includes("too-many-requests")) return "Too many attempts. Wait a minute and try again.";
  if (code.includes("user-disabled")) return "This account is disabled. Ask your teacher.";
  if (code.includes("invalid-credential") || code.includes("wrong-password") || code.includes("user-not-found"))
    return "Wrong email or password.";
  if (code.includes("email-already-in-use")) return "That email already has an account. Sign in instead.";
  if (code.includes("weak-password")) return "Use at least 6 characters for the password.";
  if (code.includes("operation-not-allowed")) return "This sign-in method is not enabled in Firebase yet.";
  if (code.includes("popup")) return "The Google window was blocked. Allow popups for this site, or try again.";
  return e.message || String(e);
}

/**
 * Top bar + sign-in. Calls onUser(user) once signed in (and, with requireVerified,
 * once the email is verified). Returns nothing; renders into `root`.
 */
export function authGate(root, { app, subtitle, requireVerified = false, onUser }) {
  const bar = h("div", { class: "topbar" },
    h("a", { class: "brand", href: "/" }, "AsksBack"),
    h("span", { class: "muted" }, app),
    usingEmulator ? h("span", { class: "chip warn" }, "local emulator") : null,
    h("span", { class: "spacer" }),
    h("span", { id: "worker-chip" }),
    h("span", { id: "user-chip" }));
  const main = h("div", { class: "wrap" });
  root.replaceChildren(bar, main);

  let started = false;
  onAuthStateChanged(auth, async (user) => {
    await redirectDone;
    user = auth.currentUser;
    const chip = bar.querySelector("#user-chip");
    chip.replaceChildren();
    if (!user) {
      started = false;
      main.replaceChildren(signInCard(app, subtitle));
      return;
    }
    chip.append(h("span", { class: "chip" }, user.email || user.uid),
      " ", h("button", { onclick: () => signOut(auth).then(() => location.reload()) }, "Sign out"));
    if (requireVerified && !user.emailVerified) {
      main.replaceChildren(verifyCard(user));
      return;
    }
    if (started) return;
    started = true;
    main.replaceChildren();
    onUser(user, main);
  });
}

// ---------------------------------------------------------------- Google sign-in

/** Browsers inside other apps (WhatsApp, Instagram, Facebook, LinkedIn, Gmail…), where Google refuses to sign in. */
export const inAppBrowser = /FBAN|FBAV|FB_IAB|Instagram|WhatsApp|Line\/|LinkedInApp|Snapchat|TikTok|MicroMessenger|GSA\/|; wv\)/
  .test(navigator.userAgent);
const touchFirst = matchMedia("(pointer: coarse)").matches && !matchMedia("(hover: hover)").matches;
let redirectError = "";
const redirectDone = getRedirectResult(auth).catch((e) => { redirectError = authErrorText(e); });

function google() {
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" }); // shared school computers: always pick the account
  return provider;
}

/** Popup on computers, a full-page redirect on phones and wherever a popup cannot open. */
export async function signInWithGoogle() {
  if (touchFirst) return signInWithRedirect(auth, google());
  try {
    return await signInWithPopup(auth, google());
  } catch (e) {
    const code = e?.code || "";
    if (code.includes("popup-blocked") || code.includes("operation-not-supported") || code.includes("web-storage-unsupported"))
      return signInWithRedirect(auth, google());
    throw e;
  }
}

function openInBrowserCard() {
  const msg = h("span", { class: "small muted" });
  return h("div", { class: "card", style: "max-width: 420px; margin: 0 auto 16px; border-color: #f1dcb3; background: var(--warn-soft)" },
    h("b", {}, "Open this page in your browser"),
    h("p", { class: "small" }, "Google does not allow signing in inside this app. Tap ⋯ and choose “Open in browser” (Chrome or Safari), or copy the link:"),
    h("div", { class: "row" }, h("button", { onclick: async () => {
      try { await navigator.clipboard.writeText(location.href); msg.textContent = "Link copied."; }
      catch { msg.textContent = location.href; }
    } }, "Copy link"), msg));
}

function signInCard(app, subtitle) {
  const email = h("input", { type: "email", placeholder: "email", autocomplete: "email" });
  const password = h("input", { type: "password", placeholder: "password (6+ characters)", autocomplete: "current-password" });
  const err = h("div", { class: "small", style: "color: var(--bad)" });
  const run = (fn) => async () => {
    err.textContent = "";
    try { await fn(); } catch (e) { err.textContent = authErrorText(e); }
  };
  err.textContent = redirectError;
  const googleBtn = h("button", { class: "primary big google-btn", onclick: async () => {
    err.textContent = "";
    googleBtn.disabled = true;
    googleBtn.lastChild.textContent = "Opening Google…";
    try { await signInWithGoogle(); } catch (e) { err.textContent = authErrorText(e); }
    googleBtn.disabled = false;
    googleBtn.lastChild.textContent = "Continue with Google";
  } }, h("span", { class: "g-logo", "aria-hidden": "true" }), h("span", {}, "Continue with Google"));
  return h("div", {},
    inAppBrowser ? openInBrowserCard() : null,
    h("div", { class: "card signin", style: "max-width: 420px; margin: 40px auto" },
      h("h2", {}, `Sign in to the ${app}`),
      subtitle ? h("p", { class: "muted small" }, subtitle) : null,
      googleBtn, err,
      h("details", { class: "email-signin" },
        h("summary", { class: "small muted" }, "Use email and password instead"),
        h("div", { class: "col", style: "margin-top: 10px" }, email, password,
          h("div", { class: "row" },
            h("button", { onclick: run(() => signInWithEmailAndPassword(auth, email.value.trim(), password.value)) }, "Sign in"),
            h("button", { onclick: run(async () => {
              const cred = await createUserWithEmailAndPassword(auth, email.value.trim(), password.value);
              await sendEmailVerification(cred.user).catch(() => {});
            }) }, "Create account"))))));
}

function verifyCard(user) {
  const msg = h("div", { class: "small muted" });
  return h("div", { class: "card", style: "max-width: 460px; margin: 40px auto" },
    h("h2", {}, "Verify your email"),
    h("p", {}, `We sent a link to ${user.email}. Open it, then come back and press continue.`),
    usingEmulator ? h("p", { class: "small muted" },
      "Local emulator: the link is printed in the emulator terminal, or open the Auth tab of the emulator UI (http://127.0.0.1:4002/auth).") : null,
    h("div", { class: "row" },
      h("button", { class: "primary", onclick: async () => {
        await user.reload();
        if (auth.currentUser.emailVerified) {
          await auth.currentUser.getIdToken(true);
          location.reload();
        } else msg.textContent = "Not verified yet.";
      } }, "I verified, continue"),
      h("button", { onclick: async () => {
        await sendEmailVerification(user).then(() => (msg.textContent = "Sent again."),
          (e) => (msg.textContent = authErrorText(e)));
      } }, "Send the email again")),
    msg);
}

/** Live "worker online/offline" chip in the top bar. */
export function watchWorker() {
  const chip = document.querySelector("#worker-chip");
  if (!chip) return;
  let last = null;
  let grader = "";
  const render = () => {
    const age = last ? (Date.now() - last.getTime()) / 1000 : Infinity;
    chip.replaceChildren(age < 150
      ? h("span", { class: "chip ok", title: "The worker on the PC is running" }, `● worker online (${grader})`)
      : h("span", { class: "chip bad", title: "Start it on the PC: uv run python -m asksback worker" }, "● worker offline"));
  };
  onSnapshot(doc(db, "workers", "main"), (snap) => {
    const d = snap.data();
    last = d?.lastSeen?.toDate?.() || null;
    grader = d?.grader || "";
    render();
  }, () => chip.replaceChildren());
  setInterval(render, 15000);
  render();
}
