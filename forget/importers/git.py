"""Mine decision-shaped memories from a git repository's history.

A repo's history is a memory store that arrives already full: every
"switched X to Y because Z" commit is a decision with a receipt. This
importer extracts those into forget memories with commit provenance, so
"why did we choose X?" gets an answer that links back to the moment it
was decided.

v0 reads commit messages only; PR discussions and agent sessions are the
next sources. Extraction is rule-based, same philosophy as the engine's
observation gate: precision over recall — a missed decision costs little,
a store full of "fix typo" noise costs the product.

Usage:
    python -m forget.importers.git /path/to/repo --user-id me [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

FIELD_SEP = "\x1f"
COMMIT_SEP = "\x1e"

# Verbs that mark a commit as a decision rather than routine motion.
DECISION_PATTERN = re.compile(
    r"\b("
    r"switch(?:ed|es)?|migrat(?:e|ed|es|ion)|adopt(?:ed|s)?|replac(?:e|ed|es)|"
    r"drop(?:ped|s)?|deprecat(?:e|ed|es)|remove(?:d|s)? support|"
    r"renam(?:e|ed|es)|cho(?:o)?se(?:n)?|chose|settle(?:d)? on|"
    r"default(?:s)? to|instead of|rather than|revert(?:ed|s)?|"
    r"introduc(?:e|ed|es)(?!\s+by)|standardiz(?:e|ed|es)|pin(?:ned)? to|"
    r"mov(?:e|ed|es) (?:to|from|off|behind)|flip(?:ped|s)?|"
    r"opt(?:ed)?[ -](?:in|out|for)|disabl(?:e|ed|es) .+ by default|"
    r"enabl(?:e|ed|es) .+ by default|works? without|no longer|"
    r"now (?:targets?|uses?|defaults?|requires?)|lead with|"
    r"fold(?:ed|s)? .{0,40}into|merg(?:e|ed|es) .{0,40}into"
    r")\b",
    re.IGNORECASE,
)

# "old-name -> new-name" subjects are rename/replacement decisions —
# except version bumps ("v0.7.0 -> v0.7.1"), which are motion, not choice.
ARROW_PATTERN = re.compile(r"(\S+)\s*(?:->|→)\s*(\S+)")
VERSION_TOKEN = re.compile(r"^v?\d+(?:[.\-][\w]+)*[,.):\]]*$")

# Automation authors never make decisions worth remembering. The 2026-07-13
# external-repo audit found pre-commit.ci autoupdates were the single
# largest noise source (5 of 20 sampled fastapi "decisions").
BOT_AUTHOR = re.compile(r"\[bot\]|pre-commit|dependabot|renovate|github-actions", re.IGNORECASE)

# "Rename bstate to bpop" / "last_vote_epoch -> lastVoteEpoch." — a bare
# rename with no reason is refactoring motion; renames earn a memory only
# with context around them.
BARE_RENAME = re.compile(
    r"^(?:rename[sd]?\s+\S+\s+to\s+\S+|\S+\s*(?:->|→)\s*\S+)[.,]?$", re.IGNORECASE
)

# "engine:", "feat(scope):", "docs:" — context labels, not content.
CONVENTIONAL_PREFIX = re.compile(r"^[a-z][\w-]*(?:\([^)]*\))?!?:\s*", re.IGNORECASE)

# Routine motion that never carries a decision worth remembering.
# Translation/doc-sync churn dominates docs-heavy repos (fastapi audit:
# 8 of 20 sampled "decisions" were translation commits).
SKIP_PATTERN = re.compile(
    r"^(fix(?:up)?|typo|fmt|format|lint|whitespace|style|chore|wip|merge|"
    r"bump version|release v?\d|update changelog|update readme|"
    r"sync \S+ docs)\b|\btranslations?\b|\bi18n\b",
    re.IGNORECASE,
)

# Leading gitmoji/emoji are labels, not content — strip before any match
# (":memo: Fix typo" and "✏️ Fix typo" must hit the skip list).
LEADING_EMOJI = re.compile(r"^(?::\w+:|[^\w\s\"'`(\[])+\s*")

REASON_PATTERN = re.compile(
    r"(?:because|since|so that|reason:|why:)\s+(.{10,240}?)(?:\.\s|\.$|\n|$)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class Decision:
    sha: str
    author: str
    date: str  # ISO 8601, commit author date
    text: str  # the memory body


def _first_sentence(text: str, limit: int = 240) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit].rstrip()


def _meaningful_arrow(text: str) -> bool:
    return any(
        not (VERSION_TOKEN.match(match.group(1)) and VERSION_TOKEN.match(match.group(2)))
        for match in ARROW_PATTERN.finditer(text)
    )


def _is_decision(text: str) -> bool:
    return bool(DECISION_PATTERN.search(text)) or _meaningful_arrow(text)


def _first_decision_sentence(body: str) -> str | None:
    for line in re.split(r"(?<=[.!?])\s+|\n", body or ""):
        line = line.strip()
        if len(line) >= 15 and _is_decision(line) and not SKIP_PATTERN.search(line):
            return _first_sentence(line)
    return None


def extract_decision(subject: str, body: str) -> str | None:
    """Return the memory text for a decision-shaped commit, else None.

    Real-world subjects hide decisions behind "engine:"-style labels and
    push the actual choice into the body — so a non-decision subject gets
    one chance: its body's first decision-shaped sentence, prefixed with
    the subject for context. Precision still beats recall: skip-listed
    subjects are dropped outright.
    """
    subject = LEADING_EMOJI.sub("", CONVENTIONAL_PREFIX.sub("", subject.strip())).strip()
    if not subject or SKIP_PATTERN.search(subject):
        return None
    reason_in_body = REASON_PATTERN.search(body or "")
    if BARE_RENAME.match(subject) and not reason_in_body:
        return None
    if _is_decision(subject):
        text = _first_sentence(subject)
    else:
        sentence = _first_decision_sentence(body)
        if not sentence:
            return None
        text = f"{_first_sentence(subject)} — {sentence}"
    reason = REASON_PATTERN.search(body or "") or REASON_PATTERN.search(subject)
    if reason:
        clause = _first_sentence(reason.group(1))
        if clause.lower() not in text.lower():
            text = f"{text} — because {clause}"
    return text


def iter_commits(repo_path: Path) -> list[dict[str, str]]:
    raw = subprocess.run(
        [
            "git", "-C", str(repo_path), "log", "--no-merges",
            f"--format=%H{FIELD_SEP}%an{FIELD_SEP}%aI{FIELD_SEP}%s{FIELD_SEP}%b{COMMIT_SEP}",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    commits = []
    for chunk in raw.split(COMMIT_SEP):
        if not chunk.strip():
            continue
        sha, author, date, subject, body = (chunk.strip("\n").split(FIELD_SEP, 4) + [""])[:5]
        commits.append({
            "sha": sha, "author": author, "date": date,
            "subject": subject, "body": body,
        })
    return commits


def mine(repo_path: Path) -> list[Decision]:
    decisions = []
    for commit in iter_commits(repo_path):
        if BOT_AUTHOR.search(commit["author"]):
            continue
        text = extract_decision(commit["subject"], commit["body"])
        if text:
            decisions.append(Decision(
                sha=commit["sha"], author=commit["author"],
                date=commit["date"], text=text,
            ))
    return decisions


def store(
    decisions: list[Decision],
    *,
    base_url: str,
    user_id: str,
    app_id: str,
    repo_name: str,
) -> int:
    stored = 0
    with httpx.Client(base_url=base_url, timeout=30) as client:
        for decision in decisions:
            response = client.post("/v1/memories/", json={
                "text": decision.text,
                "infer": False,
                "user_id": user_id,
                "app_id": app_id,
                "created_at": decision.date,
                "categories": ["decision", "project"],
                "metadata": {
                    "source": "git",
                    "repo": repo_name,
                    "commit": decision.sha[:12],
                    "author": decision.author,
                },
            })
            response.raise_for_status()
            stored += 1
    return stored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path, help="path to a git repository")
    parser.add_argument("--url", default="http://localhost:8000", help="forget server base URL")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--app-id", default="", help="memory scope; defaults to the repo directory name")
    parser.add_argument("--dry-run", action="store_true", help="print decisions without storing")
    parser.add_argument("--limit", type=int, default=0, help="keep only the N most recent decisions")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    decisions = mine(repo)
    if args.limit > 0:
        decisions = decisions[: args.limit]  # git log order: newest first
    if args.dry_run:
        for decision in decisions:
            print(f"[{decision.date[:10]} {decision.sha[:8]}] {decision.text}")
        print(f"\n{len(decisions)} decision(s) found (dry run)")
        return 0
    count = store(
        decisions,
        base_url=args.url,
        user_id=args.user_id,
        app_id=args.app_id or repo.name,
        repo_name=repo.name,
    )
    print(f"imported {count} decision(s) from {repo.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
