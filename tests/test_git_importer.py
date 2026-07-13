from forget.importers.git import extract_decision


def test_decision_shaped_subjects_are_kept():
    assert extract_decision("switch payments to Paddle", "") is not None
    assert extract_decision("migrate store from Postgres to SQLite", "") is not None
    assert extract_decision("forget-connect defaults to the local server now", "") is not None
    assert extract_decision("revert temporal rerank threshold change", "") is not None


def test_routine_motion_is_forgotten():
    assert extract_decision("fix typo in README", "") is None
    assert extract_decision("lint: appease ruff", "") is None
    assert extract_decision("bump version to 0.2.0", "") is None
    assert extract_decision("update readme badges", "") is None
    assert extract_decision("add unit tests for crypto", "") is None  # motion, not a decision


def test_reason_clause_is_attached_from_body():
    text = extract_decision(
        "switch default embedding to fastembed",
        "The deterministic embedding is private but weak.\n"
        "Because bge-small matches cloud quality on our corpus. Benchmarks in docs/.",
    )
    assert text is not None
    assert "because bge-small matches cloud quality" in text.lower()


def test_reason_in_subject_is_not_duplicated():
    text = extract_decision(
        "drop numpy requirement because rerank must not silently no-op",
        "",
    )
    assert text is not None
    assert text.lower().count("because") == 1


def test_conventional_prefix_is_stripped_before_matching():
    text = extract_decision("mcp: serverInfo name mem1-mcp -> forget-mcp", "")
    assert text is not None and "mem1-mcp -> forget-mcp" in text


def test_body_decision_is_mined_when_subject_is_a_label():
    text = extract_decision(
        "engine: temporal rerank hardening",
        "numpy stays optional. The rerank now defaults to a pure-Python "
        "fallback so a minimal install keeps the feature.",
    )
    assert text is not None
    assert text.startswith("temporal rerank hardening — ")
    assert "pure-python fallback" in text.lower()


def test_label_subject_with_no_decision_body_is_dropped():
    assert extract_decision(
        "vault: E2EE crypto primitives and key-hierarchy design",
        "Adds forget/crypto.py implementing the design doc.",
    ) is None


def test_skip_wins_over_decision_verbs():
    assert extract_decision("fix typo: chose -> choose", "") is None
    # a conventional prefix is a label, not a verdict: stripping "chore:"
    # exposes a real (if small) decision underneath
    assert extract_decision("chore: switch CI to ubuntu-24.04", "") is not None


def test_version_arrows_are_motion_not_decisions():
    assert extract_decision("pre-commit autoupdate", "ruff-pre-commit: v0.7.0 → v0.7.1") is None
    assert extract_decision("update deps v1.2.3 -> v1.2.4", "") is None
    # a real rename arrow still counts
    assert extract_decision("serverInfo name mem1-mcp -> forget-mcp", "") is not None


def test_bare_rename_without_reason_is_dropped():
    assert extract_decision("Rename bstate to bpop", "") is None
    assert extract_decision(
        "Rename bstate to bpop",
        "Because the struct now only carries blocking-pop state.",
    ) is not None
    # renames with surrounding context still pass the normal path
    assert extract_decision("Slave removal: slave -> replica in redis.conf", "") is not None
