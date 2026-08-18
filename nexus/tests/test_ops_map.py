"""운영 '지도' 생성기 — 설정 파일에서 **결정론적으로** 답변용 문서를 만든다.

왜 값이 아니라 지도인가: 실시간 수치는 임베딩하면 안 된다(적재 순간 낡는다). 대신 *무엇이
어디에 있는가* — 로그 필드 이름, 떠 있는 서비스, 배포 절차 — 를 문서로 만들어 두면 질문이
그 이름에 닿는다. PromQL 생성 정확도가 카탈로그 유무로 2.6%→69.1% 로 갈린 실측이 근거다.

이 생성기가 지키는 것 셋:

* **지어내지 않는다.** 파싱된 것만 쓴다. 없는 절은 아예 없다.
* **환경변수 값을 절대 옮기지 않는다.** 키 이름만. compose 의 `environment:` 는 비밀이 앉는
  자리이고, 그걸 코퍼스로 옮기면 검색 가능한 비밀이 된다.
* **출처와 해시를 본문에 적는다.** 설정이 바뀌면 해시가 달라지므로 낡음을 기계가 볼 수 있다.
"""

from __future__ import annotations

import textwrap

LOGBACK = textwrap.dedent("""\
    <configuration>
      <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder><pattern>%d %msg%n</pattern></encoder>
      </appender>
      <appender name="JSON" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
          <includeMdcKeyName>requestId</includeMdcKeyName>
          <includeMdcKeyName>userId</includeMdcKeyName>
          <fieldNames>
            <timestamp>time</timestamp>
            <level>severity</level>
          </fieldNames>
        </encoder>
      </appender>
      <springProfile name="prod">
        <root level="INFO"><appender-ref ref="JSON"/></root>
      </springProfile>
      <springProfile name="local">
        <root level="DEBUG"><appender-ref ref="CONSOLE"/></root>
      </springProfile>
    </configuration>
""")

COMPOSE = textwrap.dedent("""\
    services:
      api:
        image: registry.example/app:prod
        ports: ["8080:8080"]
        depends_on: [db]
        environment:
          DB_PASSWORD: hunter2-should-never-be-copied
          FEATURE_FLAG: "on"
        healthcheck:
          test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      db:
        image: mysql:8.0.30
        volumes: ["db-data:/var/lib/mysql"]
""")


def test_the_log_map_names_the_fields_a_question_can_reach():
    from nexus.ingest.sources.ops_map import logging_map

    doc = logging_map(LOGBACK, "app/logback-spring.xml")
    assert doc is not None
    for token in ("requestId", "userId", "severity", "time"):
        assert token in doc.body, f"{token} 이 지도에 없다 — 질문이 이 이름에 닿아야 한다"
    assert "prod" in doc.body and "INFO" in doc.body, "프로파일별 레벨이 없다"
    assert "app/logback-spring.xml" in doc.body, "출처 경로가 본문에 없다"


def test_the_topology_map_never_carries_an_environment_value():
    """키 이름은 지도이고, 값은 비밀이다. 값을 옮기면 검색 가능한 비밀이 된다."""
    from nexus.ingest.sources.ops_map import deploy_topology

    doc = deploy_topology({"docker-compose.prod.yml": COMPOSE})
    assert doc is not None
    assert "DB_PASSWORD" in doc.body, "키 이름은 지도의 일부다"
    assert "hunter2" not in doc.body, "환경변수 **값**이 코퍼스로 새어 들어갔다"


def test_the_topology_map_lists_what_is_running():
    from nexus.ingest.sources.ops_map import deploy_topology

    doc = deploy_topology({"docker-compose.prod.yml": COMPOSE})
    body = doc.body
    assert "api" in body and "db" in body
    assert "mysql:8.0.30" in body, "이미지 태그가 곧 '무엇이 떠 있나' 의 답이다"
    assert "8080:8080" in body
    assert "docker-compose.prod.yml" in body


def test_nothing_parsed_means_no_document():
    """대조군: 재료가 없으면 **문서를 만들지 않는다.** 빈 지도는 지도가 아니라 거짓말이다."""
    from nexus.ingest.sources.ops_map import deploy_topology, logging_map

    assert logging_map("<configuration/>", "x.xml") is None
    assert deploy_topology({"docker-compose.yml": "services: {}\n"}) is None
    assert deploy_topology({}) is None


def test_the_body_carries_a_hash_of_the_source():
    """설정이 바뀌면 해시가 달라진다 — 낡음을 사람이 아니라 기계가 본다."""
    from nexus.ingest.sources.ops_map import logging_map

    a = logging_map(LOGBACK, "app/logback-spring.xml").body
    b = logging_map(LOGBACK.replace("INFO", "WARN"), "app/logback-spring.xml").body
    import re
    ha = re.search(r"sha256:([0-9a-f]{12})", a).group(1)
    hb = re.search(r"sha256:([0-9a-f]{12})", b).group(1)
    assert ha != hb


def test_generation_is_reproducible():
    """같은 입력 → 바이트 단위로 같은 출력. 시각을 넣으면 매 실행이 재적재가 된다."""
    from nexus.ingest.sources.ops_map import logging_map

    assert logging_map(LOGBACK, "p.xml").body == logging_map(LOGBACK, "p.xml").body


def test_generate_walks_a_repo(tmp_path):
    """리포에서 아는 파일을 찾아낸다 — 경로를 사람이 타이핑하지 않는다."""
    from nexus.ingest.sources.ops_map import generate

    (tmp_path / "app" / "src" / "main" / "resources").mkdir(parents=True)
    (tmp_path / "app" / "src" / "main" / "resources" / "logback-spring.xml").write_text(
        LOGBACK, encoding="utf-8")
    (tmp_path / "docker-compose.prod.yml").write_text(COMPOSE, encoding="utf-8")

    docs = {d.name: d for d in generate(tmp_path)}
    assert set(docs) == {"ops-logging.md", "ops-deploy-topology.md"}
    assert "requestId" in docs["ops-logging.md"].body
    assert "mysql:8.0.30" in docs["ops-deploy-topology.md"].body


def test_a_repo_without_ops_config_yields_nothing(tmp_path):
    """대조군: 아무 설정도 없는 리포에서 문서를 지어내지 않는다."""
    from nexus.ingest.sources.ops_map import generate

    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    assert generate(tmp_path) == []


def test_an_entity_bomb_is_refused_not_parsed():
    """표준 ElementTree 는 내부 엔티티를 **확장한다**(확인함) — 선언 자체를 거부한다."""
    from nexus.ingest.sources.ops_map import logging_map

    bomb = ("<!DOCTYPE x [<!ENTITY a 'aaaaaaaaaa'><!ENTITY b '&a;&a;&a;&a;&a;'>]>"
            "<configuration><appender><encoder>"
            "<includeMdcKeyName>&b;</includeMdcKeyName>"
            "</encoder></appender></configuration>")
    assert logging_map(bomb, "x.xml") is None


def test_the_map_speaks_the_language_the_question_uses():
    """`prod` 옆에 `운영` 을 적는다 — 라이브에서 이것 때문에 실패했다.

    표에는 `prod` 만 있고 질문은 `운영 환경에는 어떤 서비스가 떠 있나` 였다. 문서는 찾았는데
    표가 담긴 절이 근거에 못 들어왔다. 요약 문장이 **표와 같은 절**에 있어야 한다.
    """
    from nexus.ingest.sources.ops_map import deploy_topology

    body = deploy_topology({"docker-compose.prod.yml": COMPOSE}).body
    assert "운영(prod)" in body, "환경 이름이 사람이 묻는 말로 적혀 있지 않다"
    assert "서비스는 2개다: api, db" in body, "표와 같은 절에 요약 문장이 없다"


def test_an_unknown_environment_name_is_not_guessed():
    """대조군: 모르는 이름을 한국어로 지어내지 않는다."""
    from nexus.ingest.sources.ops_map import deploy_topology

    body = deploy_topology({"docker-compose.canary.yml": COMPOSE}).body
    assert "docker-compose.canary.yml" in body
    for korean in ("운영", "스테이징", "개발"):
        assert f"{korean}(" not in body
