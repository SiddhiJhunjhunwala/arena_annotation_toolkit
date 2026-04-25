"""
Step 1: Download lmarena-ai/arena-human-preference-55k and extract
candidate rows for implicit signal annotation.

Actual schema:
  - prompt      : list of {"role": ..., "content": ...} — the conversation history
  - response_a  : model A's final response (string or list)
  - response_b  : model B's final response
  - winner_model_a, winner_model_b, winner_tie : 0/1 flags
  - model_a, model_b : model names

Multi-turn = prompt has >= 4 user turns — enough conversational history for
behavioral patterns (frustration, ignoring, abandonment) to be meaningful.
Single-turn or short exchanges are skipped.

Run: python download_data.py
Output: data/arena_candidates.json
"""

import json, re
from pathlib import Path
from datasets import load_dataset
from tqdm import tqdm

OUT_DIR = Path("data")
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "arena_candidates.json"

FRUSTRATION_RE = re.compile(
    r"\b(ugh|seriously\??|come on|that'?s not|still wrong|no[,!]? that|"
    r"again\??|wtf|what the|not what i|try again|wrong again|"
    r"you'?re not|doesn'?t work|didn'?t work|still not|that is not|"
    r"not right|you misunderstood|that('?s| is) wrong)\b",
    re.IGNORECASE,
)

ABANDONMENT_RE = re.compile(
    r"\b(forget it|never mind|nevermind|forget this|this is useless|"
    r"give up|doesn'?t matter|not worth|too hard|skip it|"
    r"don'?t bother|leave it|drop it|scrap it)\b",
    re.IGNORECASE,
)

TOPIC_SHIFT_RE = re.compile(
    r"^(ok(ay)?[,.]?\s+)?(now[,]?\s+|next[,]?\s+|can you|could you|"
    r"what about|let'?s (try|do|move|talk)|instead[,]?\s|"
    r"actually[,]?\s|moving on|different (question|topic))",
    re.IGNORECASE,
)

USER_ROLES      = {"user", "human"}
ASSISTANT_ROLES = {"assistant", "gpt", "bot", "model"}


def parse_prompt_as_user_turns(raw) -> list:
    """
    prompt is a JSON string of a flat list of user messages only.
    e.g. '["What is X?", "How about Y?", "And Z?"]'
    Returns list of {"role": "user", "content": str}
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return [{"role": "user", "content": raw}]
    if not isinstance(raw, list):
        return []
    turns = []
    for item in raw:
        if isinstance(item, str):
            turns.append({"role": "user", "content": item})
        elif isinstance(item, dict):
            content = item.get("content") or item.get("value") or item.get("text") or ""
            turns.append({"role": "user", "content": str(content)})
    return turns


def parse_responses(raw) -> list:
    """
    response_a / response_b is a JSON string of a flat list of model responses,
    one per user turn. e.g. '["Response to Q1", "Response to Q2", ...]'
    Returns list of strings.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(r) for r in parsed]
            return [str(parsed)]
        except Exception:
            return [raw]
    if isinstance(raw, list):
        return [str(r) for r in raw]
    return [str(raw)]


def get_response_text(raw) -> str:
    """Get full concatenated response text (for signal detection)."""
    responses = parse_responses(raw)
    return " ".join(responses)


def diagnose_schema(ds, n=5):
    print("\n── Schema Diagnostic ─────────────────────────────────────────────")
    for i, row in enumerate(ds):
        if i >= n:
            break
        prompt     = row.get("prompt")
        response_a = row.get("response_a")
        print(f"\nRow {i}:")
        print(f"  Keys: {list(row.keys())}")
        print(f"  winner_model_a={row.get('winner_model_a')}  winner_model_b={row.get('winner_model_b')}  winner_tie={row.get('winner_tie')}")
        print(f"  type(prompt): {type(prompt).__name__}")
        if isinstance(prompt, list):
            print(f"  len(prompt): {len(prompt)}")
            if prompt:
                print(f"  prompt[0]: {repr(prompt[0])[:250]}")
            if len(prompt) > 1:
                print(f"  prompt[1]: {repr(prompt[1])[:250]}")
        elif isinstance(prompt, str):
            print(f"  prompt (str): {repr(prompt[:250])}")
        print(f"  type(response_a): {type(response_a).__name__}")
        print(f"  response_a: {repr(get_response_text(response_a)[:150])}")

        parsed     = parse_prompt_as_user_turns(prompt)
        responses  = parse_responses(response_a)
        print(f"  --> parsed user turns: {len(parsed)}")
        print(f"  --> parsed responses:  {len(responses)}")
        if parsed:
            print(f"  --> parsed[0]: {repr(parsed[0])[:200]}")
        if responses:
            print(f"  --> response[0]: {repr(responses[0][:150])}")
    print("\n──────────────────────────────────────────────────────────────────\n")


def get_winner(row) -> str:
    """Normalize winner flags into a string."""
    if row.get("winner_tie"):
        return "tie"
    if row.get("winner_model_a"):
        return "model_a"
    if row.get("winner_model_b"):
        return "model_b"
    return ""


def get_user_turns(turns: list) -> list:
    """Works on both list-of-dicts and returns content strings."""
    return [t["content"] for t in turns if isinstance(t, dict) and t.get("role") == "user"]


def is_multi_turn(user_turns: list) -> bool:
    """user_turns is already a list of {"role":"user","content":...} dicts from parse_prompt_as_user_turns.
    Multi-turn = user sent >= 4 messages."""
    return len(user_turns) >= 4


def detect_signals(user_turns: list, responses_a: list, winner: str) -> list:
    """
    user_turns: list of {"role":"user","content":str} — all user messages in order
    responses_a: list of str — model A's per-turn responses (used for context)
    Returns list of signal dicts with rich metadata.
    """
    signals = []
    winner  = (winner or "").lower()
    seen    = set()

    user_contents = [t["content"] for t in user_turns]  # extract strings
    followups     = user_contents[1:]  # skip opening message

    def get_context(user_idx: int) -> str:
        """Get model A's response to the turn BEFORE this user turn."""
        prev_resp_idx = user_idx - 1
        if 0 <= prev_resp_idx < len(responses_a):
            return responses_a[prev_resp_idx][:300]
        return ""

    # ── Response Ignoring ─────────────────────────────────────────────────────
    if winner == "tie":
        # Point to last user turn as the accumulated ignoring signal
        u_idx = len(user_contents) - 1
        signals.append({
            "signal_type":      "response_ignoring",
            "turn_number":      u_idx * 2 + 1,   # in full interleaved convo (1-indexed)
            "user_turn_number": u_idx + 1,
            "how_its_given":    "User voted both responses unsatisfactory (tie)",
            "context":          get_context(u_idx),
            "user_msg_preview": user_contents[u_idx][:200],
        })
        seen.add("response_ignoring")

    for fu_idx, fu in enumerate(followups):
        if TOPIC_SHIFT_RE.match(fu.strip()) and "response_ignoring" not in seen:
            u_idx = fu_idx + 1
            signals.append({
                "signal_type":      "response_ignoring",
                "turn_number":      u_idx * 2 + 1,
                "user_turn_number": u_idx + 1,
                "how_its_given":    "Follow-up starts with topic shift — prior response not acknowledged",
                "context":          get_context(u_idx),
                "user_msg_preview": fu[:200],
            })
            seen.add("response_ignoring")
            break

    # ── Frustration Markers ───────────────────────────────────────────────────
    for fu_idx, fu in enumerate(followups):
        if FRUSTRATION_RE.search(fu):
            u_idx = fu_idx + 1
            signals.append({
                "signal_type":      "frustration_marker",
                "turn_number":      u_idx * 2 + 1,
                "user_turn_number": u_idx + 1,
                "how_its_given":    "Explicit frustration language in follow-up",
                "context":          get_context(u_idx),
                "user_msg_preview": fu[:200],
            })
            seen.add("frustration_marker")
            break

    if "frustration_marker" not in seen:
        for fu_idx, fu in enumerate(followups):
            wc = len(fu.split())
            if 1 <= wc <= 12 and any(m in fu.lower() for m in ["?", "!", " no", "not ", "still", "wrong"]):
                u_idx = fu_idx + 1
                signals.append({
                    "signal_type":      "frustration_marker",
                    "turn_number":      u_idx * 2 + 1,
                    "user_turn_number": u_idx + 1,
                    "how_its_given":    f"Short curt follow-up ({wc} words) with negative marker",
                    "context":          get_context(u_idx),
                    "user_msg_preview": fu[:200],
                })
                seen.add("frustration_marker")
                break

    # ── Task Abandonment ──────────────────────────────────────────────────────
    if user_contents and ABANDONMENT_RE.search(user_contents[-1]):
        u_idx = len(user_contents) - 1
        signals.append({
            "signal_type":      "task_abandonment",
            "turn_number":      u_idx * 2 + 1,
            "user_turn_number": u_idx + 1,
            "how_its_given":    "Give-up language in final user message",
            "context":          get_context(u_idx),
            "user_msg_preview": user_contents[-1][:200],
        })
        seen.add("task_abandonment")

    return signals



def build_full_turns(user_turns: list, responses: list) -> list:
    """
    Interleave user messages with model responses into a full conversation.
    user_turns: list of {"role":"user","content":...}
    responses:  list of str, one per user turn (may be shorter if truncated)
    """
    turns = []
    for i, ut in enumerate(user_turns):
        turns.append({"role": "user", "content": ut["content"][:1500]})
        if i < len(responses):
            turns.append({"role": "assistant", "content": responses[i][:1500]})
    return turns


def build_display_conversation(user_turns: list, responses_a: list, responses_b: list) -> dict:
    return {
        "conversation_a": build_full_turns(user_turns, responses_a),
        "conversation_b": build_full_turns(user_turns, responses_b),
    }


def main():
    print("Loading lmarena-ai/arena-human-preference-55k from HuggingFace...")
    ds = load_dataset("lmarena-ai/arena-human-preference-55k", split="train")
    print(f"  Total rows: {len(ds)}")

    diagnose_schema(ds, n=5)

    candidates = {
        "response_ignoring":  [],
        "frustration_marker": [],
        "task_abandonment":   [],
    }
    TARGET_PER_TYPE = 120

    stats = {"single_turn": 0, "multi_turn": 0, "no_signal": 0}

    print("Scanning (multi-turn only, ≥4 user turns)...")
    for row in tqdm(ds):
        user_turns  = parse_prompt_as_user_turns(row.get("prompt"))
        responses_a = parse_responses(row.get("response_a"))
        responses_b = parse_responses(row.get("response_b"))
        winner      = get_winner(row)

        if not is_multi_turn(user_turns):
            stats["single_turn"] += 1
            continue

        stats["multi_turn"] += 1
        signals = detect_signals(user_turns, responses_a, winner)

        if not signals:
            stats["no_signal"] += 1
            continue

        convos    = build_display_conversation(user_turns, responses_a, responses_b)
        sig_types = list({s["signal_type"] for s in signals})
        priority  = ["response_ignoring", "frustration_marker", "task_abandonment"]
        primary   = next((s for p in priority for s in signals if s["signal_type"] == p), signals[0])

        record = {
            # ── Identity ────────────────────────────────────────────────────
            "question_id":        row.get("id", ""),
            "winner":             winner,
            "model_a":            row.get("model_a", ""),
            "model_b":            row.get("model_b", ""),
            # ── Auto-inferred columns ────────────────────────────────────────
            "conv_id":            row.get("id", ""),
            "turn":               primary["turn_number"],
            "feedback_type":      primary["signal_type"],
            "how_its_given":      primary["how_its_given"],
            "context":            primary["context"],
            "user_msg_preview":   primary["user_msg_preview"],
            # ── All detected signals (may be >1) ─────────────────────────────
            "detected_signals":   sig_types,
            "all_signal_details": signals,
            "num_user_turns":     len(user_turns),
            # ── Conversations for annotation UI ──────────────────────────────
            "conversation_a":     convos["conversation_a"],
            "conversation_b":     convos["conversation_b"],
            # ── Annotator-filled fields ──────────────────────────────────────
            "annotation": {
                "confirmed_signal":    None,   # response_ignoring | frustration_marker | task_abandonment | none
                "confidence":          None,   # high | medium | low
                "task_domain":         None,   # mathematics | writing | coding | general_knowledge
                "signal_evidence":     "",     # which turn shows it
                "what_is_updated":     "",     # what preference/behavior should the agent update
                "inferred_preference": "",     # free-text preference hypothesis
                "notes":               "",
            },
        }

        for sig_type in sig_types:
            if sig_type in candidates and len(candidates[sig_type]) < TARGET_PER_TYPE:
                candidates[sig_type].append(record)

        if all(len(v) >= TARGET_PER_TYPE for v in candidates.values()):
            break

    all_candidates = []
    if any(len(v) > 0 for v in candidates.values()):
        max_len = max(len(v) for v in candidates.values())
        for i in range(max_len):
            for sig_list in candidates.values():
                if i < len(sig_list):
                    all_candidates.append(sig_list[i])

    print(f"\n── Results ──────────────────────────────────────────────────────")
    print(f"  Single-turn (skipped):  {stats['single_turn']}")
    print(f"  Multi-turn (processed): {stats['multi_turn']}")
    print(f"  Multi-turn, no signal:  {stats['no_signal']}")
    for sig, lst in candidates.items():
        print(f"  {sig}: {len(lst)}")
    print(f"  Total candidates: {len(all_candidates)}")

    with open(OUT_FILE, "w") as f:
        json.dump(all_candidates, f, indent=2)
    print(f"\nSaved → {OUT_FILE}")

    if len(all_candidates) == 0:
        print("\n*** ZERO CANDIDATES — paste the Schema Diagnostic output for debugging ***")
    else:
        print("Next: python annotator_app.py")


if __name__ == "__main__":
    main()