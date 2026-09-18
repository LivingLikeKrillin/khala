"""신원을 만들어 내는 환경변수 — **검사가 먼저 지워야 하는 목록**.

⛔ **왜 있나 (실측 2026-09-18).** `AuthConfig.from_dict` 는 config 만 읽는 것이 아니라
환경변수에서 principal 을 **주입**한다. 그래서 그 결과를 통째로 단언하는 검사
(`cfg.principals == []` 같은)는 **그 기계의 배포 설정을 같이 보게 된다.** 설정이 깔린
컨테이너에서 단위 스위트를 돌리면 이 계열로 12건이 빨갛게 났다.

⛔ **빨간 쪽은 위험한 쪽이 아니다.** 반대가 본체다 — *"선언이 없으면 이렇게 된다"* 를
확인하려는 검사가, 주변에 선언이 **있는** 기계에서는 그 조건을 한 번도 만들지 못한 채
통과한다. CI 에는 그런 환경이 없으니 **CI 가 볼 수 없는 결함**이다. #503 이 같은 병을
`test_tenant_read_scope.py` 에서 고쳤고, 이 모듈은 남은 네 파일의 몫이다.

⚠ **목록을 손으로 맞추지 않는다.** `config.py` 가 새 변수를 읽기 시작하면 이 목록은 조용히
낡고, 그 낡음은 *다음에 누가 같은 자리에서 데일 때* 드러난다. `test_auth_env_isolation.py`
가 `config.py` 를 읽어 **여기 없는 이름이 있으면 깨진다.**
"""

from __future__ import annotations

#: 정확한 이름으로 지우는 것들.
PRINCIPAL_ENV: tuple[str, ...] = (
    "NEXUS_ALLOW_ANONYMOUS",
    "NEXUS_DEV_TOKEN",
    "NEXUS_DEV_READ_TENANTS",
    "NEXUS_DEV_CLEARANCE_VERIFIED",
    "NEXUS_SLACK_TOKEN",
    "NEXUS_SLACK_TENANT",
    "NEXUS_SLACK_CLEARANCE",
    "NEXUS_SLACK_READ_TENANTS",
    "NEXUS_SLACK_CLEARANCE_VERIFIED",
    "NEXUS_REQUIRE_STRONG_DEV_TOKEN",
)

#: 접두사로 훑는 것들. `config.py` 가 `os.environ` 전체를 돌며 찾는 자리라 이름을 미리
#: 알 수 없다 — 배포마다 코퍼스 별칭이 다르다. 이 배포에도 하나 깔려 있다.
PRINCIPAL_ENV_PREFIXES: tuple[str, ...] = ("NEXUS_SLACK_CORPUS_",)


def clear_principal_env(monkeypatch) -> None:
    """신원을 만들어 내는 환경변수를 전부 지운다. 검사는 이 위에서 자기 것만 얹는다."""
    import os

    for name in PRINCIPAL_ENV:
        monkeypatch.delenv(name, raising=False)
    for name in [k for k in os.environ if k.startswith(PRINCIPAL_ENV_PREFIXES)]:
        monkeypatch.delenv(name, raising=False)
