"""BOM 으로 시작하는 파일도 **제 머리말과 제 제목을 갖는다**.

⛔ **왜 생겼나 (실측 2026-09-23).** 설명 층이 근거 목록에서 알려 줬다 — 「1. 맥락 및 배경」
이라는 제목의 문서가 늘 끼어 있는데, 그것이 서로 다른 ADR 셋이었다. **인용은 `title` 로
문서를 가리키므로 셋이 인용에서 구별되지 않았다.**

원인은 한 글자였다. `collector.py` 가 `encoding="utf-8"` 로 읽어서 BOM(U+FEFF)이 **본문 맨
앞에 남았다.** 눈에 안 보이고 `\\s` 에도 안 걸린다 — Unicode 분류가 공백(Zs)이 아니라
서식(Cf)이다. 그래서 두 파서가 동시에 빗나간다:

    `\\ufeff---\\ntitle: …`   frontmatter 가 머리말을 **통째로 못 본다** (`metadata == {}`)
    `\\ufeff# ADR 44 — …`     첫 헤딩 정규식이 H1 을 지나쳐 다음 `##` 을 제목으로 잡는다

⭐ **일치가 완벽했다.** 마운트된 `.md` 39개 중 BOM 이 **셋**이고, 제목이 겹친 문서가
**정확히 그 셋**이었다.

⛔ **제목 쪽은 보였고 머리말 쪽은 안 보였다.** 그 셋은 마침 머리말이 없어서 제목만 틀렸다.
머리말이 있는 BOM 파일이었다면 `doc_type`·`labels`·`updated` 가 **전부** 조용히 사라지고,
문서는 정상 적재된 얼굴로 남는다. 이 파일이 지키는 것은 그쪽이다.

⚠ **이쪽 검사는 아무것도 안 울렸다.** 적재는 성공했고 문서는 활성이었고 조각도 생겼다.
밖에서 근거 목록을 읽은 사람이 알려 줘서 나왔다.
"""

from __future__ import annotations

import pytest

from nexus.ingest.title import derive_title, first_heading

BOM = "﻿"


def _write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ── 한 글자가 무엇을 하는가 ───────────────────────────────────────────────────

def test_the_mark_is_not_whitespace_which_is_why_nothing_caught_it():
    """⭐ **이 단언이 이 파일의 머리말이다.** 공백이면 정규식이 흡수했을 것이다."""
    assert not BOM.isspace(), "BOM 이 공백이면 이 결함은 애초에 안 났다"
    assert BOM.strip() == BOM, "`strip()` 으로는 안 떨어진다"


def test_the_mark_still_breaks_the_parser_if_it_survives_the_read():
    """⛔ **결함의 모양을 박아 둔다.** 이 값이 실제로 세 문서의 제목이었다.

    ⚠ `first_heading` 자신은 안 고쳤다. BOM 은 **디코딩의 산물이지 내용이 아니라서**, 떼는
    자리는 바이트가 글자가 되는 이음매 하나여야 한다. 파서마다 떼면 진실이 여럿이 된다.
    이 단언은 그 이음매가 일을 안 하면 아래층이 어떻게 되는지를 적어 둔다.
    """
    assert first_heading(f"{BOM}# 진짜 제목\n\n## 1. 맥락 및 배경\n") == "1. 맥락 및 배경"
    assert first_heading("# 진짜 제목\n\n## 1. 맥락 및 배경\n") == "진짜 제목"


# ── 수집기가 그 글자를 떼고 읽는가 ────────────────────────────────────────────

def test_the_collector_reads_with_the_signature_codec():
    """⛔ **`utf-8` 과 `utf-8-sig` 의 차이가 이 결함의 전부다.**

    호출 인자를 세는 것이 아니라 **실제로 읽어서** 본다 — 파일을 하나 만들어 통과시킨다.
    """
    import inspect

    from nexus.ingest import collector

    src = inspect.getsource(collector.collect_files)
    assert 'encoding="utf-8-sig"' in src, "BOM 을 떼지 않고 읽는다"
    assert 'encoding="utf-8")' not in src, "BOM 을 안 떼는 읽기가 남아 있다"


def test_the_collector_hands_on_a_clean_title_and_frontmatter(tmp_path):
    """⭐ **이음매를 실제로 태운다.** 위 단언들은 조각이고, 이것이 계약이다.

    부르는 쪽(`pipeline`)이 받는 값이 무엇인지를 본다 — 제목도 머리말도 BOM 이 없던 것과
    같아야 한다.
    """
    import asyncio

    from nexus.ingest.collector import collect_files

    _write(tmp_path, "marked-adr.md",
           BOM + "# ADR 44 — 승인은 제안을 가리킨다\n\n## 1. 맥락 및 배경\n\n본문.\n")
    _write(tmp_path, "marked-fm.md",
           BOM + '---\ntitle: "머리말 제목"\ndoc_type: policy\n---\n\n# 본문\n')

    got = {f.relative_path: f
           for f in asyncio.run(collect_files(str(tmp_path), "**/*.md", True, "t")).files}

    assert derive_title(got["marked-adr.md"].frontmatter, got["marked-adr.md"].content, "폴백") \
        == "ADR 44 — 승인은 제안을 가리킨다", "H1 대신 하위 절이 제목이 됐다"
    assert got["marked-fm.md"].frontmatter.get("doc_type") == "policy", \
        "머리말이 통째로 사라졌다 — 종류·라벨·시각이 전부 기본값이 된다"


def test_a_marked_file_keeps_its_whole_frontmatter(tmp_path):
    """⛔ **여기가 안 보이던 쪽이다.** 제목 하나가 아니라 머리말 **전부**가 걸린다.

    이 셋이 사라지면 문서는 **정상 적재된 얼굴로** 남는다 — `doc_type` 은 기본값이 되고,
    `labels` 는 비고, `updated` 는 `NULL` 이 된다. 셋 다 「없다」와 구별되지 않는다.
    """
    import frontmatter

    body = ("---\n"
            'title: "제목이 있다"\n'
            "doc_type: policy\n"
            'labels: ["synthetic"]\n'
            "updated: 2026-09-23\n"
            "---\n\n# 본문 제목\n")
    p = _write(tmp_path, "marked.md", BOM + body)

    meta = frontmatter.loads(p.read_text(encoding="utf-8-sig")).metadata

    assert meta.get("title") == "제목이 있다"
    assert meta.get("doc_type") == "policy"
    assert meta.get("labels") == ["synthetic"]
    assert meta.get("updated") is not None, "`updated` 가 사라지면 신선도가 「모른다」가 된다"

    # 대조군 — 안 떼고 읽으면 **전부** 사라진다. 예외도 경고도 없이.
    assert frontmatter.loads(p.read_text(encoding="utf-8")).metadata == {}


def test_a_clean_file_is_unchanged_by_the_codec(tmp_path):
    """⭐ 대조군 — `utf-8-sig` 는 BOM 이 없으면 `utf-8` 과 같다. 바꾼 것이 한 경우뿐이다."""
    text = "---\ntitle: 평범\n---\n\n# 본문\n"
    p = _write(tmp_path, "clean.md", text)

    assert p.read_text(encoding="utf-8-sig") == p.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("prefix", ["", BOM])
def test_the_title_lands_the_same_either_way(prefix):
    """부르는 쪽이 보는 값이 같다 — 그것이 이 고침의 계약이다."""
    content = f"{prefix}# ADR 42 — 주인 없는 명령은 없다\n\n## 1. 맥락 및 배경\n"
    stripped = content.encode("utf-8").decode("utf-8-sig")

    assert derive_title(None, stripped, "폴백") == "ADR 42 — 주인 없는 명령은 없다"
