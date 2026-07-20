# Dirty Stores: How Agent Memory Systems Degrade Under Real-World Contamination

**Section 3 — Method** (draft v0.1, 2026-07-19; drafted before experiments per
pre-registration research/beta/design.md v2.0)

---

## 3.1 Problem Formulation

An agent memory store is a set $S = E \cup J$ of items, where $E$ are *evidence
items* — records that some future query will need — and $J$ are *contaminants*:
records that no future query needs, accumulated organically through normal
operation (session exhaust, duplicated writes, imported document fragments,
probe writes, expired ephemera). Production audits motivate this framing: in
two stores we operated, contaminants constituted 88% (personal store, 8 months,
$N{=}106$) and 92.6% of writes were unreviewed automation exhaust (agent store,
3.5 weeks, $N{=}3{,}130$).

At query time, a memory system retrieves a *delivery set* $D_k(q) \subseteq S$
of at most $k$ items — the **retrieval budget** — which is placed in the
reader's context. We study how contamination degrades what $D_k$ contains.

**Contamination pressure.** For a base store of $n$ evidence-bearing items, we
inject $m$ contaminants such that $p = m/(n+m)$; $p$ is the fraction of the
final store that is contamination. We sweep $p \in \{0, 0.3, 0.6, 0.9\}$; the
upper values bracket our production measurements (0.88, 0.93).

**Evidence redundancy.** For query $q$, let $r(q) = |E(q)|$ be the number of
store items each of which independently suffices to ground the answer. In our
substrate $r(q)$ is measurable from per-turn evidence annotations; systems that
maintain multiple representations (e.g., a compressed layer alongside raw
records) multiply effective redundancy, which we denote $r_{\mathrm{eff}}$.

**Harm.** For a metric $M$ (defined in §3.4) the harm of contamination at
pressure $p$ and budget $k$ is
$$H_M(p, k) = M(0, k) - M(p, k).$$

**Central claim (pre-registered).** Contamination harms retrieval only by
*displacement*: a query fails when all $r(q)$ evidence copies are pushed out of
the top-$k$. This yields three falsifiable predictions: (i) harm increases as
$k$ shrinks (budget dependence, C1); (ii) at fixed $(p,k)$, harm concentrates
on low-$r(q)$ queries (C2); (iii) systems that reduce copy count — by
deduplication or destructive update — degrade faster than copy-preserving
systems (the *deduplication paradox*, C3).

## 3.2 Benchmark Construction

**Substrate.** We build on LongMemEval-S (500 instances; public, per-turn
evidence labels, per-type judge prompts). Each instance provides a haystack of
~50 sessions (~550 turns) for one synthetic user, a question, and
`has_answer` annotations identifying evidence turns. We exclude the 30
abstention instances (no evidence to displace), leaving 470. The substrate is
*clean by construction* — which is precisely what makes controlled
contamination possible.

**Contamination families.** Three families, in decreasing realism and
increasing experimental control:

- **C-crosstalk** (primary): real conversation turns transplanted from *donor*
  instances (other users) into the recipient's store. Donor sessions are
  sampled uniformly excluding the recipient, transplanted whole (preserving
  discourse structure), with timestamps resampled uniformly over the
  recipient's date range. This family is simultaneously *organic* (real
  dialogue) and *topical* (same domain distribution as the substrate), at zero
  authoring cost. Its real-world referents are scope-misrouted writes and
  multi-context bleed. Leakage control: recipient evidence sets are fixed
  ex-ante, so transplants can displace but never *add* scored evidence; we
  additionally screen donors whose answer strings lexically match the
  recipient's gold answer.
- **C-organic-agent**: contaminants drawn from our anonymized production agent
  store ($N{=}3{,}130$; taxonomy in §4.1: session exhaust, near-duplicates,
  document chunks, probes, fragments). Anonymization protocol in Appendix.
- **C-synthetic**: template-generated junk in the style of prior noise
  studies — the control family representing current evaluation practice.

**Injection protocol.** Contaminants are interleaved into the store with
realistic timestamps; all systems ingest the contaminated stream in timestamp
order through their own write paths (so write-time filtering, deduplication,
and consolidation act on contaminants exactly as they would in production).

## 3.3 Systems Under Test

Two groups, serving different inferential roles.

**Within-system pairs (mechanism isolation).** Variants of a single
reference system that differ in exactly one design property:

| Variant | Property isolated |
|---|---|
| `ref-single` | one representation per record (raw only) |
| `ref-dual` | + compressed observation layer retrieved under a separate budget ($r_{\mathrm{eff}} \approx 2r$) |
| `ref-dedup` | `ref-dual` + near-duplicate removal at write time (reduces $r_{\mathrm{eff}}$) |
| `ref-gate` | `ref-dual` + write-time contamination gate |

These pairs give the cleanest tests of C2/C3: any differential harm is
attributable to the isolated property. (The reference implementation is our
open-source engine; all variants share embedder, ranker, and store.)

**Cross-system panel (external validity).** Open-source memory systems
evaluated as-shipped through their public write/read APIs: Mem0, Letta, and
Zep (self-hosted; managed offerings are excluded from published comparisons
where terms of service restrict benchmarking). Each system uses its own
retrieval stack — deliberately: the stack is part of the system under test.
Adapters are timeboxed; systems we cannot run are reported as N/A with cause.

**A methodological limitation surfaced by this design.** Our primary
(judge-free) metric requires mapping delivered items to evidence annotations.
For *extractive* systems that store derived facts rather than records
(e.g., Mem0), this mapping requires source provenance. Where the system
exposes source references, we map through them; where it does not, the system
is evaluated only at Tier 2 (end-to-end QA), and we disclose the asymmetry.
This is itself a finding-shaped constraint: systems that discard provenance
cannot be audited for evidence delivery.

## 3.4 Two-Tier Measurement

**Tier 1 — retrieval-level (primary; judge-free).** For each (system, family,
$p$, $k$) cell and each query, the delivery set $D_k(q)$ is scored against
evidence annotations:

- `evidence-hit@k` $= \mathbb{1}[D_k(q) \cap E(q) \neq \emptyset]$
- `evidence-recall@k` $= |D_k(q) \cap E(q)| / |E(q)|$

Delivery sets are payload-deduplicated (an index entry and its payload count
once). Because Tier 1 requires no LLM calls, we sweep the full
$4 \times 4 \times 3 \times |{\text{systems}}|$ grid over 470 queries locally.
Write-side telemetry is recorded per system: contaminant admission rate,
evidence retention rate, and stored copy count $r_{\mathrm{store}}$.

**Tier 2 — end-to-end QA (bridge validation).** On strategic cells
$\{p{=}0, p{=}0.9\} \times \{k{=}8, k{=}42\} \times$ {`ref-dual`, `ref-single`,
naive, one extractive system}, a frozen reader answers from $D_k(q)$ and the
benchmark's per-type judge scores correctness (both GPT-4o, matching published
practice). Tier 2 exists to validate that retrieval harm propagates to answer
harm; 200 queries stratified by type and $r$-quartile. A per-category
sub-analysis tracks knowledge-update queries, where non-destructive
supersession is predicted to confer contamination resistance.

## 3.5 Statistical Analysis (pre-registered)

- **C1 (interaction):** logistic regression of per-query hit on $p$, $k$, and
  $p{\times}k$ with cluster-robust standard errors by query;
  support requires the interaction term at $p<0.01$ *and*
  $H(0.9, 4) - H(0.9, 42) \geq 15$pp on the reference system.
- **C2 (redundancy):** harm difference between bottom and top $r$-quartiles at
  matched $(p,k)$, paired by cell, bootstrap CI; plus Spearman correlation of
  per-query harm with $r(q)$ across the grid.
- **C3 (dedup paradox):** paired comparison `ref-dedup` vs `ref-dual` at
  $(0.9, 8)$; support requires $\geq$10pp excess harm. Cross-system slope
  comparison is reported as corroborating, not confirmatory.
- **C4 (realism gap):** family contrast at matched $p$; support at $\geq$5pp.
- **C5 (rank inversion):** Kendall $\tau$ between system rankings at
  $(0, 42)$ and $(0.9, 8)$; support at $\tau < 0.5$.

All null results are reported. Seeds, code, anonymized contamination corpora,
and per-query outputs are released.

## 3.6 Threats to Validity (acknowledged in advance)

1. *Substrate circularity*: LongMemEval questions are themselves derived from
   sessions; retrieval difficulty may be understated. Mitigation: harm is a
   *difference* at fixed queries, differencing out absolute easiness.
1b. *Crosstalk timing realism*: transplant timestamps are resampled uniformly
   over the recipient's date range; real scope bleed is likely burstier. The
   injection protocol treats timing as a nuisance variable, not a modeled one.
1c. *Test specification*: paired comparisons reported as "sign test" are
   two-sided exact binomial tests on discordant pairs; ranges (e.g.,
   p=0.003–0.043) span the listed cells.
2. *Single embedder in Tier 1 reference variants*: displacement dynamics may
   differ across embedding spaces; we replicate the C1 surface with a second
   embedder on a subsample.
3. *Extractive-system asymmetry* (§3.3): Tier-1 coverage is partial; Tier-2
   covers all systems.
4. *Judge dependence in Tier 2*: mitigated by judge-free Tier 1 carrying the
   primary claims; Tier-2 judge fidelity was previously validated against a
   published external baseline (reproduction within 0.4pp).
5. *Organic-corpus provenance*: our production corpora reflect two users'
   workloads; the released protocol lets any operator regenerate the benchmark
   from their own store (community track).

---

**§3.1 revision (2026-07-20, post-Tier-1).** The single redundancy quantity
$r(q)$ conflates two structures the data forced us to separate: *disjunctive*
multiplicity $r_{\mathrm{OR}}(q)$ — the number of items any one of which
suffices — and *conjunctive* size $n_{\mathrm{AND}}(q)$ — the number of items
jointly required. Displacement predicts opposite monotonicity: harm falls
with $r_{\mathrm{OR}}$ (more fallback copies) and rises with
$n_{\mathrm{AND}}$ (more single points of failure). Both branches are
confirmed in §5.3. Query types map cleanly: single-session and
knowledge-update queries are $r_{\mathrm{OR}}$-dominated; multi-session and
temporal-reasoning queries are $n_{\mathrm{AND}}$-dominated.
