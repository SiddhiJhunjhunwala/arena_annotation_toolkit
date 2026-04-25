# Arena Signal Annotator
### Spot-check `lmarena-ai/arena-human-preference-55k` for implicit signal proxies

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

Downloads the HuggingFace dataset (~55K rows) and extracts up to **360 candidate rows** (~120 per signal type) using these heuristics:

| Signal | Detection Heuristic |
|---|---|
| **Response Ignoring** | `winner == "tie (bothbad)"` — user voted against both responses |
| **Frustration Markers** | User message matches impatient language patterns (e.g. "still wrong", "that's not", "try again"); OR short (<10 word) follow-ups containing `?!/no/not/still` |
| **Task Abandonment** | Final user message matches give-up phrases (e.g. "forget it", "never mind", "give up") |

Output: `data/arena_candidates.json`

---

## Step 2 — Annotate

```bash
python annotator_app.py
```

Opens `http://localhost:5000` — a browser annotation UI.

### For each record, you annotate:
- **Confirmed Signal** — is the heuristic right? What's the actual signal?
- **Confidence** — High / Medium / Low
- **Task Domain** — Mathematics / Coding / Writing / General Knowledge
- **Signal Evidence** — which turn(s) show the signal
- **Inferred Preference** — what does this signal tell us about what the user actually wanted?
- **Notes** — edge cases, ambiguity

### Keyboard shortcuts (fastest way to annotate):
```
i / f / a / n   → signal type (ignoring / frustration / abandonment / none)
H / M / L       → confidence
1 / 2 / 3 / 4  → domain (math / code / writing / general)
→ or Enter      → save & next
←               → go back
Ctrl+Enter      → save & next (from a text field)
```

Progress auto-saves after every record to `data/arena_candidates.json`.

---

## Step 3 — Export to Excel

Click **⬇ Export Excel** in the UI, or run:

```bash
python save_annotations.py
```

Output: `data/arena_annotations.xlsx` with two sheets:
- **Annotations** — all records with annotation columns, color-coded by signal type
- **Summary** — counts by signal, confidence, domain, and signal×domain cross-tab

---

## Signal Type Definitions (for annotation)

**Response Ignoring**: The user's next turn is topically disconnected from the agent's previous response — they don't acknowledge or engage with what was said. Proxy: user voted both responses bad.

**Frustration Marker**: The user expresses impatience without explicitly stating the core problem — short curt follow-ups, expressions like "still wrong", "that's not it". The agent must infer what preference was violated.

**Task Abandonment**: The user gives up on the task entirely, especially after signs of accumulated failure. Only code if the abandonment language is present (not just a short message).

**None**: The heuristic fired but there's no genuine implicit signal here on review.

---

## Output Format

Each annotated record in `arena_candidates.json`:

```json
{
  "question_id": "...",
  "winner": "model_a",
  "model_a": "gpt-4o",
  "model_b": "claude-3-5-sonnet",
  "detected_signals": ["frustration_marker"],
  "conversation_a": [{"role": "user", "content": "..."}, ...],
  "conversation_b": [{"role": "user", "content": "..."}, ...],
  "annotation": {
    "confirmed_signal": "frustration_marker",
    "confidence": "high",
    "task_domain": "coding",
    "signal_evidence": "Turn 3, user says 'still wrong, try again'",
    "inferred_preference": "User prefers step-by-step debug output, not just the fixed code",
    "notes": ""
  }
}
```
