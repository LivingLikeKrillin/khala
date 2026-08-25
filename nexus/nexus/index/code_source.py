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


class CodeValueResolver:
    def __init__(self, repo_path):
        self.repo_path = Path(repo_path)
        self._files: list[Path] | None = None

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

    @staticmethod
    def _declares(path: Path, qualifier: str) -> bool:
        """이 파일이 `qualifier` 타입을 담고 있는가 — 파일명이거나, 안에서 선언하거나.

        Java 는 보통 파일명 = 공개 타입명이지만 중첩 타입·보조 타입이 있으므로 선언도 본다.
        """
        if path.stem == qualifier:
            return True
        text = path.read_text(encoding="utf-8", errors="ignore")
        return qualifier in _DECL.findall(text)

    def resolve(self, source: str) -> ResolvedValue:
        # source 예: "PlanPolicy.BASIC_MAX_PROJECTS"
        qualifier, _, symbol = source.rpartition(".")
        if not symbol:
            return ResolvedValue(found=False, reason=f"value_source 를 읽을 수 없다: {source!r}")
        if not self.repo_path.is_dir():
            # **조용히 '못 찾음' 으로 떨어지지 않는다.** 마운트가 빠진 배포에서는 모든 claim 이
            # 똑같이 not-found 가 되고, 그것은 "claim 이 틀렸다" 와 구분되지 않는다.
            return ResolvedValue(
                found=False, reason=f"코드 경로가 없다: {self.repo_path} (마운트/설정 확인)")

        pat = re.compile(
            r"static\s+final\s+\w+\s+" + re.escape(symbol) + r"\s*=\s*([^;]+);"
        )
        hits: list[tuple[Path, str, str]] = []          # (path, value, whole_match)
        for path in self._eligible_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            m = pat.search(text)
            if m:
                hits.append((path, m.group(1).strip(), m.group(0)))

        if not hits:
            return ResolvedValue(found=False, symbol=symbol,
                                 reason=f"`{symbol}` 을 코드에서 찾지 못했다")

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
            # "한정자를 붙여라" 가 낫다. 실측에서 이런 이름이 40개였다.
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
            (rel + "::" + symbol + "::" + whole).encode("utf-8")
        ).hexdigest()[:12]
        return ResolvedValue(True, value, rel, symbol, symbol_hash)
