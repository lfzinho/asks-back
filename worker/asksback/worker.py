"""The worker: connects the web apps to grading and follow-ups through Firebase.

It watches Firestore for photos from the capture app, aligns each one to its exam's blank pages,
groups pages into one submission per student, reads the student's name, grades, detects the
follow-up triggers and opens the student's follow-up session. Then it answers each student reply
through the mediation ladder, and computes the three scores and the profile when the session ends.
It uses admin credentials, so it is not limited by the security rules that apply to the web apps.

Firestore (top-level collections):
  exams/{id}        ownerUid, name, course, language, grading_style, pages[{path,width,height}], questions[],
                    roster[{name,email}], name_region, followup{settings}, status: setting_up|reading|ready|error
  captures/{id}     examId, ownerUid, sessionId, seq, path, status: uploaded|processing|matched|unmatched|error
  submissions/{id}  examId, ownerUid, pages{"1": {...}}, results{qid: {...}}, status: collecting|grading|graded|error,
                    student{Name,Email}, followup{status, items[], candidates[]}, scores{...}, teacherProfile, simulated
  sessions/{id}     same id as the submission; what the student sees: items[{prompt, answer, messages[]}], status
                    draft|open|done|expired, studentEmail, windowMinutes, startedAt (set by the student),
                    presenter (the demo class's teacher answering it)
  replies/{id}      sessionId, item, text, uid, status "new" (written by the student; read only by the worker)
  banks/{course}    ownerUid, entries[] (the course's misconception bank)
  jobs/{id}         type setup|grade|open_followup(s)|try_followup|demo_class|play_scripts|reset_demo|insights, examId or submissionId
  insights/{examId} the class view: misconceptions, profile counts, demo metrics
  workers/main      heartbeat shown in the web apps
Storage (everything under the teacher's uid, so the rules check ownership from the path alone):
  uploads/ masters/ captures/ aligned/{uid}/{examId}/...
"""

from __future__ import annotations

import datetime as dt
import json
import os
import queue
import re
import threading
import time
import traceback
import uuid
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np
from google.cloud import firestore, storage
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.field_path import FieldPath

from . import demo, ladder
from .config import TRIGGERS, settings
from .exam import Exam
from .grader import ModelGrader, OfflineGrader, read_handwriting
from .images import crop
from .insights import build_insights, grow_bank
from .pipeline import grade_pages
from .register import Registrar
from .results import result_doc
from .scoring import class_summary, student_scores
from .setup import MockExamAI, ModelExamAI, build_exam, load_pages

PROJECT = os.environ.get("ASKSBACK_PROJECT", "demo-asksback")
HEARTBEAT_SECONDS = 30
ALIGNED_JPEG_QUALITY = 82
STUDENT_TYPES = {  # what the student sees as the kind of question: never the trigger itself
    "justification": "Explain your reasoning", "elaboration": "Tell us more", "clarification": "Help us understand",
    "misconception": "What do you think?", "transfer": "Apply the idea",
}


def default_bucket(project: str) -> str:
    """The emulator's bucket for demo- projects, else the default bucket of a project created since late 2024."""
    return f"{project}.appspot.com" if project.startswith("demo-") else f"{project}.firebasestorage.app"


def _log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def _plain(value):
    """Firestore-safe copy: tuples to lists, no NaN, string keys."""
    return json.loads(json.dumps(value, default=list))


def student_view(items: list[dict], questions: dict[str, dict]) -> list[dict]:
    """The session items without anything the student must not see (rubric targets, judgments, scores)."""
    return [{
        "question": i["question"],
        "prompt": questions[i["question"]].get("prompt") or f"Question {i['question'].upper()}",
        "kind": STUDENT_TYPES[i["type"]],
        "answer": i["answer"],
        "messages": [{"role": m["role"], "text": m["text"], "kind": m["kind"]} for m in i["messages"]],
        "done": i["phase"] == "done",
    } for i in items]


class Worker:
    def __init__(self, *, project: str = PROJECT, bucket: str | None = None, backend: str = "mock",
                 key: str | None = None, emulator: bool = False, cache_dir: Path = Path("out/worker")):
        creds = None
        if emulator:
            os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8085")
            os.environ.setdefault("STORAGE_EMULATOR_HOST", "http://127.0.0.1:9198")
            from google.auth.credentials import AnonymousCredentials

            creds = AnonymousCredentials()
        elif key:
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(key)
        self.db = firestore.Client(project=project, credentials=creds)
        self.bucket = storage.Client(project=project, credentials=creds).bucket(bucket or default_bucket(project))
        self.backend = backend
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.queue: queue.Queue = queue.Queue()
        self._exams: dict[str, tuple] = {}
        self._watches = []
        self._lock = threading.Lock()
        self.replies: queue.Queue = queue.Queue()

    # ---------- storage ----------

    def _download_image(self, path: str) -> np.ndarray:
        data = self.bucket.blob(path).download_as_bytes()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"not an image: {path}")
        return img

    def _upload_jpeg(self, path: str, img: np.ndarray, quality: int = ALIGNED_JPEG_QUALITY) -> None:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise ValueError("jpeg encode failed")
        blob = self.bucket.blob(path)
        # A download token lets the web apps show the image through getDownloadURL().
        blob.metadata = {"firebaseStorageDownloadTokens": str(uuid.uuid4())}
        blob.upload_from_string(buf.tobytes(), content_type="image/jpeg")

    # ---------- exams and the misconception bank ----------

    def _exam(self, exam_id: str):
        snap = self.db.collection("exams").document(exam_id).get()
        if not snap.exists:
            raise ValueError(f"exam {exam_id} not found")
        cached = self._exams.get(exam_id)
        if cached and cached[0] == snap.update_time:
            return cached[1:]
        data = snap.to_dict()
        pages = [p["path"] for p in data.get("pages", [])]
        if not pages:
            raise ValueError("the exam has no blank pages yet")
        exam = Exam.model_validate({**data, "pages": pages})
        masters = [self._download_image(p) for p in pages]
        grader = ModelGrader(exam, masters, self.backend) if self.backend in ("claude", "openrouter") \
            else OfflineGrader(self.cache_dir / "ocr")
        self._exams[exam_id] = (snap.update_time, data, exam, masters, Registrar(masters), grader)
        _log(f"loaded exam '{exam.name}' ({len(pages)} pages, {len(exam.questions)} questions)")
        return self._exams[exam_id][1:]

    def bank(self, exam: dict) -> list[dict]:
        if not exam.get("course"):
            return []
        snap = self.db.collection("banks").document(f"{exam['ownerUid']}_{exam['course']}").get()
        return (snap.to_dict() or {}).get("entries", []) if snap.exists else []

    def setup_exam(self, exam_id: str) -> None:
        """Read the uploaded blank exam (and answer key copy) and fill in the exam."""
        ref = self.db.collection("exams").document(exam_id)
        data = ref.get().to_dict()
        ref.update({"status": "reading", "setupError": None})
        _log(f"exam {exam_id}: reading the exam")
        try:
            test, key = [], []
            for up in data.get("uploads", []):
                pages = load_pages(self.bucket.blob(up["path"]).download_as_bytes(), up.get("contentType", ""))
                (key if up.get("kind") == "key" else test).extend(pages)
            if not test:
                raise ValueError("no exam pages were uploaded")
            ai = ModelExamAI(self.backend) if self.backend in ("claude", "openrouter") else MockExamAI()
            result = build_exam(test, key, ai, style=data.get("grading_style", ""), language=data.get("language", "English"))
            pages = []
            for i, img in enumerate(test, start=1):
                path = f"masters/{data['ownerUid']}/{exam_id}/page{i}-{uuid.uuid4().hex[:6]}.jpg"
                self._upload_jpeg(path, img, quality=90)
                pages.append({"path": path, "width": img.shape[1], "height": img.shape[0]})
            questions = _plain(result["questions"])
            update = {
                "pages": pages, "questions": questions, "name_region": list(result["name_region"] or []) or None,
                "status": "ready", "setupAt": firestore.SERVER_TIMESTAMP,
                "setup": {"notes": result["notes"], "keyUsed": result["key_used"], "ai": result["ai"],
                          "flagged": sum(1 for q in questions if q["flags"])},
            }
            if result["title"] and data.get("nameFromFile", True):
                update["name"] = result["title"]
            ref.update(update)
            self._exams.pop(exam_id, None)
            _log(f"exam {exam_id}: {len(pages)} page(s), {len(questions)} question(s) found ({result['ai']})")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            ref.update({"status": "error", "setupError": str(e)[:500]})

    # ---------- captures ----------

    def _submission_for(self, cap: dict, page: int) -> str:
        """The student this page belongs to. Pages arrive in pile order, so a page
        number that the current student already has starts the next student."""
        subs = self.db.collection("submissions").where(filter=FieldFilter("sessionId", "==", cap["sessionId"])).get()
        current = max(subs, key=lambda s: s.get("firstSeq"), default=None)
        if current is not None and str(page) not in (current.get("pages") or {}):
            return current.id
        ref = self.db.collection("submissions").document()
        ref.set({
            "examId": cap["examId"], "ownerUid": cap["ownerUid"], "sessionId": cap["sessionId"],
            "firstSeq": cap["seq"], "createdAt": firestore.SERVER_TIMESTAMP, "status": "collecting",
            "pages": {}, "results": {}, "score": None, "maxScore": None,
            "studentName": None, "studentEmail": None, "followup": None, "scores": None,
        })
        return ref.id

    def process_capture(self, capture_id: str) -> None:
        ref = self.db.collection("captures").document(capture_id)
        snap = ref.get()
        if not snap.exists or snap.get("status") != "uploaded":
            return
        cap = snap.to_dict()
        ref.update({"status": "processing"})
        try:
            _, exam, _, registrar, _ = self._exam(cap["examId"])
            reg = registrar.register(self._download_image(cap["path"]))
            if reg is None:
                ref.update({"status": "unmatched", "error": "this photo does not match any page of the blank exam"})
                _log(f"capture {capture_id}: no page matched")
                return
            sub_id = self._submission_for(cap, reg.page)
            path = f"aligned/{cap['ownerUid']}/{cap['examId']}/{sub_id}/p{reg.page}.jpg"
            self._upload_jpeg(path, reg.aligned)
            local = self.cache_dir / sub_id
            local.mkdir(exist_ok=True)
            cv2.imwrite(str(local / f"p{reg.page}.png"), reg.aligned)
            h, w = reg.aligned.shape[:2]
            sub_ref = self.db.collection("submissions").document(sub_id)
            sub_ref.update({
                FieldPath("pages", str(reg.page)).to_api_repr():
                    {"path": path, "width": w, "height": h, "captureId": capture_id, "inliers": reg.inliers},
            })
            ref.update({"status": "matched", "page": reg.page, "submissionId": sub_id, "inliers": reg.inliers,
                        "error": None})
            _log(f"capture {capture_id}: page {reg.page} -> submission {sub_id}")
            if len(sub_ref.get().get("pages") or {}) == len(exam.pages):
                self.grade(sub_id)
        except Exception as e:  # noqa: BLE001 - report any failure on the capture itself
            traceback.print_exc()
            ref.update({"status": "error", "error": str(e)[:500]})

    # ---------- grading ----------

    def _aligned(self, sub_id: str, page: int, path: str) -> np.ndarray:
        local = self.cache_dir / sub_id / f"p{page}.png"
        if local.exists():
            return cv2.imread(str(local), cv2.IMREAD_COLOR)
        return self._download_image(path)

    def read_name(self, data: dict, page1: np.ndarray) -> dict | None:
        """The roster entry whose name best matches the handwriting in the name box, if clear enough."""
        region, roster = data.get("name_region"), data.get("roster") or []
        if not region or not roster:
            return None
        raw = " ".join(t for t, _ in read_handwriting(crop(page1, region, 6))).lower()
        text = " ".join(w for w in re.findall(r"[^\W\d_]+", raw) if len(w) > 1)  # drops the "Name:" label's leftovers
        if not text:
            return None

        def score(r: dict) -> float:
            name = r["name"].lower()
            full = SequenceMatcher(None, text, name).ratio()
            # only part of the name read (e.g. the first name): fine if no one else on the roster shares it
            parts = [w for w in text.split() if any(SequenceMatcher(None, w, p).ratio() >= 0.85 for p in name.split())]
            return max(full, 0.6 if parts and len(" ".join(parts)) >= 3 else 0)

        ranked = sorted(roster, key=score, reverse=True)
        best = ranked[0]
        if score(best) < 0.6 or (len(ranked) > 1 and score(ranked[1]) >= score(best) and score(best) < 0.8):
            return None
        return best

    def grade(self, sub_id: str) -> None:
        sub_ref = self.db.collection("submissions").document(sub_id)
        sub = sub_ref.get().to_dict()
        sub_ref.update({"status": "grading"})
        try:
            data, exam, masters, _, grader = self._exam(sub["examId"])
            bank = self.bank(data)
            aligned = {int(k): self._aligned(sub_id, int(k), info["path"]) for k, info in (sub.get("pages") or {}).items()}
            results = {r.question: result_doc(r) for r in grade_pages(
                sub_id, exam, masters, aligned, grader, lambda qid: [m for m in bank if m.get("question") in (None, qid)])}
            update = {
                "results": _plain(results), "score": sum(r["score"] or 0 for r in results.values()),
                "maxScore": exam.max_points, "status": "graded", "grader": self.backend,
                "gradedAt": firestore.SERVER_TIMESTAMP, "error": None,
            }
            if not sub.get("studentEmail") and 1 in aligned:
                who = self.read_name(data, aligned[1])
                if who:
                    update.update(studentName=who["name"], studentEmail=who["email"].lower(), nameRead=True)
            sub_ref.update(update)
            _log(f"submission {sub_id}: graded {update['score']:g}/{exam.max_points:g} ({self.backend})"
                 + (f", {update['studentName']}" if update.get("studentName") else ""))
            self.prepare_followups(sub_id)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            sub_ref.update({"status": "error", "error": str(e)[:500]})

    # ---------- follow-ups ----------

    def prepare_followups(self, sub_id: str, auto_open: bool = True, limit: int | None = None) -> None:
        """Detect the triggers, write each N0 question, and open the session if the student is known."""
        sub_ref = self.db.collection("submissions").document(sub_id)
        sub = sub_ref.get().to_dict()
        data = self.db.collection("exams").document(sub["examId"]).get().to_dict()
        cfg = settings(data.get("followup"))
        items, candidates = demo.start_items(data["questions"], sub["results"], self.bank(data), self.backend, cfg,
                                             data.get("language") or "English")
        items = items[:limit]
        scores = student_scores(data["questions"], sub["results"], items, cfg, finished=not items)
        sub_ref.update(_plain({"followup": {"status": "ready" if items else "none", "items": items,
                                            "candidates": candidates}, "scores": scores}))
        _log(f"submission {sub_id}: {len(items)} follow-up(s) "
             + ", ".join(f"{i['question']} {i['trigger']}" for i in items))
        if items and auto_open and sub.get("studentEmail") and data.get("autoOpen", True):
            self.open_session(sub_id)

    def open_session(self, sub_id: str, presenter: str | None = None) -> bool:
        """Open the student's session. A presenter email sends it to the teacher instead (demo class only)."""
        sub_ref = self.db.collection("submissions").document(sub_id)
        sub = sub_ref.get().to_dict()
        f = sub.get("followup") or {}
        email = presenter or sub.get("studentEmail")
        if f.get("status") != "ready" or not email:
            return False
        data = self.db.collection("exams").document(sub["examId"]).get().to_dict()
        cfg = settings(data.get("followup"))
        questions = {q["id"]: q for q in data["questions"]}
        self.db.collection("sessions").document(sub_id).set(_plain({
            "ownerUid": sub["ownerUid"], "examId": sub["examId"], "examName": data.get("name", ""),
            "studentEmail": email.lower(), "studentName": sub.get("studentName") or "", "presenter": bool(presenter),
            "status": "open", "windowMinutes": cfg["window_minutes"], "softSeconds": cfg["reply_soft_seconds"],
            "startedAt": None, "current": 0, "items": student_view(f["items"], questions), "openedAt": time.time(),
            "simulated": bool(sub.get("simulated")),
        }))
        sub_ref.update({"followup.status": "open"})
        _log(f"submission {sub_id}: follow-up opened for {email}" + (" (presenter)" if presenter else ""))
        return True

    def try_followup(self, sub_id: str, email: str) -> None:
        """Demo class: restart a scanned student's follow-up and send it to the teacher, who answers it live.

        Only the first question is asked, so a live demo takes a minute."""
        sub = self.db.collection("submissions").document(sub_id).get().to_dict()
        if not (self.db.collection("exams").document(sub["examId"]).get().to_dict() or {}).get("demo"):
            raise ValueError("only the demo class can be answered by the teacher")
        self.prepare_followups(sub_id, auto_open=False, limit=1)
        if not self.open_session(sub_id, presenter=email):
            raise ValueError("this student has no follow-up")

    def handle_reply(self, reply_id: str) -> None:
        ref = self.db.collection("replies").document(reply_id)
        snap = ref.get()
        if not snap.exists or snap.get("status") != "new":
            return
        r = snap.to_dict()
        ref.update({"status": "processing"})
        try:
            self.answer(r["sessionId"], int(r.get("item", 0)), r.get("text", ""))
            ref.update({"status": "done"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            ref.update({"status": "error", "error": str(e)[:300]})

    def answer(self, sub_id: str, index: int, text: str) -> None:
        """One reply through the ladder; writes the teacher's and the student's copies."""
        with self._lock:
            sub_ref = self.db.collection("submissions").document(sub_id)
            sess_ref = self.db.collection("sessions").document(sub_id)
            sub, sess = sub_ref.get().to_dict(), sess_ref.get().to_dict()
            if not sess or sess.get("status") != "open":
                return
            data = self.db.collection("exams").document(sub["examId"]).get().to_dict()
            cfg = settings(data.get("followup"))
            questions = {q["id"]: q for q in data["questions"]}
            items = sub["followup"]["items"]
            current = next((k for k, i in enumerate(items) if i["phase"] != "done"), None)
            if current is None or index != current:
                return  # a stale or out-of-order reply
            item = items[current]
            ladder.reply(item, text[:1500], questions[item["question"]], self.backend, cfg, data.get("language") or "English")
            nxt = next((k for k, i in enumerate(items) if i["phase"] != "done"), None)
            self._save(sub_ref, sess_ref, sub, data, items, questions, nxt, cfg)
            _log(f"session {sub_id}: {item['question']} level {item['level']} -> {item['phase']}")

    def _save(self, sub_ref, sess_ref, sub, data, items, questions, nxt, cfg, status: str | None = None) -> None:
        finished = nxt is None
        status = status or ("done" if finished else "open")
        scores = student_scores(data["questions"], sub["results"], items, cfg, finished=finished)
        sub_ref.update(_plain({"followup.items": items, "followup.status": status if finished else "open",
                               "scores": scores}))
        sess_ref.update(_plain({"items": student_view(items, questions), "current": nxt if nxt is not None else len(items),
                                "status": status}))
        if finished:
            self.refresh_class(sub["examId"])

    def expire_sessions(self) -> None:
        """Close open sessions whose reply window has passed."""
        now = dt.datetime.now(dt.timezone.utc)
        for snap in self.db.collection("sessions").where(filter=FieldFilter("status", "==", "open")).get():
            s = snap.to_dict()
            started = s.get("startedAt")
            if not started or now < started + dt.timedelta(minutes=s.get("windowMinutes") or 15):
                continue
            with self._lock:
                sub_ref = self.db.collection("submissions").document(snap.id)
                sub = sub_ref.get().to_dict()
                data = self.db.collection("exams").document(sub["examId"]).get().to_dict()
                items = sub["followup"]["items"]
                for i in items:
                    ladder.expire(i)
                self._save(sub_ref, snap.reference, sub, data, items, {q["id"]: q for q in data["questions"]}, None,
                           settings(data.get("followup")), status="expired")
                _log(f"session {snap.id}: reply window closed")

    # ---------- class view ----------

    def refresh_class(self, exam_id: str, with_insights: bool = False) -> None:
        """Profile counts and demo metrics for the class view (insights/{examId})."""
        data = self.db.collection("exams").document(exam_id).get().to_dict()
        subs = [{"id": d.id, **d.to_dict()} for d in self.db.collection("submissions")
                .where(filter=FieldFilter("examId", "==", exam_id)).get()]
        subs = [s for s in subs if s.get("ownerUid") == data["ownerUid"] and s.get("results")]
        cfg = settings(data.get("followup"))
        for s in subs:  # the teacher may have changed the weights since this student was scored
            f = s.get("followup") or {}
            scores = _plain(student_scores(data["questions"], s["results"], f.get("items") or [], cfg,
                                           finished=f.get("status") in ("done", "expired", "none")))
            if s.get("scores") and scores != s["scores"]:
                self.db.collection("submissions").document(s["id"]).update({"scores": scores})
                s["scores"] = scores
        summary = class_summary(subs, data.get("followup"))
        triggers = {t: sum(1 for s in subs for i in (s.get("followup") or {}).get("items") or [] if i["trigger"] == t)
                    for t in TRIGGERS}
        doc = {"examId": exam_id, "ownerUid": data["ownerUid"], "summary": summary, "triggers": triggers,
               "updatedAt": firestore.SERVER_TIMESTAMP}
        if with_insights:
            ins = build_insights(data, subs, self.backend)
            doc.update(misconceptions=ins["misconceptions"], plan=ins["plan"], questions=ins["questions"],
                       notes=ins["notes"], ai=ins["ai"])
            if data.get("course"):
                bank_ref = self.db.collection("banks").document(f"{data['ownerUid']}_{data['course']}")
                entries, added = grow_bank(self.bank(data), ins["misconceptions"])
                bank_ref.set({"ownerUid": data["ownerUid"], "course": data["course"], "entries": entries,
                              "updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)
                doc["bankAdded"] = added
        self.db.collection("insights").document(exam_id).set(_plain({k: v for k, v in doc.items() if k != "updatedAt"})
                                                             | {"updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)

    # ---------- the demo class ----------

    def demo_class(self, exam_id: str) -> None:
        """Seed the course's misconception bank and the fifteen simulated classmates (finished follow-ups)."""
        from .synth import BANK

        exam_ref = self.db.collection("exams").document(exam_id)
        data = exam_ref.get().to_dict()
        cfg = settings(data.get("followup"))
        bank_ref = self.db.collection("banks").document(f"{data['ownerUid']}_{data['course']}")
        if not bank_ref.get().exists:
            bank_ref.set({"ownerUid": data["ownerUid"], "course": data["course"], "entries": BANK,
                          "updatedAt": firestore.SERVER_TIMESTAMP})
        bank = self.bank(data)
        questions = data["questions"]
        for c in demo.CLASSMATES:
            results = demo.typed_results(questions, c["mcq"], c["answers"])
            items, candidates = demo.start_items(questions, results, bank, "mock", cfg)
            demo.play(items, questions, c["script"], "mock", cfg)
            scores = student_scores(questions, results, items, cfg)
            sid = f"{exam_id}-sim-{c['name'].split()[0].lower()}"
            self.db.collection("submissions").document(sid).set(_plain({
                "examId": exam_id, "ownerUid": data["ownerUid"], "simulated": True, "status": "graded",
                "pages": {}, "results": results, "score": scores["real"], "maxScore": scores["max"], "grader": "mock",
                "studentName": c["name"], "studentEmail": demo.email(c["name"]),
                "followup": {"status": "done" if items else "none", "items": items, "candidates": candidates},
                "scores": scores, "createdAt": time.time(),
            }))
            if items:
                self.db.collection("sessions").document(sid).set(_plain({
                    "ownerUid": data["ownerUid"], "examId": exam_id, "examName": data.get("name", ""),
                    "studentEmail": demo.email(c["name"]), "studentName": c["name"], "status": "done",
                    "windowMinutes": cfg["window_minutes"], "softSeconds": cfg["reply_soft_seconds"],
                    "startedAt": None, "current": len(items), "simulated": True,
                    "items": student_view(items, {q["id"]: q for q in questions}),
                }))
        self.refresh_class(exam_id, with_insights=True)
        _log(f"exam {exam_id}: demo class seeded ({len(demo.CLASSMATES)} simulated classmates)")

    def reset_demo(self, owner_uid: str) -> None:
        """Delete the teacher's demo classes and everything made from them, so the demo can start over."""
        exams = self.db.collection("exams").where(filter=FieldFilter("ownerUid", "==", owner_uid)).get()
        for exam in [e for e in exams if (e.to_dict() or {}).get("demo")]:
            data = exam.to_dict()
            for coll in ("submissions", "sessions", "captures"):
                for d in self.db.collection(coll).where(filter=FieldFilter("examId", "==", exam.id)).get():
                    if coll == "sessions":
                        for r in self.db.collection("replies").where(filter=FieldFilter("sessionId", "==", d.id)).get():
                            r.reference.delete()
                    d.reference.delete()
            self.db.collection("insights").document(exam.id).delete()
            if data.get("course"):
                self.db.collection("banks").document(f"{owner_uid}_{data['course']}").delete()
            for prefix in ("uploads", "masters", "captures", "aligned"):
                for blob in self.bucket.list_blobs(prefix=f"{prefix}/{owner_uid}/{exam.id}/"):
                    blob.delete()
            exam.reference.delete()
            self._exams.pop(exam.id, None)
            _log(f"exam {exam.id}: demo class reset")

    def play_scripts(self, exam_id: str) -> None:
        """Answer the open follow-ups of the scanned demo students from their scripts (presenter shortcut)."""
        subs = self.db.collection("submissions").where(filter=FieldFilter("examId", "==", exam_id)).get()
        for s in subs:
            d = s.to_dict()
            script = demo.SCANNED_SCRIPTS.get(d.get("studentName") or "")
            if script is None or (d.get("followup") or {}).get("status") != "open":
                continue
            replies = {q: list(r) for q, r in script.items()}
            for _ in range(20):
                sess = self.db.collection("sessions").document(s.id).get().to_dict()
                if sess.get("status") != "open" or sess.get("presenter"):
                    break
                item = sess["items"][sess["current"]]
                todo = replies.get(item["question"]) or []
                self.answer(s.id, sess["current"], todo.pop(0) if todo else demo.NOT_SURE)
            self.db.collection("submissions").document(s.id).update({"scriptedReplies": True})
            _log(f"submission {s.id}: scripted replies played for {d.get('studentName')}")

    # ---------- jobs and main loop ----------

    def process_job(self, job_id: str) -> None:
        ref = self.db.collection("jobs").document(job_id)
        snap = ref.get()
        if not snap.exists or snap.get("status") != "pending":
            return
        job = snap.to_dict()
        kind = job.get("type")
        try:
            if kind == "grade":
                sub = self.db.collection("submissions").document(job.get("submissionId", "-")).get()
                if not sub.exists or sub.get("ownerUid") != job.get("ownerUid"):
                    raise ValueError("unknown submission")
                self.grade(sub.id)
            elif kind == "open_followup":
                sub = self.db.collection("submissions").document(job.get("submissionId", "-")).get()
                if not sub.exists or sub.get("ownerUid") != job.get("ownerUid"):
                    raise ValueError("unknown submission")
                if (sub.get("followup") or {}).get("status") is None:
                    self.prepare_followups(sub.id, auto_open=False)
                self.open_session(sub.id)
            elif kind == "try_followup":
                sub = self.db.collection("submissions").document(job.get("submissionId", "-")).get()
                if not sub.exists or sub.get("ownerUid") != job.get("ownerUid") or not job.get("email"):
                    raise ValueError("unknown submission")
                self.try_followup(sub.id, job["email"])
            elif kind == "reset_demo":
                self.reset_demo(job["ownerUid"])
            elif kind not in ("setup", "demo_class", "play_scripts", "insights", "open_followups"):
                raise ValueError(f"unknown job type {kind!r}: restart the worker with the latest code")
            else:
                exam = self.db.collection("exams").document(job.get("examId", "-")).get()
                if not exam.exists or exam.get("ownerUid") != job.get("ownerUid"):
                    raise ValueError("unknown exam")
                {"setup": self.setup_exam, "demo_class": self.demo_class, "play_scripts": self.play_scripts,
                 "insights": lambda e: self.refresh_class(e, with_insights=True),
                 "open_followups": self.open_all}[kind](exam.id)
            ref.update({"status": "done", "doneAt": firestore.SERVER_TIMESTAMP})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            ref.update({"status": "error", "error": str(e)[:500]})

    def open_all(self, exam_id: str) -> None:
        for s in self.db.collection("submissions").where(filter=FieldFilter("examId", "==", exam_id)).get():
            if (s.get("followup") or {}).get("status") == "ready":
                self.open_session(s.id)

    def _on(self, kind: str):
        def handler(docs, changes, read_time) -> None:
            for ch in changes:
                if ch.type.name == "ADDED":
                    self.queue.put((kind, ch.document.id, (ch.document.get("seq") or 0) if kind == "capture" else 0))
        return handler

    def _heartbeat(self) -> None:
        while True:
            try:
                self.db.collection("workers").document("main").set(
                    {"lastSeen": firestore.SERVER_TIMESTAMP, "grader": self.backend})
                self.expire_sessions()
            except Exception as e:  # noqa: BLE001
                _log(f"heartbeat failed: {e}")
            time.sleep(HEARTBEAT_SECONDS)

    def run_forever(self) -> None:
        threading.Thread(target=self._heartbeat, daemon=True).start()
        col = self.db.collection
        self._watches = [
            col("captures").where(filter=FieldFilter("status", "==", "uploaded")).on_snapshot(self._on("capture")),
            col("jobs").where(filter=FieldFilter("status", "==", "pending")).on_snapshot(self._on("job")),
            col("replies").where(filter=FieldFilter("status", "==", "new")).on_snapshot(self._on("reply")),
        ]
        _log(f"worker running (model: {self.backend}); waiting for photos, jobs and replies")
        threading.Thread(target=self._reply_loop, daemon=True).start()
        while True:
            items = [self.queue.get()]
            time.sleep(0.5)  # let a burst of uploads arrive, then handle them in capture order
            while not self.queue.empty():
                items.append(self.queue.get_nowait())
            replies = [i for i in items if i[0] == "reply"]
            for r in replies:
                self.replies.put(r[1])
            for kind, doc_id, _ in sorted({i for i in items if i[0] != "reply"}, key=lambda t: (t[0] != "capture", t[2])):
                (self.process_capture if kind == "capture" else self.process_job)(doc_id)

    def _reply_loop(self) -> None:
        """Replies get their own thread, so a student never waits behind a pile of photos being graded."""
        while True:
            self.handle_reply(self.replies.get())
