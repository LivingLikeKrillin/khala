# Nexus 팀 도그푸딩 배포 런북 (로컬 + Cloudflare Tunnel)

> 목적: **내 로컬 머신에서 Nexus를 띄우고 Cloudflare Tunnel로 팀원(예: PFPlay)에게 열어** 지식검색을 도그푸딩한다. 클라우드 VM·k8s·리버스프록시 없이. TLS와 "누가 들어오나" 게이트는 Cloudflare가 대신한다.
>
> ⚠️ **이 문서의 단 하나의 절대 규칙: Cloudflare Access(엣지 인증) 없이는 터널을 팀에 열지 말 것.** 이유는 §0.

## 0. 왜 Access가 필수인가 (읽고 시작할 것)

Nexus는 로컬 무마찰 온램프를 위해 `NEXUS_DEV_TOKEN`을 켜면:
- 앱이 **INTERNAL `local-dev` principal**을 등록하고,
- **`GET /auth/dev-token`이 그 토큰을 도달한 누구에게나 그냥 준다**(의도적 비-게이트 — 웹 UI가 자동 Bearer로 씀).

로컬(localhost)에선 안전하지만, 터널로 그냥 열면 **URL을 아는 누구/무엇(자동 스캐너 포함)이든 INTERNAL 코퍼스 전체를 무인증으로 읽는다.** 안정 서브도메인은 TLS 인증서가 **Certificate Transparency 로그에 공개**되어 며칠이면 발견된다 — "URL 아무도 모름"은 성립하지 않는다.

→ **Cloudflare Access를 터널 호스트네임 앞에 걸어** 엣지에서 신원을 막으면, `/auth/dev-token`에 **도달하기 전에** 차단된다. 그러면 이 온램프가 오히려 기능이 된다: Access = "누가 들어오나", Nexus 공유 토큰 = "무엇을 보나". 코드 0줄.

## 1. 강한 dev 토큰 발급 (약한 기본값 금지)

`docker-compose.override.yml`은 `NEXUS_DEV_TOKEN`을 안 주면 약한 기본값 `nexus-local-dev`로 폴백한다. **터널 배포에선 반드시 강값으로 덮어쓴다.**

```bash
cd nexus
python -m nexus.cli auth gen-token   # secrets.token_urlsafe(32), ≈43자
# 출력된 토큰을 복사
```

`.env`(리포 루트 `nexus/.env`, `.env.example` 참고)에 넣는다:

```dotenv
# 강한 랜덤값 — nexus-local-dev 절대 금지
NEXUS_DEV_TOKEN=<위에서 발급한 토큰>

# 터널 배포 안전장치: 약한 토큰이면 부트를 거부(§7 하드닝)
NEXUS_REQUIRE_STRONG_DEV_TOKEN=1

# Notion 적재용 (§5)
NOTION_TOKEN=<Notion 내부 인테그레이션 토큰>
```

> `NEXUS_REQUIRE_STRONG_DEV_TOKEN=1`을 켜면 약한/기본 토큰으로는 앱이 **부트를 거부**한다(로컬 무마찰은 이 env 없이 그대로 경고만). 터널 배포엔 반드시 켤 것.

## 2. 스택 기동

```bash
cd nexus
task up          # core: nexus-db(Postgres+pgvector) · nexus-ollama · nexus-app(:8000)
task models      # Ollama 임베딩 모델 pull (nomic-embed-text) — 최초 1회
```

- 앱: `http://localhost:8000` (웹 Reader UI가 `/`에 서빙됨).
- 강토큰이 안 먹었으면(약한 기본값 + `NEXUS_REQUIRE_STRONG_DEV_TOKEN=1`) 부트가 거부된다 → §1 다시 확인.
- 로컬에서 먼저 `http://localhost:8000` 열어 검색이 되는지 확인하고 터널로 넘어갈 것.

## 3. Cloudflare Tunnel 연결

`cloudflared` 설치 후(플랫폼별 설치는 Cloudflare 문서), 이름있는 터널로 `localhost:8000`을 공개 호스트네임에 연결한다:

```bash
cloudflared tunnel login                      # 브라우저로 Cloudflare 계정 인증
cloudflared tunnel create nexus-dogfood       # 터널 생성 (자격증명 파일 발급)
# DNS 라우트: nexus.<도메인> → 이 터널
cloudflared tunnel route dns nexus-dogfood nexus.<도메인>
```

`~/.cloudflared/config.yml` (또는 프로젝트 로컬):
```yaml
tunnel: nexus-dogfood
credentials-file: /path/to/<tunnel-id>.json
ingress:
  - hostname: nexus.<도메인>
    service: http://localhost:8000
  - service: http_status:404
```

실행:
```bash
cloudflared tunnel run nexus-dogfood
```

> 대안(민감정보 전혀 없는 코퍼스일 때만): `cloudflared tunnel --url http://localhost:8000` 퀵터널은 랜덤 `*.trycloudflare.com`을 준다(DNS/CT 흔적 없음). 단 **퀵터널엔 Access를 못 건다** → 무민감 코퍼스 + 세션 중에만 띄우고 즉시 내리기 전제에서만.

## 4. Cloudflare Access 정책 (필수, ~5분)

Cloudflare **Zero Trust** 대시보드:
1. **Access → Applications → Add an application → Self-hosted**.
2. Application domain = `nexus.<도메인>`.
3. **Policy 1개**: Action=**Allow**, Include 규칙 하나:
   - *Emails* = 팀원 이메일 나열, 또는
   - *Emails ending in* = `@<너네도메인>`.
4. 로그인 방식: **One-time PIN(이메일 OTP)** — 별도 IdP/SSO 연결 불필요.
5. 저장.

이제 `nexus.<도메인>`은 **Access 통과자만** 도달한다. 팀원 경험: URL 접속 → 이메일로 온 코드 입력 → Nexus 웹 UI → 바로 검색.

## 5. 팀 Notion 적재

Notion 내부 인테그레이션을 만들고(토큰 = `.env`의 `NOTION_TOKEN`), 적재할 페이지들에 **그 인테그레이션을 공유**한 뒤:

```bash
cd nexus
# 루트 페이지 ID들(콤마 구분). incremental sync는 since 워터마크로 자동.
python -m nexus.cli ingest-notion --roots "<pageId1>,<pageId2>"
```

- 루트 페이지 ID는 **매 실행 인자**다(영속 config 필드 없음). 정기 갱신은 이 명령을 크론/수동 재실행.
- 첫 도그푸딩은 **좁고 관련성 높은 페이지 뭉치**부터(콜드스타트 방지). 민감 페이지는 애초에 적재 대상에서 빼는 것도 방어선.

## 6. 검증 체크리스트

- [ ] 로컬 `http://localhost:8000`에서 검색 정상
- [ ] `NEXUS_DEV_TOKEN`이 강값(≈43자), `NEXUS_REQUIRE_STRONG_DEV_TOKEN=1` — 약한 값이면 부트 거부됨을 확인
- [ ] `cloudflared tunnel run` 동작, `https://nexus.<도메인>` 응답
- [ ] **Access 정책이 실제로 막는지**: 비인가 이메일/시크릿창으로 접속 → OTP 화면에서 막힘
- [ ] 인가된 팀원: OTP 통과 → 검색되고 인용 근거/신뢰 배지 보임
- [ ] Notion 코퍼스가 검색에 반영됨
- [ ] (CORS 이슈 시) `config.yaml`의 `auth.allowed_origins`에 `https://nexus.<도메인>` 추가 — 웹UI와 API가 같은 오리진이면 대개 불필요

## 7. 이 배포를 위한 코드 하드닝 (구현됨)

`nexus/nexus/auth/config.py` — **약한 dev 토큰 가드**:
- `NEXUS_DEV_TOKEN`이 약함(기본값 `nexus-local-dev` 또는 24자 미만)이면 부트 시 **경고**.
- `NEXUS_REQUIRE_STRONG_DEV_TOKEN=1`이면 약한 토큰에 **부트 거부**(RuntimeError).
- 로컬 무마찰(경고만)은 그대로, 터널 배포(강제)만 하드락 — 두 목적 양립.

## 8. 안전 수칙 요약

- **Access 없이 안정 서브도메인 터널 열지 말 것** (§0).
- **`NEXUS_DEV_TOKEN`은 항상 강값 + 터널 배포엔 `NEXUS_REQUIRE_STRONG_DEV_TOKEN=1`.**
- 도그푸딩 세션 밖에선 터널/스택 내리기: `cloudflared` 중지 + `task down`.
- 민감 문서는 **적재 자체를 안 하는 것**이 가장 확실한 방어선.
- 이건 도그푸딩용 최소 구성이다. 정식 다중테넌트/멤버별 토큰/JWT·SSO는 demand-pull(측정으로 수요 확인 후).
