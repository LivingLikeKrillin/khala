"""내 **보고 문장**에 용어 규칙을 거는 훅.

**왜 있나.** `.md` 를 지키는 검사(`scripts/check_terms.py`)는 전수 작업까지 끝냈는데, 정작
그 규칙을 넣은 당일부터 내가 **대화에서** 세 번 다시 어겼다. 검사기가 diff 만 보기 때문이다 —
내가 사람에게 하는 말은 아무것도 안 보고 있었다. `Stop` 훅에는 그 턴의 응답 전문이
`last_assistant_message` 로 들어오고, `{"decision": "block"}` 으로 끝내려는 것을 막을 수 있다.

**판정은 새로 만들지 않는다.** 경계 규칙(합성어·단위·조사·코드 스팬)은 `check_terms` 가 이미
갖고 있고, 그것을 복제하면 두 판정이 갈라진다. 이 파일이 더하는 것은 **대화에만 있는 것**
셋뿐이다: 펜스 코드 블록 · 인용 줄 · 재귀 방지.

⚠ **거짓 양성 하나면 매 턴이 막힌다.** 그래서 이 스위트의 절반은 "막지 말아야 할 것" 이다.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))

import terms_guard  # noqa: E402

BANNED = {"자": "테스트 · 평가 하니스", "그물": "회귀 검사"}


# ── 막아야 할 것 ───────────────────────────────────────────────────────────

def test_a_coined_word_in_my_report_is_blocked():
    hits = terms_guard.offenders("이 자가 7.7/8 로 통과했다", BANNED)
    assert [h[0] for h in hits] == ["자"]


def test_the_real_slip_that_prompted_this_hook():
    """실물(2026-08-27). 뜻은 「8월 25일자」의 날짜 접미사였지 금지어가 아니었다 — 그런데
    **읽는 사람이 못 가른다.** 숫자 경계는 붙었을 때(`25자`)만 단위로 봐주므로 띄우면 걸리고,
    그게 맞다. 처방은 예외를 다는 게 아니라 풀어 쓰는 것이다."""
    hits = terms_guard.offenders("미추적 2건은 8/25 자 로컬 잔여물이다", BANNED)
    assert [h[0] for h in hits] == ["자"]


def test_the_reason_says_what_to_write_instead():
    """막기만 하고 대안을 안 주면 다음 문장도 같은 자리에서 난다."""
    reason = terms_guard.reason(terms_guard.offenders("이 자가 통과했다", BANNED))
    assert "자" in reason and "테스트" in reason


# ── 막으면 안 되는 것 ──────────────────────────────────────────────────────

def test_a_code_span_is_how_i_quote_the_rule_itself():
    """이 규칙을 사람에게 설명하려면 그 말을 인용해야 한다. 백틱이 그 자리다."""
    assert terms_guard.offenders("`자` 대신 테스트라고 쓴다", BANNED) == []


def test_a_fenced_block_is_not_my_prose():
    """⛔ 이 자리가 새면 훅이 곧 꺼진다 — 나는 매 턴 diff·명령 출력을 붙여넣는다."""
    message = "\n".join([
        "고친 결과다:",
        "```",
        "-  이 자가 측정하는 것",
        "+  이 테스트가 측정하는 것",
        "```",
        "끝.",
    ])
    assert terms_guard.offenders(message, BANNED) == []


def test_a_quoted_line_is_someone_elses_words():
    """인용은 기록물과 같은 규칙이다 — 남이 그때 쓴 말을 내가 고쳐 옮기면 인용이 아니다."""
    assert terms_guard.offenders("> 이 자가 무엇을 측정하나\n\n그 말은 이제 안 쓴다.", BANNED) == []


def test_compounds_and_units_still_pass():
    """`check_terms` 의 경계 규칙을 그대로 쓰는지 보는 자리. 여기서 갈라지면 두 판정이 된다."""
    for line in ("사용자 12명", "본문 3,000자", "숫자를 세었다", "자동으로 돈다"):
        assert terms_guard.offenders(line, BANNED) == [], line


# ── 훅으로서 ───────────────────────────────────────────────────────────────

def _run(payload: dict, monkeypatch) -> tuple[int, str]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    code = terms_guard.main()
    return code, out.getvalue()


def test_a_clean_message_ends_the_turn(monkeypatch):
    code, out = _run({"last_assistant_message": "테스트 7/8 통과."}, monkeypatch)
    assert code == 0 and out.strip() == ""


def test_a_dirty_message_blocks_with_a_reason(monkeypatch):
    code, out = _run({"last_assistant_message": "이 자가 통과했다."}, monkeypatch)
    assert code == 0, "훅 자체는 성공해야 한다 — 판정은 stdout 의 JSON 이다"
    verdict = json.loads(out)
    assert verdict["decision"] == "block"
    assert "자" in verdict["reason"]


def test_it_blocks_at_most_once_per_turn(monkeypatch):
    """`stop_hook_active` 는 이미 한 번 막고 다시 온 것이다. 여기서 또 막으면 무한이 된다 —
    **막힌 세션은 되살릴 방법이 없다.** 한 번 알려 주는 것으로 족하다."""
    code, out = _run(
        {"last_assistant_message": "이 자가 통과했다.", "stop_hook_active": True}, monkeypatch)
    assert code == 0 and out.strip() == ""


def test_it_fails_open(monkeypatch):
    """훅이 죽어서 매 턴이 막히는 것이 이 훅이 막으려는 것보다 훨씬 비싸다."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json at all"))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert terms_guard.main() == 0 and out.getvalue().strip() == ""


def test_an_unreadable_glossary_does_not_block(monkeypatch, tmp_path):
    monkeypatch.setattr(terms_guard, "GLOSSARY", tmp_path / "없다.md")
    code, out = _run({"last_assistant_message": "이 자가 통과했다."}, monkeypatch)
    assert code == 0 and out.strip() == ""


# ── 정본과의 결속 ──────────────────────────────────────────────────────────

def test_the_live_glossary_is_what_the_hook_enforces():
    """목록을 사본으로 들면 부패한다 — 훅도 `GLOSSARY.md` 를 읽는다."""
    banned = terms_guard.load_banned()
    assert "자" in banned and "그물" in banned


# ── 실제로 돌 자리에서 ─────────────────────────────────────────────────────

def test_it_survives_a_cp949_console():
    """⛔ **이 자리에서 훅이 한 번 죽었다** — 그리고 위의 단위 테스트는 전부 초록이었다.

    훅의 stdin/stdout 은 콘솔 코드페이지로 해석된다(한국어 Windows = `cp949`). 한글 페이로드를
    문자열로 읽으면 조용히 뭉개지고, 그러면 어떤 말도 안 걸린 채 턴이 끝난다. 그래서 이
    검사는 함수를 부르지 않고 **훅을 훅으로 돌린다**(`-S -E`, 설정에 적힌 그대로).
    """
    import os
    import subprocess

    # 코드페이지를 **강제**한다. 안 그러면 이 검사는 한국어 Windows 에서만 이가 있고
    # UTF-8 인 CI 에서는 언제나 초록이다 — 즉 결함이 나던 바로 그 환경에서만 도는 검사가 된다.
    env = dict(os.environ, PYTHONIOENCODING="cp949")
    payload = json.dumps({"last_assistant_message": "이 자가 통과했다."}, ensure_ascii=False)
    proc = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts" / "hooks" / "terms_guard.py")],
        input=payload.encode("utf-8"), capture_output=True, env=env)
    assert proc.returncode == 0, proc.stderr[-400:]
    verdict = json.loads(proc.stdout.decode("utf-8"))
    assert verdict["decision"] == "block"
    assert "자" in verdict["reason"], "한글이 왕복하지 못하면 이유가 전달되지 않는다"


def test_the_settings_file_wires_this_hook():
    """훅은 등록돼야 돈다. 파일만 있고 배선이 없으면 **없는 검사**다."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"]
                for entry in settings.get("hooks", {}).get("Stop", [])
                for h in entry.get("hooks", [])]
    assert any("terms_guard.py" in c for c in commands), commands
