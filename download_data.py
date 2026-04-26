"""
Step 1: Download lmarena-ai/arena-human-preference-140k and extract
candidate rows for implicit signal annotation.

Schema (140k — proper role/content dicts, no flat JSON strings):
  conversation_a/b : list of {role, content: [{type, text, image, mimeType}]}
  winner           : "model_a" | "model_b" | "tie" | "both_bad"
  category_tag     : dict with domain/complexity tags
  language         : "en", "pl", "de", etc.
  is_code          : bool
  timestamp        : datetime

Multi-turn gate: >= 4 user turns in conversation_a.
Only English conversations by default (set ENGLISH_ONLY=False to include all).

Run: python download_data.py
Output: data/arena_candidates.json
"""

import json, re
from pathlib import Path
from datasets import load_dataset
from tqdm import tqdm

OUT_DIR      = Path("data")
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE     = OUT_DIR / "arena_candidates.json"
ENGLISH_ONLY = True   # set False to include all languages
TARGET_PER_TYPE = 120

# ── Signal regexes ────────────────────────────────────────────────────────────

FRUSTRATION_RE = re.compile(
    r"\b(ugh|seriously\??|come on|that'?s not|still wrong|no[,!]? that|"
    r"again\??|wtf|what the|not what i|try again|wrong again|"
    r"you'?re not|doesn'?t work|didn'?t work|still not|that is not|"
    r"not right|you misunderstood|that('?s| is) wrong|"
    r"still not (right|correct|working)|not (what|how) i (asked|wanted|meant))\b",
    re.IGNORECASE,
)

ABANDONMENT_RE = re.compile(
    r"\b(forget it|never mind|nevermind|forget this|this is useless|"
    r"give up|doesn'?t matter|not worth|too hard|skip it|"
    r"don'?t bother|leave it|drop it|scrap it|just forget|"
    r"let'?s move on|moving on|can we just|start over)\b",
    re.IGNORECASE,
)

TOPIC_SHIFT_RE = re.compile(
    r"^(ok(ay)?[,.]?\s+)?(now[,]?\s+|next[,]?\s+|can you|could you|"
    r"what about|let'?s (try|do|move|talk)|instead[,]?\s|"
    r"actually[,]?\s|moving on|different (question|topic)|"
    r"switch(ing)? to|on a (different|another)|forget that[,]?\s)",
    re.IGNORECASE,
)

# ── Schema parsing ────────────────────────────────────────────────────────────

def extract_text(content) -> str:
    """
    content field is a list of {type, text, image, mimeType} blocks.
    Extract and join all text blocks.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                t = block.get("text") or block.get("content") or ""
                if t:
                    parts.append(str(t))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return str(content)


def parse_conversation(conv_raw) -> list:
    """
    Parse conversation_a or conversation_b into
    list of {"role": "user"|"assistant", "content": str}
    """
    if not conv_raw:
        return []
    turns = []
    for turn in conv_raw:
        if not isinstance(turn, dict):
            continue
        role    = (turn.get("role") or "").lower()
        content = extract_text(turn.get("content"))
        if role in ("user", "human"):
            turns.append({"role": "user", "content": content})
        elif role in ("assistant", "gpt", "model", "bot"):
            turns.append({"role": "assistant", "content": content})
    return turns


def get_user_turns(turns: list) -> list:
    return [t["content"] for t in turns if t["role"] == "user"]


def is_multi_turn(turns: list) -> bool:
    return len(get_user_turns(turns)) >= 4


def get_winner(row) -> str:
    w = (row.get("winner") or "").lower().replace(" ", "_")
    # normalise variants
    if w in ("both_bad", "tie (bothbad)", "bothbad"):
        return "both_bad"
    if w in ("tie", "tie (both good)", "both_good"):
        return "tie"
    if w in ("model_a", "a"):
        return "model_a"
    if w in ("model_b", "b"):
        return "model_b"
    return w


def infer_domain(row) -> str:
    """Use category_tag if available, else is_code flag."""
    cat = row.get("category_tag") or {}
    criteria = cat.get("criteria_v0.1") or {}
    if row.get("is_code"):
        return "coding"
    # heuristic from category tags
    if criteria.get("math"):
        return "mathematics"
    if criteria.get("creative_writing") or (cat.get("creative_writing_v0.1") or {}).get("creative_writing"):
        return "writing"
    if criteria.get("domain_knowledge") or criteria.get("problem_solving"):
        return "general_knowledge"
    return ""


# ── Signal detection ──────────────────────────────────────────────────────────

def detect_signals(turns_a: list, winner: str) -> list:
    """
    Returns list of signal dicts with rich metadata.
    turns_a: parsed conversation_a (full interleaved turns).
    """
    signals = []
    seen    = set()

    user_contents = get_user_turns(turns_a)
    followups     = user_contents[1:]

    def get_context(user_idx: int) -> str:
        """Get assistant turn just before user turn at user_idx."""
        # Walk backwards through turns_a to find it
        seen_users = 0
        for t in turns_a:
            if t["role"] == "user":
                if seen_users == user_idx:
                    break
                seen_users += 1
            elif t["role"] == "assistant" and seen_users == user_idx:
                return t["content"][:400]
        # simpler: assistant turn index = user_idx - 1 in interleaved
        asst_turns = [t["content"] for t in turns_a if t["role"] == "assistant"]
        idx = user_idx - 1
        return asst_turns[idx][:400] if 0 <= idx < len(asst_turns) else ""

    # turn number in full interleaved convo (1-indexed):
    # user turn i → position 2*i+1 (0-indexed user_idx → turn_number = 2*i+1+1)
    def turn_num(user_idx):
        return user_idx * 2 + 1  # user is always odd positions (1,3,5...)

    # ── Response Ignoring ─────────────────────────────────────────────────────
    if winner == "both_bad":
        u_idx = len(user_contents) - 1
        signals.append({
            "signal_type":      "response_ignoring",
            "turn_number":      turn_num(u_idx),
            "user_turn_number": u_idx + 1,
            "how_its_given":    "User voted both responses bad (both_bad winner)",
            "context":          get_context(u_idx),
            "user_msg_preview": user_contents[u_idx][:200],
        })
        seen.add("response_ignoring")

    for fu_idx, fu in enumerate(followups):
        if TOPIC_SHIFT_RE.match(fu.strip()) and "response_ignoring" not in seen:
            u_idx = fu_idx + 1
            signals.append({
                "signal_type":      "response_ignoring",
                "turn_number":      turn_num(u_idx),
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
                "turn_number":      turn_num(u_idx),
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
                    "turn_number":      turn_num(u_idx),
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
            "turn_number":      turn_num(u_idx),
            "user_turn_number": u_idx + 1,
            "how_its_given":    "Give-up language in final user message",
            "context":          get_context(u_idx),
            "user_msg_preview": user_contents[-1][:200],
        })
        seen.add("task_abandonment")

    return signals


# ── Diagnostic ────────────────────────────────────────────────────────────────

def diagnose_schema(ds, n=3):
    print("\n── Schema Diagnostic ─────────────────────────────────────────────")
    for i, row in enumerate(ds):
        if i >= n:
            break
        conv_a  = row.get("conversation_a") or []
        parsed  = parse_conversation(conv_a)
        u_turns = get_user_turns(parsed)
        print(f"\nRow {i}:")
        print(f"  id={row.get('id','')} | winner={row.get('winner')} | lang={row.get('language')} | is_code={row.get('is_code')}")
        print(f"  model_a={row.get('model_a')} | model_b={row.get('model_b')}")
        print(f"  conv_a turns: {len(conv_a)} raw → {len(parsed)} parsed → {len(u_turns)} user turns")
        if parsed:
            print(f"  parsed[0]: role={parsed[0]['role']} | content={repr(parsed[0]['content'][:120])}")
        if len(parsed) > 1:
            print(f"  parsed[1]: role={parsed[1]['role']} | content={repr(parsed[1]['content'][:120])}")
        domain = infer_domain(row)
        print(f"  inferred domain: {domain or '(unknown)'}")
    print("\n──────────────────────────────────────────────────────────────────\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading lmarena-ai/arena-human-preference-140k from HuggingFace...")
    ds = load_dataset("lmarena-ai/arena-human-preference-140k", split="train")
    print(f"  Total rows: {len(ds)}")

    diagnose_schema(ds, n=3)

    candidates = {
        "response_ignoring":  [],
        "frustration_marker": [],
        "task_abandonment":   [],
    }

    stats = {"skipped_lang": 0, "single_turn": 0, "multi_turn": 0, "no_signal": 0}

    print(f"Scanning (multi-turn ≥4, {'English only' if ENGLISH_ONLY else 'all languages'})...")
    for row in tqdm(ds):
        # Language filter
        if ENGLISH_ONLY and row.get("language", "en") != "en":
            stats["skipped_lang"] += 1
            continue

        turns_a = parse_conversation(row.get("conversation_a"))
        turns_b = parse_conversation(row.get("conversation_b"))

        if not is_multi_turn(turns_a):
            stats["single_turn"] += 1
            continue

        stats["multi_turn"] += 1
        winner  = get_winner(row)
        signals = detect_signals(turns_a, winner)

        if not signals:
            stats["no_signal"] += 1
            continue

        sig_types = list({s["signal_type"] for s in signals})
        priority  = ["response_ignoring", "frustration_marker", "task_abandonment"]
        primary   = next((s for p in priority for s in signals if s["signal_type"] == p), signals[0])
        domain    = infer_domain(row)

        record = {
            # ── Identity ──────────────────────────────────────────────────
            "question_id":        row.get("id", ""),
            "conv_id":            row.get("id", ""),
            "winner":             winner,
            "model_a":            row.get("model_a", ""),
            "model_b":            row.get("model_b", ""),
            # ── Auto-inferred columns ──────────────────────────────────────
            "turn":               primary["turn_number"],
            "feedback_type":      primary["signal_type"],
            "how_its_given":      primary["how_its_given"],
            "context":            primary["context"],
            "user_msg_preview":   primary["user_msg_preview"],
            # ── Metadata from dataset ──────────────────────────────────────
            "language":           row.get("language", ""),
            "is_code":            row.get("is_code", False),
            "timestamp":          str(row.get("timestamp", "")),
            "dataset_domain":     domain,
            # ── All signals ────────────────────────────────────────────────
            "detected_signals":   sig_types,
            "all_signal_details": signals,
            "num_user_turns":     len(get_user_turns(turns_a)),
            # ── Conversations (truncated for display) ──────────────────────
            "conversation_a": [
                {"role": t["role"], "content": t["content"][:1500]} for t in turns_a
            ],
            "conversation_b": [
                {"role": t["role"], "content": t["content"][:1500]} for t in turns_b
            ],
            # ── Annotator fields ───────────────────────────────────────────
            "annotation": {
                "confirmed_signal":    None,
                "confidence":          None,
                "task_domain":         domain or None,  # pre-fill from dataset
                "signal_evidence":     "",
                "what_is_updated":     "",
                "inferred_preference": "",
                "notes":               "",
            },
        }

        for sig_type in sig_types:
            if sig_type in candidates and len(candidates[sig_type]) < TARGET_PER_TYPE:
                candidates[sig_type].append(record)

        if all(len(v) >= TARGET_PER_TYPE for v in candidates.values()):
            break

    # Interleave signal types
    all_candidates = []
    if any(len(v) > 0 for v in candidates.values()):
        max_len = max(len(v) for v in candidates.values())
        for i in range(max_len):
            for sig_list in candidates.values():
                if i < len(sig_list):
                    all_candidates.append(sig_list[i])

    print(f"\n── Results ──────────────────────────────────────────────────────")
    print(f"  Skipped (non-English): {stats['skipped_lang']}")
    print(f"  Single-turn (skipped): {stats['single_turn']}")
    print(f"  Multi-turn processed:  {stats['multi_turn']}")
    print(f"  Multi-turn, no signal: {stats['no_signal']}")
    for sig, lst in candidates.items():
        print(f"  {sig}: {len(lst)}")
    print(f"  Total candidates:      {len(all_candidates)}")
    print(f"─────────────────────────────────────────────────────────────────")

    with open(OUT_FILE, "w") as f:
        json.dump(all_candidates, f, indent=2)
    print(f"\nSaved → {OUT_FILE}")

    if len(all_candidates) == 0:
        print("\n*** ZERO CANDIDATES — check Schema Diagnostic output above ***")
    else:
        print("Next: python annotator_app.py")


if __name__ == "__main__":
    main()