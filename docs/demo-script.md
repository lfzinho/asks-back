# Demo video script (5 minutes)

The same script works in **mock mode** (no AI, local handwriting reading and teacher-written hints) and with a **real model** (`--model claude` or `--model openrouter`). Only the wording of the follow-up questions and the judging of replies change. Where the two differ, the script says so.

## Before recording

```bash
# terminal 1, repo root
firebase emulators:start --only auth,firestore,storage,hosting
```

```bash
# terminal 2, worker/
uv run python -m asksback worker --emulator --model mock
```

Three browser windows:

- **A, the tour:** <http://127.0.0.1:5002/tour>
- **B, the teacher:** <http://127.0.0.1:5002/teacher>. Sign up as any teacher, press **＋ Demo class**, and wait until the 15 simulated students appear (about 5 s).
- **C, the student:** <http://127.0.0.1:5002/student> in a narrow window or a private window. Do not sign in yet.

Keep the **Scan papers** page of the demo class open in a phone or a fourth window.

## 0:00–0:40 · The problem (tour, slides 1–2)

> "Two students got 7 out of 11. Only one of them is stuck. A grade measures the paper, not the student. Bruno wrote *It is O(log n)*: right, but is there any evidence he knows why?"

Advance to slide 2 and point at the three cards.

## 0:40–1:20 · How it works (tour, slides 3 and 5)

> "The exam stays on paper. We grade it, and where the paper is not enough evidence, one of five triggers fires: correct with no reasoning, partial, ambiguous, a known misconception, or an answer that reads unlike the rest of the student's exam. Only then do we ask back, in writing, three questions at most."

On slide 5, stop on G5: "It never accuses. The student just gets a new case to apply it to."

## 1:20–2:00 · Scan (Scan papers + teacher window)

Press **Upload demo photos** (or photograph the five printed papers). Switch to the teacher window:

> "Ten photos, in any order, one upside down. Each is matched to its page, the name is read from the paper, and the answers are graded. Ana gets nothing: her paper is enough. Bruno gets three follow-ups, Carla two misconception questions, Eva one authorship check."

Point at the trigger chips in the Follow-up column (Q5 G1, Q6 G1, Q7 G2 for Bruno).

## 2:00–3:20 · The follow-up (student window) — the core of the demo

In window C, the local demo panel offers the five scanned students. Click **Bruno Lima**, open the follow-up, press **Start**.

> "Bruno sees one short question at a time. It quotes his own answer and asks why."

Type the replies (the same ones the scripted run uses):

1. *It gets smaller every step.* → a **hint** appears: "Re-read what you wrote, then look at what one comparison with the middle element tells you."
2. *Each comparison cuts the interval in half, and that only works because the array is sorted.* → reached at N1, so one more question with no help: the **transfer** question about a descending array.
3. *I would flip the comparison and go the other way, it is still log n.*
4. For Q6: *Every call adds a frame to the call stack until the memory runs out.*
5. For Q7: *A stack is like a pile of plates, a queue is like a line at a shop.*

> "Five short replies, under three minutes. He needed one implicit hint, and the idea transferred."

*With a real model:* the questions are worded by the model around Bruno's own words and checked against the quality rules before they are sent; the replies are judged by the model. The flow and the levels are the same.

## 3:20–4:20 · The teacher's view (teacher window)

Press **Play scripted replies** to answer the other four scanned students from their scripts.

> "Here is what a grade would have hidden. 25% of this class was **Almost there** behind a low grade. Bruno had 7 out of 11 and recovered 88% of the missing points with one implicit hint. Carla had 6 and is *Building*: she needed conceptual hints. On paper they were one point apart."

Open **Bruno Lima**: the three scores (real 7, mediated 10.5, potential 88%), the profile and its reason, each transcript with its levels.

Go back and open **Eva Rocha**:

> "Eva got full marks. Her stack-and-queue answer reads unlike the rest of her exam, so she was given a new case to apply it to, and she could not. The profile is *Verify understanding*: talk with her. The decision is the teacher's."

Set your judgment for Bruno to *Almost there*: the class view now measures agreement.

## 4:20–5:00 · Science and next steps (tour, slides 7–10)

> "Each level of help is worth less: N0 100%, N1 75%, N2 50%, N3 25%. These weights are ours to calibrate, and the teacher can change them; the class is rescored. The method comes from dynamic assessment: actual, mediated and learning-potential scores. Next: a pilot comparing these profiles with teachers' own judgment of the same students."

End on slide 10.

## If something goes wrong

- **Worker offline** chip in the teacher app: restart terminal 2.
- **A student is unnamed** (the name box could not be read): pick the student in the student view and press **Save and send follow-up**.
- **The reply window ran out**: the session shows *Time is up*; create a new demo class.
