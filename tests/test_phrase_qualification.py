"""phrase_bonus only rewards tokens that can carry topical signal.

Cycle 18 root-caused F2 recall pollution to C1: score_memory's per-token
phrase bonus (+0.02, substring match) summed over single-char particles
(조사) and bare numbers, handing long Korean memories a topic-free score
floor (~+0.3) that unbound the 0.45 gate. Cycle 22's selectivity sweep
narrowed the treatment to the qualification filter alone (len>=2 and not
isdigit) — the 0.10 cap variant was measured regressive (it demotes
high-overlap *relevant* memories; e2ee query top-1 broke with the cap,
recovered without it). Cycle 81 wires that filter in; these tests pin it.

Memories below place query tokens as substrings of *different* tokens so
token-set overlap stays 0 and the score isolates the phrase term.
"""
from forget.memory_engine import score_memory


def test_single_char_particle_earns_no_phrase_bonus():
    # "로" appears inside "필터로" (substring hit, zero token overlap).
    # Pre-treatment this scored 0.02 — the C1 farming primitive. The
    # second query token keeps the full-query bonus out of the picture.
    assert score_memory("로 은", {"memory": "필터로 간다"}) == 0.0


def test_pure_numeric_token_earns_no_phrase_bonus():
    # "2026" appears inside the alnum token "v2026x" only.
    assert score_memory("2026 9999", {"memory": "v2026x rollout"}) == 0.0


def test_qualified_token_still_earns_phrase_bonus():
    # "kubernetes" is a substring of "kubernetesland" (no token overlap),
    # "zephyrq" is absent — the 0.02 phrase term is the entire score.
    assert score_memory("kubernetes zephyrq", {"memory": "kubernetesland guide"}) == 0.02


def test_qualified_bonus_is_uncapped():
    # Six qualified substring-only matches: 6 * 0.02 = 0.12. The rejected
    # cap design (0.10) would clip this — cycle 22 measured that cap
    # regressive, so accumulation above 0.10 must survive.
    query = "alphaz betaz gammaz deltaz epsilonz zetaz"
    memory = {"memory": "alphazx betazx gammazx deltazx epsilonzx zetazx"}
    assert score_memory(query, memory) == 0.12


def test_full_query_bonus_unchanged():
    # The exact-phrase bonus (0.25) is not part of the treatment: the
    # whole lowered query inside the memory still earns it on top of the
    # qualified per-token bonus. Both memories keep token overlap at 0 and
    # match both query tokens as substrings (2 * 0.02); they differ only
    # in whether the full query appears contiguously.
    with_phrase = score_memory("kubernetes cluster", {"memory": "xkubernetes clusterz"})
    without_phrase = score_memory("kubernetes cluster", {"memory": "xkubernetesz clusterz"})
    assert with_phrase == 0.29
    assert without_phrase == 0.04
