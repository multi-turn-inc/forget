from __future__ import annotations

import hashlib
import math
from functools import lru_cache
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .utils import CJK_CHAR_RE, STOPWORDS, parse_datetime, tokenize


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
COMPOUND_USER_CLAUSE_RE = re.compile(
    r"\s+(?:and|but)\s+(?=I\s+(?:am|work|teach|have|moved|just moved|live|prefer|like|love|avoid|use|want|need)\b)",
    re.IGNORECASE,
)
MEM0_COMPAT_MERGE_CATEGORIES = {"preferences", "travel", "health", "schedule"}
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
QUOTED_RE = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{2,80})[\"'“”‘’]")
PROPER_NOUN_RE = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,3})\b")
BRANDED_WORD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\b")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,8}\b")

KNOWN_LOCATIONS = {
    "austin",
    "berlin",
    "london",
    "new york",
    "new york city",
    "nyc",
    "paris",
    "san francisco",
    "seoul",
    "tokyo",
}

KNOWN_ORGANIZATIONS = {
    "anthropic",
    "amazon",
    "apple",
    "cloudflare",
    "hacker news",
    "hashicorp",
    "hn",
    "meta",
    "vercel",
    "y combinator",
    "yc",
    "github",
    "google",
    "microsoft",
    "openai",
}

KNOWN_TECHNOLOGIES = {
    "api",
    "ci",
    "cd",
    "dns",
    "docker",
    "e2ee",
    "graphql",
    "grpc",
    "ip",
    "jwt",
    "k8s",
    "kafka",
    "kubernetes",
    "launchd",
    "llm",
    "mcp",
    "mongodb",
    "mysql",
    "nginx",
    "oauth",
    "oss",
    "postgres",
    "postgresql",
    "prometheus",
    "redis",
    "s3",
    "sqlite",
    "systemd",
    "terraform",
    "tls",
    "vpn",
    "wal",
    "aceternity",
    "aceternity ui",
    "codex",
    "claim",
    "claims",
    "fontshare",
    "enacta",
    "fastapi",
    "gpu",
    "hyperui",
    "http",
    "javascript",
    "json",
    "ledger",
    "llm",
    "lora",
    "magic",
    "magic ui",
    "magicui",
    "mem0",
    "mem1",
    "mcp",
    "oauth",
    "observation",
    "observations",
    "playwright",
    "python",
    "react",
    "realtime colors",
    "runtime",
    "sdk",
    "sqlite",
    "typescript",
    "ui",
    "url",
    "vue",
}

KNOWN_TIMEZONES = {
    "kst",
    "utc",
}

ENTITY_SKIPWORDS = {
    "after",
    "assert",
    "current",
    "external",
    "fixed",
    "generated",
    "historical",
    "implemented",
    "new",
    "next",
    "noop",
    "ok",
    "pid",
    "pass",
    "public",
    "retract",
    "review",
    "shifted",
    "supersede",
    "toward",
    "verified",
    "we",
}

OPERATIONAL_ENTITY_PREFIXES = {
    "diagnostic",
    "engine",
    "evidence",
    "generated",
    "goal",
    "implemented",
    "product",
    "researched",
    "task",
    "verification",
}

KNOWN_FOOD = {
    "coffee",
    "jasmine tea",
    "shellfish",
    "sushi",
    "tea",
    "tiramisu",
}

KNOWN_HEALTH = {
    "allergy",
    "allergies",
    "dietary restriction",
    "medication",
    "shellfish allergy",
}

KNOWN_SCHEDULE = {
    "calendar",
    "meeting",
    "morning meetings",
    "planning meetings",
    "schedule",
}

QUERY_SYNONYMS = {
    "live": {"live", "lives", "living", "reside", "resides", "location", "city", "moved", "home"},
    "lives": {"live", "lives", "living", "reside", "resides", "location", "city", "moved", "home"},
    "where": {"location", "city", "home", "moved"},
    "dietary": {"dietary", "food", "allergy", "allergies", "shellfish", "vegetarian", "vegan"},
    "food": {"food", "dietary", "allergy", "allergies", "shellfish", "avoid", "avoids"},
    "avoid": {"avoid", "avoids", "avoided", "dietary", "shellfish"},
    "avoided": {"avoid", "avoids", "avoided", "dietary", "shellfish"},
    "hobbies": {"hobby", "hobbies", "likes", "loves", "enjoys", "weekends"},
    "work": {"work", "job", "role", "company", "team", "project"},
    "meeting": {"meeting", "calendar", "schedule", "availability", "morning", "afternoon"},
}


CATEGORY_KEYWORDS = {
    "location": {"moved", "city", "location", "lives", "address", "san", "new york", "austin", "seoul"},
    "preferences": {"prefer", "prefers", "like", "likes", "love", "loves", "favorite", "avoid"},
    "work": {"work", "job", "team", "project", "company", "engineer", "developer", "stack"},
    "education": {"teach", "teacher", "student", "school", "algebra", "learn", "study"},
    "health": {"allergy", "allergies", "dietary", "medication", "shellfish", "vegan"},
    "finance": {"budget", "finance", "financial", "invoice", "pricing", "cost"},
    "travel": {"travel", "hotel", "flight", "itinerary", "concierge", "boutique"},
    "schedule": {"meeting", "calendar", "schedule", "morning", "afternoon", "timezone"},
    "technology": {"python", "typescript", "fastapi", "react", "database", "api", "agent"},
}


# 인용쌍은 원자다 (#2): 여는 따옴표와 닫는 따옴표 사이에서는 문장 경계를 내지 않는다.
# 직선 큰따옴표는 패리티로, 방향 있는 쌍(“” 「」 『』)은 깊이로 추적한다.
# 직선 작은따옴표는 아포스트로피(don't)와 구분이 불가능해 의도적으로 제외.
_QUOTE_OPENERS = {"\u201c": "\u201d", "\u300c": "\u300d", "\u300e": "\u300f"}
_QUOTE_CLOSERS = {v: k for k, v in _QUOTE_OPENERS.items()}


def _split_outside_quotes(text: str) -> list[str]:
    parts: list[str] = []
    last = 0
    straight = 0
    depth = 0
    scanned = 0
    for match in SENTENCE_RE.finditer(text):
        for ch in text[scanned:match.start()]:
            if ch == '"':
                straight ^= 1
            elif ch in _QUOTE_OPENERS:
                depth += 1
            elif ch in _QUOTE_CLOSERS and depth > 0:
                depth -= 1
        scanned = match.start()
        if straight == 0 and depth == 0:
            parts.append(text[last:match.start()])
            last = match.end()
            scanned = match.end()
    parts.append(text[last:])
    return parts


def split_sentences(text: str) -> list[str]:
    parts = [p.strip(" \t\r\n\"'") for p in _split_outside_quotes(text or "")]
    return [p for p in parts if len(p) > 1]


def normalize_fact(sentence: str, role: str = "user", speaker: str | None = None) -> str:
    text = re.sub(r"\s+", " ", sentence.strip())
    if not text:
        return text
    speaker_name = re.sub(r"\s+", " ", str(speaker or "").strip())
    subject = speaker_name or "User"
    possessive = f"{subject}'" if subject.endswith("s") else f"{subject}'s"
    replacements = [
        (r"^i am\s+", f"{subject} is "),
        (r"^i'm\s+", f"{subject} is "),
        (r"^i work\s+", f"{subject} works "),
        (r"^i teach\s+", f"{subject} teaches "),
        (r"^i have\s+", f"{subject} has "),
        (r"^i moved\s+", f"{subject} moved "),
        (r"^i just moved\s+", f"{subject} just moved "),
        (r"^i live\s+", f"{subject} lives "),
        (r"^i prefer\s+", f"{subject} prefers "),
        (r"^i want\s+", f"{subject} wants "),
        (r"^i need\s+", f"{subject} needs "),
        (r"^i use\s+", f"{subject} uses "),
        (r"^i like\s+", f"{subject} likes "),
        (r"^i love\s+", f"{subject} loves "),
        (r"^i avoid\s+", f"{subject} avoids "),
        (r"^my ([a-zA-Z0-9_ -]+) is\s+", rf"{possessive} \1 is "),
        (r"^we are\s+", f"{possessive} team is "),
        (r"^we use\s+", f"{possessive} team uses "),
    ]
    lowered = text.lower()
    for pattern, repl in replacements:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            normalized = re.sub(pattern, repl, text, count=1, flags=re.IGNORECASE)
            return normalize_conjunctions(normalized)
    if CJK_CHAR_RE.search(text):
        # A sentence containing Hangul/CJK anywhere (English first-person
        # patterns were already handled above) is treated as Korean — a
        # Korean sentence that merely starts with a latin word like
        # "codex 훅은..." must not fall through to the "User said:" wrapper.
        # Korean first-person normalization, mirroring the English rules.
        subject_ko = speaker_name or "사용자"
        ko_replacements = [
            (r"^(?:저는|나는|전|난)\s*", f"{subject_ko}는 "),
            (r"^(?:제|저의|나의|내)\s+", f"{subject_ko}의 "),
            (r"^우리(?:는|가)\s*", f"{subject_ko} 팀은 "),
        ]
        for pattern, repl in ko_replacements:
            if re.search(pattern, text):
                return re.sub(pattern, repl, text, count=1)
        # Caseless scripts can't pass the isupper() gate below; a Korean
        # sentence is already a well-formed fact, so store it verbatim
        # instead of wrapping it in the "User said:" fallback.
        return text
    if speaker_name and not lowered.startswith((speaker_name.lower(), "user ", "customer ")):
        return f"{speaker_name} said: {text}"
    if role == "assistant":
        return text
    if text[:1].isupper() and not lowered.startswith(("user ", "customer ", "alice ", "bob ")):
        return text
    return f"User said: {text}"


def normalize_conjunctions(text: str) -> str:
    replacements = {
        "avoid": "avoids",
        "prefer": "prefers",
        "want": "wants",
        "need": "needs",
        "like": "likes",
        "love": "loves",
        "have": "has",
        "teach": "teaches",
        "work": "works",
        "live": "lives",
        "use": "uses",
    }
    normalized = text
    for source, target in replacements.items():
        normalized = re.sub(rf"\band i {source}\b", f"and {target}", normalized, flags=re.IGNORECASE)
        normalized = re.sub(rf"\band {source}\b", f"and {target}", normalized, flags=re.IGNORECASE)
    return normalized


def _categories_for_text(text: str) -> set[str]:
    return set(categorize(text)) - {"general"}


def _mem0_compat_should_keep_compound_sentence(text: str, clauses: list[str]) -> bool:
    if len(clauses) < 2:
        return False
    lowered = text.lower()
    if " and i " not in lowered:
        return False
    clause_categories = [_categories_for_text(normalize_fact(clause)) for clause in clauses]
    if not clause_categories or any(not categories for categories in clause_categories):
        return False
    shared = set.intersection(*clause_categories)
    return bool(shared.intersection(MEM0_COMPAT_MERGE_CATEGORIES))


def split_memory_clauses(sentence: str, role: str = "user", extraction_policy: str | None = None) -> list[str]:
    text = re.sub(r"\s+", " ", str(sentence or "").strip())
    if not text:
        return []
    if str(role).lower() == "assistant":
        return [text]
    clauses = [part.strip(" ,;") for part in COMPOUND_USER_CLAUSE_RE.split(text)]
    clauses = [clause for clause in clauses if clause]
    if str(extraction_policy or "").lower() in {"mem0_compat", "mem0-compatible", "mem0_observed"}:
        if _mem0_compat_should_keep_compound_sentence(text, clauses):
            return [text]
    return clauses


def message_content_text(content: Any) -> str:
    """Normalize Mem0-style message content to plain text.

    Supports plain strings and multimodal content-part lists such as
    ``[{"type": "text", "text": ...}, {"type": "image_url", ...}]``. Non-text
    parts become explicit ``[image]``/``[document]`` markers instead of being
    stringified into repr noise or silently dropped.
    """
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, dict):
        return _content_part_text(content)
    if isinstance(content, list):
        parts = [_content_part_text(item) if isinstance(item, dict) else str(item) for item in content if item is not None]
        return "\n".join(part for part in parts if part)
    return str(content)


def _content_part_text(part: dict[str, Any]) -> str:
    text = part.get("text") or part.get("content")
    if isinstance(text, str) and text.strip():
        return text
    part_type = str(part.get("type") or "").lower()
    keys = {str(key).lower() for key in part.keys()}
    if "image" in part_type or keys.intersection({"image", "image_url"}):
        return "[image]"
    if part_type in {"document", "doc_url", "pdf_url", "mdx_url", "file", "file_url", "audio_url"} or keys.intersection(
        {"document", "doc_url", "pdf_url", "mdx_url", "file", "file_url", "audio_url"}
    ):
        return "[document]"
    return ""


def keyword_overlap_score(query: str, text: str) -> float:
    """Deterministic keyword overlap: fraction of query tokens present in text."""
    query_tokens = {token for token in tokenize(str(query or "")) if token not in STOPWORDS}
    if not query_tokens:
        return 0.0
    text_tokens = set(tokenize(str(text or "")))
    return round(len(query_tokens.intersection(text_tokens)) / len(query_tokens), 4)


_SECRET_RUN_RE = re.compile(r"[A-Za-z0-9_\-]{40,}")
_RAW_EVENT_RE = re.compile(r'"type"\s*:\s*"?(event_msg|response_item|token_count|function_call)')
# Serialized agent-session shards: fragments of rollout/report JSON that leak
# through clients as "memories" (observed in the dogfood corpus 2026-07-07 —
# final-answer echoes, rollout ids, citation structures, truncated key:value
# runs). A real durable fact never contains these markers.
_SESSION_SHARD_RE = re.compile(
    r'"(phase|rolloutIds|memory_citation|final_answer|turn_id|output_text|input_text'
    r'|model_context_window|total_tokens|rate_limits?)"\s*[:\]}]'
)

# Default ceiling for an auto-captured "memory". A durable fact is a
# sentence, not a transcript page; anything longer is almost always a raw
# dump. Callers can override via the sanitize options.
LOW_VALUE_MAX_CHARS = 600


def low_value_memory_reason(text: str, max_chars: int = LOW_VALUE_MAX_CHARS) -> str:
    """Classify why a candidate memory is low-value, or '' if it is fine.

    Pure and side-effect free so it can be unit-tested and reused by both the
    server sanitize path and the corpus-cleanup migration. Tuned against the
    real dogfood corpus taxonomy (raw JSON events, transcript tails,
    key-like strings, oversize dumps).
    """
    stripped = (text or "").strip()
    if not stripped:
        return "empty"
    if len(stripped) > max_chars:
        return "oversize"
    if stripped.startswith(("Session transcript tail", "User said: {", "User said: [")):
        return "transcript_or_raw"
    if '"payload"' in stripped or _RAW_EVENT_RE.search(stripped):
        return "raw_json_event"
    if _SESSION_SHARD_RE.search(stripped):
        return "session_shard"
    if _SECRET_RUN_RE.search(stripped):
        # 40+ unbroken alphanumerics: API keys, JWT fragments, base64 blobs.
        # Real prose breaks on spaces/punctuation well before this.
        return "secret_like"
    return ""


_CJK_ANAPHOR_RE = re.compile(r"^(?:이|그|해당|위|이는|이것|그것|이걸|그걸|여기|거기)[\s은는이가을를의도]")


def _merge_cjk_fragments(sentences: list[str]) -> list[str]:
    # CJK follow-up sentences lose their subject when split from the
    # preceding sentence and become meaningless orphan facts. Two cases keep
    # them attached to the sentence that carries the context: short fragments
    # ("Stripe가 아닙니다.") and anaphor-initial sentences ("이 스크립트가
    # env를 소싱합니다.") whose referent lives in the previous sentence.
    merged: list[str] = []
    for sentence in sentences:
        anaphoric = bool(_CJK_ANAPHOR_RE.match(sentence)) and len(sentence) <= 80
        if (
            merged
            and (len(sentence) <= 14 or anaphoric)
            and CJK_CHAR_RE.search(sentence)
            and CJK_CHAR_RE.search(merged[-1])
        ):
            merged[-1] = f"{merged[-1]} {sentence}"
        else:
            merged.append(sentence)
    return merged


# --- observation gate -------------------------------------------------------
# A memory is an observation about the USER's durable state, not an echo of
# the assistant's knowledge. Measured on the STALE diag corpus (2026-07-07),
# the ungated splitter stored 85% assistant content — advice, listicles,
# recommendations — which drowned the ~15% of rows that carry actual user
# state and polluted every embedding neighborhood downstream (search, stale
# siblings, temporal promotion). The gate keeps assistant sentences only in
# the narrow register that RECORDS user state, and drops user sentences that
# are pure acknowledgment. Kill switch: MEM1_OBSERVATION_GATE=0.

_ASSISTANT_LISTY_RE = re.compile(r"^\s*(\*|-|\d+\.|#|\*\*)")
_ASSISTANT_ADVICE_RE = re.compile(
    r"^(remember|consider|try|make sure|keep|start|use|check|ensure|avoid|take|look|visit|give|add|focus"
    r"|research|be |don'?t|feel free|note that|also,|additionally|alternatively|here (are|is)|below"
    r"|these |this (can|will|helps)|it'?s (a good|worth|important))",
    re.IGNORECASE,
)
_ASSISTANT_SECOND_PERSON_ADVICE_RE = re.compile(
    r"\b(you can|you could|you might|you may|you should|you'?ll want|you'?ll be|if you|would you|do you"
    r"|help you|for you to)\b",
    re.IGNORECASE,
)
_ASSISTANT_STATE_RECORD_RE = re.compile(
    r"\b(your \w+ (is|are|was|were)|you (said|mentioned|told|decided|chose|prefer|live|work|moved|booked"
    r"|have booked|are (now|currently))|i'?ve (noted|recorded|updated|saved|logged))\b",
    re.IGNORECASE,
)
_USER_SMALLTALK_RE = re.compile(
    r"^(that sounds|sounds |happy |great|awesome|perfect|cool|okay|ok\b|thanks|thank you|good luck"
    r"|enjoy|nice|wonderful|amazing)\W*",
    re.IGNORECASE,
)
# KO acknowledgments drop only when the WHOLE sentence is a bare go-ahead
# ("좋아.", "진행하자", "응 고고") — prefix matching would eat content-bearing
# short answers ("응, 서버는 4090이야"), so this is a fullmatch over ack words.
_USER_KO_ACK_WORD = r"(좋아|좋습니다|좋네요?|응|넵|알겠어요?|알겠습니다|그래|그렇게 해|맞아|맞습니다|고마워요?|감사합니다|진행하자|진행해줘?|해줘|가자|고고|오케이|콜)"
_USER_KO_ACK_RE = re.compile(rf"^(?:{_USER_KO_ACK_WORD}[\s,.!?~]*){{1,3}}$")


def observation_gate_enabled() -> bool:
    return (os.getenv("MEM1_OBSERVATION_GATE") or "1").strip().lower() not in {"0", "false", "no"}


def _assistant_sentence_records_user_state(sentence: str) -> bool:
    """Keep an assistant sentence only when it records the user's state.

    Default is drop: assistant prose is overwhelmingly advice and knowledge
    dumps, which are not durable facts about the user. The state-record check
    runs before the advice patterns because record sentences often embed
    advisory phrasing around the recorded fact ("since you mentioned you
    don't have debt, we can start by...").
    """
    if _ASSISTANT_LISTY_RE.match(sentence):
        return False
    if sentence.rstrip().endswith("?"):
        return False
    if _ASSISTANT_STATE_RECORD_RE.search(sentence):
        return True
    return False


def _user_sentence_is_smalltalk(sentence: str) -> bool:
    """Drop pure acknowledgment ("That sounds great!", "Thanks!").

    Deliberately conservative — user sentences carry the product's recall, so
    only short, unambiguous pleasantries go."""
    if _USER_KO_ACK_RE.match(sentence.strip()):
        return True
    words = sentence.split()
    if len(words) <= 5 and (sentence.rstrip().endswith("!") or _USER_SMALLTALK_RE.match(sentence)):
        return True
    return bool(_USER_SMALLTALK_RE.match(sentence)) and len(words) <= 8


def extract_memories(
    messages: list[dict[str, Any]],
    infer: bool = True,
    extraction_policy: str | None = None,
    assistant_is_subject: bool = False,
    gate_log: list[dict[str, Any]] | None = None,
    accounting: dict[str, Any] | None = None,
) -> list[str]:
    facts: list[str] = []
    gate = observation_gate_enabled()

    def _count(key: str, n: int = 1) -> None:
        # F5 침묵 잊음: every path that loses input leaves a number. The gate
        # log carries the *content* of refusals; these counters carry the
        # *denominator* — store.add_accounting_violations checks conservation.
        if accounting is not None:
            accounting[key] = accounting.get(key, 0) + n

    def _log_drop(text: str, role: str, reason: str) -> None:
        # The gate is an editor, and editors are power: what was dropped and
        # why must stay auditable ("잊은 것의 목록조차 네 것이어야 한다").
        if gate_log is not None:
            gate_log.append({"text": text.strip()[:300], "role": role, "reason": reason})
    for message in messages:
        _count("messages_in")
        role = str(message.get("role", "user"))
        speaker = str(message.get("name", "")).strip() or None
        content = message_content_text(message.get("content")).strip()
        if not content:
            _count("empty_messages")
            continue
        if not infer:
            facts.append(f"{speaker} said: {content}" if speaker else content)
            _count("facts_raw")
            continue
        if role == "assistant":
            lowered = content.lower()
            if lowered.startswith(("got it", "logged", "i'll", "i will", "thanks", "sure")):
                _log_drop(content, role, "assistant_ack")
                _count("ack_messages_dropped")
                continue
        for sentence in _merge_cjk_fragments(split_sentences(content)):
            _count("sentences_seen")
            if len(sentence.split()) < 3 and role == "assistant":
                _count("fragments_dropped")
                continue
            # a NAMED assistant (chat participant) or an agent-scoped add
            # (assistant_is_subject) speaks AS the observed entity — the gate
            # only targets the anonymous answering model's knowledge dumps
            if (
                gate
                and role == "assistant"
                and not speaker
                and not assistant_is_subject
                and not _assistant_sentence_records_user_state(sentence)
            ):
                _log_drop(sentence, role, "assistant_advice_or_knowledge")
                _count("gate_dropped")
                continue
            if gate and role == "user" and _user_sentence_is_smalltalk(sentence):
                _log_drop(sentence, role, "user_smalltalk")
                _count("gate_dropped")
                continue
            for clause in split_memory_clauses(sentence, role=role, extraction_policy=extraction_policy):
                if len(clause.split()) < 3 and role == "assistant":
                    _count("fragments_dropped")
                    continue
                facts.append(normalize_fact(clause, role=role, speaker=speaker))
                _count("facts_raw")
    seen: set[str] = set()
    unique: list[str] = []
    for fact in facts:
        key = fact.lower()
        if key not in seen:
            seen.add(key)
            unique.append(fact)
    _count("batch_deduped", len(facts) - len(unique))
    _count("facts_extracted", len(unique))
    return unique


def categorize(text: str, metadata: dict[str, Any] | None = None) -> list[str]:
    metadata = metadata or {}
    explicit = metadata.get("categories") or metadata.get("category")
    values: list[str] = []
    if isinstance(explicit, str):
        values.extend([v.strip() for v in explicit.split(",") if v.strip()])
    elif isinstance(explicit, list):
        values.extend([str(v).strip() for v in explicit if str(v).strip()])
    lowered = text.lower()
    tokens = set(tokenize(text))
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords) or tokens.intersection(keywords):
            values.append(category)
    if not values:
        values.append("general")
    deduped: list[str] = []
    for value in values:
        normalized = value.lower().replace(" ", "_")
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


@lru_cache(maxsize=32768)
def expanded_tokens(text: str) -> frozenset[str]:
    """Tokenization dominates search latency when recomputed per row per
    query (M5 profile: ~26% of a 1.1s search). Memory texts and the query
    string repeat massively across calls — cache them. Frozenset: every
    caller does read-only set algebra."""
    base = set(tokenize(text))
    expanded = set(base)
    for token in list(base):
        expanded.update(QUERY_SYNONYMS.get(token, set()))
    return frozenset(t for t in expanded if t not in STOPWORDS)


def score_memory(query: str, memory: dict[str, Any], reference_date: Any = None) -> float:
    q_tokens = expanded_tokens(query)
    m_tokens = expanded_tokens(str(memory.get("memory", "")))
    if not q_tokens:
        return 1.0

    overlap = len(q_tokens.intersection(m_tokens))
    union = len(q_tokens.union(m_tokens)) or 1
    jaccard = overlap / union
    coverage = overlap / len(q_tokens)
    phrase_bonus = 0.0
    lowered_memory = str(memory.get("memory", "")).lower()
    lowered_query = query.lower()
    for token in q_tokens:
        if token in lowered_memory:
            phrase_bonus += 0.02
    if lowered_query and lowered_query in lowered_memory:
        phrase_bonus += 0.25
    categories = {str(c).lower() for c in memory.get("categories", [])}
    category_bonus = 0.12 if q_tokens.intersection(categories) else 0.0

    recency_bonus = 0.0
    anchor = parse_datetime(reference_date) or datetime.now(timezone.utc)
    updated = parse_datetime(memory.get("updated_at"))
    if updated:
        age_days = max((anchor - updated).total_seconds() / 86400, 0)
        recency_bonus = 0.08 * math.exp(-age_days / 60)

    score = (0.45 * coverage) + (0.35 * jaccard) + phrase_bonus + category_bonus + recency_bonus
    score += temporal_bonus(query, memory, reference_date)
    return max(0.0, min(1.0, round(score, 4)))


def dates_in_text(text: str) -> list[datetime]:
    dates: list[datetime] = []
    for match in DATE_RE.findall(text or ""):
        parsed = parse_datetime(match)
        if parsed:
            dates.append(parsed)
    return dates


def temporal_bonus(query: str, memory: dict[str, Any], reference_date: Any = None) -> float:
    tokens = set(tokenize(query))
    lowered_query = query.lower()
    lowered_memory = str(memory.get("memory", "")).lower()
    anchor = parse_datetime(reference_date) or datetime.now(timezone.utc)
    dates = dates_in_text(str(memory.get("memory", "")))
    bonus = 0.0

    if {"upcoming", "future", "next", "tomorrow", "soon"}.intersection(tokens):
        if any(date.date() >= anchor.date() for date in dates) or any(word in lowered_memory for word in ("upcoming", "tomorrow", "next ")):
            bonus += 0.24
        elif dates and all(date.date() < anchor.date() for date in dates):
            bonus -= 0.08

    if {"past", "previous", "earlier", "old"}.intersection(tokens) or "last year" in lowered_query:
        if any(date.date() < anchor.date() for date in dates) or any(word in lowered_memory for word in ("previous", "earlier", "last year")):
            bonus += 0.18

    if {"latest", "recent", "recently"}.intersection(tokens):
        updated = parse_datetime(memory.get("updated_at"))
        if updated:
            age_days = max((anchor - updated).total_seconds() / 86400, 0)
            bonus += 0.18 * math.exp(-age_days / 14)

    if "today" in tokens and any(date.date() == anchor.date() for date in dates):
        bonus += 0.22
    if "tomorrow" in tokens and any(date.date() == (anchor + timedelta(days=1)).date() for date in dates):
        bonus += 0.22
    if "yesterday" in tokens and any(date.date() == (anchor - timedelta(days=1)).date() for date in dates):
        bonus += 0.22

    return bonus


def rerank_score(query: str, memory: dict[str, Any], base_score: float, reference_date: Any = None) -> float:
    q_tokens = expanded_tokens(query)
    m_tokens = expanded_tokens(str(memory.get("memory", "")))
    if not q_tokens:
        return base_score
    exact_coverage = len(q_tokens.intersection(m_tokens)) / len(q_tokens)
    categories = {str(c).lower() for c in memory.get("categories", [])}
    category_overlap = 0.08 if q_tokens.intersection(categories) else 0.0
    temporal = temporal_bonus(query, memory, reference_date)
    reranked = (base_score * 0.72) + (exact_coverage * 0.2) + category_overlap + (temporal * 0.25)
    return max(0.0, min(1.0, round(reranked, 4)))


def deterministic_embedding(text: str, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    tokens = tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for offset in range(0, 8, 2):
            index = int.from_bytes(digest[offset : offset + 2], "big") % dimensions
            sign = 1.0 if digest[offset] % 2 == 0 else -1.0
            vector[index] += sign
        for synonym in QUERY_SYNONYMS.get(token, set()):
            digest = hashlib.sha256(synonym.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % dimensions
            vector[index] += 0.35
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) != len(right):
        # Vectors from different embedding spaces carry no comparable signal.
        # Truncating to min(len) yields near-neutral noise that lands ~0.5 on
        # the (cos+1)/2 scale — above the 0.45 recall gate — so mismatches are
        # rejected outright instead of silently scored.
        return 0.0
    size = len(left)
    dot = sum(left[i] * right[i] for i in range(size))
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return max(0.0, min(1.0, round((dot / (left_norm * right_norm) + 1.0) / 2.0, 4)))


def normalize_entity(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).strip(" .,:;!?\"'")


_KO_TECH_CONTEXT = (
    "데이터베이스", "스택", "서버", "배포", "프레임워크", "캐시", "인프라",
    "빌드", "저장소", "백엔드", "프론트", "로그", "코드", "라이브러리",
)


def classify_entity(raw: str, base_type: str, text: str) -> tuple[str, float]:
    normalized = normalize_entity(raw)
    lowered_text = f" {text.lower()} "
    tokens = set(tokenize(raw))
    context_tokens = set(tokenize(text))

    if normalized in KNOWN_LOCATIONS:
        return "location", 0.94
    if normalized in KNOWN_ORGANIZATIONS:
        return "organization", 0.93
    if normalized in KNOWN_TECHNOLOGIES or tokens.intersection(KNOWN_TECHNOLOGIES):
        return "technology", 0.9
    if normalized in KNOWN_TIMEZONES:
        return "timezone", 0.86
    if normalized in KNOWN_HEALTH or "allergy" in context_tokens or "dietary" in context_tokens:
        if normalized in {"shellfish", "medication"} or normalized in KNOWN_HEALTH:
            return "health", 0.9
    if normalized in KNOWN_FOOD:
        return "food", 0.88
    if normalized in KNOWN_SCHEDULE or context_tokens.intersection({"meeting", "meetings", "calendar", "schedule"}):
        if normalized in KNOWN_SCHEDULE or any(token in normalized for token in ("meeting", "calendar", "schedule")):
            return "schedule", 0.84

    if any(phrase in lowered_text for phrase in (f" in {normalized} ", f" to {normalized} ", f" from {normalized} ")):
        if base_type in {"proper_noun", "acronym"}:
            return "location", 0.86
    if any(word in context_tokens for word in ("company", "organization", "org", "research", "team")) and base_type in {"proper_noun", "acronym"}:
        if normalized not in {"user", "alice", "bob"}:
            return "organization", 0.78
    if (
        any(word in context_tokens for word in ("prefers", "likes", "loves", "uses", "stack", "database", "framework"))
        or any(kw in text for kw in _KO_TECH_CONTEXT)
    ):
        if normalized in KNOWN_TECHNOLOGIES or base_type == "acronym":
            return "technology", 0.82
    if not any(ch.islower() for ch in raw) and 2 <= len(normalized) <= 6:
        # 전부 대문자인 짧은 토큰(IP, CI, E2EE, WAL …)은 사람이 아니다 (#1)
        return "acronym", 0.7
    if base_type == "proper_noun" and " " not in normalized and normalized not in KNOWN_LOCATIONS:
        return "person", 0.62
    if base_type == "quoted_text":
        return "quoted_text", 0.9
    if base_type == "acronym":
        return "acronym", 0.78
    return "concept", 0.58


def extract_linked_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(raw: str, entity_type: str, confidence: float) -> None:
        entity = re.sub(r"\s+", " ", raw.strip(" .,:;!?\"'"))
        normalized = normalize_entity(entity)
        normalized_parts = normalized.split()
        if not normalized or normalized in seen or normalized in STOPWORDS or normalized in ENTITY_SKIPWORDS or len(normalized) < 2:
            return
        if normalized_parts and normalized_parts[0] in OPERATIONAL_ENTITY_PREFIXES:
            return
        classified_type, classified_confidence = classify_entity(entity, entity_type, text or "")
        seen.add(normalized)
        entities.append(
            {
                "entity": entity,
                "normalized_entity": normalized,
                "entity_type": classified_type,
                "confidence": classified_confidence if classified_type == "person" else max(confidence, classified_confidence),
            }
        )

    for quoted in QUOTED_RE.findall(text or ""):
        add(quoted, "quoted_text", 0.95)

    for match in PROPER_NOUN_RE.findall(text or ""):
        if match.lower() in {"user", "i"}:
            continue
        add(match, "proper_noun", 0.9)

    for match in BRANDED_WORD_RE.findall(text or ""):
        add(match, "proper_noun", 0.88)

    for match in ACRONYM_RE.findall(text or ""):
        add(match, "acronym", 0.85)

    tokens = tokenize(text)
    known_terms = KNOWN_LOCATIONS | KNOWN_ORGANIZATIONS | KNOWN_TECHNOLOGIES | KNOWN_FOOD | KNOWN_HEALTH | KNOWN_SCHEDULE
    for token in tokens:
        if token in known_terms:
            add(token, "concept", 0.72)

    for i in range(len(tokens) - 1):
        phrase = " ".join(tokens[i : i + 2])
        if phrase not in known_terms:
            continue
        if any(part.isdigit() for part in phrase.split()):
            continue
        if any(part in STOPWORDS or part in ENTITY_SKIPWORDS for part in phrase.split()):
            continue
        if any(part in KNOWN_TECHNOLOGIES or part in KNOWN_ORGANIZATIONS or part in KNOWN_TIMEZONES for part in phrase.split()):
            continue
        add(phrase, "concept", 0.55)
    return entities[:20]
