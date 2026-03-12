---
name: split-pr
description: "현재 변경을 여러 PR로 분할하는 방법을 안내합니다. /split-pr로 수동 호출."
allowed-tools: Read, Bash, Grep, Glob
---

현재 브랜치의 변경이 여러 관심사에 걸쳐 있을 때, 구체적인 분할 방법을 안내합니다.

## 1단계: 분석

1. `npx karax check --json`으로 변경 분석
2. 각 관심사 그룹별로 파일 목록을 나열
3. 의존 관계를 고려한 머지 순서 제안

## 2단계: 브랜치 상태 진단

4. 커밋 구조를 파악한다:
   - `git log --oneline main..HEAD` — 현재 브랜치의 커밋 목록
   - `git log --oneline --graph main..HEAD` — 브랜치 구조 시각화
5. 부모 브랜치 관계를 확인한다:
   - 현재 브랜치가 main에서 직접 파생됐는지, 다른 feature 브랜치 위에 쌓였는지 판단

## 3단계: 실행 전략 선택

진단 결과에 따라 아래 세 전략 중 하나를 추천한다.

### 전략 A: 새 브랜치 + cherry-pick (기본 추천)

**언제:** 커밋이 관심사별로 섞여 있거나, 일부 커밋만 PR에 포함하고 싶을 때.
실무에서 가장 흔한 상황이고 가장 덜 꼬인다.

**핵심:** PR은 "브랜치 전체"가 아니라 "base 대비 최종 diff"를 본다.
따라서 깨끗한 새 브랜치를 만들고 필요한 커밋만 옮기면 원하는 diff만 PR에 담을 수 있다.

**절차:**
1. 1단계에서 분석한 그룹별로, 각 그룹에 속하는 커밋을 식별한다.
   - `git log --oneline main..HEAD`에서 커밋 해시와 내용을 매칭
   - 하나의 커밋이 여러 그룹에 걸치면, 해당 커밋은 가장 선순위 그룹에 배정
2. 그룹별로 새 브랜치를 생성하고 cherry-pick한다:
   ```
   git checkout main && git pull origin main
   git checkout -b <group-branch-name>
   git cherry-pick <commit1> <commit2> ...
   ```
3. 충돌 발생 시:
   - 충돌 파일과 내용을 보여주고 해결을 돕는다
   - `git cherry-pick --continue`로 진행
4. 각 브랜치를 push하고 PR을 생성한다.
   - 머지 순서(1단계에서 결정)를 PR 설명에 명시

**주의:** 기존 브랜치는 건드리지 않고 보존한다. 새 브랜치들로 PR을 올린 후, 기존 브랜치는 나중에 정리하면 된다.

### 전략 B: base branch 조정

**언제:** 부모 작업 브랜치(feature/A) 위에 후속 작업(feature/B)을 쌓았고, B의 변경만 리뷰받고 싶을 때.

**핵심:** PR의 base를 main이 아닌 부모 브랜치로 잡으면 A→B 차이만 보인다.

**절차:**
1. 부모 브랜치가 이미 PR로 올라가 있는지 확인
2. `gh pr create --base <parent-branch>` 로 PR 생성
3. PR 설명에 머지 순서를 명시:
   - "이 PR은 `feature/A` 머지 후에 main으로 리베이스 예정입니다"

**주의:** 부모 PR이 먼저 머지되어야 한다. 머지 순서 관리가 필요하므로 이 점을 사용자에게 안내한다.

### 전략 C: rebase 정리 (안내만 제공)

**언제:** 분할 대상이 아니라, 내용은 맞는데 커밋 히스토리만 지저분할 때.
(예: WIP 커밋, fixup 커밋이 많아서 정리가 필요한 경우)

**핵심:** `rebase -i`로 커밋을 squash/drop/reorder 하여 깔끔한 히스토리를 만든다.

**절차 (안내):**
이 전략은 interactive input이 필요하므로 직접 실행하지 않는다.
사용자에게 아래 명령어와 절차를 안내한다:
```
git rebase -i main
# 에디터에서:
#   pick  — 유지
#   squash — 이전 커밋에 합치기
#   drop  — 제거
# 저장 후 종료

git push origin <branch> --force-with-lease
```

**주의:** 다른 사람과 공유 중인 브랜치에서는 히스토리 재작성에 주의해야 한다. 이 점을 반드시 경고한다.

## 전략 선택 기준 요약

| 상황 | 추천 전략 |
|---|---|
| 커밋이 관심사별로 섞여 있다 | A: 새 브랜치 + cherry-pick |
| 일부 커밋만 PR에 넣고 싶다 | A: 새 브랜치 + cherry-pick |
| 부모 브랜치 위에 쌓인 후속 작업이다 | B: base branch 조정 |
| 내용은 맞는데 커밋 로그만 더럽다 | C: rebase 정리 (안내) |

$ARGUMENTS로 특정 전략을 지정할 수 있습니다 (예: `/split-pr cherry-pick`, `/split-pr rebase`).
