"""End-to-end test of the web apps against the local Firebase emulators, with the worker in mock mode.

Needs, in other terminals:
  firebase emulators:start --only auth,firestore,storage,hosting      (repo root)
  uv run python -m asksback worker --emulator --model mock             (worker/)

Then, from worker/:  uv run python e2e/web_flow.py   (screenshots go to out/e2e/)

It plays every role in a real (headless) browser:
  teacher  signs up, creates the demo class (15 simulated classmates), scans the five papers;
  worker   reads each name, grades, detects the triggers and opens each follow-up;
  student  Bruno signs in and answers his follow-up in the chat (hints, transfer question);
  presenter the teacher answers Bruno's follow-up with their own account;
  rules    a student cannot read another student's follow-up, nor reply to it, nor reply before Start;
  class    every profile appears, the "Almost there behind a low grade" metric and the transcripts show.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = "http://127.0.0.1:5002"
PROJECT = "demo-asksback"
AUTH = "http://127.0.0.1:9098"
FIRESTORE = f"http://127.0.0.1:8085/v1/projects/{PROJECT}/databases/(default)/documents"
OUT = Path("out/e2e")
RUN = str(int(time.time()))[-6:]
TEACHER = (f"teacher{RUN}@example.com", "secret123")
WORDS = ("cheating", "ai-generated", "plagiarism")
PASSED: list[str] = []

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from asksback.demo import SCANNED_SCRIPTS


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        sys.exit(1)
    PASSED.append(name)


def http(method: str, url: str, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw[:1] in (b"{", b"[") else {}
    except urllib.error.HTTPError as e:
        return e.code, {}


def id_token(email: str, password: str) -> str:
    _, r = http("POST", f"{AUTH}/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake",
                {"email": email, "password": password, "returnSecureToken": True})
    return r["idToken"]


def verified_student(email: str, password: str = "demo-student") -> str:
    """A verified student account (as the student page's local demo sign-in makes), returns an ID token."""
    _, r = http("POST", f"{AUTH}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=fake",
                {"email": email, "password": password, "returnSecureToken": True})
    if r.get("localId"):
        http("POST", f"{AUTH}/identitytoolkit.googleapis.com/v1/projects/{PROJECT}/accounts:update",
             {"localId": r["localId"], "emailVerified": True}, token="owner")
    return id_token(email, password)


def value(v: dict):
    """Firestore REST value -> Python."""
    if "mapValue" in v:
        return {k: value(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "arrayValue" in v:
        return [value(x) for x in v["arrayValue"].get("values", [])]
    for k in ("stringValue", "booleanValue", "timestampValue"):
        if k in v:
            return v[k]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    return None


def get_doc(path: str, token: str) -> tuple[int, dict]:
    code, d = http("GET", f"{FIRESTORE}/{path}", token=token)
    return code, {k: value(x) for k, x in d.get("fields", {}).items()}


def add_reply(token: str, uid: str, session_id: str, item: int, text: str) -> int:
    body = {"fields": {"sessionId": {"stringValue": session_id}, "item": {"integerValue": item},
                       "text": {"stringValue": text}, "uid": {"stringValue": uid}, "status": {"stringValue": "new"}}}
    url = f"{FIRESTORE}:commit"
    write = {"update": {"name": f"projects/{PROJECT}/databases/(default)/documents/replies/e2e{RUN}{item}{uid[:4]}",
                        **body}, "updateTransforms": [{"fieldPath": "createdAt", "setToServerValue": "REQUEST_TIME"}],
             "currentDocument": {"exists": False}}
    return http("POST", url, {"writes": [write]}, token=token)[0]


def uid_of(token: str) -> str:
    _, r = http("POST", f"{AUTH}/identitytoolkit.googleapis.com/v1/accounts:lookup?key=fake", {"idToken": token})
    return r["users"][0]["localId"]


def sign_up(page: Page, email: str, password: str) -> None:
    page.locator("details.email-signin summary").click()
    page.get_by_placeholder("email").fill(email)
    page.get_by_placeholder("password (6+ characters)").fill(password)
    page.get_by_role("button", name="Create account").click()


def google_account(page: Page, email: str, name: str) -> None:
    """The Auth emulator's stand-in for Google's account picker: add an account and continue."""
    page.wait_for_load_state()
    page.get_by_text("Add new account").click()
    page.locator("#email-input").fill(email)
    page.locator("#display-name-input").fill(name)
    page.get_by_role("button", name="Sign in with Google.com").click()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    http("DELETE", f"{AUTH}/emulator/v1/projects/{PROJECT}/accounts")
    http("DELETE", f"http://127.0.0.1:8085/emulator/v1/projects/{PROJECT}/databases/(default)/documents")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # ------------------------------------------------ teacher: demo class
        teacher = browser.new_context(viewport={"width": 1400, "height": 1000})
        t = teacher.new_page()
        t.on("pageerror", lambda e: print("  [teacher error]", e))
        t.goto(f"{BASE}/teacher")
        sign_up(t, *TEACHER)
        expect(t.get_by_role("heading", name="Your classes")).to_be_visible(timeout=15000)
        expect(t.locator("#worker-chip")).to_contain_text("worker online", timeout=45000)
        check("teacher signs up; worker shows online", True)
        t.get_by_role("button", name="＋ Demo class").click()
        expect(t.get_by_role("heading", name="Everyday Science: Quiz 3")).to_be_visible(timeout=20000)
        expect(t.locator("table.students tbody tr")).to_have_count(15, timeout=60000)
        check("demo class: 15 simulated classmates with finished follow-ups", True)
        exam_id = t.url.split("#/exam/")[1]
        token = id_token(*TEACHER)
        _, exam = get_doc(f"exams/{exam_id}", token)
        _, bank = get_doc(f"banks/{uid_of(token)}_SCI1", token)
        check("course misconception bank seeded", len(bank.get("entries") or []) >= 4, f"{len(bank.get('entries') or [])} entries")

        # ------------------------------------------------ capture: five scanned papers
        c = teacher.new_page()
        c.goto(f"{BASE}/capture?exam={exam_id}")
        c.get_by_role("button", name="Upload demo photos").click()
        expect(c.get_by_text("10 photo(s), 10 matched to a page")).to_be_visible(timeout=180000)
        check("capture uploads 10 photos; worker matches all 10 to a page", True)
        c.close()

        expect(t.locator("table.students tbody tr")).to_have_count(20, timeout=60000)
        names = ["Ana Souza", "Bruno Lima", "Carla Dias", "Diego Alves", "Eva Rocha"]
        for n in names:
            expect(t.locator("table.students tr", has_text=n)).to_have_count(1, timeout=180000)
        check("every name read from the paper and matched to the roster", True)
        t.wait_for_function("document.querySelectorAll('table.students .trig').length >= 21", timeout=180000)
        trig = {n: t.locator("table.students tr", has_text=n).locator(".trig").all_inner_texts() for n in names}
        expect_trig = {"Ana Souza": [], "Bruno Lima": ["Q5 G1", "Q6 G1", "Q7 G2"], "Carla Dias": ["Q5 G4", "Q6 G4"],
                       "Diego Alves": ["Q5 G3", "Q7 G4"], "Eva Rocha": ["Q7 G5"]}
        got = {n: [x.split(" ✓")[0].split(" ✗")[0] for x in v] for n, v in trig.items()}
        check("triggers G1–G5 detected on the scanned papers as designed", got == expect_trig, json.dumps(got))
        t.screenshot(path=str(OUT / "1-class-open.png"), full_page=True)

        # ------------------------------------------------ rules
        subs = {}
        for n in names:
            t.locator("table.students tr", has_text=n).click()
            t.wait_for_url("**#/sub/*")
            subs[n] = t.url.split("#/sub/")[1]
            t.go_back()
        roster = {r["name"]: r["email"] for r in exam["roster"]}
        bruno_email, ana_email = roster["Bruno Lima"], roster["Ana Souza"]
        bruno, ana = verified_student(bruno_email), verified_student(ana_email)
        check("rules: Bruno can read his follow-up", get_doc(f"sessions/{subs['Bruno Lima']}", bruno)[0] == 200)
        check("rules: Ana cannot read Bruno's follow-up", get_doc(f"sessions/{subs['Bruno Lima']}", ana)[0] == 403)
        check("rules: a student cannot read the teacher's submission", get_doc(f"submissions/{subs['Bruno Lima']}", bruno)[0] == 403)
        check("rules: no reply before the student presses Start",
              add_reply(bruno, uid_of(bruno), subs["Bruno Lima"], 0, "hello") == 403)
        check("rules: Ana cannot reply in Bruno's follow-up",
              add_reply(ana, uid_of(ana), subs["Bruno Lima"], 0, "hello") == 403)
        _, sess = get_doc(f"sessions/{subs['Bruno Lima']}", bruno)
        leaked = [k for k in ("targets", "met", "reason", "misconception", "checks") if any(k in i for i in sess["items"])]
        check("the student's session carries no rubric, judgment or trigger reason", not leaked, ", ".join(leaked))

        # ------------------------------------------------ students sign in with Google
        roster = {r["name"]: r["email"] for r in exam["roster"]}
        desk = browser.new_context(viewport={"width": 1200, "height": 900})
        g = desk.new_page()
        g.goto(f"{BASE}/student")
        with desk.expect_page() as popup:
            g.get_by_role("button", name="Continue with Google").click()
        google_account(popup.value, roster["Eva Rocha"], "Eva Rocha")
        expect(g.get_by_role("heading", name="Hi Eva, a few quick questions")).to_be_visible(timeout=20000)
        check("Google sign-in on a computer (popup) opens Eva's follow-up", True)
        desk.close()
        phone = browser.new_context(**pw.devices["iPhone 13"])
        m = phone.new_page()
        m.goto(f"{BASE}/student")
        m.get_by_role("button", name="Continue with Google").click()
        google_account(m, roster["Carla Dias"], "Carla Dias")
        expect(m.get_by_role("heading", name="Hi Carla, a few quick questions")).to_be_visible(timeout=20000)
        m.screenshot(path=str(OUT / "2b-phone-google.png"))
        check("Google sign-in on a phone (redirect) opens Carla's follow-up", True)
        m.get_by_role("button", name="Sign out").click()
        m.get_by_role("button", name="Continue with Google").click()
        google_account(m, "someone.else@example.com", "Someone Else")
        expect(m.get_by_role("button", name="Switch account")).to_be_visible(timeout=20000)
        check("a student signed in with the wrong account is told which one and can switch", True)
        phone.close()
        wa = browser.new_context(user_agent=pw.devices["iPhone 13"]["user_agent"] + " WhatsApp/24.1", is_mobile=True, has_touch=True)
        w = wa.new_page()
        w.goto(f"{BASE}/student")
        expect(w.get_by_text("Open this page in your browser")).to_be_visible(timeout=15000)
        check("inside WhatsApp's browser, the student is told to open the page in a real browser", True)
        wa.close()

        # ------------------------------------------------ student: Bruno answers in the chat
        student = browser.new_context(viewport={"width": 430, "height": 900})
        s = student.new_page()
        s.on("pageerror", lambda e: print("  [student error]", e))
        s.goto(f"{BASE}/student")
        s.get_by_role("button", name="Bruno Lima").click()
        expect(s.get_by_role("button", name="Sign out")).to_be_visible(timeout=20000)
        s.goto(f"{BASE}/student#{subs['Bruno Lima']}")
        expect(s.get_by_role("heading", name="Hi Bruno, a few quick questions")).to_be_visible(timeout=20000)
        s.screenshot(path=str(OUT / "2-student-intro.png"))
        s.get_by_role("button", name="Start").click()
        expect(s.locator(".fu-composer textarea")).to_be_visible(timeout=10000)
        first = s.locator(".bubble.tutor").first.inner_text()
        check("N0 question quotes the student's own answer", "pushes the air down" in first, first)
        s.screenshot(path=str(OUT / "3-student-n0.png"))
        script = {q: list(r) for q, r in SCANNED_SCRIPTS["Bruno Lima"].items()}
        texts = []
        for _ in range(12):
            _, sess = get_doc(f"sessions/{subs['Bruno Lima']}", bruno)
            if sess["status"] != "open":
                break
            item = sess["items"][sess["current"]]
            todo = script.get(item["question"]) or []
            s.locator(".fu-composer textarea").fill(todo.pop(0) if todo else "I am not sure.")
            s.get_by_role("button", name="Send").click()
            s.wait_for_function("!document.querySelector('.fu-composer textarea')?.disabled", timeout=30000)
            s.wait_for_timeout(300)
            texts += s.locator(".bubble.tutor").all_inner_texts()
            if any("On your own" in x or "one more" in x.lower() for x in s.locator(".bubble .tag").all_inner_texts()):
                s.screenshot(path=str(OUT / "4-student-transfer.png"))
        expect(s.get_by_role("heading", name="All done, thank you!")).to_be_visible(timeout=30000)
        s.screenshot(path=str(OUT / "5-student-done.png"))
        check("Bruno finishes the follow-up in the chat", True)
        bad = [w for w in WORDS for x in texts if w in x.lower()]
        check("student-facing text never accuses", not bad, ", ".join(bad))

        # ------------------------------------------------ teacher: play the other scripts, read the class
        t.get_by_role("button", name="Play scripted replies").click()
        t.wait_for_function("[...document.querySelectorAll('table.students tbody tr')].every(r => r.querySelector('.chip.profile'))",
                            timeout=120000)
        t.wait_for_timeout(1500)
        prof = {n: t.locator("table.students tr", has_text=n).locator(".chip.profile").inner_text() for n in names}
        print("  profiles:", prof)
        check("Bruno: Almost there behind a low grade", prof["Bruno Lima"] == "Almost there")
        check("Eva: Verify understanding", prof["Eva Rocha"] == "Verify understanding")
        check("Ana: Mastered with no follow-up", prof["Ana Souza"] == "Mastered")
        legend = t.locator(".profile-legend").inner_text()
        all_profiles = all(t.locator(f".profile-bar div[title^='{p}']").count() == 1
                           for p in ("Mastered", "Almost there", "Building", "Not reached", "Verify understanding"))
        check("every profile appears in the class", all_profiles, legend.replace("\n", " "))
        metric = t.locator(".hero-metric .big").inner_text()
        check("demo metric: share of the class that was Almost there behind a low grade", metric.endswith("%"), metric)
        page_text = t.locator("#app").inner_text().lower()
        check("teacher-facing text never accuses", not any(w in page_text for w in WORDS))
        t.screenshot(path=str(OUT / "6-class.png"), full_page=True)

        # agreement with the teacher's judgment
        t.locator("table.students tr", has_text="Bruno Lima").click()
        expect(t.locator(".profile-card .pname")).to_have_text("Almost there", timeout=10000)
        check("student view: three scores", t.locator(".scores3 .s3").count() == 3)
        check("student view: one transcript per follow-up", t.locator(".card.item").count() == 3)
        check("student view: hints and transfer recorded with their level",
              t.locator(".tline .who", has_text="N1").count() >= 1 and t.locator(".tline .who", has_text="Transfer").count() >= 1)
        t.screenshot(path=str(OUT / "7-student-view.png"), full_page=True)
        t.locator(".judgment select").select_option(label="Almost there")
        expect(t.get_by_text("Agrees with the generated profile.")).to_be_visible(timeout=10000)
        t.get_by_role("link", name="← Everyday Science: Quiz 3").click()
        t.get_by_role("button", name="Update misconception bank").click()
        expect(t.locator(".stat", has_text="agree with your judgment").locator(".v")).to_have_text("100%", timeout=60000)
        check("agreement with the teacher's judgment is measured", True)

        # ------------------------------------------------ weights are the teacher's
        t.locator("details.card summary", has_text="Weights and time").click()
        before = t.locator("table.students tr", has_text="Bruno Lima").locator("td").nth(2).inner_text()
        t.locator(".weights input").nth(1).fill("50")
        t.get_by_role("button", name="Save").click()
        t.wait_for_function(f"""[...document.querySelectorAll('table.students tr')].find(r => r.innerText.includes('Bruno Lima'))
                            ?.querySelectorAll('td')[2].innerText !== {json.dumps(before)}""", timeout=60000)
        after = t.locator("table.students tr", has_text="Bruno Lima").locator("td").nth(2).inner_text()
        check("changing the N1 weight rescores the class", before != after, f"Bruno mediated {before} -> {after}")

        # ------------------------------------------------ the presenter answers Bruno's follow-up live
        tok = id_token(*TEACHER)
        http("POST", f"{AUTH}/identitytoolkit.googleapis.com/v1/projects/{PROJECT}/accounts:update",
             {"localId": uid_of(tok), "emailVerified": True}, token="owner")
        t.reload()
        with teacher.expect_page() as popup:
            t.get_by_role("button", name="Answer as Bruno").click()
        p = popup.value
        expect(p.get_by_text("Demo: you are answering Bruno Lima's follow-up")).to_be_visible(timeout=30000)
        p.get_by_role("button", name="Start").click()
        expect(p.locator(".fu-composer textarea")).to_be_visible(timeout=10000)
        p.locator(".fu-composer textarea").fill("It just goes up.")
        p.get_by_role("button", name="Send").click()
        expect(p.locator(".bubble.tutor")).to_have_count(2, timeout=30000)
        _, sess = get_doc(f"sessions/{subs['Bruno Lima']}", tok)
        check("the presenter's follow-up is one question (the airplane)", len(sess["items"]) == 1, str(len(sess["items"])))
        p.screenshot(path=str(OUT / "8-presenter.png"))
        check("the teacher answers Bruno's follow-up with their own account and gets a hint", True)
        t.get_by_role("button", name="Play scripted replies").click()
        t.wait_for_timeout(3000)
        _, sess = get_doc(f"sessions/{subs['Bruno Lima']}", tok)
        check("scripted replies leave the presenter's session alone", sess["status"] == "open" and sess["current"] == 0)

        # ------------------------------------------------ tour
        tp = teacher.new_page()
        tp.set_viewport_size({"width": 1440, "height": 900})
        errors = []
        tp.on("pageerror", lambda e: errors.append(str(e)))
        tp.goto(f"{BASE}/tour")
        n = tp.locator(".slide").count()
        for i in range(1, n + 1):
            tp.goto(f"{BASE}/tour#{i}")
            tp.wait_for_timeout(900)
            tp.screenshot(path=str(OUT / f"tour-{i:02d}.png"))
        tp.keyboard.press("ArrowRight")
        check("tour: every slide renders without errors", n >= 6 and not errors, f"{n} slides {errors[:1]}")
        tp.goto(f"{BASE}/tour#4")
        tp.wait_for_timeout(900)
        tp.locator("#trig-pick button", has_text="G4").click()
        check("tour: picking a trigger shows its example", "verão" in tp.locator("#trig-detail").inner_text())
        tp.keyboard.press("n")
        check("tour: N shows the presenter notes for the slide", tp.locator("#notes-panel").is_visible()
              and "exceções" in tp.locator("#notes-text").inner_text())
        tp.keyboard.press("n")
        tp.goto(f"{BASE}/tour#8")
        tp.wait_for_timeout(900)
        tp.locator("#c-students").fill("1000")
        check("tour: the cost calculator updates", "R$" in tp.locator("#c-out-text").inner_text(), tp.locator("#c-out-text").inner_text())
        links = {a.get_attribute("href") for a in tp.locator(".try a, .slide a.cta").all()}
        check("tour: demo steps link to the teacher, capture and student apps", {"/teacher", "/capture", "/student"} <= links)
        browser.close()
    print(f"\nAll {len(PASSED)} checks passed. Screenshots in {OUT.resolve()}")


if __name__ == "__main__":
    main()
