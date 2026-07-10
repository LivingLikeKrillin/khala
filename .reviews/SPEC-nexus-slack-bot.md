---
target: SPEC-nexus-slack-bot
critiqued_hash: sha256:f25c789c65ecf7cfff17d62ca6107c6944f0831eadab39a25f1960c923dbba9c
critiqued_at: '2026-07-10T15:00:28Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: medium
  description: The design defers 'Surfacing Archon grounding distinctly (I-001)' entirely
    out of scope, attributing it wholly to the /search/answer endpoint. But ADR-0004
    §2.2 says an Archon answer 'must still surface *as* a live-code-constant fact-check
    ... visibly distinct' and explicitly calls hiding the grounding character an erasure
    of Archon's value. If the Slack formatter (formatter.py builds answer/evidence/sources
    blocks) flattens or drops the distinct grounding signal the endpoint returns,
    the bot silently contradicts ADR-0004's 'visible to the user' requirement. The
    doc assumes the endpoint marks it and the bot merely 'renders what the endpoint
    returns' — but no requirement pins that the formatter preserves the distinction,
    so compliance is unverified for this surface.
  status: rejected
  disposition_reason: Archon grounding 을 별도로 드러내는 것은 /search/answer 응답의 성질이며 모든 표면(웹·MCP·A2A)에
    공통으로 지는 빚이다. Slack 봇이 자체 버전을 만드는 것이야말로 피해야 할 파편화다. §2 non-goal 로 명시하고 답변 엔드포인트
    쪽에 추적.
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: The single-service-principal model assumes every Slack workspace member
    should read whatever the principal's clearance permits, with the operator's clearance
    setting as the only control. External shared-channel participants and single-channel
    guests inherit full read access at that clearance. The doc acknowledges this but
    relies entirely on the operator correctly choosing PUBLIC vs INTERNAL — a human
    configuration decision with no technical guardrail preventing an INTERNAL setting
    on a workspace with external guests. The blast radius (whole INTERNAL corpus to
    external guests) makes the assumption high-severity.
  status: rejected
  disposition_reason: '게스트 접근 위험은 실재하나 코드가 ''이 워크스페이스에 외부 게스트가 있는가''를 알 방법이 없다 — Slack
    멤버십은 Nexus 통제 밖 상류다. 완화책은 이미 반영: 기본 clearance=PUBLIC(안전 바닥), 런북에 ''봇 clearance
    = 워크스페이스 전원(게스트 포함)에게 확장하는 신뢰의 바닥''을 명시. 코드 가드가 불가능한 운영자 결정.'
- issue_id: I-003
  category: missing-invariant
  severity: medium
  description: No invariant ties the default clearance floor to actual guest presence.
    §4.2 states default is PUBLIC and instructs operators to set PUBLIC when external
    guests exist, but nothing detects or enforces that an INTERNAL clearance is incompatible
    with a workspace containing external/guest members. The safe floor is only a documentation
    convention, not an enforced property — the same class of gap ADR-0004 flags ('convention,
    not an enforced invariant').
  status: rejected
  disposition_reason: I-002 와 같은 지점 — 기본값을 게스트 실재에 자동 연동할 방법이 없다(코드가 게스트를 못 본다). 기본
    PUBLIC 이 이미 그 부재에 대한 안전 응답이다.
- issue_id: I-004
  category: untestable-requirement
  severity: medium
  description: The claim that the bot token 'appears in no formatted block and no
    log call ... asserted against captured output on the error branches too' is described
    as 'a property of the code, not of one captured path.' Asserting a negative universal
    (token never interpolated anywhere across all code paths) via captured output
    on selected branches cannot actually verify the universal property; the test only
    covers the branches exercised. The requirement as stated is not fully testable.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: unverifiable-claim
  severity: low
  description: §4.2 asserts a zero-capability principal hitting a write route gets
    403 because write paths 'already gate on manage_documents / manage_sources capability,
    default-deny.' This depends on the current server-side behavior of documents/api.py
    and sources/api.py being accurate and stable; the doc pins one test (/documents/{rid}/hide)
    but generalizes to 'every write route,' which is not verified for all write routes.
  status: rejected
  disposition_reason: '코드로 확인함(2026-07-11): documents/api.py 의 hide/restore/unsupersede/supersede
    전부 _require(principal) 로 manage_documents 를 강제, 없으면 403. 주장이 사실이며 §6 이 그 경로로 테스트한다.'
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: The empty-grounding vs empty-corpus distinction (§4.3) assumes /search/answer
    returns enough signal to reliably distinguish '0 evidence' from '0 documents.'
    No spec of the endpoint response schema is given to confirm the bot can tell these
    apart; if the endpoint does not distinguish them, the two distinct messages are
    unachievable.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: scope-creep
  severity: low
  description: §2 declares 'Rebuilding the handlers or the answer formatter' a non-goal
    and frames error mapping as 'a small addition, not a rewrite,' yet §4.3 introduces
    a new outcome-classification function in _call_nexus_api plus a full new outcome→message
    mapping table with five branches and per-row tests. This is genuinely new behavior/logic
    beyond wiring, sitting in tension with the stated 'wire them to run' scope framing.
  status: rejected
  disposition_reason: 에러 매핑은 scope 확장이 아니라 §1 목표('봇이 답할 수 없을 때 말한다')의 핵심이다. format_answer/handlers
    는 그대로 두고 매핑 함수만 더한다 — non-goal 은 '재작성 안 함'이지 '아무것도 안 더함'이 아니다.
- issue_id: I-008
  category: undefined
  severity: low
  description: 'The precise semantics and provenance of the auth.slack.clearance operator
    setting are underspecified: where it is validated against the minted token''s
    registered ceiling, what happens on mismatch between the token''s actual (tenant,
    clearance) ceiling and auth.slack.clearance, and whether the setting or the token
    ceiling is authoritative. §4.2 and §7 reference both but do not reconcile them.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: unverifiable-claim
  severity: low
  description: The go-live acceptance (§7) — '@nexus <question> in a channel returns
    a grounded answer in-thread' via a live workspace — is confirmed only by a manual
    end-to-end check, not automated. It is deferred as a 'go-live gate,' making the
    core adoption goal (§1) unverifiable within the shipped test suite.
  status: rejected
  disposition_reason: 라이브 워크스페이스 게이트는 Access JWT SPEC 의 라이브 터널 게이트와 같은 형태다 — 도메인/실
    Slack 앱 없이 검증 불가한 마지막 한 걸음이고, SPEC 이 그 사실을 숨기지 않고 게이트로 명시했다. 자동 반복 검증 불가는 인정된
    한계지 결함이 아니다.
approved_by: LivingLikeKrillin
approved_at: '2026-07-10T15:04:16Z'
---

