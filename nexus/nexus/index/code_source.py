"""CodeValueResolver — 코드 상수의 *현재값*을 읽고 (상대경로+심볼) hash를 낸다.

MVP: Java `static final` 상수. 'System decides, LLM narrates' — 파싱은 결정론, LLM 미개입.
값을 복사 저장하지 않고 코드를 가리켜 조회 시점에 재읽기(anti-shelfware).

**모호하면 답하지 않는다.** 이 모듈의 값은 `claims/answer.py` 를 거쳐
*"현재 200 (확실: 코드 상수 …)"* 로 나간다 — 그 문장은 확신을 약속하므로, 확신할 수 없을 때
아무 값이나 돌려주는 것은 이 모듈이 할 수 있는 가장 나쁜 일이다.

⚠ 2026-08-25 실측이 그 나쁜 일을 하고 있음을 보여줬다. 첫 판은 `source` 의 한정자를 버리고
(`rpartition(".")` 로 심볼만 취함) `*.java` 전체에서 **첫 매치**를 돌려줬다. 그래서:

  · 존재하지 않는 클래스명으로도 값이 나왔다 (`SomeClass.MAX_PAGE_SIZE` → `200`).
  · 대상 코드베이스에 해석 가능한 상수 이름 364개 중 **80개가 두 파일 이상**에 있고
    **40개는 값이 서로 다르다.** 그 40개의 답은 파일 열거 순서가 정했다.
  · 테스트 픽스처도 같이 훑어서 `EMAIL` 이 `"test@example.com"` 으로 잡힐 수 있었다.
  · `rglob` 순서는 OS·파일시스템에 달렸으므로 **같은 체크아웃이 다른 답을 낼 수 있었다.**

`claims` 가 0행이라 아직 아무도 이 값을 받지 않았다. 심기 전이 고칠 때다.

⚠ **범위 결함 (2026-08-30 실측).** 이 해석기는 `static final` 상수만 읽었다. 그런데 실제
Java 코드베이스에서 *"몇 자까지"* 같은 제약은 상수가 아니라 **어노테이션 인자**에 산다.
팀 코드를 열어 보니 문서와 대 볼 값이 정확히 그 모양이었다 — `@Size(max = 100)`(요청 검증)과
`@Column(length = 20)`(저장 한계). 상수만 읽는 해석기는 실물에 거의 닿지 못한다. 그래서 두
번째 형태를 받는다:

    CreatePartyroomRequest.title@Size.max

그리고 여기서 한정자는 상수 때보다 **더** 중요하다. 같은 코드베이스에서 `nickname` 에 걸린
`@Size(max = …)` 가 세 클래스에서 64, 다른 한 클래스에서 20 이었다. 한정자 없이 답하면
어느 화면의 규칙인지 모르는 값을 확신하는 문장으로 내보내게 된다.
"""


from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ResolvedValue:
    found: bool
    value: str | None = None
    rel_path: str | None = None
    symbol: str | None = None
    symbol_hash: str | None = None
    #: 못 찾았거나 **거절한** 이유. 호출부(`ValueQueryService`)가 그대로 사람에게 전한다 —
    #: "심볼이 없다" 와 "모호해서 답하지 않았다" 는 처방이 다르다(전자는 claim 수정, 후자는
    #: 한정자 추가). 뭉뚱그리면 어느 쪽인지 알 수 없다.
    reason: str = ""


#: 이 파일이 어떤 타입을 선언하는가. 한정자(`PlanPolicy.X` 의 `PlanPolicy`)를 **실제로** 쓰기
#: 위한 것이다. Java 는 보통 파일명 = 공개 타입명이지만, 중첩/보조 타입도 있으므로 둘 다 본다.
_DECL = re.compile(r"\b(?:class|interface|enum|record)\s+(\w+)")

#: 값의 출처가 될 수 없는 경로.
#:
#: · 테스트 소스 — 테스트 상수는 **제품의 현재값이 아니다**. 섞으면 `"test@example.com"` 이
#:   운영 값으로 나간다(실측된 모양이다).
#: · 빌드 산출물 — 파생물이다. 여기서 읽으면 "현재값" 이 **마지막 빌드 시점의 값**이 되고,
#:   소스를 고치고 빌드하지 않은 상태에서 조용히 낡은 답을 낸다.
_SKIP_PARTS = ("/src/test/", "/build/", "/target/", "/out/", "/generated/")


# ── 어노테이션 인자 읽기 ──────────────────────────────────────────────────────
#
# 왜 정규식 하나로 안 되는가: 이 코드베이스에 실제로 이런 줄이 있다.
#
#     @Column(name = "role", nullable = false, length = 32, columnDefinition = "VARCHAR(32)")
#
# `[^)]*` 로 인자를 잡으면 문자열 안의 `)` 에서 끊긴다. 그리고 javadoc 의 `@param` 이나
# 주석에 적힌 예시 어노테이션까지 코드로 읽힌다. 값을 **확신하는 문장으로** 내보내는 모듈이라
# 그 정도 오독도 비싸다. 그래서 문자열과 주석을 아는 작은 스캐너를 쓴다.


def _skip_string(text: str, i: int) -> int:
    """`"` 로 시작하는 문자열 리터럴의 **다음** 위치.

    작은따옴표는 일부러 안 본다 — 산문 주석의 아포스트로피(`don't`)가 문자열 시작으로
    읽히면 뒤 본문을 통째로 삼킨다. Java char 리터럴은 어노테이션 인자에 사실상 안 나온다.
    """
    n = len(text)
    i += 1
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return n


def _blank_comments(text: str) -> str:
    """주석을 공백으로 덮는다. **길이와 줄바꿈은 그대로 둔다** — 뒤에서 쓰는 위치가 어긋나면
    엉뚱한 필드에 어노테이션이 붙는다."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _skip_string(text, i)
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


def _match_paren(text: str, start: int) -> int:
    """`(` 의 짝이 되는 `)` 위치. 문자열 안의 괄호는 세지 않는다. 못 닫으면 -1."""
    depth = 0
    i, n = start, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _skip_string(text, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _scan_annotations(text: str) -> list[tuple[int, int, str, str]]:
    """파일의 어노테이션 전부를 `(시작, 끝, 이름, 인자원문)` 으로."""
    out: list[tuple[int, int, str, str]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "@":
            i += 1
            continue
        j = i + 1
        while j < n and (text[j].isalnum() or text[j] == "_"):
            j += 1
        name = text[i + 1:j]
        if not name:
            i += 1
            continue
        k = j
        while k < n and text[k] in " \t\r\n":
            k += 1
        args = ""
        end = j
        if k < n and text[k] == "(":
            close = _match_paren(text, k)
            if close < 0:
                i = j
                continue
            args = text[k + 1:close]
            end = close + 1
        out.append((i, end, name, args))
        i = end
    return out


def _attached_annotations(text, anns, decl_start):
    """필드 선언 **바로 위**에 붙은 어노테이션들. 사이에 다른 글자가 있으면 거기서 끊는다.

    끊지 않으면 위쪽 다른 필드의 어노테이션까지 딸려 와 값이 뒤섞인다.
    """
    out, pos = [], decl_start
    for ann in reversed(anns):
        start, end = ann[0], ann[1]
        if end > pos:
            continue
        if text[end:pos].strip():
            break
        out.append(ann)
        pos = start
    return out


def _field_declarations(text: str, field: str) -> list[int]:
    pat = re.compile(r"(?:private|protected|public)[^;{}=]*?\b" + re.escape(field) + r"\s*[;=]")
    return [m.start() for m in pat.finditer(text)]


def _attr_value(args: str, attr: str) -> str | None:
    esc = chr(92)
    lit = '"(?:[^"' + esc + esc + ']|' + esc + esc + '.)*"'
    m = re.search(esc + "b" + re.escape(attr) + esc + "s*=" + esc + "s*("
                  + lit + "|[^,]+)", args)
    return m.group(1).strip() if m else None


class CodeValueResolver:
    def __init__(self, repo_path):
        self.repo_path = Path(repo_path)
        self._files: list[Path] | None = None
        self._texts: dict[str, str] = {}

    def _eligible_files(self) -> list[Path]:
        """값의 출처가 될 수 있는 `.java` 파일. **정렬한다.**

        `rglob` 순서는 OS·파일시스템이 정한다. 그 순서가 답을 고르게 두면 같은 체크아웃이
        기계에 따라 다른 값을 낸다 — 재현 불가능한 "확실한 답" 이다.
        """
        if self._files is None:
            out = []
            for p in self.repo_path.rglob("*.java"):
                rel = "/" + str(p.relative_to(self.repo_path)).replace("\\", "/")
                if any(part in rel for part in _SKIP_PARTS):
                    continue
                out.append(p)
            self._files = sorted(out)
        return self._files

    def _declares(self, path: Path, qualifier: str) -> bool:
        """이 파일이 `qualifier` 타입을 담고 있는가 — 파일명이거나, 안에서 선언하거나.

        Java 는 보통 파일명 = 공개 타입명이지만 중첩 타입·보조 타입이 있으므로 선언도 본다.
        """
        if path.stem == qualifier:
            return True
        return qualifier in _DECL.findall(self._text(path))

    def _text(self, path):
        """주석을 지운 본문. 파일당 한 번만 읽는다."""
        key = str(path)
        if key not in self._texts:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            self._texts[key] = _blank_comments(raw)
        return self._texts[key]

    def resolve(self, source: str) -> ResolvedValue:
        """`source` 는 두 형태다.

        · `PlanPolicy.BASIC_MAX_PROJECTS`        — `static final` 상수
        · `CreatePartyroomRequest.title@Size.max` — 필드에 붙은 어노테이션 인자
        """
        if not self.repo_path.is_dir():
            # **조용히 '못 찾음' 으로 떨어지지 않는다.** 마운트가 빠진 배포에서는 모든 claim 이
            # 똑같이 not-found 가 되고, 그것은 "claim 이 틀렸다" 와 구분되지 않는다.
            return ResolvedValue(
                found=False, reason=f"코드 경로가 없다: {self.repo_path} (마운트/설정 확인)")
        if "@" in source:
            return self._resolve_annotation(source)
        return self._resolve_constant(source)

    def _decide(self, source, hits, qualifier, symbol, missing_reason):
        """찾은 것들에서 답 하나를 낸다 — **낼 수 있을 때만**.

        상수와 어노테이션이 이 판정을 공유한다. 두 경로가 서로 다른 규칙으로 확신하면
        한쪽만 고쳐지고 다른 쪽은 조용히 틀린 채 남는다.
        """
        if not hits:
            return ResolvedValue(found=False, symbol=symbol, reason=missing_reason)

        if qualifier:
            # **한정자를 실제로 쓴다.** 옛 판은 이것을 버려서 없는 클래스명으로도 값이 나왔다.
            named = [h for h in hits if self._declares(h[0], qualifier)]
            if not named:
                return ResolvedValue(
                    found=False, symbol=symbol,
                    reason=(f"`{symbol}` 은 있지만 `{qualifier}` 를 선언한 파일에는 없다 "
                            f"({len(hits)}곳에서 발견)"))
            hits = named

        values = {v for _, v, _ in hits}
        if len(values) > 1:
            # **모호하면 답하지 않는다.** 어느 하나를 골라 확신하는 문장으로 내보내는 것보다
            # "한정자를 붙여라" 가 낫다. 상수는 이런 이름이 40개였고, 어노테이션은 더 흔하다 —
            # `nickname` 의 `@Size(max=…)` 가 팀 코드에서 64와 20으로 갈려 있다.
            where = ", ".join(sorted(str(p.relative_to(self.repo_path)).replace("\\", "/")
                                     for p, _, _ in hits)[:3])
            return ResolvedValue(
                found=False, symbol=symbol,
                reason=(f"`{symbol}` 이 {len(hits)}곳에 **서로 다른 값**으로 있다 — "
                        f"한정자로 좁혀라 ({where})"))

        # 값이 하나로 모였다. 경로는 정렬돼 있으므로 어느 기계에서도 같은 것을 고른다.
        path, value, whole = hits[0]
        rel = str(path.relative_to(self.repo_path)).replace("\\", "/")
        symbol_hash = hashlib.sha256(
            (rel + "::" + source + "::" + whole).encode("utf-8")
        ).hexdigest()[:12]
        return ResolvedValue(True, value, rel, symbol, symbol_hash)

    def _resolve_constant(self, source: str) -> ResolvedValue:
        qualifier, _, symbol = source.rpartition(".")
        if not symbol:
            return ResolvedValue(found=False, reason=f"value_source 를 읽을 수 없다: {source!r}")

        pat = re.compile(
            r"static\s+final\s+\w+\s+" + re.escape(symbol) + r"\s*=\s*([^;]+);"
        )
        hits: list[tuple[Path, str, str]] = []          # (path, value, whole_match)
        for path in self._eligible_files():
            m = pat.search(self._text(path))
            if m:
                hits.append((path, m.group(1).strip(), m.group(0)))
        return self._decide(source, hits, qualifier, symbol,
                            f"`{symbol}` 을 코드에서 찾지 못했다")

    def _resolve_annotation(self, source: str) -> ResolvedValue:
        """`Qualifier.field@Annotation.attr` 를 읽는다."""
        left, _, right = source.partition("@")
        qualifier, _, field = left.rpartition(".")
        ann_name, _, attr = right.rpartition(".")
        if not (field and ann_name and attr):
            return ResolvedValue(
                found=False,
                reason=(f"value_source 를 읽을 수 없다: {source!r} — "
                        f"`클래스.필드@어노테이션.인자` 형태로 적는다"))

        symbol = f"{field}@{ann_name}.{attr}"
        hits: list[tuple[Path, str, str]] = []
        for path in self._eligible_files():
            text = self._text(path)
            if "@" + ann_name not in text:
                continue
            anns = _scan_annotations(text)
            for decl in _field_declarations(text, field):
                for start, end, name, args in _attached_annotations(text, anns, decl):
                    if name != ann_name:
                        continue
                    value = _attr_value(args, attr)
                    if value is not None:
                        hits.append((path, value, text[start:end]))
        return self._decide(
            source, hits, qualifier, symbol,
            f"`{field}` 에 붙은 `@{ann_name}({attr} = …)` 를 코드에서 찾지 못했다")
