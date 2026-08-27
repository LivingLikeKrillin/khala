# Pack A 판정 대기 인용 — 판정 워크시트 (revision 4 후보)

답변이 인용했으나 라벨이 gold/not_gold 어느 쪽으로도 판정하지 않은 문서들.

⛔ **정정 (2026-08-17): 이 목록은 게이트를 막지 않는다.** 이 파일의 첫 판이 "비지 않으면 총점을
막는다" 고 적었는데 **거짓이다** — r3·r4·r5 네 실행 모두 `partial: false` 로 총점을 냈고, 그때도
이 목록은 17건이었다. 게이트가 막는 조건은 **한 질의의 인용이 전부 미판정일 때**(그 질의의 판정이
`unadjudicated` 가 된다)이고, 실제로는 매 질의가 gold 문서도 함께 인용해 그 조건이 성립하지
않았다. 판정의 값은 게이트 해제가 아니라 (1) 목록의 잡음 제거와 (2) **앞으로** 그 문서만 인용한
답변이 미판정으로 새지 않게 하는 것이다.

**판정 규칙은 라벨 revision 1~3 이 쓴 것과 같다:** 그 문서 본문에서 라벨의 요구
(`must_contain`)가 **전부** 성립하면 gold, 하나라도 불성립이면 not_gold. 채점기와
**같은 함수**(`facts_present`)로 재고, 사본을 두지 않는다.

⚠ **이 규칙은 대리자다.** 토큰이 본문에 있다는 것과 그 문서가 질문에 답한다는 것은
같지 않다 — 그래서 이 파일은 *제안*이고, 서명은 사람의 것이다. 특히 gold 제안은
`rationale` 없이 토큰만으로 통과할 수 있으니 아래 요구 성립 근거를 보고 판단하라.

제안 생성: 에이전트 · 2026-08-17 · 대상 질의 19건

## q006 — 인증서 서명 요청을 만들어 클라이언트 인증서를 발급받으려면

- 요구: `[['CertificateSigningRequest', '인증서 서명 요청'], ['승인', 'approve']]`
- 기존 gold: ['tasks/tls/certificate-issue-client-csr.md', 'tasks/administer-cluster/certificates.md', 'tasks/tls/managing-tls-in-a-cluster.md']
- **gold 제안** — `kubeadm을 사용한 인증서 관리` (`tasks/administer-cluster/kubeadm/kubeadm-certs.md`, 11,882자)
    - `['CertificateSigningRequest', '인증서 서명 요청']` → 성립: CertificateSigningRequest, 인증서 서명 요청
    - `['승인', 'approve']` → 성립: 승인, approve

## q007 — 미니큐브에서 엔진엑스 인그레스 컨트롤러를 켜려면

- 요구: `[['addons', '애드온'], ['ingress', '인그레스']]`
- 기존 gold: ['tasks/access-application-cluster/ingress-minikube.md']
- **not_gold 제안** — `인그레스(Ingress)` (`concepts/services-networking/ingress.md`, 17,718자)
    - `['addons', '애드온']` → **불성립**
    - `['ingress', '인그레스']` → 성립: ingress, 인그레스

## q008 — 워드프레스와 마이에스큐엘을 퍼시스턴트 볼륨 위에 올리는 예제

- 요구: `[['퍼시스턴트볼륨', 'PersistentVolume'], ['MySQL']]`
- 기존 gold: ['tutorials/stateful-application/mysql-wordpress-persistent-volume.md']
- **not_gold 제안** — `스토리지로 퍼시스턴트볼륨(PersistentVolume)을 사용하도록 파드 설정하기` (`tasks/configure-pod-container/configure-persistent-volume-storage.md`, 6,173자)
    - `['퍼시스턴트볼륨', 'PersistentVolume']` → 성립: 퍼시스턴트볼륨, PersistentVolume
    - `['MySQL']` → **불성립**
- **not_gold 제안** — `퍼시스턴트볼륨 반환 정책 변경하기` (`tasks/administer-cluster/change-pv-reclaim-policy.md`, 3,029자)
    - `['퍼시스턴트볼륨', 'PersistentVolume']` → 성립: 퍼시스턴트볼륨, PersistentVolume
    - `['MySQL']` → **불성립**

## q009 — 퍼시스턴트볼륨클레임을 만들어 파드에 저장소를 붙이는 절차

- 요구: `[['퍼시스턴트볼륨클레임', 'PersistentVolumeClaim'], ['마운트', 'volumeMounts']]`
- 기존 gold: ['tasks/configure-pod-container/configure-persistent-volume-storage.md']
- **gold 제안** — `스토리지 클래스` (`concepts/storage/storage-classes.md`, 19,072자)
    - `['퍼시스턴트볼륨클레임', 'PersistentVolumeClaim']` → 성립: 퍼시스턴트볼륨클레임
    - `['마운트', 'volumeMounts']` → 성립: 마운트, volumeMounts
- **gold 제안** — `예시: WordPress와 MySQL을 퍼시스턴트 볼륨에 배포하기` (`tutorials/stateful-application/mysql-wordpress-persistent-volume.md`, 6,004자)
    - `['퍼시스턴트볼륨클레임', 'PersistentVolumeClaim']` → 성립: 퍼시스턴트볼륨클레임
    - `['마운트', 'volumeMounts']` → 성립: 마운트

## q010 — 스테이트풀셋 레플리카 개수를 늘리거나 줄이려면

- 요구: `[['scale'], ['레플리카']]`
- 기존 gold: ['tasks/run-application/scale-stateful-set.md']
- **gold 제안** — `복제 스테이트풀 애플리케이션 실행하기` (`tasks/run-application/run-replicated-stateful-application.md`, 13,155자)
    - `['scale']` → 성립: scale
    - `['레플리카']` → 성립: 레플리카

## q013 — 파드시큐리티어드미션은 어떤 모드로 강제하나

- 요구: `[['enforce', '강제'], ['audit', '감사'], ['warn', '경고']]`
- 기존 gold: ['concepts/security/pod-security-admission.md', 'setup/best-practices/enforcing-pod-security-standards.md']
- **gold 제안** — `파드 시큐리티 스탠다드를 클러스터 수준에 적용하기` (`tutorials/security/cluster-level-pss.md`, 10,993자)
    - `['enforce', '강제']` → 성립: enforce
    - `['audit', '감사']` → 성립: audit
    - `['warn', '경고']` → 성립: warn, 경고

## q014 — 리소스쿼터로 네임스페이스별 사용량을 제한하려면

- 요구: `[['ResourceQuota', '리소스 쿼터'], ['네임스페이스']]`
- 기존 gold: ['concepts/policy/resource-quotas.md']
- **gold 제안** — `네임스페이스에 대한 메모리 및 CPU 쿼터 구성` (`tasks/administer-cluster/manage-resources/quota-memory-cpu-namespace.md`, 4,137자)
    - `['ResourceQuota', '리소스 쿼터']` → 성립: ResourceQuota
    - `['네임스페이스']` → 성립: 네임스페이스
- **gold 제안** — `리밋 레인지(Limit Range)` (`concepts/policy/limit-range.md`, 3,789자)
    - `['ResourceQuota', '리소스 쿼터']` → 성립: 리소스 쿼터
    - `['네임스페이스']` → 성립: 네임스페이스
- **gold 제안** — `멀티 테넌시(multi-tenancy)` (`concepts/security/multi-tenancy.md`, 17,343자)
    - `['ResourceQuota', '리소스 쿼터']` → 성립: 리소스 쿼터
    - `['네임스페이스']` → 성립: 네임스페이스
- **gold 제안** — `스토리지 사용량 제한` (`tasks/administer-cluster/limit-storage-consumption.md`, 1,806자)
    - `['ResourceQuota', '리소스 쿼터']` → 성립: ResourceQuota
    - `['네임스페이스']` → 성립: 네임스페이스
- **gold 제안** — `파드 및 컨테이너 리소스 관리` (`concepts/configuration/manage-resources-containers.md`, 21,958자)
    - `['ResourceQuota', '리소스 쿼터']` → 성립: ResourceQuota, 리소스 쿼터
    - `['네임스페이스']` → 성립: 네임스페이스

## q016 — 컨피그맵을 붙여서 레디스 설정을 바꾸려면

- 요구: `[['컨피그맵', 'ConfigMap'], ['Redis', '레디스']]`
- 기존 gold: ['tutorials/configuration/configure-redis-using-configmap.md']
- **not_gold 제안** — `컨피그맵(ConfigMap)` (`concepts/configuration/configmap.md`, 5,898자)
    - `['컨피그맵', 'ConfigMap']` → 성립: 컨피그맵, ConfigMap
    - `['Redis', '레디스']` → **불성립**

## q019 — 컨테이너에게 환경 변수를 넘겨주려면

- 요구: `[['env'], ['환경 변수']]`
- 기존 gold: ['tasks/inject-data-application/define-environment-variable-container.md', 'concepts/containers/container-environment.md', 'tasks/inject-data-application/define-interdependent-environment-variables.md']
- **gold 제안** — `시크릿(Secret)을 사용하여 안전하게 자격증명 배포하기` (`tasks/inject-data-application/distribute-credentials-secure.md`, 4,696자)
    - `['env']` → 성립: env
    - `['환경 변수']` → 성립: 환경 변수
- **gold 제안** — `환경 변수로 컨테이너에 파드 정보 노출하기` (`tasks/inject-data-application/environment-variable-expose-pod-information.md`, 3,164자)
    - `['env']` → 성립: env
    - `['환경 변수']` → 성립: 환경 변수

## q020 — 잡에서 병렬 처리 개수를 늘리려면

- 요구: `[['병렬', 'parallelism'], ['잡', 'Job']]`
- 기존 gold: ['tasks/job/parallel-processing-expansion.md', 'tasks/job/coarse-parallel-processing-work-queue.md', 'tasks/job/fine-parallel-processing-work-queue.md', 'tasks/job/indexed-parallel-processing-static.md']
- **not_gold 제안** — `크론잡(CronJob)` (`concepts/workloads/controllers/cron-jobs.md`, 8,028자)
    - `['병렬', 'parallelism']` → **불성립**
    - `['잡', 'Job']` → 성립: 잡, Job

## q021 — 파드 안에서 API 서버로 요청을 보내려면

- 요구: `[['서비스 어카운트', 'ServiceAccount'], ['토큰', 'token']]`
- 기존 gold: ['tasks/run-application/access-api-from-pod.md']
- **gold 제안** — `클러스터 접근` (`tasks/access-application-cluster/access-cluster.md`, 6,935자)
    - `['서비스 어카운트', 'ServiceAccount']` → 성립: 서비스 어카운트
    - `['토큰', 'token']` → 성립: 토큰, token

## q022 — 여러 팀이 클러스터를 나눠 쓰도록 가르려면

- 요구: `[['네임스페이스'], ['분할', '나눠', '공유']]`
- 기존 gold: ['tasks/administer-cluster/namespaces.md', 'concepts/security/multi-tenancy.md']
- **not_gold 제안** — `네임스페이스` (`concepts/overview/working-with-objects/namespaces.md`, 4,124자)
    - `['네임스페이스']` → 성립: 네임스페이스
    - `['분할', '나눠', '공유']` → **불성립**

## q024 — 볼륨으로부터 스냅샷을 떠두려면

- 요구: `[['VolumeSnapshot', '볼륨 스냅샷']]`
- 기존 gold: ['concepts/storage/volume-snapshots.md']
- **gold 제안** — `볼륨 스냅샷 클래스` (`concepts/storage/volume-snapshot-classes.md`, 1,742자)
    - `['VolumeSnapshot', '볼륨 스냅샷']` → 성립: VolumeSnapshot, 볼륨 스냅샷

## q025 — 노드에 taint 를 걸면 파드가 어떻게 되나

- 요구: `[['NoSchedule'], ['NoExecute', '축출']]`
- 기존 gold: ['concepts/scheduling-eviction/taint-and-toleration.md']
- **not_gold 제안** — `노드` (`concepts/architecture/nodes.md`, 8,290자)
    - `['NoSchedule']` → **불성립**
    - `['NoExecute', '축출']` → 성립: NoExecute, 축출

## q027 — kubeadm 클러스터를 어떤 순서로 업그레이드하나

- 요구: `[['컨트롤 플레인'], ['워커', 'worker']]`
- 기존 gold: ['tasks/administer-cluster/kubeadm/kubeadm-upgrade.md', 'tasks/administer-cluster/cluster-upgrade.md']
- **gold 제안** — `kubeadm을 사용한 인증서 관리` (`tasks/administer-cluster/kubeadm/kubeadm-certs.md`, 11,882자)
    - `['컨트롤 플레인']` → 성립: 컨트롤 플레인
    - `['워커', 'worker']` → 성립: worker

## q029 — CoreDNS 로 서비스 디스커버리를 붙이려면

- 요구: `[['CoreDNS'], ['kube-dns']]`
- 기존 gold: ['tasks/administer-cluster/coredns.md', 'tasks/administer-cluster/dns-custom-nameservers.md']
- **not_gold 제안** — `구성 모범 사례` (`concepts/configuration/overview.md`, 5,247자)
    - `['CoreDNS']` → **불성립**
    - `['kube-dns']` → **불성립**
- **not_gold 제안** — `서비스 디버깅하기` (`tasks/debug/debug-application/debug-service.md`, 18,216자)
    - `['CoreDNS']` → **불성립**
    - `['kube-dns']` → 성립: kube-dns
- **gold 제안** — `서비스와 애플리케이션 연결하기` (`tutorials/services/connect-applications-service.md`, 12,088자)
    - `['CoreDNS']` → 성립: CoreDNS
    - `['kube-dns']` → 성립: kube-dns

## q030 — livenessProbe 와 readinessProbe 를 어떻게 나눠 설정하나

- 요구: `[['livenessProbe'], ['readinessProbe']]`
- 기존 gold: ['tasks/configure-pod-container/configure-liveness-readiness-startup-probes.md']
- **not_gold 제안** — `활성(Liveness), 준비성(Readiness) 그리고 시작(Startup) 프로브` (`concepts/configuration/liveness-readiness-startup-probes.md`, 1,068자)
    - `['livenessProbe']` → **불성립**
    - `['readinessProbe']` → **불성립**

## q035 — 컨피그 맵을 바꾸면 설정 파일을 어떻게 갱신하나

- 요구: `[['마운트', '볼륨'], ['갱신', '반영', '업데이트']]`
- 기존 gold: ['tutorials/configuration/updating-configuration-via-a-configmap.md', 'concepts/configuration/configmap.md']
- **gold 제안** — `컨피그맵을 사용해서 Redis 설정하기` (`tutorials/configuration/configure-redis-using-configmap.md`, 4,094자)
    - `['마운트', '볼륨']` → 성립: 마운트, 볼륨
    - `['갱신', '반영', '업데이트']` → 성립: 갱신

## q039 — 인그레스컨트롤러는 어떤 기준으로 고르나

- 요구: `[['인그레스 컨트롤러'], ['설명서', '문서'], ['검토', '다르게 작동']]`
- 기존 gold: ['concepts/services-networking/ingress-controllers.md']
- **gold 제안** — `인그레스(Ingress)` (`concepts/services-networking/ingress.md`, 17,718자)
    - `['인그레스 컨트롤러']` → 성립: 인그레스 컨트롤러
    - `['설명서', '문서']` → 성립: 설명서, 문서
    - `['검토', '다르게 작동']` → 성립: 검토, 다르게 작동

## 요약

- gold 제안 **18건** · not_gold 제안 **10건** (질의 19건)

### 적용 결과 (2026-08-17, 서명 후)

- **not_gold 10건 적용.** `answer-labels.yaml` revision 4, 판정 문서 본문 해시 81건 결속,
  에이전트 저술 항목 45건의 `reviewed_revision` 4 로 갱신, 멀티턴 스레드 핀 재조정.
- ⛔ **gold 18건은 적용하지 않았다 — 사전등록 규칙이 막았다.**
  `SPEC-nexus-korean-embedding-comparison §4.5`(검사: `test_growing_the_gold_set_requires_judging_the_pool_first`)는
  **블라인드 풀의 미판정 후보 821건을 먼저 판정하기 전에 gold 를 키우는 것을 금지한다.**
  이유가 정확히 이 상황이다: 이 18건은 **현 시스템이 검색해 인용한 문서들**이라, 판정 없이 gold 로
  올리면 평가 하니스가 "현 시스템이 찾는 것" 을 정답으로 세게 되고 그 편향은 이후 모든 비교에 물려진다.
  게다가 답변 gold 는 검색 gold 와 갈라질 수 없으므로(`test_the_answer_set_inherits_the_retrieval_set`)
  이 추가는 **검색 평가 하니스**(mecab 유지·KURE 컷오버 판정의 바닥값)까지 움직이는 변경이었다.
- 그래서 이 18건은 **블라인드 풀 판정 단위의 입력**으로 남는다 — 그 단위가 §4.5 가 요구하는 순서다.
