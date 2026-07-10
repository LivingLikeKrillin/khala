---
target: SPEC-nexus-notion-connection-health
critiqued_hash: sha256:8310107edb5e8825abac54d174995e5369d2c25674eb1b72a195d415860208ea
critiqued_at: '2026-07-10T06:23:18Z'
issues:
- issue_id: I-001
  category: unverifiable-claim
  severity: medium
  description: The claim that current notion_client's str(e)/repr(e) 'contain no credential'
    is asserted from a single observation (2026-07-10) and cannot be verified against
    all versions or all exception paths; the doc itself hedges by calling redaction
    a 'guard against regression', but the load-bearing safety property rests on an
    unverifiable snapshot of library behavior.
  status: rejected
  disposition_reason: 관측 기반 주장이다. 2026-07-10 라이브 API 에 bogus 토큰으로 호출해 str(e)/repr(e)
    에 자격증명이 없음을 확인했고, 문서에 관측일자와 함께 그렇게 적었다.
- issue_id: I-002
  category: risky-assumption
  severity: medium
  description: Redaction 'by value, not by pattern' assumes the exact token string
    is known and appears verbatim in exception text. If the library ever embeds the
    token in an encoded/escaped/partial form (URL-encoded header, base64, truncated),
    value-based replacement silently fails to redact, and the doc explicitly rejects
    pattern matching that could catch such cases.
  status: rejected
  disposition_reason: 값 기반 redaction 이 인코딩된 형태를 못 잡는 것은 사실이나, 토큰을 인코딩해 기록하는 경로가 없다.
    패턴 기반은 다음 토큰 형식(ntn_ 이전엔 secret_ 이었다)을 놓친다.
- issue_id: I-003
  category: missing-invariant
  severity: medium
  description: The 'token never leaves the process' invariant covers finish_run reason
    and general logs, but does not state what happens to the token in concurrent probe
    error paths, HTTP client exception wrappers, or the probe_connection failure results
    that may carry underlying error strings into the health response's 'unknown' state;
    no invariant guarantees the health response body itself is scrubbed of exception
    text.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: medium
  description: '''No response body, log line, or persisted row contains more than
    the token''s first four characters'' is stated as a universal property but tested
    only against a seeded finish_run and fake transport; there is no defined mechanism
    to enforce or verify this across all log lines and all future code paths, making
    the universal claim untestable as written.'
  status: rejected
  disposition_reason: '''어떤 로그 줄에도 없다''는 전역 보장은 무엇으로도 테스트할 수 없다. 주장을 우리 코드 경로가 생산하는
    값으로 좁히고 그것만 단언하도록 §6 을 고쳤다. 원 지적의 전역 요구는 반려.'
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: The design assumes Notion returns 404 (not 403) for uninvited pages
    based on one observation (2026-07-10). The entire root-state model (unreachable
    vs invited-but-indistinguishable) hinges on this behavior; a future API change
    to 403 would break the page/database retry logic and the 'we must not claim which'
    reasoning without any fallback specified.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: low
  description: The 404-on-page-then-retry-database logic assumes a database probed
    at /pages/{id} always answers 404 (not 400 or another status). If a database id
    ever returns 400 at the pages endpoint, it would be classified invalid_id and
    never retried as a database, contradicting the stated goal of not sending users
    to re-share a valid database.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: low
  description: '''Bounded concurrency'' for root probing is asserted as the reason
    no aggregate deadline is needed, but the concurrency bound is never specified.
    With an unbounded number of registered roots and only a per-probe 5s timeout,
    total latency is not actually bounded without a stated concurrency limit.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: low
  description: The doc gates GET /sources/notion/health behind manage_sources and
    exposes nexus_sources_health() over MCP, but ADR-0004 §3 classifies MCP/agent
    surfaces as 'agent-wired' with no capability/token model described for them; the
    interaction between Cloudflare Access capability gating (web) and MCP invocation
    is undefined, and the doc's threat-model reasoning ('behind a tunnel, whoever
    Access admits') does not obviously cover the MCP/CLI paths.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: scope-creep
  severity: low
  description: The redaction requirement modifies finish_run and 'every other place
    that records an exception string' — a cross-cutting change to the sync run persistence
    path that is broader than the stated goal of surfacing connection health, and
    touches code paths (notion_sync_runs.reason) outside the health-diagnosis feature.
  status: rejected
  disposition_reason: redaction 이 finish_run 을 건드리는 것은 scope 확장이 맞다. 그러나 그 한 줄이 자격증명을
    DB 에 영구 기록할 수 있는 유일한 경로다. 진단 표면을 만들면서 그 경로를 열어둔 채 두는 편이 더 큰 결함이다.
- issue_id: I-010
  category: unverifiable-claim
  severity: low
  description: The workspace/integration name display ('실증 테스트 · Joo Young Jung의 Notion')
    is presented as coming from GET /v1/users/me, but the doc does not verify that
    /users/me reliably returns both integration name and workspace name for all token
    types (internal vs public integrations), which affects whether the 'ok' surface
    can always render as specified.
  status: rejected
  disposition_reason: 예시의 integration/workspace 이름은 라이브 /v1/users/me 응답에서 그대로 온 값이다.
    꾸며낸 값이 아니다.
- issue_id: I-011
  category: missing-invariant
  severity: low
  description: The design says nothing is cached and the answer is 'about now', but
    does not define behavior when roots change between the token probe and root probes,
    or when a root is deleted from notion_sources concurrently with a health call;
    no consistency invariant is stated for the checked_at snapshot.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-10T07:15:25Z'
---

