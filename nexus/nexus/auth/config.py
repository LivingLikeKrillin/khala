"""Auth configuration: mode, allowed origins, principals, and the startup guard."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

PLACEHOLDER = "REPLACE_ME"
_DEFAULT_ORIGINS = ["http://localhost:8000"]
_WEAK_DEV_TOKEN_DEFAULT = "nexus-local-dev"
_MIN_DEV_TOKEN_LEN = 24


@dataclass
class AuthConfig:
    mode: str = "enforced"  # "enforced" (default, fail-closed) | "permissive"
    allowed_origins: list[str] = field(default_factory=lambda: list(_DEFAULT_ORIGINS))
    principals: list[dict] = field(default_factory=list)
    dev_token_weak: bool = False
    access: "object | None" = None   # AccessConfig | None (순환 회피용 느슨한 타입)

    @classmethod
    def from_dict(cls, cfg: dict | None) -> "AuthConfig":
        from .access_config import AccessConfig

        auth = (cfg or {}).get("auth") or {}
        access = AccessConfig.from_auth(auth)
        mode = str(auth.get("mode", "enforced")).lower()
        # explicit, loud opt-out only
        if os.getenv("NEXUS_ALLOW_ANONYMOUS") == "1":
            mode = "permissive"
        if mode not in ("enforced", "permissive"):
            mode = "enforced"  # unknown -> fail closed
        origins = auth.get("allowed_origins") or list(_DEFAULT_ORIGINS)
        principals = list(auth.get("principals") or [])
        # 로컬 dev 온램프: NEXUS_DEV_TOKEN 이 있을 때만(=docker-compose.override.yml 의 로컬
        # 편의 레이어) INTERNAL local-dev principal 을 *추가* 주입한다. 리포 기본 config 는
        # enforced + principals:[] 그대로라 prod(override 미사용)는 영향 없음. 토큰은 env 로만
        # 들어오고 리포에 커밋되지 않는다. override 를 prod 에 쓰지 말 것.
        dev_token = os.getenv("NEXUS_DEV_TOKEN")
        dev_token_weak = False
        # Access 가 설정되면 공유 dev-token 경로는 꺼진다 — 두 신원 경로가 동시에 돌지 않는다.
        # Access 가 문이면 공유 열쇠는 끈다 (SPEC §4.5).
        if dev_token and access is not None:
            dev_token = None
        if dev_token:
            from .principal import hash_token
            # local-dev 는 **운영자 신원**이지 독자 신원이 아니다. 웹 콘솔(소스 관리)이
            # 자기 화면에서 403 으로 막히지 않도록 manage_sources 를 기본 부여한다.
            #
            # ⚠️ GET /auth/dev-token 은 이 토큰을 도달한 누구에게나 내준다. 터널 뒤에서는
            #    Cloudflare Access 통과자 누구나 소스를 관리하고 (미리보기를 거쳐) 문서를
            #    내릴 수 있다는 뜻이다. 그게 싫으면 config.yaml 에
            #        auth.local_dev_capabilities: []
            #    ⚠️ manage_documents 는 문서 숨김·supersede 를 연다(파괴적).
            #    를 두어 로컬 UI 를 읽기 전용으로 만든다. 명시 설정된 principal 은
            #    여전히 default-deny 다.
            dev_caps = auth.get("local_dev_capabilities")
            if dev_caps is None:
                dev_caps = ["manage_sources", "manage_documents"]
            principals.append({
                "name": "local-dev",
                "token_sha256": hash_token(dev_token),
                "tenant": "default",
                "clearance": "INTERNAL",
                "capabilities": list(dev_caps),
            })
            dev_token_weak = (
                dev_token == _WEAK_DEV_TOKEN_DEFAULT or len(dev_token) < _MIN_DEV_TOKEN_LEN
            )
        # 슬랙 봇 신원: **봇이 보내는 그 토큰**으로 서버 쪽 principal 을 만든다.
        #
        # 봇은 `NEXUS_SLACK_TOKEN` 을 bearer 로 보내는데, 지금까지 서버에는 그 토큰에 대응하는
        # principal 이 없었다 — compose 주석은 "gen-token 으로 발급한 읽기 전용 principal" 이라
        # 적어 두었지만 그것을 만드는 코드도, config 항목도 없었다. 봇을 띄우면 401 이다.
        #
        # 같은 env 변수를 양쪽이 읽게 두는 것이 요점이다. 서버가 config 의 해시를, 봇이 env 의
        # 토큰을 각각 들고 있으면 둘은 조용히 어긋날 수 있고, 그 어긋남은 401 루프로만 보인다.
        # 하나의 변수에서 둘 다 파생되면 어긋남 자체가 표현 불가능하다.
        #
        # 능력은 비운다: 봇은 **읽기 전용**이고, 워크스페이스 전원에게 열리는 표면이 문서를
        # 내리거나 소스를 고칠 수 있으면 안 된다. clearance 기본이 PUBLIC 인 것도 같은 이유다
        # (`NEXUS_SLACK_CLEARANCE` — 봇 쪽 기본값과 같은 변수).
        slack_token = os.getenv("NEXUS_SLACK_TOKEN")
        if slack_token:
            from .principal import hash_token
            principals.append({
                "name": "slack-bot",
                "token_sha256": hash_token(slack_token),
                "tenant": os.getenv("NEXUS_SLACK_TENANT", "default"),
                "clearance": os.getenv("NEXUS_SLACK_CLEARANCE", "PUBLIC"),
                "capabilities": [],
            })

        # 두 번째 코퍼스: `NEXUS_SLACK_CORPUS_<별칭> = 토큰|테넌트[|등급]`
        #
        # **테넌트는 토큰이 정한다** (`auth/scope.py`: 요청의 tenant 는 무시된다 — 테넌트 격리이자
        # 존재 유출 방지). 그래서 봇이 다른 코퍼스에 물으려면 문자열이 아니라 **그 테넌트에 묶인
        # 토큰**이 필요하다. 채널마다 코퍼스를 나누는 일이 결국 토큰을 나누는 일인 이유다.
        #
        # 위와 같은 규율을 지킨다: 봇이 보내는 그 값에서 서버 principal 이 파생되므로 둘이 어긋날
        # 수 없고, 능력은 비어 있고(읽기 전용), 등급은 명시하지 않으면 기본 봇과 같은 값이다.
        # 값이 깨졌으면 **그 코퍼스만 건너뛴다** — 오타 하나가 배포 전체를 못 뜨게 하면 안 된다.
        for key, raw in os.environ.items():
            if not key.startswith("NEXUS_SLACK_CORPUS_") or not raw.strip():
                continue
            alias = key[len("NEXUS_SLACK_CORPUS_"):].strip().lower()
            parts = [x.strip() for x in raw.split("|")]
            if not alias or len(parts) < 2 or not parts[0] or not parts[1]:
                logger.warning("slack_corpus_env_malformed", key=key)
                continue
            from .principal import hash_token
            principals.append({
                "name": f"slack-{alias}",
                "token_sha256": hash_token(parts[0]),
                "tenant": parts[1],
                "clearance": (parts[2] if len(parts) > 2 and parts[2]
                              else os.getenv("NEXUS_SLACK_CLEARANCE", "PUBLIC")),
                "capabilities": [],
            })

        return cls(
            mode=mode,
            allowed_origins=list(origins),
            principals=principals,
            dev_token_weak=dev_token_weak,
            access=access,
        )

    @property
    def permissive(self) -> bool:
        return self.mode == "permissive"

    def validate_startup(self) -> None:
        """Refuse to boot in enforced mode while any principal still carries the placeholder.

        Prevents shipping a known credential: an operator must mint a real token before the
        server will serve in enforced mode.
        """
        # Weak-dev-token guard runs regardless of mode: the exposure risk (GET /auth/dev-token
        # handing an INTERNAL bearer to any caller) is independent of enforced/permissive.
        if self.dev_token_weak:
            msg = (
                "NEXUS_DEV_TOKEN is weak/default — GET /auth/dev-token serves an INTERNAL bearer "
                "to anyone who can reach it. Safe only on localhost. If exposing beyond localhost "
                "(tunnel/LAN), set a strong random NEXUS_DEV_TOKEN (`nexus auth gen-token`) AND gate "
                "at the edge (e.g. Cloudflare Access)."
            )
            if os.getenv("NEXUS_REQUIRE_STRONG_DEV_TOKEN") == "1":
                raise RuntimeError("auth: " + msg)
            logger.warning("weak_dev_token", detail=msg)

        if self.permissive:
            return
        for p in self.principals:
            if str(p.get("token_sha256", "")) == PLACEHOLDER:
                raise RuntimeError(
                    f"auth: principal {p.get('name', '?')!r} still uses the {PLACEHOLDER} "
                    "placeholder hash. Run `nexus auth gen-token | nexus auth hash-token` and "
                    "paste a real hash, or set auth.mode: permissive for local dev."
                )
