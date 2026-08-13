---
target: SPEC-nexus-multi-turn-retrieval
critiqued_hash: sha256:6611be5952ad27580d1eed63108eb7f72147b4db506655b0f8d1a190ec159710
critiqued_at: '2026-08-13T02:49:17Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: '§3.5 persists `rephrased_query` into `search_log`, but `search_log`
    is explicitly declared PII-safe — `nexus/init.sql:430`: "the raw query is NEVER
    stored — only sha256 + length (Nexus principle #3)". The rewritten query contains
    the user''s own wording plus facts pulled from history (§3.2 item 3, "우리는 1.28
    을 쓴다"), i.e. more sensitive text than the raw query, stored unconditionally. It
    also bypasses the entire opt-in retention architecture built for exactly this
    text (`migrations/017_query_text_retention.sql` / `018_retention_principals.sql`:
    separate tenant-salted key, `principals` allowlist, `notice_shown`, `retain_days`).
    Worse, the row it lands in already carries `query_sha256`, which `a2a_audit` also
    holds next to `principal` — the join that 017''s salted key was designed to make
    impossible is reconstituted. This also contradicts the SPEC''s own §2 non-goal
    ("서버는 이력을 받아 그 요청 안에서 쓰고 버린다"). No invariant in §4 covers retention, consent,
    or expiry of the rewritten query.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: '§1.3 makes Slack the first consumer and sources history from `conversations.replies`,
    which is authored by *multiple people*. Nothing in §3.1 or §4 states that `history`
    is untrusted, client-supplied, multi-author input: (a) the consent allowlist in
    `018_retention_principals.sql` gates on the calling principal, and the bot has
    one principal — so under §3.5 every thread participant''s text gets persisted
    under one consenting identity; (b) I4 filters documents by tenant/clearance but
    says nothing about whose text may enter history, so text a user could not have
    retrieved themselves can steer their retrieval; (c) I5 caps turn *count* only,
    so a single multi-megabyte turn passes, and free-text history flows straight into
    a rewrite prompt with no injection boundary stated.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: unverifiable-claim
  severity: high
  description: '§5.2''s 기각 branch claims the fallback state is still an improvement
    — "그것도 오늘보다 낫다(20→23/24)" — but this contradicts the SPEC''s own §1.2 table and
    finding #2. In the drifted arm (the arm §5.2 uses as the decision arm), concatenation
    scores 20/24, exactly equal to today''s 생략형, with MRR 0.570 which is *worse* than
    today''s 0.611. The 23/24 figure is taken from the non-drifted arm. The pre-registered
    rejection branch therefore rests on a number the doc has already measured to be
    false in the condition the rule is evaluated in; on the doc''s own data, rejection
    leaves recall unchanged and ranking degraded.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: undefined
  severity: high
  description: 'The weighted RRF in §3.3 is unspecified against the code it must change.
    `nexus/nexus/search/hybrid.py:231` `_rrf_fusion(bm25_results, vector_results,
    k)` has no weight parameter and stores exactly one `bm25_rank`/`vector_rank` per
    rid. The SPEC''s table gives one weight per *query variant* and labels the rewrite
    channel "(semantic)", never stating: whether the original question runs BM25 only,
    vector only, or both; how the variant axis crosses the existing leg axis (does
    weight 1.3 apply once, or to each of two legs, making it effectively 2.6 vs 1.0?);
    what happens to the graph leg and to `bm25_top_k`/`vector_top_k` candidate pool
    sizes when the number of legs doubles; and how `_diversify`/`per_doc_cap` interact
    with a doubled pool. §8''s claim that "채널별 BM25/vector 순위가 이미 `SearchHit` 에 있다"
    is false once four legs collapse into two rank fields — the stated method for
    resolving the open mecab question does not exist.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: adr-contradiction
  severity: high
  description: 'ADR-0008 §3 item 3 unblocks multi-turn retrieval to be *proposed*
    only under ADR-0002''s demand-pull procedure, and states the procedure explicitly:
    the gate is "declared fired by the director and recorded in that direction''s
    first SPEC — it is not argued into existence by the SPEC." This SPEC does precisely
    what that sentence forbids: §1.2 is framed as "이 SPEC 의 존재 근거" and no director
    gate declaration is recorded anywhere. Separately, ADR-0008 §5''s backstop obliges
    re-reading ADR-0008 at the start of "any work that would materially expand Nexus''s
    retrieval stack — a new retrieval channel"; §3.3 adds exactly that, and the SPEC
    cites ADR-0008 only for the borrow-design-not-code point, never recording the
    backstop re-read or its outcome.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: untestable-requirement
  severity: high
  description: 'I3 ("이력에만 있고 문서에 없는 사실은 답변에 들어갈 수 없다") is stated with no mechanism
    and no test. §7 concedes the harness measures retrieval only (document Recall@10/MRR),
    so nothing in U1–U4 can detect an answer that repeats a fact supplied by history.
    The existing checks do not cover it: citation verification (#134) matches cited
    titles against shown snippets and answer-number verification (#139) matches numbers
    against what the LLM was shown — history-injected facts pass both if history is
    in the prompt at all. Since §3.2 item 3 deliberately propagates user-asserted
    facts, I3 is the invariant most likely to break and the only one with no verification
    path.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: medium
  description: §3.3 hardcodes `k=50`, but the running system reads `rrf_k` from config
    with default 60 (`nexus/nexus/search/hybrid.py:437`), and that value participates
    in the search cache/config key (`nexus/nexus/search/signals.py:188`). The SPEC
    never says whether 50 replaces the configured default globally, applies only to
    the two-channel path, or is a config change requiring a cache-key bump. If it
    replaces the default, I1's "오늘과 바이트 단위로 같은 질의" no longer implies today's ranking,
    and every no-history query silently re-ranks.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: unverifiable-claim
  severity: medium
  description: '§3.3 claims that after dedup, "재작성 결과가 원문과 같으면 … 자동으로 강화된다". This
    is arithmetically empty in rank-based RRF: if the two query strings are identical,
    both channels produce identical rank lists, so summing 1.3 + 0.5 multiplies *every*
    document''s fused score by the same 1.8 and leaves the ordering byte-identical.
    Nothing is "강화"되지 않는다 — the only observable effect is inflated absolute scores.
    That side effect is itself uncovered by any invariant: fused scores feed `search_log.top_score`,
    so post-U3 rows become incomparable with historical rows and with any absolute
    threshold, and §4 constrains only the query string, never score magnitude.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: medium
  description: §3.5 says the rewrite call's tokens/cost are wired into "기존 계측", but
    `search_log` carries exactly one `prompt_tokens`/`completion_tokens`/`cost_usd`
    triple per row, and `nexus/nexus/llm/budget.py::measured_averages` averages those
    columns across all rows as the basis for "답변 1회 비용". Folding a second per-turn
    LLM call into the same columns silently biases the cost estimator; keeping it
    separate requires a schema change the SPEC does not name. The SPEC also never
    says whether the rewrite call is subject to the existing sufficiency/budget path
    or bypasses it entirely — a per-turn call outside the spend gate.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: untestable-requirement
  severity: medium
  description: §5 claims pre-registration ("구현 전에 박는다") but leaves two escape hatches
    that make the rules post-hoc adjustable. The 부분 채택 branch authorises re-measuring
    the 1.3/0.5 weights with no pre-declared candidate set, no iteration cap, and
    no stopping rule — the weight search is unbounded and its outcome is decided after
    seeing the numbers. §8 then adds an assistant-turn arm "U3 에서", i.e. a fifth arm
    introduced after the thresholds were fixed on user-turn-only arms, with no statement
    of how the pre-registered criteria apply to it.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: The decision thresholds treat single-run n=24 values as exact. At n=24,
    one query's worth of movement is ~0.042 MRR and 1/24 recall — the same order as
    the margins the rules turn on ("이어붙임(0.570)보다 잡음 폭 이상 높고", "상한에서 1건 이내"). §5.1's
    noise floor is measured only for the rewrite arm, from a 3-run *range* (a biased,
    high-variance estimator), and no noise floor at all is established for the baselines
    (0.570 / 0.611 / 0.812 / 0.938) the comparison is made against — even though embedding/ANN
    and gold-inheritance paths are not guaranteed run-to-run identical either. The
    doc's own cited lesson (vision-reader reproducibility) is about exactly this failure.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: adr-contradiction
  severity: medium
  description: '§3.3 presents the 1.3/0.5 split as the reconciliation point with ADR-0002''s
    integrity principle "system decides, LLM narrates" (re-placed there as the layer
    that makes recaptured understanding trustworthy). The arithmetic says the opposite:
    the LLM-authored channel outweighs the deterministic user-text channel 2.6:1,
    so the LLM effectively decides what is retrieved and the original question is
    a minority tiebreaker, not a guarantee. §5.2 then concedes the two numbers are
    Onyx''s constants, unvalidated on this corpus — so the claimed reconciliation
    with a load-bearing ADR principle rests on an untested imported constant, and
    no invariant bounds the rewrite channel''s share.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: risky-assumption
  severity: medium
  description: '§3.4 says the 24 threads inherit gold from the Pack A labels "여기서
    새로 저술하지 않는다", but Pack A rev3 is a 45-query *answer* label set, and §1.2 scores
    document-level Recall@10/MRR. Two things are asserted rather than shown: that
    document-level gold exists per qid at that granularity, and how the 24 of 45 were
    selected. Selection is unstated and the threads were hand-authored by the same
    person who already knew which retrieval failure was to be demonstrated — the mechanism
    by which §7''s admitted "생략이 실사용보다 규칙적일 수 있다" would bias every number in §1.2,
    including the baselines the §5.2 rules compare against.'
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: undefined
  severity: medium
  description: 'I5 asserts a server-side history cap of N turns, but N is only determined
    in §5.3 (via U3''s harness) while U2 ships the wiring first — the SPEC never says
    what U2 enforces in the interim. Also undefined: the cap unit (turns vs bytes
    vs tokens — turn count alone bounds nothing), the behaviour on over-cap input
    (silent truncation vs 4xx — silent truncation makes the surface-independence rationale
    unobservable to clients), truncation direction, and whether I1''s no-op path triggers
    when a non-empty history truncates to zero user turns or contains only assistant
    turns.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: risky-assumption
  severity: medium
  description: §1.3's core premise — "대화 저장을 우리가 안 해도 된다" and "봇 쪽 배선은 수십 줄" — is
    unverified. `nexus/nexus/slack/bot.py::_answer` has no Slack Web API read path
    at all today; `conversations.replies` requires history scopes (`channels:history`/`groups:history`/`im:history`)
    that force an app re-install, is rate-limited per follow-up turn, and on a free
    workspace only returns 90 days. The SPEC treats Slack-side history as free and
    already available, which is also the assumption that makes Slack "쉽다" relative
    to web and drives the whole unit ordering.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-13T07:46:38Z'
---

