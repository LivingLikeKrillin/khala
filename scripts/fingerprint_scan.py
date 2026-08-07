"""추적되는 파일에 남의 조직 지문이 있는지 — 이 리포는 public 이다.

khala 는 2026-07-01 에 공개로 전환하면서 파트너 조직의 지문을 지웠다. 그런데 그 뒤로 다시
들어왔다: 팀 배포 작업(2026-07-10)이 조직명·업무 이메일·Cloudflare Access 테넌트 호스트명·실제
Notion 페이지 ID 를 테스트 픽스처와 설정 주석에 넣었고, 소스 적재 작업(2026-08-06/07)이 조직명을
주석·문서·**커밋 메시지**에 넣었다. 한 달 동안 아무것도 그것을 보지 않았다.

기억은 이 일을 두 번 실패했다. 그래서 여기서는 **매 푸시에 센다.**

무엇이 지문인가 — 되풀 수 있는 것:
  · 파트너 조직명            → 검색되면 khala 와 그 조직의 관계가 드러난다
  · 실존 이메일·계정         → 개인 식별
  · Access/SSO 테넌트 호스트 → 조직의 인증 경계 이름
  · 32자 Notion 페이지 ID    → 그 워크스페이스의 실제 페이지를 가리킨다

무엇이 아닌가:
  · `example.com` · `example-team` 같은 예약 도메인 (RFC 2606)
  · 콘텐츠 해시(sha256 등) — 길이가 다르고 16진이어도 페이지를 안 가리킨다
  · 이미 스탬프된 기록물 안의 **8자 접두** — 페이지로 되풀 수 없고, 본문을 고치면 해시가 깨진다

새 지문을 막는 것이 목적이지 과거를 지우는 것이 목적이 아니다. 허용 목록은 **이유와 함께**
적는다 — 이유 없는 예외는 다음 사람이 지울 수 없다.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 조직 이름. 소문자 부분일치로 본다 — `PFPLAY`, `pfplay.com`, `NOTION_TOKEN_PFPLAY` 를 다 잡는다.
ORG_NAMES = ("pfplay",)

#: 대시 있든 없든 32자 16진.
#:
#: **모양만으로는 못 가린다.** Notion ID 는 그냥 UUID 라서, 이 패턴 하나만 쓰면 k8s 평가 코퍼스의
#: UID·probe 픽스처의 콘텐츠 해시까지 123건을 잡는다(첫 판에 실제로 그랬고, 그 소음에 음성
#: 대조군이 파묻혔다). 잡는 것이 많은 검사는 아무것도 안 잡는 검사와 같다.
#:
#: 그래서 **맥락과 함께** 본다: 같은 줄이나 파일 경로에 Notion 표식이 있을 때만 지문으로 센다.
HEX_ID = re.compile(
    r"\b[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}\b")

#: 이것이 있으면 그 줄의 16진은 워크스페이스의 실제 페이지를 가리킬 수 있다.
NOTION_MARKERS = ("notion", "page_id", "root_id", "block_id", "data_source")

#: 합성이라고 **사람이 판정한** ID. 판정 근거를 각 줄에 남긴다 — 근거 없는 예외는 다음 사람이
#: 지울 수 없고, 그러면 허용 목록이 곧 구멍이 된다.
ALLOWED_IDS = {
    # 2026-08-07 스크럽이 실제 페이지 ID 두 개를 이것으로 바꿨다. 어느 워크스페이스도 안 가리킨다.
    "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
    "1a2b3c4d5e6f4a7b8c9d0e1f2a3b4c5d",
    # 같은 스크럽에서 두 번째 실제 루트를 대체. 위와 겹치지 않아야 두 루트를 구분하는 테스트가 산다.
    "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e",
    "2b3c4d5e6f7a4b8c9d0e1f2a3b4c5d6e",
    # 등록되지 않은 루트를 나타내는 픽스처 상수. 코퍼스에 대응하는 문서가 없다(2026-08-07 확인).
    "fc054c8f-cc62-409c-8154-deafb826cac9",
}

#: 검사에서 빼는 경로 — 각 줄에 이유.
SKIP = (
    ".reviews/",                     # 콘텐츠 해시 기록. 16진이지만 페이지가 아니다
    "scripts/fingerprint_scan.py",   # 이 파일이 패턴 자체를 담는다
)

#: 스탬프된 기록물 안의 8자 접두. 본문을 고치면 해시가 깨지고, 접두로는 페이지를 못 연다.
#: **되풀 수 없는 것만** 여기 들어간다 — 전체 ID 는 절대 안 된다.
ALLOWED_PREFIXES = {
    "specs/SPEC-nexus-search-recall.md": ("2740c71b",),
}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    return [p for p in out.splitlines() if not any(p.startswith(s) for s in SKIP)]


def scan() -> list[str]:
    problems: list[str] = []
    for rel in tracked_files():
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue        # 바이너리·읽을 수 없는 것은 지문의 대상이 아니다
        allowed_prefixes = ALLOWED_PREFIXES.get(rel, ())
        path_is_notion = any(m in rel.lower() for m in NOTION_MARKERS)
        for n, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            for org in ORG_NAMES:
                if org in low:
                    problems.append(f"{rel}:{n}: 파트너 조직명 '{org}' — 이 리포는 public 이다")
            if not (path_is_notion or any(m in low for m in NOTION_MARKERS)):
                continue        # 맥락이 없으면 그냥 UUID 다 — k8s UID·콘텐츠 해시가 여기 걸린다
            for match in HEX_ID.findall(line):
                if match in ALLOWED_IDS or match in allowed_prefixes:
                    continue
                problems.append(
                    f"{rel}:{n}: Notion 맥락의 32자 ID '{match}' — 실제 워크스페이스를 가리킬 수 "
                    f"있다. 합성으로 바꾸거나 근거와 함께 ALLOWED_IDS 에 넣어라")
    return problems


def main() -> int:
    problems = scan()
    if problems:
        print(f"✗ 지문 {len(problems)}건 — 추적되는 파일에 남의 조직이 남아 있다:")
        for p in problems:
            print(f"  {p}")
        print("\n커밋 메시지와 PR 본문도 공개된다. 거기까지는 이 검사가 못 본다.")
        return 1
    print(f"✓ 추적 파일 {len(tracked_files())}개에 조직 지문 없음")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    sys.exit(main())
