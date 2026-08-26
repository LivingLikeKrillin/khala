-- 035: 재수집 덮어쓰기 신호에 **문서 수**를 나란히 둔다.
--
-- **무엇이 틀렸나.** 034 는 이 신호의 테넌트 오염을 고쳤지만, 남은 절반은 그대로였다.
-- 2026-08-26 라이브 `default` 실측:
--
--     이벤트 53 · 그 이벤트가 닿은 **문서 18** · 그중 38건이 사흘(08-08·08-10·08-11)에
--     몰려 있다. 활성 문서는 126.
--
-- 즉 이 수는 "코퍼스가 얼마나 흔들리는가" 가 아니라 **"우리가 같은 문서 열여덟 개를 몇 번
-- 다시 적재했는가"** 다. 그 사흘은 파이프라인을 고치며 재적재를 돌린 날이고, 문서가 바뀐
-- 날이 아니다. ADR-0006 이 이 신호를 demand-pull 방아쇠로 지정했으므로, #308 이 고친 것과
-- **같은 종류의 오염이 한 겹 더 남아 있었다.**
--
-- **ADR 이 정의한 수는 안 건드린다.** ADR-0006 은 신호 ①을 *events* 로 적었다. 그 컬럼의
-- 뜻을 바꾸면 승인된 문서와 코드가 조용히 갈라진다. 그래서 **더한다** — 같은 줄에 분모가
-- 함께 서면, 53 을 혼자 읽던 사람이 53/18 을 읽게 된다.
--
-- **이 컬럼도 "우리 재적재 vs 문서 변경" 을 가르지는 못한다.** 그것은 데이터로 못 가른다
-- (재적재도 문서 편집도 content_hash 를 바꾼다). 가르려면 삽입 시점에 원인을 적어야 하고,
-- 그건 별도 SPEC 이다. 여기서 하는 것은 **부풀림을 걷어내는 것**까지다.

-- **`CREATE OR REPLACE` 로는 못 한다.** Postgres 는 뷰 컬럼을 **뒤에만** 붙일 수 있고, 이
-- 컬럼은 짝이 되는 `events` 바로 옆에 서야 읽힌다(그 옆이 아니면 분모로 안 읽힌다). 그래서
-- 의존 순서대로 지우고 다시 만든다 — 뷰뿐이라 데이터는 움직이지 않는다.
DROP VIEW IF EXISTS v_entropy_signals;
DROP VIEW IF EXISTS v_entropy_signals_by_tenant;

CREATE VIEW v_entropy_signals_by_tenant AS
WITH tenants AS (
    SELECT tenant FROM documents WHERE status='active'
    UNION
    SELECT tenant FROM doc_reingest_events
),
reingest AS (
    SELECT tenant, count(*) AS n, count(DISTINCT rid) AS docs
      FROM doc_reingest_events GROUP BY tenant
),
dups AS (
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
       COALESCE(r.n,    0)::bigint AS reingest_overwrite_events,
       COALESCE(r.docs, 0)::bigint AS reingest_overwrite_docs,
       COALESCE(dp.n,   0)::bigint AS exact_dup_pairs,
       COALESCE(cl.n,   0)::bigint AS title_stem_collisions,
       COALESCE(s.n,    0)::bigint AS supersessions,
       COALESCE(il.n,   0)::bigint AS identityless_chunks
  FROM tenants t
  LEFT JOIN reingest     r  ON r.tenant  = t.tenant
  LEFT JOIN dups         dp ON dp.tenant = t.tenant
  LEFT JOIN collisions   cl ON cl.tenant = t.tenant
  LEFT JOIN supers       s  ON s.tenant  = t.tenant
  LEFT JOIN identityless il ON il.tenant = t.tenant;

-- 전역은 테넌트별의 합이다(034 와 같은 이유). **문서 수는 테넌트를 가로질러 겹치지 않는다** —
-- rid 는 테넌트 안에서만 뜻을 가지므로 합이 곧 문서 수다.
CREATE VIEW v_entropy_signals AS
  SELECT COALESCE(sum(reingest_overwrite_events), 0)::bigint AS reingest_overwrite_events,
         COALESCE(sum(reingest_overwrite_docs),   0)::bigint AS reingest_overwrite_docs,
         COALESCE(sum(exact_dup_pairs),           0)::bigint AS exact_dup_pairs,
         COALESCE(sum(title_stem_collisions),     0)::bigint AS title_stem_collisions,
         COALESCE(sum(supersessions),             0)::bigint AS supersessions,
         COALESCE(sum(identityless_chunks),       0)::bigint AS identityless_chunks
    FROM v_entropy_signals_by_tenant;
