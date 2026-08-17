-- 029_code_deleted_symbols: **한때 있었고 지워진 이름**을 커밋·날짜와 함께 남긴다.
-- (SPEC-nexus-doc-code-anchors §3.3 분류 / ②b 읽기 경로)
--
-- **왜.** 문서가 부르는데 지금 코드에 없는 이름에는 서로 다른 이유가 있고 처분도 다르다:
-- 프레임워크가 주는 외부 타입(문서 잘못 아님) · 아직 안 만든 것(설계 문서에선 정상) ·
-- **지워진 것**(드리프트). 세 번째만이 읽는 사람에게 조치를 요구하고, 그것만 여기 온다.
-- 라이브 실측에서 이 셋의 비율은 99 : 1,354 : 63 이었다 — 안 가르고 다 올리면 목록이
-- 신뢰를 잃는다.
--
-- **이름 단위로 저장한다.** 거부 행(`doc_code_refusals`)마다 판정을 복사하지 않는다:
-- 판정은 (저장소, 이름)의 성질이고 청크의 성질이 아니다. 이름으로 두면 스캔 이후에 적재된
-- 문서도 재분류 없이 곧바로 이 표의 덕을 본다 — 조인 한 번이면 되기 때문이다.
--
-- **git 은 스캔 시점에 한 번만 부른다.** `git log --diff-filter=D` 한 번이 전 이력을 준다
-- (`index/history.py:deletion_map`). 이름마다 `git log` 를 돌리면 몇 분이 걸리고, 그 비용이
-- 곧 이 보고서를 아무도 안 돌리는 이유가 된다.
--
-- **멱등성.** 스캔은 (tenant, repo) 단위로 이전 판정을 **대체**한다. 누적하면 되살아난
-- 이름이 영원히 "삭제됨" 으로 남는다.

CREATE TABLE IF NOT EXISTS code_deleted_symbols (
    tenant       text        NOT NULL,
    repo         text        NOT NULL,
    symbol_name  text        NOT NULL,
    -- 삭제 커밋. 사람이 `git show` 로 바로 갈 수 있는 짧은 해시다.
    deleted_commit text      NOT NULL,
    -- YYYY-MM-DD. 시각까지는 필요 없다 — 읽는 사람이 판단하는 단위는 날짜다.
    deleted_date text        NOT NULL,
    -- 커밋 제목. **왜 지웠는지가 곧 처방**이다("refactor: unify DTO naming" 은 이름을
    -- 바꾸라는 말이고, "remove dead code" 는 문단을 지우라는 말이다).
    subject      text        NOT NULL,
    -- 삭제된 파일 경로. 소스 본문은 여기에도 들어가지 않는다 (028 의 불변식).
    file_path    text        NOT NULL,
    scan_commit  text        NOT NULL,
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, repo, symbol_name)
);
