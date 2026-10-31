"""Command line: python -m asksback {worker,run,synth,demo-assets,regions} ..."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    """Read KEY=value lines from worker/.env (git-ignored). Variables already set in the shell win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def default_backend() -> str:
    """The model whose key is set (OpenRouter first, it has free models), else the offline mock."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return "mock"


def demo_assets(out: Path) -> None:
    """Write the demo exam for the web apps: blank pages, PDF, five students' photos, exam.json."""
    from .demo import email
    from .synth import STUDENTS, generate

    tmp = Path("out/demo-assets")
    shutil.rmtree(tmp, ignore_errors=True)
    exam = generate(tmp)
    (out / "master").mkdir(parents=True, exist_ok=True)
    (out / "students").mkdir(exist_ok=True)
    for f in (tmp / "master").iterdir():
        shutil.copy(f, out / "master" / f.name)
    shutil.copy(tmp / "exam.pdf", out / "exam.pdf")
    photos = []
    for sid in STUDENTS:
        for f in sorted((tmp / "students" / sid).iterdir()):
            shutil.copy(f, out / "students" / f"{sid}-{f.name}")
            photos.append(f"/demo/students/{sid}-{f.name}")
    (out / "students" / "list.json").write_text(json.dumps(photos, indent=1))
    from .demo import CLASSMATES

    names = [s["name"] for s in STUDENTS.values()] + [c["name"] for c in CLASSMATES]
    exam["pages"] = [{"demo": f"/demo/master/page{i}.png", "width": 1240, "height": 1754} for i in (1, 2)]
    exam["roster"] = [{"name": n, "email": email(n)} for n in names]
    (out / "exam.json").write_text(json.dumps(exam, indent=1, ensure_ascii=False))


def main() -> None:
    load_env()
    p = argparse.ArgumentParser(prog="asksback", description="AsksBack worker and tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    models = ["openrouter", "claude", "mock"]
    model_help = ("openrouter (OPENROUTER_API_KEY), claude (ANTHROPIC_API_KEY) or mock (offline: local OCR and "
                  "templates). Default: the model whose key is set, else mock")

    w = sub.add_parser("worker", help="the worker for the web apps (watches Firebase)")
    w.add_argument("--model", choices=models, default=default_backend(), help=model_help)
    w.add_argument("--key", help="service account JSON for a real Firebase project")
    w.add_argument("--project", help="Firebase project id (default: demo-asksback, or ASKSBACK_PROJECT)")
    w.add_argument("--bucket", help="Storage bucket (default: <project>.appspot.com)")
    w.add_argument("--emulator", action="store_true", help="use the local Firebase emulators")

    r = sub.add_parser("run", help="grade every student folder of an exam offline and print the follow-ups")
    r.add_argument("exam_dir", type=Path)
    r.add_argument("--model", choices=models, default=default_backend(), help=model_help)

    s = sub.add_parser("synth", help="generate the synthetic quiz with five students' phone photos")
    s.add_argument("--out", type=Path, default=Path("data/synthetic"))
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--conditions", choices=["easy", "normal", "hard"], default="normal")

    d = sub.add_parser("demo-assets", help="regenerate public/demo (exam, pages, photos)")
    d.add_argument("--out", type=Path, default=Path("../public/demo"))

    g = sub.add_parser("regions", help="draw boxes on a blank page to get exam.yaml coordinates")
    g.add_argument("image", type=Path)

    a = p.parse_args()
    if a.cmd == "worker":
        from .worker import PROJECT, Worker

        Worker(backend=a.model, key=a.key, emulator=a.emulator, project=a.project or PROJECT,
               bucket=a.bucket).run_forever()
    elif a.cmd == "run":
        import yaml

        from .demo import start_items
        from .exam import Exam
        from .grader import ModelGrader, OfflineGrader
        from .images import load_image
        from .pipeline import run
        from .results import result_doc

        exam = Exam.load(a.exam_dir)
        bank_file = a.exam_dir / "bank.yaml"
        bank = yaml.safe_load(bank_file.read_text()) if bank_file.exists() else []
        grader = ModelGrader(exam, [load_image(x) for x in exam.page_paths()], a.model) if a.model != "mock" \
            else OfflineGrader(Path("out/ocr"))
        out = Path("out") / a.exam_dir.name
        run(a.exam_dir, out, grader, lambda qid: [m for m in bank if m.get("question") in (None, qid)])
        by: dict[str, dict] = {}
        for res in json.loads((out / "results.json").read_text())["results"]:
            by.setdefault(res["student"], {})[res["question"]] = result_doc(res)
        questions = exam.model_dump()["questions"]
        for student, results in by.items():
            items, _ = start_items(questions, results, bank, a.model)
            print(f"\n{student}: {sum(x['score'] or 0 for x in results.values()):g}/{exam.max_points:g}")
            for i in items:
                print(f"  {i['question']} {i['trigger']} ({i['reason']})\n    -> {i['messages'][0]['text']}")
    elif a.cmd == "synth":
        from .synth import generate

        generate(a.out, a.seed, a.conditions)
        print(f"Synthetic quiz written to {a.out.resolve()}")
    elif a.cmd == "demo-assets":
        demo_assets(a.out)
        print(f"Demo files written to {a.out.resolve()}")
    elif a.cmd == "regions":
        from .regions import define_regions

        define_regions(a.image)


if __name__ == "__main__":
    main()
