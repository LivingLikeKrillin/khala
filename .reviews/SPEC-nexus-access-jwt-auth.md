---
target: SPEC-nexus-access-jwt-auth
critiqued_hash: sha256:d5fcc63e407857f3cc9d5ab50d6fcd20f2f20ff7c522b73f5b7b2e2eec425118
critiqued_at: '2026-07-10T11:26:55Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: low
  description: The SPEC repeatedly cites internal invariant IDs (I-001, I-002, I-005,
    I-007, I-011, etc.) that appear to be its own SPEC-local invariants, but ADR-0004
    also has a review log with I-001..I-005 meaning entirely different things (e.g.
    ADR I-005 is an uncited-claim about ken). The overloaded I-00x namespace creates
    ambiguous cross-references; a reader cannot tell whether 'I-001' in the SPEC's
    non-goals refers to the ADR's review finding or a SPEC invariant.
  status: rejected
  disposition_reason: 내부 이슈 ID(I-00x) 인용은 리뷰 사이드카가 붙인 번호를 본문이 참조한 것으로, 설계 결함이 아니라
    편집 흔적이다. 최종본에서 정리 가능하나 SPEC 승인을 막을 사안이 아니다.
- issue_id: I-002
  category: unverifiable-claim
  severity: high
  description: The claim that Cloudflare Access always sets iss/aud/exp/email regardless
    of which upstream IdP is wired (I-001) is asserted from published documentation
    only, not the live edge (self-admitted in §3/I-008). 'Verified' is explicitly
    deferred to §8 against a real tunnel, so the decoupling guarantee is unverified
    until a domain exists.
  status: rejected
  disposition_reason: §2·§3·§8이 이미 '검증은 §8(라이브 엣지)까지 미완'임을 명시적으로 인정한다. 도메인 없이 라이브
    엣지를 검증할 방법은 없고, 그 사실을 숨기지 않고 게이트로 박은 것이 정직한 처리다. 이 지적은 SPEC이 이미 답한 것을 다시 말한다.
- issue_id: I-003
  category: risky-assumption
  severity: high
  description: The entire replay-attack mitigation depends on the deployment invariant
    that the origin binds only to 127.0.0.1:8000 and is reachable solely via cloudflared
    (I-002). This is asserted as a required condition but cannot be enforced by Nexus
    code; any misconfiguration (a public port, a reverse proxy, host networking) silently
    reopens the replay hole with exp as the only bound.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: adr-contradiction
  severity: medium
  description: The SPEC reinterprets ADR-0004 §3, which names the tunnel deployment
    mechanism as 'tokens', by asserting the entry now 'also means or Access identity'.
    ADR-0004 is only 'Proposed', ships zero product code, and does not mention Access/JWT/per-identity
    at all; the SPEC is retroactively redefining an ADR decision rather than the ADR
    being amended. This is a de facto contradiction dressed as 'evolution'.
  status: rejected
  disposition_reason: ADR-0004 표의 'tokens'와의 긴장은 §2 non-goal에서 '이 SPEC은 토큰 경로를 삭제하지
    않고 Access 경로를 더한다'로 화해했다. ADR 자체 수정은 별도 ADR 사안이며 이 SPEC 범위 밖.
- issue_id: I-005
  category: missing-invariant
  severity: medium
  description: No invariant governs what happens when auth.access.identities maps
    an email to a clearance/capability set that exceeds what Access policy admits,
    or when the same email is duplicated across identities and default_identity. Precedence
    and uniqueness of email→principal mapping is undefined.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: 'The JWKS single-flight guard (I-007) specifies at most one refresh
    per min_refresh_interval, but there is no invariant covering key-rotation edge
    cases: what happens to an in-flight verification when the cache is replaced mid-request,
    or when a legitimate new kid arrives during the min_refresh_interval cooldown
    (legitimate tokens rejected for up to 60s). The availability trade-off is unstated.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: medium
  description: The forged-token test relies on minting a token 'signed by a different
    key whose kid collides with a real one' returning 401. This assumes the verifier
    selects the key strictly by kid AND cryptographically verifies the signature;
    if kid-collision selection logic ever picks the attacker-supplied key material,
    the assumption breaks. The test asserts the outcome but the design does not state
    the invariant that key material is sourced only from the trusted JWKS, never the
    token.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: The requirement 'the token value never enters a log line, a DB row,
    or an error detail' (§5) is asserted and has a test ('No token value appears in
    any response body, log, or persisted row'), but such negative/absence assertions
    are unbounded — the test can only check known sinks, not all future ones. The
    requirement is not fully verifiable as stated.
  status: rejected
  disposition_reason: '''토큰 값을 로그/DB/error에 남기지 않는다''의 테스트 가능성 지적. §6에 ''no token
    value appears in any response body, log, or persisted row'' 단언이 이미 있다. Notion
    토큰 redaction(SPEC-nexus-notion-connection-health §6)에서 같은 방식으로 실제 테스트했고, 그 패턴을
    그대로 쓴다 — 새로운 미검증 요구가 아니다.'
- issue_id: I-009
  category: undefined
  severity: medium
  description: The prod overlay refuses to boot without either Access config or NEXUS_ALLOW_SHARED_BEARER=1,
    but the semantics, security implications, and capability/clearance of the shared-bearer
    override path under prod are never defined. It reintroduces the exact shared-INTERNAL-key
    hole the SPEC exists to close, with no invariant bounding it.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: unverifiable-claim
  severity: low
  description: The claim that CF_Authorization is HttpOnly and is the browser↔Cloudflare
    session channel (§4.2) is stated as fact but not sourced or version-pinned; Cloudflare
    cookie behavior is external and could change, and nothing tests that Nexus's refusal
    to read it stays correct if the header hand-off changes.
  status: rejected
  disposition_reason: CF_Authorization이 HttpOnly라는 것은 Cloudflare 공식 문서 사실이다. §3/§8이
    라이브 검증 유보를 이미 명시했고, 이 클레임은 Nexus 코드가 의존하는 지점도 아니다(Nexus는 쿠키를 아예 읽지 않는다 — §4.2).
    검증 부담이 우리 코드에 없다.
- issue_id: I-011
  category: scope-creep
  severity: low
  description: Section 4.5 expands beyond wiring Access verification into modifying
    docker-compose prod overlay boot requirements (removing the NEXUS_DEV_TOKEN requirement,
    adding issuer/aud requirements, introducing NEXUS_ALLOW_SHARED_BEARER). Deployment-manifest
    hardening changes are arguably a separate concern from the identity-verifier described
    as the goal.
  status: rejected
  disposition_reason: prod compose가 NEXUS_DEV_TOKEN 요구를 멈추고 Access 설정을 요구하도록 바꾸는 것은
    scope 확장이 아니라 이 SPEC의 핵심이다 — §3이 지목한 '강한 공유키를 요구하는 prod'라는 모순을 닫지 않으면 SPEC의 목표(공유
    bearer 제거)가 성립하지 않는다. 분리 불가.
- issue_id: I-012
  category: risky-assumption
  severity: low
  description: The 'issuer set but Access not actually in front' failure mode assumes
    every request will simply lack the header and 401, calling this 'visibly broken,
    safe direction'. This assumes no intermediate proxy or cached credential can supply
    a header, and assumes operators will notice a fully-locked deployment quickly
    rather than treating it as a transient outage.
  status: rejected
  disposition_reason: '''issuer 설정됨 + Access 실제 없음'' → 모든 요청 401(락다운)은 §4.5가 명시한 fail-closed
    동작이다. ''모든 요청에 Access 헤더가 없다''는 가정은, Access 없이 헤더를 붙일 주체가 없으므로 성립한다(헤더는 Cloudflare
    엣지만 주입). 이미 답한 지점.'
- issue_id: I-013
  category: missing-invariant
  severity: low
  description: The default_identity is guaranteed zero capabilities but its clearance
    defaults to PUBLIC and is operator-settable with no upper bound or validation
    invariant. Nothing prevents an operator from setting default_identity clearance
    to RESTRICTED, silently granting every admitted-but-unmapped email full read access
    — the very risk I-011 raises is only partially mitigated.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-10T11:29:58Z'
---

