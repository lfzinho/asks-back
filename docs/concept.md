# Dynamic Assessment with AI: rationale and concept

*English rendering of the team's concept document "Avaliação Dinâmica com IA — Embasamento e Conceito" (31 Oct 2026, Luís Fernando Laguardia). The original is in Portuguese; where wording differs, the original wins.*

## Positioning

AsksBack is a **dynamic assessment** system. It grades the written exam and, when the written answer is not enough evidence, it talks with the student to measure what they really understand.

**Thesis in one sentence:** the grade says where the student is; dynamic assessment says how far they get with help, and that is what the teacher needs to act.

**30-second pitch:** since generative AI, a written answer is no longer proof of understanding. Universities are going back to oral exams, but they don't scale. Our system grades the written exam and, only when an answer is ambiguous, shallow or suspicious, asks 1 to 3 follow-up questions with graded help. The teacher gets not only the grade but how much help each student needed: a diagnosis no automatic grader delivers today.

Working name for the concept: *the grader that asks back*.

| | Automatic grader | Dynamic assessment (AsksBack) |
|---|---|---|
| Question it answers | How much did the student score? | What does the student understand, and what is missing for them to get there? |
| Evidence used | Only the written text | Written text + replies to follow-ups |
| Output | 1 grade + explanation | 3 scores: real, mediated and learning potential |
| Value for the teacher | Saves time | Actionable diagnosis per student and per class |
| Value for the student | Knows why they lost points | Learns during the assessment itself |
| Answer to generative AI | Assumes the text is the student's | Checks authorship through demonstrated understanding |

## Scientific basis

Four independent lines of research, from three decades of literature to 2025–2026 studies with AI.

### 1. Asking for a justification reveals what the answer hides
- **Author:** David Treagust (Curtin University), two-tier diagnostic tests, 1988.
- **Idea:** the first tier asks for the answer; the second, for the reason. The justification exposes alternative conceptions (misconceptions) that the answer alone does not show.
- **Evidence:** Tamir (1989) showed that asking for justifications is a sensitive and effective way to assess meaningful learning. Tsui & Treagust (2010), in genetics, found students who chose the right answer without choosing an adequate explanation.
- **Use in the project:** being right does not prove understanding. The justification follow-up is the "second tier" applied to open questions.

### 2. Dynamic Assessment: measure the response to help
- **Authors:** L. S. Vygotsky (Zone of Proximal Development); Reuven Feuerstein; Matthew Poehner and James Lantolf (Penn State).
- **Idea:** assessment and teaching happen together, through mediation. How much and what kind of help the student needs reveals their level of development.
- **Graded mediation:** starts implicit and becomes more explicit as the student needs it (reminders, leading questions, hints, models).
- **Three scores:** computerized Dynamic Assessment (Poehner & Lantolf, 2013) produces an actual score (no help), a mediated score (with help) and a learning potential score (the gain between the two).
- **Use in the project:** this is the theoretical core. It turns "an AI that asks questions" into an assessment instrument with a defined construct.

### 3. Interactive orals as an answer to generative AI
- **Author:** Popi Sotiriadou (Griffith University), Interactive Oral model, with Danielle Logan-Fleming.
- **Adoption:** in use since 2015 and implemented in more than 30 universities in Australasia, Europe and South-East Asia; communities of practice also in Ireland (DCU), Singapore and the US.
- **Argument:** because it is personalized and interactive, the format makes it hard for the student to rely on outsourced or AI-generated content.
- **Performance:** Huxham, Campbell & Westwood (2012, Edinburgh Napier) found significantly higher performance in oral than written assessment, and students saw it as more useful and authentic.
- **Limit:** teachers rarely run orals for lack of time. That is exactly the bottleneck AI removes.

### 4. AI-led follow-ups already work
- **Socratic Mind** (Georgia Tech + UC San Diego): a study with 173 CS 1301 students gave the first empirical evidence that AI-mediated Socratic questioning improves engagement and learning. Pilot with 2,000 students in 2025.
- **NYU** (Prof. Panos Ipeirotis): 36 oral exams in nine days for about US$15 of AI cost.
- **Cambridge** (TESOL Quarterly, 2025): an LLM dialogue system ran a structured interview with adequate follow-ups, and candidates perceived it positively.
- **Follow-up quality** (Scientific Reports, 2026): psycholinguists rated 1,658 LLM-generated follow-ups on four criteria: benevolence, necessity, context awareness and openness.

### How this supports the argument
Pillars 1 and 2 say why asking back measures better; 3 says why now (generative AI); 4 says it is feasible with AI. None of these lines couples dynamic assessment to a written exam that has already been graded. That is the gap the project fills.

## The follow-up generator

The generator only acts when the written answer is not enough evidence. It then asks 1 to 3 questions with graded help and records how much help the student needed to get there.

```
written exam → initial grading (real score + confidence) → trigger?
   no  → the real score is the final score; the student never sees the system
   yes → follow-up of the trigger's type → mediation ladder N0–N3 → 3 scores + profile → teacher report
```

### When it fires: 5 triggers

**Cost rule:** at most 3 questions with follow-ups per student and 3 turns per question, to limit time and anxiety.

| | Trigger | Signal detected | Why ask | Basis |
|---|---|---|---|---|
| G1 | Correct, no justification | Right answer, reasoning missing or generic | A correct answer can be a guess or memorized | Treagust (two tiers) |
| G2 | Partial answer | Covers only part of the rubric criteria | The student may know more than they wrote | Interactive Oral |
| G3 | Ambiguity | Grader confidence below the threshold | The grade depends on interpretation | Grader calibration |
| G4 | Known misconception | The error matches a catalogued misconception | The student may be one hint away from getting it | Dynamic Assessment |
| G5 | Uncertain authorship | Style differs from the student's other answers | Verify understanding, never accuse | Sotiriadou |

### How it generates the question

The question **type is fixed per trigger** (standardization across students); the **content is adapted** to the answer (personalization). Example with the question *"What is the time complexity of binary search, and why?"*:

| Trigger | Question type | Example |
|---|---|---|
| G1 | Justification | "You answered O(log n). What happens to the size of the problem at each step?" |
| G2 | Elaboration | "You said it splits the array. What condition does the array need to meet for that to work?" |
| G3 | Clarification | "When you say 'half', do you mean the whole array or the search interval?" |
| G4 | Confront the misconception | "A classmate said binary search works on any array. Do you agree?" |
| G5 | Transfer | "And if the array were sorted in descending order, what would change in the algorithm?" |

**Prompt inputs:** the question text, the rubric, the student's answer, the trigger, and the course's misconception bank, which the class itself feeds with every exam.

**Quality checklist** (the criteria of the Scientific Reports 2026 study, plus two of ours):
- **Benevolent:** neutral tone, never suggests the student was wrong or cheated.
- **Necessary:** only asks what changes the score or the diagnosis.
- **Contextual:** quotes the student's own answer.
- **Open:** cannot be answered with yes or no.
- Does not give the answer away at levels N0 and N1.
- One idea per question.

### Mediation ladder

Based on the graded mediation of Dynamic Assessment: it starts implicit and only becomes explicit if the student needs it.

1. **N0, no help:** the question of the chosen type.
2. **N1, implicit hint:** directs attention. "Re-read what you wrote about the array."
3. **N2, conceptual hint:** names the concept. "Think about what being sorted lets you discard."
4. **N3, explicit hint:** offers a model. "At each step we discard half of the elements. How many steps until one is left?"

The ladder stops when the student gets it or N3 is used up. If they got it with help, one **transfer** question without help confirms they internalized it, as in the transfer items of computerized Dynamic Assessment.

### The three scores

- **Real score:** the grade of the written exam. A clarification (G3) may adjust it, because clarifying is not helping.
- **Mediated score:** points recovered in the conversation, weighted by the level of help. Initial proposal, configurable by the teacher: N0 is worth 100% of the point, N1 75%, N2 50%, N3 25%, not reached 0%.
- **Learning potential:** the gain of the mediated score over the real score, divided by what was missing to reach the maximum.

The weights are a design decision, not values from the literature; they must be calibrated with teachers in the pilot.

### Profiles the teacher receives

The teacher always has the final word and sees the transcript of every conversation.

| Real score | Gain with help | Profile | Suggested action |
|---|---|---|---|
| High | Not applicable | Mastered | Move on |
| Low | High, with little help (N0–N1) | Almost there | Short review |
| Low | Only with explicit help (N2–N3) | Building | Guided reteaching |
| Low | None | Not reached | Reteach the concept |
| High on paper | Low in the follow-up | Verify understanding | Conversation with the teacher |

## Differentiator and risks

The differentiator is not "an AI that asks questions", which already exists, but coupling dynamic assessment to the written exam: the conversation only happens where writing failed as evidence, and the output measures the response to help.

| Approach | Starting point | What it delivers | Limit |
|---|---|---|---|
| Automatic grader | Written exam | Grade + explanation | Assumes the text proves understanding |
| Interactive Oral (Sotiriadou) | Live conversation with the teacher | Rubric grade, high authenticity | Does not scale: needs teacher time |
| Socratic Mind (Georgia Tech) | AI oral assessment, separate from the exam | Socratic questioning at scale | It is another assessment, does not complement the existing exam |
| **This project** | Written exam already graded | 3 scores + a profile for each student | Weights and triggers still need validation |

**Demo metric:** agreement between the generated profile and the teacher's judgment, and the % of students whose real score hid an "Almost there".

| Risk | Mitigation |
|---|---|
| Student anxiety: in Huxham et al. (2012) students were more nervous in the oral, but Phan (UC San Diego, ASEE 2023) measured lower perceived stress in oral than written exams | Written, short follow-up, only when triggered, benevolent tone, at most 3 questions |
| Adaptivity vs. standardization: different questions per student can feel unfair | Question type fixed per trigger, content adapted, transcript saved |
| Authorship false positive (G5) | Never label it as cheating; the profile is "verify understanding" and the decision is the teacher's |
| Student uses AI to answer the follow-up | Short reply window, inside the exam environment |
| A hint gives the answer away | N3 only after N2 fails; the mediated score is weighted by level |
| Arbitrary weights | Pilot: compare the generated profiles with the teacher's assessment of the same students |

## References

- Treagust, D. F. (1988). Development and use of diagnostic tests to evaluate students' misconceptions in science. *International Journal of Science Education*, 10, 159–169.
- Tsui, C.-Y. & Treagust, D. (2010). Evaluating secondary students' scientific reasoning in genetics using a two-tier diagnostic instrument. *International Journal of Science Education*, 32(8).
- Poehner, M. E. & Lantolf, J. P. (2013). Bringing the ZPD into the equation: Capturing L2 development during Computerized Dynamic Assessment. *Language Teaching Research*, 17(3).
- Poehner, M. E. (2008). *Dynamic Assessment: A Vygotskian approach*. Springer.
- Sotiriadou, P., Logan, D., Daly, A. & Guest, R. (2019). The role of authentic assessment to preserve academic integrity and promote skill development and employability. *Studies in Higher Education*.
- Huxham, M., Campbell, F. & Westwood, J. (2012). Oral versus written assessments: a test of student performance and attitudes. *Assessment & Evaluation in Higher Education*, 37(1), 125–136.
- Lee, J., Hung, J.-T., Joyner, D. A. et al. (2025). Socratic Mind: Impact of a Novel GenAI-Powered Assessment Tool on Student Learning and Higher-Order Thinking. arXiv.
- Reboot Foundation. *Using AI to Bring Back Oral Exams* (includes the NYU case).
- Xu, J. et al. (2025). Exploring the Potential of Conversational AI for Assessing Second Language Oral Proficiency. *TESOL Quarterly*.
- The AI interviewer: multi-faceted evaluation of adaptive questioning by large language models (2026). *Scientific Reports*.
- Semantic Variability of Replies Across LLMs: Implications for Designing Conversation-Based Assessment (2026). arXiv.
- Phan, A. (2023). Impact of Perceived Stress during Oral Examination on Student Performance Outcomes. ASEE.
