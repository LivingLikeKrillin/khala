# DB 마이그레이션 (경량 순차)

`init.sql` 은 **빈 DB 최초 1회** 베이스라인(`/docker-entrypoint-initdb.d`)이다. 이후
스키마 변경(델타)은 이 디렉터리에 순서 있는 `.sql` 파일로 누적한다.

## 규칙

- 파일명 = 버전 키, **정렬 순서로 적용**: `001_<설명>.sql`, `002_<설명>.sql`, …
- 적용된 버전은 `schema_migrations` 테이블에 기록되고 재실행 시 건너뛴다(**멱등**).
- 각 파일은 자체 트랜잭션으로 적용된다.
- **멱등 DDL 권장**: `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE/INDEX IF NOT EXISTS` —
  빈 DB(init.sql 직후)와 기존 DB 양쪽에서 안전하도록.

## 적용

```bash
# 업데이트 한 줄 (이미지 재빌드·재기동 + 마이그레이션):
task update

# 마이그레이션만:
docker compose exec -T nexus-app python -m scripts.migrate
docker compose exec -T nexus-app python -m scripts.migrate --status   # 현황만
```
