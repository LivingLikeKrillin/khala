-- 034: 엔트로피 신호를 **테넌트별로** 가르고, 신원 없는 청크를 신호에 추가한다.
--
-- **왜 고치나 — 이 뷰는 하중을 받는다.** ADR-0006 은 `v_entropy_signals` 를 Slice-2 작업들의
-- demand-pull 방아쇠로 지정했고, 여러 SPEC 처분이 *"deferred — gated on v_entropy_signals"*
-- 로 보류돼 있다(해시 정규화 I-003 · freshness TTL/rank · 넛지). 즉 **무엇을 만들지가 이
-- 숫자로 결정된다.**
--
-- 그런데 뷰가 전역이었다. 2026-08-25 실측:
--
--     전역          정확중복쌍 61,425 · 제목충돌 221
--     라이브 default 정확중복쌍      0 · 제목충돌   2
--
-- 61,425 중 34,165 는 **같은 코퍼스를 평가 테넌트에 복사한 것**이고 나머지는 아예 테넌트를
-- 가로지른 쌍이다. 버릴 테넌트(ko_eval_*, merge_probe, tool_probe)가 신호를 삼켰다. 이 숫자를
-- 본 사람은 중복이 재앙이라고 결론 내리지만, 실제 팀 코퍼스의 중복은 **0** 이다.
-- 게이트가 오염된 계측기를 읽고 있었다.
--
-- **테넌트를 가로지르는 쌍은 공존이 아니다.** 테넌트는 격리 경계다 — 검색은 절대 둘을 같이
-- 보지 않으므로, 그 쌍은 어느 답변에서도 충돌하지 않는다. 그래서 자기 테넌트 안에서만 센다.
--
-- **새 신호 `identityless_chunks`.** 색인 텍스트에 문서 신원이 하나도 없는 청크다.
-- `search_text` 는 `COALESCE(context_prefix, '[' || section_path || ']') || ' ' || chunk_text`
-- 이므로(001·030), `context_prefix` 가 NULL 이고 `section_path` 가 `root` 이고 본문에도 제목이
-- 없으면 **그 청크는 무엇에 관한 것인지를 색인에 한 글자도 안 남긴다.**
-- 라이브 default 에서 407 중 91 건(22%)이 그렇다. 이 수는 이미 한 번 측정됐는데
-- (`docs/KOREAN_SEARCH_QUALITY.md` §3.6, 2026-08-15, 309 중 90) **읽는 곳이 없어서** 문서
-- 한 줄로 남고 끝났다. 여기에 두면 `nexus entropy-signals` 가 매번 그것을 낸다.
--
-- ⚠ 판정식은 §3.6 이 실제로 쓴 것 그대로다(`section_path='root'`). "접두사·섹션·본문 어디에도
-- 제목이 없다" 는 더 엄밀해 보이는 판정식도 재 봤지만, 저장된 제목과 섹션 표기가 **형식만**
-- 달라도 걸려서 한 테넌트를 100% 로 찍었다. 방어할 수 없는 숫자는 신호가 아니다.
--
-- 이 마이그레이션은 **읽기 전용 뷰만** 바꾼다. 데이터는 건드리지 않는다.

CREATE OR REPLACE VIEW v_entropy_signals_by_tenant AS
WITH tenants AS (
    SELECT tenant FROM documents WHERE status='active'
    UNION
    SELECT tenant FROM doc_reingest_events
),
reingest AS (
    SELECT tenant, count(*) AS n FROM doc_reingest_events GROUP BY tenant
),
dups AS (
    -- 같은 테넌트 안의 쌍만. `d1.tenant = d2.tenant` 가 이 마이그레이션의 핵심 한 줄이다.
    SELECT d1.tenant, count(*) AS n
      FROM documents d1
      JOIN documents d2
        ON d1.content_hash = d2.content_hash
       AND d1.rid < d2.rid
       AND d1.tenant = d2.tenant
     WHERE d1.status='active' AND d2.status='active' AND d1.content_hash <> ''
     GROUP BY d1.tenant
),
collisions AS (
    SELECT tenant, count(*) AS n
      FROM (SELECT tenant, norm_title_stem(title) AS stem
              FROM documents WHERE status='active'
             GROUP BY tenant, norm_title_stem(title)
            HAVING count(*) > 1) g
     GROUP BY tenant
),
supers AS (
    SELECT tenant, count(*) AS n FROM documents WHERE superseded_by <> '' GROUP BY tenant
),
identityless AS (
    SELECT c.tenant, count(*) AS n
      FROM chunks c
      JOIN documents d ON d.rid = c.doc_rid
     WHERE c.status='active' AND d.status='active'
       AND c.context_prefix IS NULL
       AND c.section_path = 'root'
       AND (d.title = '' OR position(d.title in c.chunk_text) = 0)
     GROUP BY c.tenant
)
SELECT t.tenant,
       COALESCE(r.n,  0)::bigint AS reingest_overwrite_events,
       COALESCE(dp.n, 0)::bigint AS exact_dup_pairs,
       COALESCE(cl.n, 0)::bigint AS title_stem_collisions,
       COALESCE(s.n,  0)::bigint AS supersessions,
       COALESCE(il.n, 0)::bigint AS identityless_chunks
  FROM tenants t
  LEFT JOIN reingest     r  ON r.tenant  = t.tenant
  LEFT JOIN dups         dp ON dp.tenant = t.tenant
  LEFT JOIN collisions   cl ON cl.tenant = t.tenant
  LEFT JOIN supers       s  ON s.tenant  = t.tenant
  LEFT JOIN identityless il ON il.tenant = t.tenant;

-- 전역 뷰는 **테넌트별 뷰의 합**으로 다시 정의한다. 컬럼 이름·순서·타입은 그대로이므로 기존
-- 소비자는 안 깨지고, 테넌트를 가로지르던 쌍만 사라진다(그것이 고치는 대상이다).
-- 행이 하나도 없어도 한 행을 내야 한다 — 기존 계약이 `fetch_one` 이다. 그래서 COALESCE.
CREATE OR REPLACE VIEW v_entropy_signals AS
  SELECT COALESCE(sum(reingest_overwrite_events), 0)::bigint AS reingest_overwrite_events,
         COALESCE(sum(exact_dup_pairs),           0)::bigint AS exact_dup_pairs,
         COALESCE(sum(title_stem_collisions),     0)::bigint AS title_stem_collisions,
         COALESCE(sum(supersessions),             0)::bigint AS supersessions,
         COALESCE(sum(identityless_chunks),       0)::bigint AS identityless_chunks
    FROM v_entropy_signals_by_tenant;
