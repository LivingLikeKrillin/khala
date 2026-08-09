"""마이그레이션을 도는 잡과 안 도는 잡이 갈라져 있으면, 스키마가 둘이 된다.

2026-08-09: `documents.n_images` 를 더한 마이그레이션 하나가 `nexus (search recall, mecab)` 을
`UndefinedColumnError` 로 무너뜨렸다. 그 잡은 존재한 내내 `init.sql` 만 적용하고 마이그레이션을
안 돌렸고, 형제 잡(`nexus (pytest, postgres)`)은 돌렸다. 한 리포에 스키마가 둘이었던 것이다.

`init.sql` 은 **빈 DB 기준선**이지 정본 스키마가 아니다. DB 를 세우는 모든 잡은 그 뒤에
마이그레이션을 적용해야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _jobs_that_apply_init_sql(text: str) -> list[str]:
    """`init.sql` 을 적용하는 잡 이름들 (nexus 것만 — adept 는 자기 db/init.sql 을 쓴다)."""
    out, current = [], None
    for line in text.splitlines():
        if (m := re.match(r"^  ([a-z0-9-]+):\s*$", line)):
            current = m.group(1)
        if "-f init.sql" in line and current:
            out.append(current)
    return out


def test_every_job_that_seeds_the_schema_also_migrates():
    text = CI.read_text(encoding="utf-8")
    seeding = _jobs_that_apply_init_sql(text)
    assert seeding, "init.sql 을 적용하는 잡을 못 찾았다 — 이 검사가 헛돈다"

    blocks = re.split(r"^  (?=[a-z0-9-]+:\s*$)", text, flags=re.M)
    by_job = {}
    for b in blocks:
        if (m := re.match(r"([a-z0-9-]+):\s*$", b.splitlines()[0] if b.splitlines() else "")):
            by_job[m.group(1)] = b

    for job in seeding:
        body = by_job.get(job, "")
        assert "migrations/" in body or "scripts.migrate" in body, (
            f"잡 '{job}' 이 init.sql 만 적용하고 마이그레이션을 안 돌린다 — "
            f"컬럼 하나만 더해도 이 잡만 깨진다. init.sql 은 기준선이지 정본이 아니다.")


def test_the_check_would_notice_a_job_that_stopped_migrating():
    """이 검사가 실제로 문다는 것. 통과만 보는 검사는 이 리포가 반복해 잡아낸 무효 대조군이다."""
    fake = (
        "jobs:\n"
        "  seeder:\n"
        "    steps:\n"
        "      - run: psql \"$DATABASE_URL\" -f init.sql\n"
        "      - run: pytest\n")
    assert _jobs_that_apply_init_sql(fake) == ["seeder"]
    assert "migrations/" not in fake and "scripts.migrate" not in fake
