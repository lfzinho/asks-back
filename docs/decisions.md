# Design decisions

Where the concept ([concept.md](concept.md)) leaves room for interpretation, we picked the simplest reading that keeps the product honest and the demo strong. Each entry says what we chose and why. All numbers live in one place in code (`worker/asksback/config.py`) and are teacher-configurable per exam.

## Triggers

1. **Rubric criteria have a kind: `answer` or `reasoning`.** G1 ("correct, no justification") needs to know which criteria are the answer and which are the reasoning. A criterion with no kind counts as `answer`. G1 fires when every answer criterion is met and at least one reasoning criterion is not, or the grader says the justification is missing or generic.
2. **G2 fires on any partial score** (some points, not all) that G1 doesn't already explain.
3. **G3 uses the grader's confidence mapped to a number** (high 0.9, medium 0.6, low 0.3) against a threshold of 0.7, so "medium" and "low" both fire. It does not fire on full marks: a clarification there cannot change the score or the diagnosis, so it would not be *necessary*.
4. **G4 matches against the misconception bank in two ways:** the grader names the bank entries the answer shows (with a real model), and a plain phrase match against each entry's typical wording (always, so it also works offline).
5. **G5 is computed in code, not by the model.** We compare simple style features of each open answer (average word length, average sentence length, share of long words, vocabulary richness, punctuation) against the same student's other answers. An answer that is *more elaborate* than the student's own baseline (z-score of 2.0 or more on two or more features) fires G5; writing less than usual never does. The model never judges authorship. G5 needs at least two other written answers of five words or more from the same student.
6. **One trigger per question.** When several fire on the same answer, we keep the one whose follow-up can change the most points, with ties broken in this order: G3, G4, G1, G2, G5 (clarifying first, because it can correct the real score itself).
7. **Choosing the 3 questions:** each candidate gets an *impact* in points: the points still missing for G2, G3 and G4, the reasoning points at stake for G1, and the points the answer currently earns for G5 (the points whose evidence is in doubt). We keep the 3 with the largest impact.
8. **Blank or fully wrong answers with no catalogued misconception do not trigger.** They are clear evidence; the student goes to the profile from the written score.

## Questions and quality

9. **G4's "do you agree?" is made open.** The concept's example ("A classmate said… do you agree?") is a yes/no question, which the checklist forbids. Our G4 questions always end by asking *why* ("…What would you tell them?"), so they stay open.
10. **The quality check is rules first, then an optional cheap model pass.** Rules cover what can be checked for sure: quotes the student (a word sequence from their answer), not yes/no (opening words and a closing *why/how/what*), one question mark, no banned words (accusations, "wrong", "mistake"), and at N0/N1 none of the answer key's key terms. With a model, a second short request checks benevolence and necessity. A failed question is regenerated up to 2 times, then replaced by the trigger's template question, which always passes.
11. **Words that never appear in student- or teacher-facing text:** "cheating", "cheat", "AI-generated", "plagiarism", "copied". The checker enforces it for generated text; the UI text was written without them.

## Ladder and turns

12. **"3 turns per question" means up to 3 hints.** N0 is the question itself, then at most N1, N2 and N3, which is the 3-turn limit of the cost rule. A transfer question, when it is needed, is one more message, so a question takes at most 5 student replies. This keeps the four-level ladder of the concept intact.
13. **G3 (clarification) has no hints.** Clarifying is not helping, so a G3 question is asked once (N0). If the reply clarifies in the student's favour, the criteria it confirms are added to the **real** score (the "adjusted real" score). Hints would turn it into mediation.
14. **A failed transfer question lowers the credit by one level** (for example N1 counts as N2). A passed one keeps it. This is the simplest way to make "internalized" matter without inventing a new scale.
15. **The reply window** is per session: it starts when the student opens the follow-up and lasts `window_minutes` (default 15). The security rules refuse replies after it. Each question shows a soft 3-minute timer to keep replies short, but it does not cut the student off.

## Scores and profiles

16. **Mediated score per question:** `real + Σ points(criterion) × weight(level where it was met)` over the criteria the follow-up recovered, capped at the question's points. G1 recovers its missing reasoning points the same way; G5 has nothing to recover and only verifies. Questions without a follow-up keep their real score.
17. **Learning potential:** `(mediated − real) / (max − real)`, using the adjusted real score; `n/a` when the real score is already the maximum.
18. **Profile rules**, in order:
    - Real score ≥ 70% of the maximum ("high"): **Verify understanding** if any verification follow-up (G1 or G5) was not reached or needed N2–N3; otherwise **Mastered**.
    - Real score below 70%: **Almost there** if learning potential ≥ 0.5 and every recovered criterion needed at most N1; **Building** if anything was recovered (learning potential > 0); **Not reached** otherwise, including students with no follow-up.
19. **Demo metric "% of students whose real score hid an Almost there"** is the share of the whole class whose profile is Almost there (they all have a low real score by definition). The teacher view also shows it as "X of the Y students with a low grade".
20. **Agreement with the teacher:** the teacher can set their own profile for any student. Agreement is the share of those students where it matches the generated profile.

## Scoring stays in code

21. The model only answers yes/no questions about criteria (in the grading and in each reply). Every number (points, weights, the three scores, profiles) is computed in `scoring.py`. Same inputs, same scores.

## Offline and mock mode

22. **`mock` mode works without any AI key or network for AI.** It reads the handwriting with the local OCR engine (RapidOCR, already used to read the blank test), grades by looking for each criterion's `look_for` terms, writes follow-ups from per-trigger templates that quote the student, and judges replies the same way. Everything it writes is labelled `[mock]` for the teacher. "Offline" means *no AI service*: the web apps still load the Firebase SDK and fonts from their CDNs.
23. **Teachers can pre-write the ladder.** A criterion may carry three hints (N1, N2, N3) and a question may carry a transfer question with look-for terms. Templates use them as written; a model adapts them to the student's answer and conversation. Without them, generic per-level templates are used. The demo exam has them, so mock mode asks real questions.
24. **A criterion is credited at the level where the student first meets it**, so a reply can recover one criterion at N1 and another at N2. "Reached" is the level where the last target was met.
25. **Simulated classmates in the demo class are run through the real follow-up engine** with scripted replies and the mock judge, so their transcripts are real engine output. They are labelled *simulated* in the teacher view.

## Platform

26. **Local development uses a `demo-` Firebase project id** (`demo-asksback`), which the emulators run fully offline with no cloud project. The real project is chosen at deploy time.
27. **Students read their own follow-up session and write only replies.** The worker writes everything else. A session document holds only what the student may see (their answer, the questions, the transcript); the rubric, judgments and scores stay in the teacher-only submission.
