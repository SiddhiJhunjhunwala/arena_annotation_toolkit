# Arena Signal Annotator

**Part of**: *Beyond Explicit Corrections: Benchmarking Implicit Behavioral Signal Learning in Multi-Session Collaborative LLM Agents*

This toolkit mines `lmarena-ai/arena-human-preference-140k` (and optionally the earlier `55k` version) for real-world examples of **implicit behavioral signals** — the behavioral cues users give when dissatisfied with an AI response, without ever saying so directly. Annotated examples feed into the BSEM benchmark dataset.

---

## Why This Dataset

`lmarena-ai/arena-human-preference-140k` contains 135,634 real human-AI conversations from Chatbot Arena, where users compared two model responses and voted for the better one. Because votes are cast by real users mid-conversation, the dataset contains naturally occurring instances of:

- Users who kept talking even though neither response satisfied them (**response ignoring** proxy)
- Users who expressed frustration in follow-up messages (**frustration markers**)
- Users who gave up and switched topics or abandoned the task (**task abandonment**)

This gives us **grounded, real-world signal examples** rather than purely synthetic data. Annotations become seed examples for the WildChat-style scenario construction in Section 4.1 of the paper.

---

## Dataset Schema (140k)

| Field | Type | Description |
|---|---|---|
| `id` | str | UUID conversation identifier |
| `model_a` / `model_b` | str | Model names (e.g. `gemini-2.5-pro`, `claude-3-7-sonnet`) |
| `winner` | str | `"model_a"` / `"model_b"` / `"tie"` / `"both_bad"` |
| `conversation_a` / `conversation_b` | list | Full interleaved turns: `[{role, content: [{type, text, image}]}]` |
| `full_conversation` | list | Combined view with both model responses per turn |
| `category_tag` | dict | Domain/complexity tags (`domain_knowledge`, `creative_writing`, etc.) |
| `language` | str | ISO language code (`"en"`, `"pl"`, `"de"`, …) |
| `is_code` | bool | Whether the conversation is code-related |
| `timestamp` | datetime | When the conversation was recorded |

Unlike the older 55k dataset (which stored conversations as flat JSON strings), the 140k dataset uses proper structured dicts with role/content blocks — responses are already embedded inside `conversation_a/b`.

---

## What We Extract and Why

### Signal Types

| Signal | Research Meaning | Detection Proxy |
|---|---|---|
| **Response Ignoring** | User's next turn is topically disconnected — they didn't engage with the prior response at all | `winner == "both_bad"` in a multi-turn row; OR follow-up starts with a topic-shift phrase (`"now let's…"`, `"can you instead…"`) |
| **Frustration Marker** | User expresses impatience without stating the core problem | Regex on frustration phrases in follow-up turns (`"still wrong"`, `"that's not what I asked"`); OR ≤12-word curt follow-up with `?/!/no/not/still/wrong` |
| **Task Abandonment** | User gives up entirely after accumulated failure | Regex on give-up phrases in final user message (`"forget it"`, `"never mind"`, `"let's move on"`) |

### Multi-Turn Gate (≥4 user turns)

Only rows where the user sent **at least 4 messages** are kept. This is a deliberate design decision:

- Single-turn rows cannot show behavioral patterns — there's no follow-up behavior to observe
- 2–3 turn rows give minimal context — hard to distinguish frustration from normal clarification
- ≥4 turns means the user went back and forth enough that signals are clearly visible and defensible

### Known Limitation: Task Abandonment is Rare

Both the 55k and 140k datasets yield very few task abandonment examples (~1–6 confirmed). Real Arena users rarely type explicit give-up phrases. The ~50 abandonment scenarios needed for BSEM will need to be generated synthetically using WildChat episodes as seeds (see plan.md, Day 2).

### Auto-Inferred Fields

`download_data.py` auto-computes these before annotation:

| Field | How Computed |
|---|---|
| **Turn** | Exact position in the full interleaved conversation where the signal appears |
| **Feedback Type** | Detected signal type from heuristics |
| **How It's Given** | Human-readable description (e.g. `"Explicit frustration language in follow-up"`) |
| **Context** | Model's response immediately before the signal turn |
| **User Message Preview** | Signal-turn text, truncated to 200 chars |
| **Dataset Domain** | Auto-inferred from `is_code` + `category_tag` fields |
| **Task Domain** | Pre-filled in annotation from dataset domain (overridable) |

---

## Dataset Stats (140k, English only, ≥4 turns)

```
Total rows:              135,634
Skipped (non-English):    64,459
Single-turn (skipped):    69,486
Multi-turn processed:      1,689
Multi-turn, no signal:       705
─────────────────────────────────
response_ignoring:           120
frustration_marker:          120
task_abandonment:              6
Total candidates:            246
```

---

## Setup

```bash
cd arena_annotation_toolkit
pip install -r requirements.txt
```


> **Python env note**: If you have multiple Python environments (e.g. miniconda + system Python), make sure `pip` and `python` point to the same environment. Use `/opt/miniconda3/bin/pip install datasets` if needed.

---

## Workflow

### Step 1 — Download & Filter

```bash
python download_data.py
```

Downloads all 135,634 rows, filters to English multi-turn conversations (≥4 user turns), runs signal detection heuristics, saves up to 120 candidates per signal type.

**Key setting at top of file:**
```python
ENGLISH_ONLY = True   # set False to include all languages
TARGET_PER_TYPE = 120
```

Output: `data/arena_candidates.json`

---

### Step 2 — Annotate

```bash
python annotator_app.py
```

Then open **`http://127.0.0.1:8765`** in Chrome, Safari, or Firefox.

> **Do not click `python annotator_app.py` if your terminal renders it as a hyperlink** — type the command manually. The underscore in the filename can cause terminal markdown parsers to mangle it.

### UI Layout

Three-column layout:

**Left — Conversation List (280px)**
- Search bar: filter by conversation ID or message text
- Filter chips: All / Ignoring / Frustration / Abandon / **Todo** (unannotated only)
- Scrollable list showing ID, signal dot color, ✓ badge when annotated, message preview
- Click any row to jump to that conversation

**Center — Conversation View**
- Messenger-style bubble UI: user messages right-aligned (green), AI responses left-aligned (blue)
- Signal turn highlighted with a red outline
- Both Model A and Model B conversations shown
- Header shows: conv ID, signal badges, winner, turn count, 🌐 language, `{ }` code tag, date

**Right — Annotation Sidebar**
- Auto-inferred metadata shown at top (Turn, How It's Given, User Message Preview)
- Annotation fields to fill in

### Annotation Fields

| Field | What to Fill |
|---|---|
| **Confirmed Signal** | Is the heuristic correct? Which signal is this actually? |
| **Confidence** | High / Medium / Low |
| **Task Domain** | Mathematics / Coding / Writing / General Knowledge (pre-filled from dataset where possible) |
| **Signal Evidence** | The key phrase — copy the exact text that shows the signal |
| **What's Updated** | What should the agent update? (e.g. `"Response format preference"`, `"Explanation depth"`) |
| **Inferred Preference** | Full hypothesis sentence (e.g. `"User prefers step-by-step debug output rather than just the fixed code"`) |
| **Notes** | Edge cases, ambiguity, why you marked None |

### Keyboard Shortcuts

```
i          → confirmed signal: response ignoring
f          → confirmed signal: frustration marker
a          → confirmed signal: task abandonment
n          → confirmed signal: none (false positive)
H / M / L  → confidence: high / medium / low
1          → task domain: mathematics
2          → task domain: coding
3          → task domain: writing
4          → task domain: general knowledge
→ or Enter → save & next
←          → previous record
Ctrl+Enter → save & next (from inside a text field)
```

Auto-saves to `data/arena_candidates.json` after every record.

### Annotation Guidelines

**Mark as None when:**
- Follow-up is a natural continuation, not frustrated or ignoring
- Frustration language is casual/rhetorical, not expressing genuine dissatisfaction
- Topic shift is a natural next step in a multi-part task
- `both_bad` vote is because responses were genuinely equal, not both bad

**Confidence = Low when:**
- Something seems off but you can't pin down the signal type
- Could be two different signal types (e.g. ignoring vs abandonment)
- Conversation too short to be sure

**Inferred Preference format:** Write as a complete hypothesis the way BSEM Stage 1 would output it:
> *"User prefers concise responses without preamble — Interaction Efficiency preference, coding task"*

---

### Step 3 — Sample 100 (optional)

```bash
python sample100.py
```

Randomly samples 100 records from `data/arena_candidates.json` → `data/arena_sample100.json`. Same JSON structure, works directly with `annotator_app.py`.

To annotate the sample instead of the full set, change line 21 in `annotator_app.py`:
```python
DATA_FILE = Path("data/arena_sample100.json")
```

> **Filename note**: The script is named `sample100.py` (not `sample_100.py`) — underscores before numbers cause some terminals to misparse the filename as a markdown link.

---

### Step 4 — Export to Excel

Click **⬇ Export Excel** in the UI, or run:

```bash
python save_annotations.py
```

Output: `data/arena_annotations.xlsx`

#### Sheet 1: Annotations

Columns in order:

| Column | Source |
|---|---|
| Conv ID | Dataset `id` field |
| Turn | Auto-computed signal turn number |
| Feedback Type | Auto-detected signal type |
| How It's Given | Auto-described detection method |
| Context | Model response before the signal turn |
| What's Updated | Annotator: what preference should change |
| Notes | Annotator: edge cases |
| User Message Preview | Signal turn text (200 chars) |
| Task Domain | Annotator: domain |
| Confirmed Signal | Annotator's verified signal type |
| Confidence | High / Medium / Low |
| Signal Evidence | Annotator's key phrase |
| Inferred Preference | Annotator's preference hypothesis |
| Winner | `model_a` / `model_b` / `tie` / `both_bad` |
| Model A / Model B | Model names |
| Num User Turns | Total user turns |
| All Detected Signals | All heuristic signals fired |
| Language | ISO language code |
| Is Code | Boolean |
| Dataset Domain | Auto-inferred from category tags |
| Timestamp | Conversation date |

Color-coded by confirmed signal: 🔵 blue = response ignoring, 🔴 red = frustration marker, 🟡 yellow = task abandonment, ⬜ gray = none.

#### Sheet 2: Summary

Counts by signal type, confidence, task domain, and signal × domain cross-tab.

---

## How Annotations Feed Into the Paper

1. **Few-shot examples for BSEM Stage 1** — `signal_evidence` and `user_msg_preview` become the 4–6 few-shot examples per signal type in the Stage 1 detection prompt

2. **Seed templates for synthetic generation** (Day 2) — confirmed signal examples are used as seeds for GPT-4o to generate the full 250-scenario benchmark; especially important for frustration markers and response ignoring where real examples exist

3. **Taxonomy validation** — `inferred_preference` entries confirm that the 4-category preference taxonomy (Response Style, Explanation Depth, Content Focus, Interaction Efficiency) covers preferences users signal implicitly in real conversations

---

## File Structure

```
arena_annotation_toolkit/
├── requirements.txt           # pip dependencies
├── download_data.py           # Step 1: download, filter, extract candidates (140k)
├── annotator_app.py           # Step 2: Flask annotation UI (port 8765)
├── sample100.py               # Step 3: sample 100 random records
├── save_annotations.py        # Step 4: export to Excel
├── README.md                  # this file
└── data/
    ├── arena_candidates.json     # all candidates + annotations (auto-saved)
    ├── arena_sample100.json      # 100-record random sample (optional)
    └── arena_annotations.xlsx   # final Excel export
```