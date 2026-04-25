# Arena Signal Annotator

**Part of**: *Beyond Explicit Corrections: Benchmarking Implicit Behavioral Signal Learning in Multi-Session Collaborative LLM Agents*

This toolkit mines the `lmarena-ai/arena-human-preference-55k` dataset for real-world examples of **implicit behavioral signals** — the behavioral cues users give when they're dissatisfied with an AI response, without ever saying so directly. These examples feed into the BSEM benchmark dataset (Day 2 of the project plan).

---

## Why This Dataset

`lmarena-ai/arena-human-preference-55k` contains 57,477 real human-AI conversations from Chatbot Arena, where users compared two model responses and voted for the better one. Because votes are cast by real users mid-conversation, the dataset contains naturally occurring instances of:

- Users who kept talking even though neither response satisfied them (response ignoring proxy)
- Users who expressed frustration in follow-up messages (frustration markers)
- Users who gave up and switched topics or abandoned the task (task abandonment)

This gives us **grounded, real-world signal examples** to draw from, rather than purely synthetic data. The annotations produced here become seed examples for the WildChat-style scenario construction in Section 4.1 of the paper.

---

## Dataset Schema

The actual fields in `lmarena-ai/arena-human-preference-55k`:

| Field | Type | Description |
|---|---|---|
| `id` | str | Unique conversation ID |
| `prompt` | str | JSON-encoded list of user messages only — `["Q1", "Q2", "Q3"]` |
| `response_a` | str | JSON-encoded list of Model A's responses — `["R1", "R2", "R3"]` |
| `response_b` | str | JSON-encoded list of Model B's responses — `["R1", "R2", "R3"]` |
| `model_a` | str | Model A name (e.g. `gpt-4o`) |
| `model_b` | str | Model B name (e.g. `claude-3-5-sonnet`) |
| `winner_model_a` | int | 1 if user preferred Model A |
| `winner_model_b` | int | 1 if user preferred Model B |
| `winner_tie` | int | 1 if user voted tie (neither response satisfied them) |

`prompt` and `response_a/b` interleave as: `Q1 → R1 → Q2 → R2 → Q3 → R3 ...`

**Important**: The dataset is overwhelmingly single-turn (~98.5%). Only ~296 rows have ≥2 user turns, and only a subset of those have ≥4 turns (our threshold for meaningful behavioral signal analysis). Task abandonment examples are extremely rare (~1 confirmed). Frustration markers and response ignoring are more recoverable.

---

## What We're Extracting and Why

### Signal Types

| Signal | What It Means for BSEM | Detection Proxy in This Dataset |
|---|---|---|
| **Response Ignoring** | User's next turn is topically disconnected — they didn't engage with the agent's previous response at all | `winner_tie == 1` in a multi-turn row (user kept going but was never satisfied), OR follow-up starts with a topic-shift phrase |
| **Frustration Marker** | User expresses impatience without stating the core problem — short curt follow-ups, negative language | Regex match on frustration phrases in follow-up turns (e.g. "still wrong", "that's not it"); OR ≤12-word follow-up with `?/!/no/not/still/wrong` |
| **Task Abandonment** | User gives up entirely after accumulated failure | Regex match on give-up phrases in the final user message (e.g. "forget it", "never mind", "give up") |

### Multi-Turn Requirement (≥4 user turns)

We only keep rows where the user sent **at least 4 messages**. This is a deliberate design decision:

- Single-turn rows (one user message → two model responses → vote) cannot show behavioral patterns — there's no follow-up behavior to observe
- 2–3 turn rows give minimal context — it's hard to distinguish frustration from normal clarification
- ≥4 turns means the user went back and forth enough times that behavioral signals (frustration buildup, repeated rephrasing, topic ignoring) are clearly visible and distinguishable from noise

### What Gets Auto-Inferred

`download_data.py` auto-computes these fields for every candidate before you annotate:

| Column | How It's Computed |
|---|---|
| **Turn** | The exact turn number (in the full interleaved conversation) where the signal appears |
| **Feedback Type** | The detected signal type from the heuristics |
| **How It's Given** | Human-readable description of why the heuristic fired (e.g. "Explicit frustration language in follow-up", "Short curt follow-up (6 words) with negative marker") |
| **Context** | Model A's response immediately before the signal turn — what the user was reacting to |
| **User Message Preview** | The actual signal-turn text, truncated to 200 chars |

Your job as annotator is to verify these auto-inferences and add the fields the heuristics can't compute: task domain, what preference was violated, and whether the heuristic actually fired correctly.

---

## Setup

```bash
cd arena_annotation_toolkit
pip install -r requirements.txt
```


---

## Step 1 — Download & Filter

```bash
python download_data.py
```

Downloads all 57,477 rows from HuggingFace, filters to multi-turn conversations (≥4 user turns), runs signal detection heuristics, and saves up to 120 candidates per signal type.

**What it prints:**
```
── Schema Diagnostic ─────────────────────────────────────────
Row 0:
  type(prompt): str
  prompt (str): '["Q1", "Q2", "Q3", "Q4"]'
  --> parsed user turns: 4
  --> parsed responses:  4
  --> parsed[0]: {'role': 'user', 'content': 'Q1'}
──────────────────────────────────────────────────────────────

── Results ──────────────────────────────────────────────────
  Single-turn (skipped):  57181
  Multi-turn (processed): 296
  Multi-turn, no signal:  96
  response_ignoring: 108
  frustration_marker: 120
  task_abandonment: 1
  Total candidates: 229
```

Output: `data/arena_candidates.json` — interleaved across signal types for annotation variety.

**Known limitation**: Task abandonment is nearly absent in this dataset (real Arena users rarely type give-up phrases explicitly). The ~50 abandonment scenarios needed for the benchmark will need to be generated synthetically using WildChat episodes as seeds (see plan.md Day 2).

---

## Step 2 — Annotate

```bash
python annotator_app.py
```

Then open **`http://127.0.0.1:8765`** in Chrome, Safari, or Firefox.

### What the UI shows

- **Left panel**: Full conversation in messenger-style bubble UI
  - User messages → right-aligned green bubbles
  - AI responses → left-aligned blue bubbles
  - The auto-detected signal turn → highlighted with a red outline
  - Both Model A and Model B conversations shown (they share the same user messages but have different AI responses)
- **Right sidebar**: Annotation fields + auto-inferred metadata (Turn, How It's Given, User Message Preview shown at the top so you don't have to scroll to find the signal)

### For each record, you decide:

| Field | What to fill |
|---|---|
| **Confirmed Signal** | Is the heuristic correct? Which signal type is this actually? |
| **Confidence** | How certain are you? High / Medium / Low |
| **Task Domain** | Mathematics / Coding / Writing / General Knowledge |
| **Signal Evidence** | Which turn shows it — copy the key phrase |
| **What's Updated** | What should the agent update in its preference model? (e.g. "Response length", "Explanation depth", "Format preference") |
| **Inferred Preference** | Free-text preference hypothesis (e.g. "User prefers step-by-step debug output rather than just the fixed code") |
| **Notes** | Edge cases, ambiguity, why you marked None |

### Keyboard shortcuts

```
i          → confirmed signal: response ignoring
f          → confirmed signal: frustration marker
a          → confirmed signal: task abandonment
n          → confirmed signal: none (heuristic false positive)
H / M / L  → confidence: high / medium / low
1          → task domain: mathematics
2          → task domain: coding
3          → task domain: writing
4          → task domain: general knowledge
→ or Enter → save & next record
←          → go back to previous record
Ctrl+Enter → save & next (when cursor is in a text field)
```

Progress auto-saves after every record to `data/arena_candidates.json`.

### Annotation guidelines

**Confirmed Signal = None** when:
- The follow-up is just a normal continuation (not frustrated, not ignoring — just asking a follow-up question)
- The frustration language is casual/rhetorical, not expressing genuine dissatisfaction with the AI
- The "topic shift" is actually a natural next step in a multi-part task
- The tie vote is because both responses were genuinely equally good, not because both were bad

**Confidence = Low** when:
- You can see *something* off but can't pin down the signal type
- The signal is ambiguous between two types (e.g. could be ignoring or abandonment)
- The conversation is too short to be sure

**Inferred Preference**: Write this as a complete hypothesis sentence, the way BSEM would output it. Example: *"User prefers concise responses without preamble — Interaction Efficiency preference, coding task"*. This becomes training signal for BSEM Stage 2.

---

## Step 3 — Export to Excel

Click **⬇ Export Excel** in the UI, or run:

```bash
python save_annotations.py
```

Output: `data/arena_annotations.xlsx`

### Sheet 1: Annotations

All records with these columns in order:

| Column | Source |
|---|---|
| Conv ID | Dataset `id` field |
| Turn | Auto-computed turn number of signal |
| Feedback Type | Auto-detected signal type |
| How It's Given | Auto-described detection method |
| Context | Model's response before the signal turn |
| What's Updated | Annotator fills — what preference should change |
| Notes | Annotator fills — edge cases |
| User Message Preview | Signal turn text (200 chars) |
| Task Domain | Annotator fills |
| Confirmed Signal | Annotator's verified signal type |
| Confidence | High / Medium / Low |
| Signal Evidence | Annotator's key phrase |
| Inferred Preference | Annotator's preference hypothesis |
| Winner / Model A / Model B | Dataset metadata |
| Num User Turns | Total user turns in this conversation |
| All Detected Signals | All signals the heuristic detected |

Rows are color-coded by confirmed signal type: blue = response ignoring, red = frustration marker, yellow = task abandonment, gray = none.

### Sheet 2: Summary

Counts broken down by: signal type, confidence level, task domain, and a signal × domain cross-tab.

---

## How These Annotations Feed Into the Paper

The confirmed and annotated examples from this toolkit are used in three ways:

1. **Few-shot examples for BSEM Stage 1** (Signal Detection prompt) — the annotated `signal_evidence` and `user_msg_preview` fields become the 4–6 few-shot examples per signal type in the Stage 1 prompt

2. **Seed templates for synthetic scenario generation** (Day 2, dataset construction) — real WildChat + Arena episodes with confirmed signals are used as seeds for GPT-4o to generate the full 250-scenario benchmark, especially for frustration markers and response ignoring where real examples exist

3. **Taxonomy validation** — the `inferred_preference` field confirms that our 4-category preference taxonomy (Response Style, Explanation Depth, Content Focus, Interaction Efficiency) actually covers the preferences users signal implicitly in real conversations

---

## File Structure

```
arena_annotation_toolkit/
├── requirements.txt          # pip dependencies
├── download_data.py          # Step 1: download, filter, extract candidates
├── annotator_app.py          # Step 2: Flask annotation UI
├── save_annotations.py       # Step 3: export to Excel
├── README.md                 # this file
└── data/
    ├── arena_candidates.json # all candidates + annotations (auto-saved)
    └── arena_annotations.xlsx  # final Excel export
```