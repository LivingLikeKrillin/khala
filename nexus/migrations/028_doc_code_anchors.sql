-- 028_doc_code_anchors: 문서가 코드를 가리키는 **타입 있는 참조**를 저장한다.
-- (SPEC-nexus-doc-code-anchors §3.1/§3.3, 안 1~3단위)
--
-- **왜.** "이 문서 낡았나" 를 사람이 커밋을 세어 판정하고 있었다. 문서가 코드 안으로 들어가는
-- 참조를 들고 있으면 그 판정이 **조인 한 번**이 된다 — 심볼이 아직 해소되는가, 그 텍스트가
-- 바뀌었는가. 모델을 부르지 않으므로 오탐이 확률이 아니라 버그다.
--
-- ⚠ **여기 코드 본문은 저장하지 않는다.** 줄 번호와 `span_hash`(sha256) 만 남긴다. 스니펫을
--    넣고 싶어지는 순간이 오면 — 디버깅이 편하다는 이유로 — 그때가 이 표가 대상 저장소의
--    소스를 담기 시작하는 순간이다. 해시는 변경을 감지하는 데 충분하고, 원문은 체크아웃에 있다.
--    `tests/test_code_symbols.py` 가 이 불변식을 검사한다.
--
-- **멱등성.** 스캔은 (tenant, repo) 단위로 이전 스캔을 **대체**한다(한 트랜잭션). 누적하면
-- 사라진 심볼이 남아 `orphaned` 가 계산 불가능해진다 — 그게 이 표의 존재 이유인데.

CREATE TABLE IF NOT EXISTS code_symbols (
    tenant       text        NOT NULL,
    repo         text        NOT NULL,
    file_path    text        NOT NULL,
    symbol_kind  text        NOT NULL,
    symbol_name  text        NOT NULL,
    start_line   int         NOT NULL,
    end_line     int         NOT NULL,
    -- sha256(정규화된 심볼 소스). 정규화 규칙은 index/symbols.py:normalize_span 이 정본이다.
    -- CRLF 통일이 없으면 Windows 체크아웃에서 전 앵커가 뒤집힌다 (SPEC §3.1).
    span_hash    text        NOT NULL,
    scan_commit  text        NOT NULL,
    scanned_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, repo, file_path, symbol_kind, symbol_name, start_line)
);

-- 해소 키는 symbol_name 단독이다 (SPEC §3.3) — 문서는 파일명을 거의 부르지 않는다.
CREATE INDEX IF NOT EXISTS idx_code_symbols_name
    ON code_symbols (tenant, repo, symbol_name);

-- 스캔 1회 = 1행. 가드(§3.5)와 분모(§6.6)가 여기서 나온다.
CREATE TABLE IF NOT EXISTS code_scans (
    tenant         text        NOT NULL,
    repo           text        NOT NULL,
    scan_commit    text        NOT NULL,
    symbol_count   int         NOT NULL,
    -- 파싱하지 못한 파일 수. 커버리지를 비율로만 보고하면 거짓이 되므로 분모를 함께 남긴다.
    unparsed_files int         NOT NULL DEFAULT 0,
    scanned_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, repo)
);

-- 바인딩된 앵커. 유일 해소된 후보만 여기 온다.
CREATE TABLE IF NOT EXISTS doc_code_anchors (
    chunk_rid   text        NOT NULL REFERENCES chunks(rid) ON DELETE CASCADE,
    tenant      text        NOT NULL,
    repo        text        NOT NULL,
    candidate   text        NOT NULL,   -- 문서에 적힌 백틱 토큰 그대로
    edge_type   text        NOT NULL DEFAULT 'mentions',
    symbol_name text        NOT NULL,
    file_path   text        NOT NULL,
    span_hash   text        NOT NULL,   -- 바인딩 시점의 값. 재검사가 이것과 비교한다
    scan_commit text        NOT NULL,
    bound_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_rid, candidate)
);

CREATE INDEX IF NOT EXISTS idx_doc_code_anchors_symbol
    ON doc_code_anchors (tenant, repo, symbol_name);

-- 거부도 **행으로 남긴다** (SPEC §3.3). 버리면 재바인딩이 불가능해지고, 스캔보다 먼저 적재된
-- 문서는 영구히 미앵커로 남는다 — 그러면 수율 수치가 코퍼스가 아니라 실행 순서를 재게 된다.
CREATE TABLE IF NOT EXISTS doc_code_refusals (
    chunk_rid   text        NOT NULL REFERENCES chunks(rid) ON DELETE CASCADE,
    tenant      text        NOT NULL,
    repo        text        NOT NULL,
    candidate   text        NOT NULL,
    reason      text        NOT NULL,   -- 'unresolved' | 'ambiguous'
    match_count int         NOT NULL DEFAULT 0,
    refused_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_rid, candidate)
);

CREATE INDEX IF NOT EXISTS idx_doc_code_refusals_retry
    ON doc_code_refusals (tenant, repo, reason);
