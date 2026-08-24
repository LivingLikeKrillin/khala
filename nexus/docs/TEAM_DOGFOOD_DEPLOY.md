# Nexus 팀 도그푸딩 배포 런북 (로컬 + Cloudflare Tunnel)

> 목적: **내 로컬 머신에서 Nexus를 띄우고 Cloudflare Tunnel로 팀원에게 열어** 지식검색을 도그푸딩한다. 클라우드 VM·k8s·리버스프록시 없이. TLS와 "누가 들어오나" 게이트는 Cloudflare가 대신한다.
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

## 2. 스택 기동 (prod 오버레이)

```bash
task up:prod     # 리포 루트에서. 재빌드 + 기동. 임베딩 모델도 자동 pull.
```

`docker-compose.prod.yml` 오버레이가 로컬 dev와 다르게 하는 것:

| | 로컬 dev (`task up`) | 팀 배포 (`task up:prod`) |
|---|---|---|
| uvicorn | `--reload` (watcher) | reload 없음 |
| 코드 | `.:/app` 바인드 마운트 | **이미지에 구움**(재현 가능) |
| 재시작 | 없음 | `unless-stopped` (재부팅 후 자동 복구) |
| app 포트 | `0.0.0.0:8000` | **`127.0.0.1:8000`** (cloudflared만 접근) |
| db·ollama | 호스트에 5432·11434 게시 | **미게시** (컨테이너 네트워크 전용) |
| dev 토큰 | 약한 기본값 폴백 | **강값 필수** — 없으면 compose 실패 |

> `task up:prod`는 `docker-compose.override.yml`을 **병합하지 않는다**(`-f` 명시). 그 오버레이는
> 약한 토큰으로 폴백시키는 로컬 전용이다.

- 앱: `http://127.0.0.1:8000` (웹 Reader UI가 `/`에 서빙됨).
- `NEXUS_DEV_TOKEN` 미설정 → **compose 단계에서 실패**. 약값 + `NEXUS_REQUIRE_STRONG_DEV_TOKEN=1` →
  **앱이 부트 거부**(RuntimeError). 둘 다 §1을 다시 확인하라는 뜻이다.
- 로컬에서 먼저 `http://127.0.0.1:8000` 열어 검색이 되는지 확인하고 터널로 넘어갈 것.
- 정지는 `task down:prod`, 코드 갱신 후 재배포는 `task update:prod`(마이그레이션 포함).

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
# 리포 루트에서 (루트 페이지 ID들, 콤마 구분)
task ingest:notion ROOTS="<pageId1>,<pageId2>"
```

- **정본은 Notion에 남는다.** Nexus는 인덱스다(CLAUDE.md 원칙 5). 팀은 계속 Notion에서 쓴다.
- 적재는 **콘텐츠 해시로 멱등**하다 — 크론으로 반복 실행해도 중복이 안 생기고 변경분만 재인덱싱된다.
  루트 페이지 ID는 **매 실행 인자**다(영속 config 필드 없음).
- 첫 도그푸딩은 **좁고 관련성 높은 페이지 뭉치**부터(콜드스타트 방지). 민감 페이지는 애초에 적재 대상에서 빼는 것도 방어선.

### 5.2 khala 자기 문서 적재 (`task ingest:self`)

팀 코퍼스의 절반은 이미 khala 자기 문서다(`nexus/docs/**/*.md`). 그런데 전부 기술·운영
문서라서, 2026-08-14 에 팀원이 *"왜 서비스이름이 칼라인거지?"* 라고 물었을 때 봇은
👎 `not_found` 를 냈다 — 이름과 목적을 설명하는 문서가 적재 경로 **밖**(`docs/`, `adr/`)에
있었기 때문이다.

```bash
# 리포 루트에서
task ingest:self
```

- 넣는 것: `docs/src/content/docs/ko/philosophy.md` · `adr/ADR-0005-*.md` (18청크)
- **사본을 리포에 남기지 않는다.** 실행 시점에 정본에서 복사하고 끝나면 지운다.
- 콘텐츠 해시 멱등 — 반복 실행해도 변경분만 다시 인덱싱된다.
- 정본이 바뀌면 **다시 돌려야 반영된다**(자동 추적 없음).
- 적재 전후로 정책 8질의 자를 2런씩 돌려 **7/8 유지 · 정책 답변 8건 어디에도 이 문서들이
  근거로 섞이지 않음**을 확인했다(2026-08-24). 다른 테넌트는 `TENANT=<이름>`.

### 5.1 삭제 반영 (재조정)

기본 적재는 **추가만** 한다. Notion에서 지운 페이지를 Nexus에서도 내리려면 `--reconcile`을 준다:

```bash
# 먼저 계획만 본다 — DB는 건드리지 않는다
task ingest:notion ROOTS="<pageId1>,<pageId2>" FLAGS="--reconcile --dry-run"

# 확인했으면 적용: 사라진 페이지 soft_delete + 되살아난 페이지 revive
task ingest:notion ROOTS="<pageId1>,<pageId2>" FLAGS="--reconcile"
```

> ⚠️ **첫 `--reconcile` 실행은 반드시 `--since` 없이(=전체) 돌릴 것.** 문서의 출처 root는 적재
> 시점에 `prov_inputs`로 기록되는데, `--since`로 건너뛴 페이지는 그 기록이 갱신되지 않는다. 백필이
> 끝나기 전까지 그런 문서는 재조정 범위 밖이라 **아무 일도 일어나지 않는다**(안전한 방향의 실패다).

지켜지는 규칙:

- **`--roots`를 좁혀 실행해도 안전하다.** 문서의 출처 root가 이번 실행에 **전부** 포함된 경우에만
  판정 대상이다. rootA·rootB 양쪽에 걸린 페이지를 rootA만 걷고 지우는 일은 일어나지 않는다.
- prune 대상이 활성 문서의 **50%를 넘으면 거부**하고 아무것도 적용하지 않는다(`--roots` 오타 방어).
  의도한 대량 정리라면 `--force`.
- 되살릴 때 **현재 세대의 청크만** 복구된다. 낡은 본문이 검색에 돌아오지 않는다.
- 명시적으로 `supersede`한 문서는 재조정이 건드리지 않는다(양방향 모두).

### 알려진 한계 (적재 전에 알고 들어갈 것)

- **걸어온 root 밖으로 옮겨진 페이지는 삭제된 페이지와 구분되지 않는다.** 인테그레이션 공유가 끊긴
  페이지도 마찬가지다. 둘 다 `--reconcile` 시 내려간다. 다만 **자기치유**된다 — 그 페이지의 새 위치를
  포함해 다시 걸으면 되살아난다.
- 표·토글·임베드·컬럼·synced block은 미지원(`rich_text`가 있으면 살리고 없으면 드롭). 이미지는 placeholder.
- Notion API rate limit 백오프가 없다 — 큰 워크스페이스는 나눠서 적재할 것.
- `--since` 워터마크는 실패한 페이지를 건너뛸 수 있다(워터마크가 먼저 전진). 주기적으로 `--since` 없이 전체 재실행.
- 적재된 문서는 `external_spec` 라벨이 붙어 **거버넌스 밖**이다 — 검색에는 뜨지만 승인·신뢰 라벨 체계에는 안 들어간다.

## 6. 검증 체크리스트

- [ ] 로컬 `http://localhost:8000`에서 검색 정상
- [ ] `NEXUS_DEV_TOKEN`이 강값(≈43자), `NEXUS_REQUIRE_STRONG_DEV_TOKEN=1` — 약한 값이면 부트 거부됨을 확인
- [ ] `cloudflared tunnel run` 동작, `https://nexus.<도메인>` 응답
- [ ] **Access 정책이 실제로 막는지**: 비인가 이메일/시크릿창으로 접속 → OTP 화면에서 막힘
- [ ] 인가된 팀원: OTP 통과 → 검색되고 인용 근거/신뢰 배지 보임
- [ ] Notion 코퍼스가 검색에 반영됨
- [ ] 첫 `--reconcile`을 `--since` 없이 1회 실행(=`prov_inputs` 백필) → 이후 cron 에 `--reconcile` 상시 부착 가능
- [ ] Notion 에서 시험용 페이지 1개를 지우고 `--reconcile --dry-run` → `pruned=1` 로 잡히는지 확인
- [ ] (CORS 이슈 시) `config.yaml`의 `auth.allowed_origins`에 `https://nexus.<도메인>` 추가 — 웹UI와 API가 같은 오리진이면 대개 불필요
- [ ] `/status` 의 `embedding_*` 필드가 이 배포가 의도한 세대를 말하는지 (§6.1) — 컷오버를 안 했다면 `nomic-embed-text` · `embedding` · `ollama`

## 6.1 임베딩 세대 전환 (한국어 검색을 KURE-v1 로)

배포는 **자기 세대를 스스로 고른다.** 리포 기본값은 현행(`nomic-embed-text` · `embedding` ·
`ollama`)이고, 재임베딩을 마치지 않은 설치가 빈 컬럼을 읽는 일이 없도록 그대로 둔다. 전환은 이
배포의 `.env` 에서만 일어난다 — 추적 파일을 고치면 `git checkout` 이 프로덕션 설정을 되돌린다.

측정 근거: 한국어 팩(공개 대역)에서 벡터 다리 `Recall@10` 0.402 → 0.975, ivfflat 을 통과한
융합 0.777 → 0.988 (`docs/KOREAN_SEARCH_QUALITY.md` §3.4~3.5).

```bash
# 0) 적재를 잠시 멈춘다(수동/크론 둘 다). 창 안에 적재된 청크는 새 컬럼이 비어 있게 된다.
# 1) 사이드카 (2~3GB 이미지, 모델 적재 ~9초). 리비전은 compose 에 커밋으로 박혀 있다.
docker compose --profile embed up -d nexus-embed
curl -s localhost:8080/health          # ready:true · revision 이 40자 커밋인지 확인

# 2) 재임베딩 — `--column` 은 **명시**한다. 설정을 따라가면 아직 옛 컬럼을 겨눈다.
docker compose exec -T nexus-app nexus reembed run     --column embedding_1024 --model KURE-v1 --backend sidecar --all-tenants

# 3) 인덱스는 **다 채운 뒤**에 만든다 (lists 는 그때의 행 수로 정해진다)
docker compose exec -T nexus-app nexus reembed create-index --column embedding_1024

# 4) 두 번째 패스 — 0 이어야 한다. 0 이 아니면 창 안에 적재된 것이 있었다는 뜻이고, 이 패스가 채운다.
docker compose exec -T nexus-app nexus reembed run     --column embedding_1024 --model KURE-v1 --backend sidecar --all-tenants

# 5) 컷오버 조건 — 테넌트마다 서야 한다
docker compose exec -T nexus-app nexus reembed status --column embedding_1024 --all-tenants

# 6) flip: `.env` 의 세 줄을 **함께** 바꾸고 재기동한다. 하나만 바꾸면 앱이 부팅을 거부한다.
#      NEXUS_EMBEDDING_MODEL=KURE-v1
#      NEXUS_EMBEDDING_COLUMN=embedding_1024
#      NEXUS_EMBEDDING_BACKEND=sidecar
docker compose up -d nexus-app
curl -s localhost:8000/status | jq '{embedding_model, embedding_column, embedding_backend,
                                    embedding_backend_connected, embedding_coverage}'
```

**롤백**은 그 세 줄을 지우고 재기동하는 것이다. 옛 컬럼과 인덱스는 손대지 않았으므로 랭킹이 그대로
돌아온다 — 단, **flip 이후 적재된 청크는 옛 컬럼이 비어 있다.** 그 수는
`nexus reembed status --column embedding --all-tenants` 가 `남은` 으로 보고하고, 되메우려면 같은
도구를 반대로 겨눈다(`--column embedding --model nomic-embed-text --backend ollama --all-tenants`).

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
