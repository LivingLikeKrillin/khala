"""배포가 `.env` 로 세대를 움직일 수 있는가 — compose 가 **해석한 값**으로 확인한다
(SPEC-nexus-embedding-cutover-seam §4.5).

`.env` 는 compose 의 **보간**에만 먹힌다. `environment:` 에 리터럴을 적으면 그 값이 `.env` 를
이기고, 그러면 컷오버 절차는 세 줄을 고치고 재기동한 뒤 "flip 했다" 고 믿지만 프로세스는 옛 세대
그대로다 — 게다가 셋이 다 옛 값이라 §4.2 의 정합성 검사도 통과한다. **성공을 보고하면서 아무것도
바꾸지 않는 절차**가 이 파일이 막는 것이다.

그래서 파일을 읽어 `${...}` 를 찾는 대신 `docker compose config` 가 내놓는 최종 값을 본다:
문법을 검사하는 게 아니라 **결과**를 검사한다.

CI 는 `NEXUS_REQUIRE_COMPOSE=1` 로 이 스위트를 강제한다 — 조용히 스킵되는 검사는 없는 검사다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REQUIRED = os.getenv("NEXUS_REQUIRE_COMPOSE") == "1"
_HAVE_DOCKER = shutil.which("docker") is not None

pytestmark = pytest.mark.skipif(
    not _HAVE_DOCKER and not _REQUIRED,
    reason="docker 없음 (CI 는 NEXUS_REQUIRE_COMPOSE=1 로 강제한다)")

ROOT = Path(__file__).resolve().parents[1]

#: 컷오버가 움직이는 값들과, 그것을 실어 나르는 변수.
GENERATION_ENV = {
    "NEXUS_EMBEDDING_MODEL": "KURE-v1",
    "NEXUS_EMBEDDING_COLUMN": "embedding_1024",
    "NEXUS_EMBEDDING_BACKEND": "sidecar",
}


def _resolved_app_env(env_file_body: str, tmp_path: Path) -> dict:
    """`.env` 를 주고 compose 가 `nexus-app` 에 실제로 넣는 환경을 받아 온다."""
    env_file = tmp_path / ".env"
    env_file.write_text(env_file_body, encoding="utf-8")
    proc = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"),
         "--env-file", str(env_file), "config", "--format", "json"],
        capture_output=True, text=True, cwd=ROOT, timeout=120)
    if proc.returncode != 0:
        pytest.fail(f"docker compose config 실패: {proc.stderr[:400]}")
    return json.loads(proc.stdout)["services"]["nexus-app"]["environment"]


def test_the_deployment_env_reaches_the_service_definition(tmp_path):
    body = "\n".join(f"{k}={v}" for k, v in GENERATION_ENV.items()) + "\n"
    resolved = _resolved_app_env(body, tmp_path)
    for key, value in GENERATION_ENV.items():
        assert resolved.get(key) == value, (
            f"{key} 가 `.env` 값({value})으로 해석되지 않았다 — compose 에 리터럴이 적혀 있으면 "
            "컷오버는 성공을 보고하면서 아무것도 바꾸지 않는다")


def test_an_untouched_deployment_stays_on_the_old_generation(tmp_path):
    """음성 대조군 — 기본값이 새 세대면, 재임베딩 안 한 설치가 빈 컬럼을 읽는다."""
    resolved = _resolved_app_env("", tmp_path)
    assert resolved.get("NEXUS_EMBEDDING_MODEL") == "nomic-embed-text"
    assert resolved.get("NEXUS_EMBEDDING_COLUMN") == "embedding"
    assert resolved.get("NEXUS_EMBEDDING_BACKEND") == "ollama"


def test_the_app_knows_where_the_sidecar_is(tmp_path):
    """앱이 사이드카 주소를 모르면 백엔드를 sidecar 로 바꿔도 붙을 곳이 없다 (§1.6)."""
    resolved = _resolved_app_env("", tmp_path)
    assert resolved.get("EMBED_URL", "").startswith("http://nexus-embed"), (
        "compose 안에서는 서비스 이름으로 붙는다 — localhost 는 앱 컨테이너 자신이다")


def test_the_checkpoint_is_pinned_to_a_commit(tmp_path):
    """이름이 아니라 커밋이어야 한다. 같은 이름의 다른 리비전은 차원이 같아 조용히 섞인다 (§4.5)."""
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    proc = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"),
         "--env-file", str(env_file), "--profile", "embed", "config", "--format", "json"],
        capture_output=True, text=True, cwd=ROOT, timeout=120)
    if proc.returncode != 0:
        pytest.fail(f"docker compose config 실패: {proc.stderr[:400]}")
    revision = json.loads(proc.stdout)["services"]["nexus-embed"]["environment"]["EMBED_REVISION"]
    assert len(revision) == 40 and all(c in "0123456789abcdef" for c in revision), (
        f"EMBED_REVISION={revision!r} — 40자 커밋 해시여야 한다")


#: 로컬 개발 배포(base + override)에서 저절로 돌아와야 하는 것들. 재적재 잡은 base 에 이미 있다.
LOCAL_SELF_RESTARTING = ("nexus-db", "nexus-embed", "nexus-ollama", "nexus-app", "nexus-slack")


def _resolved_local_services(tmp_path: Path) -> dict:
    """`docker compose up -d` 가 자동으로 얹는 조합(base + override)의 최종 서비스 정의."""
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    proc = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"),
         "-f", str(ROOT / "docker-compose.override.yml"), "--env-file", str(env_file),
         "--profile", "embed", "--profile", "slack", "--profile", "reingest",
         "config", "--format", "json"],
        # 재적재 잡의 시동 스크립트에 한국어가 있다 — 지역 인코딩(cp949)으로 읽으면 깨진다.
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=120)
    if proc.returncode != 0:
        pytest.fail(f"docker compose config 실패: {proc.stderr[:400]}")
    return json.loads(proc.stdout)["services"]


def test_the_local_stack_comes_back_by_itself(tmp_path):
    """2026-10-14 · 10-16 에 엔진이 컨테이너를 255 로 내렸을 때 **재적재 잡만** 돌아왔다 —
    `restart` 가 붙은 것이 그것 하나였다. 나머지는 사람이 알아챌 때까지(4.5시간 · 하루 가까이) 꺼져 있었다."""
    services = _resolved_local_services(tmp_path)
    missing = [name for name in LOCAL_SELF_RESTARTING
               if services[name].get("restart") != "unless-stopped"]
    assert not missing, f"엔진이 내려도 저절로 안 돌아오는 서비스: {missing}"


def test_the_one_shot_pull_still_runs_once(tmp_path):
    """음성 대조군 — 모델을 받고 끝나는 컨테이너에 재시작을 붙이면 매번 다시 받는다."""
    services = _resolved_local_services(tmp_path)
    assert services["nexus-ollama-init"].get("restart") == "no"
