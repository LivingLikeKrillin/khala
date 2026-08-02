# 리눅스 노드 업그레이드




이 페이지는 kubeadm으로 생성된 리눅스 노드를 업그레이드하는 방법을 설명한다.

##


* [남은 kubeadm 클러스터를 업그레이드하는 프로세스](/ko/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade)에
익숙해져야 한다.
리눅스 노드를 업그레이드하기 전에 컨트롤 플레인 노드를 업그레이드해야 한다.



## 워커 노드 업그레이드

### kubeadm 업그레이드

 kubeadm을 업그레이드한다.



  ```shell
  # .x-00 에서 x 에 최신 버전을 넣는다.
  apt-mark unhold kubeadm && \
  apt-get update && apt-get install -y kubeadm=.x-00 && \
  apt-mark hold kubeadm
  ```


  ```shell
  # .x-00 에서 x 에 최신 버전을 넣는다.
  yum install -y kubeadm-.x-0 --disableexcludes=kubernetes
  ```



### "kubeadm upgrade" 호출

- 워커 노드의 경우 로컬 kubelet 구성을 업그레이드한다.

  ```shell
  sudo kubeadm upgrade node
  ```

### 노드 드레인

- 노드를 스케줄 불가능한 것으로 표시하고 워크로드를 축출하여 유지 보수할 노드를 준비한다.

  ```shell
  # <node-to-drain> 에 드레인하려는 노드의 이름을 넣는다.
  kubectl drain <node-to-drain> --ignore-daemonsets
  ```

### kubelet과 kubectl 업그레이드

- kubelet과 kubectl 업그레이드.



  ```shell
  # .x-00 에서 x 에 최신 버전을 넣는다.
  apt-mark unhold kubelet kubectl && \
  apt-get update && apt-get install -y kubelet=.x-00 kubectl=.x-00 && \
  apt-mark hold kubelet kubectl
  ```


  ```shell
  # .x-00 에서 x 에 최신 버전을 넣는다.
  yum install -y kubelet-.x-0 kubectl-.x-0 --disableexcludes=kubernetes
  ```


  <br />

- kubelet을 재시작한다.

  ```shell
  sudo systemctl daemon-reload
  sudo systemctl restart kubelet
  ```

### 노드에 적용된 cordon 해제

- 스케줄 가능으로 표시하여 노드를 다시 온라인으로 가져온다.

  ```shell
  # <node-to-uncordon> 에 노드의 이름을 넣는다.
  kubectl uncordon <node-to-uncordon>
  ```

 ##

* [윈도우 노드 업그레이드](/ko/docs/tasks/administer-cluster/kubeadm/upgrading-windows-nodes/)하는 방법을 알아본다.
