"""운영 '지도' 생성 — 설정 파일에서 답변용 문서를 **결정론적으로** 만든다.

**왜 지도인가.** 실시간 수치(메트릭 값·현재 CPU·마지막 배포 시각)는 임베딩하면 안 된다.
적재하는 순간 낡고, 낡은 수치는 없느니만 못하다. 임베딩해야 하는 것은 그 위층 —
*무엇이 어디에 있는가* 다: 로그에 어떤 필드가 실리는지, 어떤 서비스가 떠 있는지, 배포가 어떤
절차인지. 이 이름들이 코퍼스에 있어야 질문이 거기 닿고, 나중에 도구 호출을 붙일 때도
"무엇을 물어야 하는지" 를 아는 쪽이 그 도구를 부를 수 있다.

**재료는 이미 리포에 있다.** 그런데 XML·YAML 로 있어서 아무도 못 읽고 어떤 다리도 못 잡는다
(설정 파일은 산문이 아니라 임베딩이 붙을 자리가 없다). 그래서 파싱해서 산문으로 바꾼다.

지키는 것 셋:

* **지어내지 않는다.** 파싱된 것만 쓴다. 재료가 없으면 `None` — 빈 지도는 지도가 아니라
  거짓말이고, 그런 문서가 코퍼스에 있으면 "찾았는데 아무것도 없다" 가 된다.
* **환경변수 값을 절대 옮기지 않는다.** 키 이름만 옮긴다. `environment:` 는 비밀이 앉는
  자리이고, 값을 옮기면 그 순간 **검색 가능한 비밀**이 된다.
* **출처 경로와 해시를 본문에 적는다.** 설정이 바뀌면 해시가 달라지므로, 이 문서가 낡았다는
  것을 사람의 기억이 아니라 기계가 판정할 수 있다. 그리고 같은 입력은 **바이트 단위로 같은
  출력**을 낸다 — 생성 시각을 넣으면 매 실행이 재적재가 되고 재적재는 벡터를 무효화한다.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import yaml

#: 리포에서 찾아볼 자리. 이름이 규약인 파일만 본다 — 추측으로 파일을 고르면 엉뚱한 것을
#: 운영 설정이라고 우기게 된다.
LOGBACK_GLOBS = ("**/logback-spring.xml", "**/logback.xml")
COMPOSE_GLOBS = ("docker-compose*.yml", "docker-compose*.yaml")


@dataclass(frozen=True)
class OpsDoc:
    """적재 가능한 마크다운 한 건. `body` 는 frontmatter 를 포함한 전체 텍스트."""

    name: str
    title: str
    body: str


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _frontmatter(title: str) -> str:
    # doc_type 은 분류기가 frontmatter 를 존중한다(classifier._detect_doc_type).
    # RUNBOOK 은 staleness TTL 90일 — 운영 문서는 빨리 낡는다는 선언이다.
    return f"---\ntitle: {title}\ndoc_type: RUNBOOK\n---\n\n"


def _provenance(sources: list[tuple[str, str]]) -> str:
    """출처 절. 사람이 읽고 원본으로 갈 수 있어야 하고, 기계가 낡음을 볼 수 있어야 한다."""
    lines = ["## 이 문서의 출처", "",
             "이 문서는 아래 설정 파일에서 **기계로 생성**됐다. 값이 코드와 다르면 "
             "**코드가 정본**이다 — 다시 생성하면 이 문서가 따라온다.", ""]
    lines += [f"- `{path}` (sha256:{digest})" for path, digest in sources]
    return "\n".join(lines) + "\n"


# ── 로그 필드 스키마 ────────────────────────────────────────────────────────────

#: 설정 파일 하나가 이보다 크면 설정이 아니다. 파싱 전에 자른다.
MAX_XML_BYTES = 2_000_000


def _safe_xml(text: str) -> bool:
    """엔티티 선언이 있는 XML 은 **파싱하지 않는다**.

    표준 `ElementTree` 는 외부 엔티티(XXE)는 안 풀지만 **내부 엔티티는 확장한다** — 확인했다:
    중첩 선언 하나로 문서가 폭발한다(billion laughs). 이 함수의 입력은 리포에서 온 파일이고
    리포는 사람이 넣은 것이지만, 적재 경로에 있는 파서가 입력 하나로 프로세스를 죽일 수 있으면
    그건 설계 결함이지 신뢰의 문제가 아니다.

    `defusedxml` 을 새로 들이는 대신 선언 자체를 거부한다 — logback 설정에 DOCTYPE 이 필요한
    경우가 없고, 없는 기능을 막는 것은 공짜다.
    """
    if len(text.encode("utf-8", "ignore")) > MAX_XML_BYTES:
        return False
    head = text.lstrip()[:4096].upper()
    return "<!DOCTYPE" not in head and "<!ENTITY" not in text.upper()

def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def logging_map(xml_text: str, source_path: str) -> OpsDoc | None:
    """logback 설정 → 로그 필드 지도.

    답하려는 질문: *"로그에 어떤 필드가 있나"* · *"requestId 는 어디서 오나"* ·
    *"운영에서는 로그 레벨이 뭔가"*. 셋 다 오늘은 XML 을 열어야만 답이 나온다.
    """
    if not _safe_xml(xml_text):
        return None
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None

    mdc_keys = [e.text.strip() for e in root.iter()
                if _localname(e.tag) == "includeMdcKeyName" and (e.text or "").strip()]
    field_names: list[tuple[str, str]] = []
    for holder in (e for e in root.iter() if _localname(e.tag) == "fieldNames"):
        for child in holder:
            if (child.text or "").strip():
                field_names.append((_localname(child.tag), child.text.strip()))

    profiles: list[tuple[str, str, list[str]]] = []
    for prof in (e for e in root.iter() if _localname(e.tag) == "springProfile"):
        name = prof.get("name", "")
        for r in (e for e in prof.iter() if _localname(e.tag) == "root"):
            refs = [a.get("ref", "") for a in r
                    if _localname(a.tag) == "appender-ref" and a.get("ref")]
            profiles.append((name, r.get("level", ""), refs))

    if not (mdc_keys or field_names or profiles):
        return None

    title = "로그 필드 스키마 (설정에서 생성)"
    out = [_frontmatter(title), f"# {title}\n"]
    if mdc_keys:
        out.append("## 로그에 실리는 MDC 키\n")
        out.append("요청 단위로 로그 줄에 함께 찍히는 값들이다. 로그를 검색할 때 "
                   "이 이름으로 거를 수 있다.\n")
        out += [f"- `{k}`" for k in dict.fromkeys(mdc_keys)]
        out.append("")
    if field_names:
        out.append("## 표준 필드 이름 매핑\n")
        out.append("| 로그백 필드 | 실제 JSON 키 |")
        out.append("|---|---|")
        out += [f"| {k} | `{v}` |" for k, v in field_names]
        out.append("")
    if profiles:
        out.append("## 프로파일별 로그 레벨과 출력\n")
        out.append("| 프로파일 | 레벨 | appender |")
        out.append("|---|---|---|")
        out += [f"| {n} | {lvl} | {', '.join(refs) or '-'} |" for n, lvl, refs in profiles]
        out.append("")
    out.append(_provenance([(source_path, _digest(xml_text))]))
    return OpsDoc(name="ops-logging.md", title=title, body="\n".join(out))


# ── 배포 토폴로지 ──────────────────────────────────────────────────────────────

def _service_rows(spec: dict) -> list[dict]:
    rows = []
    for name, svc in (spec.get("services") or {}).items():
        svc = svc or {}
        ports = svc.get("ports") or []
        rows.append({
            "name": name,
            "image": svc.get("image") or "(빌드)",
            "ports": [str(p) for p in ports],
            "depends_on": list(svc.get("depends_on") or []),
            "healthcheck": "있음" if svc.get("healthcheck") else "없음",
            # **키 이름만.** 값은 비밀이 앉는 자리다.
            "env_keys": sorted((svc.get("environment") or {}).keys())
            if isinstance(svc.get("environment"), dict) else
            sorted(e.split("=", 1)[0] for e in (svc.get("environment") or [])),
        })
    return rows


#: 파일 이름의 환경 토큰 → 사람이 **묻는** 말. 실측으로 들어간 표다: 생성 직후 라이브에서
#: "운영 환경에는 어떤 서비스가 떠 있나" 가 실패했다 — 문서는 찾아 놓고 서비스 표가 담긴 절이
#: 근거에 안 들어왔다. 표에는 `prod` 만 있고 질문에는 `운영` 만 있었기 때문이다.
#: **지도는 질문자의 어휘로 쓰여야 한다.**
ENV_GLOSS = {
    "prod": "운영", "production": "운영",
    "stg": "스테이징", "staging": "스테이징",
    "dev": "개발", "development": "개발",
    "local": "로컬", "test": "테스트",
}


def _env_label(fname: str) -> str:
    """`docker-compose.prod.yml` → `운영(prod)`. 모르는 이름이면 파일 이름 그대로.

    한글만 넣지 않고 **둘 다** 넣는다: 사람은 '운영' 으로 묻고 설정은 `prod` 로 적힌다.
    """
    stem = fname.rsplit("/", 1)[-1]
    for token, korean in ENV_GLOSS.items():
        if f".{token}." in stem or stem.endswith(f"-{token}.yml"):
            return f"{korean}({token})"
    return stem


def deploy_topology(files: dict[str, str]) -> OpsDoc | None:
    """docker-compose 파일들 → 무엇이 어디에 떠 있는가.

    답하려는 질문: *"운영에 무슨 서비스가 도나"* · *"DB 는 어떤 버전인가"* ·
    *"이 서비스는 어떤 포트인가"*. 환경별 파일이 여럿이면 **환경별로** 적는다 —
    하나로 뭉치면 stg 의 사실이 prod 의 답으로 나간다.
    """
    sections: list[str] = []
    sources: list[tuple[str, str]] = []
    for fname in sorted(files):
        text = files[fname]
        try:
            spec = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            continue
        rows = _service_rows(spec) if isinstance(spec, dict) else []
        if not rows:
            continue
        sources.append((fname, _digest(text)))
        label = _env_label(fname)
        sections.append(f"## {label} 환경 — `{fname}`\n")
        # 요약 한 줄을 표와 **같은 절**에 둔다. 질문의 어휘(환경·서비스·뜬다)가 여기 있어야
        # 표를 담은 청크가 검색에 걸린다. 표만 있으면 문서는 맞히고 절은 틀린다 — 라이브에서
        # 실제로 그렇게 실패했다.
        sections.append(
            f"{label} 환경에서 뜨는 서비스는 {len(rows)}개다: "
            f"{', '.join(r['name'] for r in rows)}.\n")
        sections.append("| 서비스 | 이미지 | 포트 | 의존 | 헬스체크 |")
        sections.append("|---|---|---|---|---|")
        for r in rows:
            sections.append(
                f"| {r['name']} | `{r['image']}` | {', '.join(r['ports']) or '-'} | "
                f"{', '.join(r['depends_on']) or '-'} | {r['healthcheck']} |")
        sections.append("")
        env = [(r["name"], r["env_keys"]) for r in rows if r["env_keys"]]
        if env:
            sections.append("설정 키 (**이름만** — 값은 옮기지 않는다):\n")
            sections += [f"- {n}: {', '.join(f'`{k}`' for k in keys)}" for n, keys in env]
            sections.append("")

    if not sections:
        return None

    title = "배포 토폴로지 (compose 에서 생성)"
    out = [_frontmatter(title), f"# {title}\n",
           "환경마다 뜨는 서비스와 이미지 태그다. **현재 돌고 있는 상태가 아니라 "
           "선언된 상태**이고, 둘이 다를 수 있다.\n"]
    out += sections
    out.append(_provenance(sources))
    return OpsDoc(name="ops-deploy-topology.md", title=title, body="\n".join(out))


# ── 리포 순회 ─────────────────────────────────────────────────────────────────

def generate(repo: Path) -> list[OpsDoc]:
    """리포에서 아는 설정을 찾아 지도를 만든다. 못 찾으면 **빈 목록**."""
    repo = Path(repo)
    docs: list[OpsDoc] = []

    for pattern in LOGBACK_GLOBS:
        for path in sorted(repo.glob(pattern)):
            if "/build/" in path.as_posix() or "/test/" in path.as_posix():
                continue
            doc = logging_map(path.read_text(encoding="utf-8"),
                              path.relative_to(repo).as_posix())
            if doc:
                docs.append(doc)
                break
        if docs:
            break

    composes: dict[str, str] = {}
    for pattern in COMPOSE_GLOBS:
        for path in sorted(repo.glob(pattern)):
            composes[path.relative_to(repo).as_posix()] = path.read_text(encoding="utf-8")
    topo = deploy_topology(composes)
    if topo:
        docs.append(topo)
    return docs
