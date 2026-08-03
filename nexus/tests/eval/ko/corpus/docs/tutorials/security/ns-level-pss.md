# 파드 시큐리티 스탠다드를 네임스페이스 수준에 적용하기



이 튜토리얼은 새로운 클러스터에만 적용할 수 있다.


파드 시큐리티 어드미션은 파드가 생성될 때
[파드 시큐리티 스탠다드](/ko/docs/concepts/security/pod-security-standards/)를 적용하는
어드미션 컨트롤러이다. v1.25에서 정식 출시되었다.
이 튜토리얼에서는,
각 네임스페이스별로 `baseline` 파드 시큐리티 스탠다드를 강제(enforce)할 것이다.

파드 시큐리티 스탠다드를 클러스터 수준에서 여러 네임스페이스에 한 번에 적용할 수도 있다.
이에 대한 안내는
[파드 시큐리티 스탠다드를 클러스터 수준에 적용하기](/ko/docs/tutorials/security/cluster-level-pss/)를 참고한다.

##

워크스테이션에 다음을 설치한다.

- [KinD](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [kubectl](/ko/docs/tasks/tools/)

## 클러스터 생성하기

1. 다음과 같이 `KinD` 클러스터를 생성한다.

   ```shell
   kind create cluster --name psa-ns-level
   ```

   다음과 비슷하게 출력될 것이다.

   ```
   Creating cluster "psa-ns-level" ...
    ✓ Ensuring node image (kindest/node:v1.23.0) 🖼
    ✓ Preparing nodes 📦
    ✓ Writing configuration 📜
    ✓ Starting control-plane 🕹️
    ✓ Installing CNI 🔌
    ✓ Installing StorageClass 💾
   Set kubectl context to "kind-psa-ns-level"
   You can now use your cluster with:

   kubectl cluster-info --context kind-psa-ns-level

   Not sure what to do next? 😅  Check out https://kind.sigs.k8s.io/docs/user/quick-start/
   ```

1. kubectl context를 새로 생성한 클러스터로 설정한다.

   ```shell
   kubectl cluster-info --context kind-psa-ns-level
   ```
   다음과 비슷하게 출력될 것이다.

   ```
   Kubernetes control plane is running at https://127.0.0.1:50996
   CoreDNS is running at https://127.0.0.1:50996/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy

   To further debug and diagnose cluster problems, use 'kubectl cluster-info dump'.
   ```

## 네임스페이스 생성하기

`example`이라는 네임스페이스를 생성한다.

```shell
kubectl create ns example
```

다음과 비슷하게 출력될 것이다.

```
namespace/example created
```

## 파드 시큐리티 스탠다드 적용하기

1. 내장 파드 시큐리티 어드미션이 지원하는 레이블을 사용하여
   이 네임스페이스에 파드 시큐리티 스탠다드를 활성화한다.
   이 단계에서는 `latest` 버전(기본값)에 따라 `baseline(기준)` 파드 시큐리티 스탠다드에 대해 경고를 설정한다.

   ```shell
   kubectl label --overwrite ns example \
      pod-security.kubernetes.io/warn=baseline \
      pod-security.kubernetes.io/warn-version=latest
   ```

2. 어떠한 네임스페이스에도 복수 개의 파드 시큐리티 스탠다드를 활성화할 수 있으며,
   이는 레이블을 이용하여 가능하다.
   다음 명령어는 최신 버전(기본값)에 따라, `baseline(기준)` 파드 시큐리티 스탠다드는 `enforce(강제)`하지만
   `restricted(제한된)` 파드 시큐리티 스탠다드에 대해서는 `warn(경고)` 및 `audit(감사)`
   하도록 설정한다.

   ```shell
   kubectl label --overwrite ns example \
     pod-security.kubernetes.io/enforce=baseline \
     pod-security.kubernetes.io/enforce-version=latest \
     pod-security.kubernetes.io/warn=restricted \
     pod-security.kubernetes.io/warn-version=latest \
     pod-security.kubernetes.io/audit=restricted \
     pod-security.kubernetes.io/audit-version=latest
   ```

## 파드 시큐리티 스탠다드 검증하기

1. 클러스터의 `example` 네임스페이스에 해당 파드 스펙을 적용한다.

   ```shell
   kubectl apply -n example -f /tmp/pss/nginx-pod.yaml
   ```
   다음과 비슷하게 출력될 것이다.

   ```
   Warning: would violate PodSecurity "restricted:latest": allowPrivilegeEscalation != false (container "nginx" must set securityContext.allowPrivilegeEscalation=false), unrestricted capabilities (container "nginx" must set securityContext.capabilities.drop=["ALL"]), runAsNonRoot != true (pod or container "nginx" must set securityContext.runAsNonRoot=true), seccompProfile (pod or container "nginx" must set securityContext.seccompProfile.type to "RuntimeDefault" or "Localhost")
   pod/nginx created
   ```

1. 클러스터의 `default` 네임스페이스에 해당 파드 스펙을 적용한다.

   ```shell
   kubectl apply -n default -f /tmp/pss/nginx-pod.yaml
   ```
   다음과 비슷하게 출력될 것이다.

   ```
   pod/nginx created
   ```

파드 시큐리티 스탠다드는 `example` 네임스페이스에만 적용되었다.
동일한 파드를 `default` 네임스페이스에 생성하더라도
경고가 발생하지 않는다.

## 정리하기

위에서 생성한 클러스터들을 다음 명령어를 실행하여 삭제한다.

```shell
kind delete cluster --name psa-ns-level
```

##

- 다음의 모든 단계를 한 번에 수행하려면
  [셸 스크립트](/examples/security/kind-with-namespace-level-baseline-pod-security.sh)를
  실행한다.

  1. kind 클러스터를 생성한다
  2. 새로운 네임스페이스를 생성한다
  3. `baseline` 파드 시큐리티 스탠다드는 `enforce` 모드로 적용하고
     `restricted` 파드 시큐리티 스탠다드는 `warn` 및 `audit` 모드로 적용한다.
  4. 해당 파드 시큐리티 스탠다드가 적용된 상태에서 새로운 파드를 생성한다

- [파드 시큐리티 어드미션](/ko/docs/concepts/security/pod-security-admission/)
- [파드 시큐리티 스탠다드](/ko/docs/concepts/security/pod-security-standards/)
- [파드 시큐리티 스탠다드를 클러스터 수준에 적용하기](/ko/docs/tutorials/security/cluster-level-pss/)
