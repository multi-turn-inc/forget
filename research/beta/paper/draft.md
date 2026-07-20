# Dirty Stores: How Agent Memory Systems Degrade Under Real-World Contamination

*Master draft v0.1 (2026-07-20). Numbers in `[..]` are placeholders wired to the
pre-registered analyses; §3 is maintained in method.md and inlined at export.
Target: arXiv → NeurIPS 2026 D&B / ICLR 2027.*

---

## Abstract

Agent memory systems are evaluated on clean stores; production stores are
mostly junk. Auditing two stores we operated, 88% of a personal store (8
months, N=106) and 92.6% of an agent-workload store (N=3,130) consisted of
records no future query needs. We introduce **DirtyStores**, a protocol that
contaminates a public memory substrate (LongMemEval-S) under controlled
pressure $p$ and retrieval budget $k$ with three contamination families:
synthetic templates (prior practice), translated production exhaust (real
junk), and *crosstalk* — real conversations belonging to other users. We
expected junk to be the threat. It was not: at ninefold contamination
($p{=}0.9$), synthetic and organic junk cost at most 1.5pp of evidence
delivery, while crosstalk cost up to 14.7pp — a 15–25× gap. **The dangerous
contamination is not garbage but other people's context**: in-distribution
records that compete for the same retrieval slots. Harm follows a
displacement mechanism — monotone in budget everywhere we measured (14.7pp at
$k{=}4$ shrinking to 6.6pp at $k{=}42$) — and evidence multiplicity carries
two signs: redundant copies protect disjunctive queries (12.2pp vs 8.4pp harm,
low vs high $r$), while aggregation queries invert (10.8pp vs 17.5pp),
because needing more pieces means more ways to lose one. Deduplication,
marketed as hygiene, cost 2.3pp even on clean stores by destroying legitimate
copies (p<0.05) and amplified contamination harm at generous budgets
(27W/2L, p<10⁻⁴). Clean-store scores at customary budgets thus measure the
regime where none of this is visible. We release the protocol, corpora, and
per-query results, with a community track for regenerating the benchmark from
any operator's own store — and a design conclusion: the defense that matters
is scope isolation, not junk filtering.

## 1. Introduction

The evaluation regime for long-term agent memory has an unstated assumption:
the store contains only what the benchmark put there. LongMemEval and LOCOMO
ingest curated haystacks; systems retrieve from them with budgets of dozens of
items; leaderboards rank systems by answer accuracy over this clean substrate.

Deployed stores violate this assumption immediately. Memory is written by
hooks, importers, and agents — not curators. Auditing a personal store after 8
months of real use, we found 88% of records were junk (news fragments,
truncated imports, probe writes, filler). Auditing an agent-workload store
after 3.5 weeks, provenance metadata showed 92.6% of 3,130 records were
unreviewed session exhaust written by automation, and 1.1% were deliberate,
curated writes. These proportions are not exotic: anyone operating agents
accumulates such a store. The question is whether clean-store scores predict
behavior on the stores people actually have.

This paper answers with a mechanism, not just a measurement. Contamination
does not corrupt stored evidence; it *competes with evidence for a
fixed-size retrieval budget*. A query fails only when every copy of its
evidence is displaced from the top-$k$ — which makes harm a function of three
quantities the field's evaluations hold fixed and generous: contamination
pressure $p$, retrieval budget $k$, and evidence redundancy $r$. From this
single displacement principle follow three falsifiable predictions:

1. **Budget dependence.** At the customary $k \approx 40$, contamination is
   nearly invisible; at the budgets of ambient memory injection
   ($k \in [4, 8]$), the same contamination is severe. Preliminary evidence:
   in a controlled pilot, misattributed topical text cost 0.6pp of recall at
   $k{=}42$ and 35pp of hit rate at $k{=}4$.
2. **Redundancy concentration.** Harm lands on low-$r$ queries — one-off
   details mentioned once — while gist queries with many copies survive.
3. **The deduplication paradox.** Any mechanism that collapses copies —
   near-duplicate removal, destructive updates that overwrite prior versions —
   lowers $r$ and therefore buys clean-store tidiness with contamination
   fragility. Systems advertising these as quality features should degrade
   first under pressure.

We test these predictions with a two-tier protocol (§3): a judge-free
retrieval tier that sweeps the full $p \times k \times$ family $\times$ system
grid against per-turn evidence annotations, and an end-to-end QA tier on
strategic cells that validates harm propagation. Mechanisms are isolated
within a single reference system (variants differing in exactly one property:
single vs dual representation, deduplication on/off), and external validity
comes from a cross-system panel (Mem0, Letta, Zep) evaluated through their own
write/read paths.

**Contributions.**
- The first contamination benchmark for agent memory grounded in *real*
  production junk, with a released protocol any operator can rerun on their
  own store (§4).
- A displacement theory of contamination harm with three pre-registered,
  falsified-or-confirmed predictions (§5): budget dependence [C1: ..],
  redundancy concentration [C2: ..], and the deduplication paradox [C3: ..].
- Evidence that evaluation practice measures the wrong regime: clean-store
  rankings reshuffle under contamination [C5: τ=..], and synthetic-noise
  robustness overestimates real-world robustness [C4: ..].
- A methodological finding shaped like a constraint: systems that discard
  provenance cannot be audited for evidence delivery at all (§3.3).

All hypotheses, bars, and analyses were pre-registered before results
(repository history documents two prior hypotheses killed by their own
pre-registered bars); null results are reported.

## 2. Related Work

**Long-term memory systems.** Token-space memory has progressed from paged
context management (MemGPT/Letta) through extractive fact stores with
update/dedup pipelines (Mem0), temporal knowledge graphs (Zep/Graphiti),
hierarchical temporal indexes (MemForest), dual-granularity event/turn stores
(HiGMem), and write-time observation compression (Mastra OM; LightMem).
Learned memory management trains write-side operations with downstream-QA
reward (Memory-R1; the MEM1 line optimizes within-trajectory state). Our
subject is orthogonal: not how systems build memory, but how what they build
survives the stores real operation produces. Notably, several of these
systems' headline features — extraction, deduplication, destructive update —
are precisely the copy-collapsing mechanisms our C3 predicts to be fragile.

**Evaluation.** LongMemEval and LOCOMO evaluate over clean, benchmark-authored
histories; LOCOMO's adversarial category — the nearest existing probe of
robustness — is the weakest area of every published system (pass rates
30–45%). HaluMem evaluates hallucinations *introduced by memory operations*;
we evaluate degradation *caused by store composition* — complementary failure
axes. In RAG, noise studies report that random distractors can even help
generation at generous budgets; our budget-dependence law is consistent with
those results and identifies the regime they did not test: organic, topical
contamination against tight budgets.

**Boundaries.** Adversarial memory poisoning (backdoor injection; OWASP
agentic-security taxonomies) concerns attacker-crafted writes; we study
*organic* contamination that accrues without an adversary, a precondition
that any deployment meets. Memory-transfer integrity (portable agent memory)
concerns moving stores between agents; we study the quality of what is stored.
Both boundaries are scoping decisions, not claims of irrelevance.

**Cognitive framing.** That recall is reconstruction over interfering traces
is a century old (Bartlett); retroactive interference — new material impairing
access to old — is the psychological analog of displacement, and rational
analyses of memory model access as relevance ranking under environmental
statistics. We import the *access-competition* lens, not the biology: machine
stores can keep every byte; their scarcity is the context budget.

## 3. Method

*(maintained in `method.md` — inlined at export)*

## 4. The DirtyStores Corpus and Protocol

### 4.1 What real contamination looks like

Two production stores, audited:

| | Personal store | Agent-workload store |
|---|---|---|
| Lifetime | 8 months | 3.5 weeks |
| N | 106 | 3,130 |
| Junk share | 88% (manual audit) | [..]% (labels: W1) |
| Automation share | — | 92.6% (provenance) |
| Curated writes | — | 1.1% |

The agent store's provenance is the sharper fact: 2,899 of 3,130 records were
written by a session-state hook, none carrying task or project coordinates —
memory as automation exhaust. First-pass taxonomy over this corpus:
session-state ephemera ([..]%), near-duplicates written minutes apart
([..]%), imported document chunks ([..]%), probe writes ([..]%), fragments
([..]%). Final labels combine rule-based classification, LLM-assisted
labeling, and owner review of a stratified sample ([W1 pending]).

### 4.2 Contamination families

*(protocol as §3.2; family rationale)* C-crosstalk instantiates the
scope-misrouting failure mode every multi-context user risks; C-organic-agent
carries the empirical taxonomy above (translated to the substrate language;
register preserved; disclosed); C-synthetic represents the noise models of
prior practice — its gap to the organic families is itself measured (C4).

### 4.3 Community track

The benchmark is a protocol, not a dataset: classification taxonomy, injection
rules, and metrics run against any operator's store. We release tooling to
regenerate DirtyStores locally and (optionally) contribute anonymized
taxonomy statistics — the benchmark grows the way the problem does.

## 5. Results  *(Tier-1 numbers in; Tier-2 bridge and cross-system pending W2)*

### 5.1 Junk is harmless; crosstalk is not (C4 — headline)

At $p{=}0.9$, $k{=}4$ (single-representation reference): synthetic 0.0pp,
organic exhaust 0.6pp, **crosstalk 14.7pp** of evidence-hit harm. The pattern
holds at every budget (at $k{=}8$: 0.0 / 1.1 / 11.7pp). The pre-registered
form of C4 ("organic > synthetic") is *refuted for exhaust and confirmed
overwhelmingly for crosstalk*: the operative dimension is not organic-ness
but distributional proximity — contamination harms in proportion to how well
it competes for the same retrieval slots. Real-world referent: scope-misrouted
writes and multi-context bleed, not accumulated garbage. (This also explains
two earlier null results in our program: unique-token synthetic junk at small
scale, and out-of-domain exhaust, both fail to compete.)

### 5.2 The harm surface (C1)

Harm is monotone in budget in every family×pressure row measured. Crosstalk:
| $p$ | $k{=}4$ | $k{=}8$ | $k{=}16$ | $k{=}42$ |
|---|---|---|---|---|
| 0.3 | 1.5 | 0.9 | 1.3 | 0.6 |
| 0.6 | 4.5 | 3.2 | 3.4 | 1.9 |
| 0.9 | 14.7 | 11.7 | 10.9 | 6.6 |

The pre-registered gap bar ($H(0.9,4)-H(0.9,42) \geq 15$pp) is **not met**
(8.1pp); the direction is unambiguous. [GLM interaction test: paper pass]

### 5.3 Evidence multiplicity has two signs (C2, revised by data)

Our $r$-proxy conflated two kinds of multiplicity. Splitting by query type:
- *Disjunctive* evidence (single-session, knowledge-update — any copy
  suffices): low-$r$ harm 12.2pp vs high-$r$ 8.4pp — displacement protection,
  as predicted.
- *Conjunctive* evidence (multi-session, temporal — pieces are needed
  jointly): the sign inverts, 10.8pp vs 17.5pp — more required pieces mean
  more ways to lose one.
The theory gains a distinction ($r_{\mathrm{OR}}$ vs $n_{\mathrm{AND}}$,
§3.1 revision) and both branches now confirm it.

### 5.4 The deduplication paradox (C3, nuanced)

Near-duplicate removal cost **2.3pp on clean stores** (destroying legitimate
copies; sign test p=0.003–0.043) and amplified contamination harm at $k{=}42$
(dual over dedup 27W/2L, p<10⁻⁴; excess harm ≈3pp) — but showed no
differential amplification at the registered $(0.9, 8)$ cell (bar ≥10pp: not
met). Verdict: deduplication is a cost everywhere and a contamination
amplifier at generous budgets; the registered effect size was not reached.

### 5.5 Leaderboard stability (C5) — pending cross-system panel (W2)

### 5.6 Bridge validation — pending Tier-2 cells (W2); includes
knowledge-update sub-analysis (supersession resistance under contamination).

*Measurement note: Tier-1 strict credit undercounts dual-representation
variants (observation slots earn no turn-credit); within-pair comparisons are
unaffected. Bounds reported per §3.4.*

## 6. Discussion  *(stubs)*

- **For system design.** Copy preservation is a robustness feature, not
  storage waste; provenance is the precondition of auditability; ambient
  injection (small $k$) is the fragile regime and needs precision, not volume.
- **For evaluation practice.** Report harm surfaces, not points; clean-store
  scores at generous budgets measure a solved sub-problem.
- **For operators.** Your store is mostly exhaust; its danger is not size but
  displacement pressure at your actual injection budget.

## 7. Limitations

Substrate circularity (differenced out by design, §3.6); translation of the
organic corpus (register-preserving, disclosed); two-operator provenance of
the corpora (mitigated by the community protocol); extractive systems only
partially auditable at Tier 1 (§3.3); single embedder for the reference
variants (second-embedder replication on a subsample); organic corpora reflect
one operator culture per store type.
