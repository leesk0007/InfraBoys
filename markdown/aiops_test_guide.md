# AIOps 장애 및 스케일링 데모 테스트 가이드 (실제 부하 발생)

이 가이드는 데모 영상 촬영을 위해 실제 서버에 장애나 부하를 발생시켜 AIOps 자동화 파이프라인(장애 감지 → AI 분석 → 디스코드 알람 → GitHub Actions 복구)을 시연하는 방법을 설명합니다.

> [!TIP]
> 데모 촬영 시나리오가 겹치지 않도록, 스케일링 시연과 AIOps 장애 조치 시연은 순차적으로 하나씩 진행하시는 것을 권장합니다.

---

## 🚀 사전 준비 (서버 접속)

장애를 인위적으로 유발하려면 대상 WAS 서버에 SSH로 접속해야 합니다.

**1. 현재 살아있는 WAS 서버 IP 확인하기**
터미널에서 아래 명령어를 실행하여 작동 중인 IP를 얻습니다.
```bash
docker exec -u runner mgmt-runner aws ec2 describe-instances \
  --filters "Name=tag:aws:autoscaling:groupName,Values=project02-asg" "Name=instance-state-name,Values=running" \
  --query "Reservations[*].Instances[*].PrivateIpAddress" \
  --output text
```

**2. 대상 서버에 접속하기**
출력된 IP 중 하나(예: `10.0.10.177`)를 선택해 SSH로 접속합니다.
```bash
# 본인의 SSH 키 경로를 지정하여 접속하세요.
ssh -i ~/.ssh/YOUR_KEY_NAME ec2-user@<확인된_IP>
```

---

## 📈 시나리오 1: 과부하 발생 시 스케일 아웃 및 스케일 인 (Auto Scaling)

서버 CPU에 극심한 과부하를 주어 인프라가 자동으로 확장(Scale Out)되고, 부하가 끝나면 다시 축소(Scale In)되는 것을 시연합니다. 
ALB의 차단(DDoS 방어)을 피하기 위해, Ansible을 이용해 모든 WAS 서버에 동시에 부하 명령을 내립니다.

1. **동시 부하 발생 (터미널에서 실행)**
   ```bash
   # mgmt-runner 환경에서 모든 WAS 서버(그룹명 was)에 동시에 CPU 부하 실행 명령을 쏩니다.
   docker exec -u runner mgmt-runner env ANSIBLE_HOST_KEY_CHECKING=False ansible was -i /workspace/ansible/inventories/dev/aws_ec2.yml -m shell -a "sudo dnf install stress -y && stress --cpu 4 --timeout 300"
   ```
   > 💡 **메모리 부하가 필요할 경우**: 아래 명령어를 대신 사용하세요. (250MB 메모리 부하, OOM 방지)
   > ```bash
   > docker exec -u runner mgmt-runner env ANSIBLE_HOST_KEY_CHECKING=False ansible was -i /workspace/ansible/inventories/dev/aws_ec2.yml -m shell -a "sudo dnf install stress -y && stress --vm 1 --vm-bytes 250M --timeout 300"
   > ```
   
   > 💡 **참고**: 명령어 끝에 `--timeout 300`이 있으므로, 이 명령어는 **5분 동안 대기 상태(아무 반응이 없는 것처럼 보임)를 유지**합니다. 에러가 아니며 백그라운드에서 정상적으로 부하를 발생시키고 있습니다. 이 상태 그대로 두고 그라파나 대시보드에서 지표가 올라가는지 확인하세요. 터미널을 분리하고 싶다면 명령어 맨 끝에 `&`를 붙이시면 됩니다.
   *(경로: 프로젝트 경로에 맞게 인벤토리 경로를 설정하세요. 위는 예시입니다)*
2. **발생하는 알람**: `Level1-cpu` 또는 `Level2-cpu` (프로메테우스 룰 설정 조건에 따라 1~5분 소요)
3. **디스코드 결과**: 알람 수준에 따라 스케일 아웃 +1대 또는 +2대가 진행된다는 메시지가 발송됩니다.
4. **스케일 아웃 진행**: Alertmanager가 FastAPI의 `/api/scale-out` 웹훅을 호출하고, GitHub Actions(`scale-out.yml`)가 동작하여 테라폼을 통해 새로운 EC2를 런칭합니다.
5. **확인**: AWS 콘솔 화면에 접속하거나 `aws ec2 describe-instances` 명령어로 인스턴스 대수가 늘어난 것을 확인합니다.
6. **부하 종료 및 스케일 인 (Scale In) 유도**: 부하 발생 명령어에 `--timeout 300` 옵션이 있어 5분 뒤 자동으로 부하가 종료되지만, 즉시 부하를 멈추고 스케일 인 과정을 확인하려면 아래 명령어를 실행하세요.
   ```bash
   # 모든 WAS 서버에서 실행 중인 stress 프로세스를 일괄 강제 종료합니다.
   docker exec -u runner mgmt-runner env ANSIBLE_HOST_KEY_CHECKING=False ansible was -i /workspace/ansible/inventories/dev/aws_ec2.yml -m shell -a "sudo pkill -f stress"
   ```
   부하가 종료되고 일정 시간(약 10분)이 지나 CPU 및 메모리 사용량이 임계치(기본 설정된 Scale-In 기준치) 이하로 안정화되면, 알람이 해제되면서 정상 상태로 복귀하거나 스케일 인 웹훅이 동작하여 추가된 인스턴스가 다시 축소됩니다.

---

## 🔥 시나리오 2: Nginx 비정상 종료 (장애 대응 기본)

가장 빠르고 직관적으로 AIOps 파이프라인을 보여줄 수 있는 베스트 시나리오입니다.

1. **장애 유발 (WAS 서버 접속 후 실행)**
   ```bash
   docker stop app-nginx-1
   ```
2. **발생하는 알람**: `Nginx-down` (약 30초 소요)
3. **디스코드 결과**: AI가 에러 로그를 분석한 뒤 **"Nginx 프로세스 재시작(`was_restart_nginx.yml`)"**을 추천합니다.
4. **복구 (자동화)**: 디스코드에서 [✅ 런북 실행 승인]을 클릭하면, GitHub Actions가 해당 IP로 Ansible 플레이북을 쏴서 Nginx 컨테이너를 강제로 재생성하고 헬스체크까지 완료합니다.

---

## 💾 시나리오 3: 디스크 95% 초과 (디스크 풀)

디스크 용량을 인위적으로 꽉 채워서 서버 마비 상태를 발생시킵니다.

1. **장애 유발 (WAS 서버 접속 후 실행)**
   ```bash
   # 서버의 /tmp 디렉토리에 10GB짜리 더미(가짜) 파일을 생성 (남은 용량에 따라 10G를 조절)
   fallocate -l 10G /tmp/dummy_disk_full.img
   ```
2. **발생하는 알람**: `Disk-full` (약 1분 소요)
3. **디스코드 결과**: AI가 **"디스크 임시 파일 정리(`was_cleanup_disk.yml`)"**를 추천합니다.
4. **복구 (자동화)**: 런북 실행 승인 시 Ansible이 서버의 불필요한 로그 파일과 방금 만든 더미 이미지 파일 등을 삭제하여 디스크 용량을 쾌적하게 확보합니다.

---

## 🧟‍♂️ 시나리오 4: 좀비 프로세스 발생

명령에 응답하지 않는 멈춘 프로세스(Zombie)를 만들어냅니다.

1. **장애 유발 (WAS 서버 접속 후 실행)**
   ```bash
   cat << 'EOF' > make_zombie.py
import os, time
pid = os.fork()
if pid > 0:
    time.sleep(300)  # 부모는 살아있음
else:
    os._exit(0)      # 자식은 즉시 종료되어 좀비(Defunct) 상태가 됨
EOF
   python3 make_zombie.py &
   ```
2. **발생하는 알람**: `ZombieProcess` (약 2분 소요)
3. **디스코드 결과**: AI가 **"고부하/좀비 프로세스 강제 종료(`was_kill_process.yml`)"** 런북을 추천합니다.
4. **복구 (자동화)**: 런북이 실행되면 서버의 프로세스 트리 상태를 분석하여, 문제를 일으키는 프로세스에 SIGTERM/SIGKILL 시그널을 날려 강제 정리합니다.

---

## 💥 시나리오 5: 데이터베이스(PostgreSQL) 커넥션 풀 고갈

DB에 비정상적으로 많은 커넥션이 맺어져서 새로운 요청을 처리하지 못하는 상태를 시뮬레이션합니다. 

1. **장애 유발 (터미널에서 실행)**
   DB가 설치된 서버 IP를 확인한 후, PostgreSQL 공식 도구인 `pgbench`를 사용해 강제로 다량의 동시 커넥션을 발생시킵니다.
   ```bash
   # 주의: 172.16.8.201 부분은 실제 환경의 DB IP로 변경해서 실행하세요.
   # 1. pgbench 테스트 환경 초기화 (최초 1회만 수행)
   docker run --rm postgres pgbench -h 172.16.8.201 -p 5432 -U aiops_user -d aiops_db -i
   
   # 2. 커넥션 30개를 300초(5분) 동안 점유하여 커넥션 풀 고갈 유발
   docker run --rm postgres pgbench -h 172.16.8.201 -p 5432 -U aiops_user -d aiops_db -c 30 -T 300
   ```
2. **발생하는 알람**: `Postgres-connectionfullout` (커넥션 사용률 20% 초과 조건, 약 1분 소요)
3. **디스코드 결과**: AI가 에러 상황을 인지하고 **"DB 유휴 커넥션 정리(`db_kill_idle_connections.yml`)"** 런북을 추천합니다.
4. **복구 (자동화)**: 런북을 승인하면 Ansible이 DB 서버로 접근하여 장기 체류 중이거나 의미 없는 Idle 커넥션들을 DB단에서 강제로 끊어내어 커넥션 풀 여유 공간을 확보합니다.

---

## 🛑 시나리오 6: 데이터베이스(PostgreSQL) 프로세스 다운

DB 프로세스 자체가 죽어 서비스 전체 장애가 발생하는 치명적인 상황을 유발합니다.

1. **장애 유발 (DB 서버 접속 후 실행)**
   실제 DB가 떠있는 대상 서버(예: 172.16.8.201 등)에 SSH로 직접 접속한 뒤, 실행 중인 DB 컨테이너를 강제로 중지시킵니다.
   ```bash
   # 대상 서버에서 DB 컨테이너를 중지 (환경에 따라 컨테이너 이름 확인 필요)
   docker stop <postgres_컨테이너_이름>  # 예: docker stop aiops-postgres
   ```
2. **발생하는 알람**: `Postgres-down` (약 30초 소요)
3. **디스코드 결과**: 로그에서 Connection refused 등의 키워드를 분석한 AI가 **"DB 프로세스/컨테이너 재시작(`db_restart_container.yml`)"**을 추천합니다.
4. **복구 (자동화)**: 런북 승인 시 Ansible이 DB 서버에 붙어 다운된 postgres 컨테이너를 다시 시작(`docker start`)하여 서비스를 정상화시킵니다.

---

## 🧐 심화: AIOps 부하 감지 및 정상화 룰 이해하기

프로메테우스에 설정된 알람 룰(`alert_rules.yml`)은 단순한 임계치 초과가 아니라, **예측 기반(Predictive)**으로 동작합니다.

### 1. 스케일 아웃 (과부하 판단) 👉 `OR` 연산
- **조건**: `(현재 사용량 > 임계치) OR (10분 뒤 예측 사용량 > 임계치)`
- **동작 원리**: 현재 서버 부하가 임계치를 넘었거나, 최근 30분간의 증가 추세를 분석했을 때 10분 뒤에 임계치를 넘을 것으로 예측되는 경우 둘 중 하나만 만족(`OR`)해도 알람이 발생합니다.
- **목적**: 트래픽 폭증으로 서버가 다운되기 전에 미리 선제적으로 서버를 늘리기 위함입니다.

### 2. 스케일 인 (정상화 판단) 👉 `AND` 연산
- **조건**: `(현재 사용량 <= 안정치) AND (10분 뒤 예측 사용량 <= 안정치)`
- **동작 원리**: 현재 사용량이 안정권에 들어왔고, 예측 추세상으로도 앞으로 10분간 안정권일 때만 두 조건을 모두 만족(`AND`)해야 알람이 해제되거나 스케일 인이 발생합니다.
- **목적**: 일시적으로 부하가 줄었다고 섣불리 서버를 줄였다가, 바로 다시 트래픽이 몰려 장애가 발생하는 현상(Flapping)을 방지하기 위해 보수적으로 판단합니다.

---

## 🚨 심화: 메모리 과부하 테스트 시 주의사항 (OOM Killer)

테스트 시 메모리 과부하(`stress --vm-bytes`) 옵션을 너무 크게 줄 경우, 터미널 명령어 실행 직후 `signal 9` 또는 `FAIL` 에러가 발생하며 테스트가 즉시 종료될 수 있습니다.

- **원인 (OOM Killer)**: 리눅스 커널은 시스템 전체 메모리가 부족해지면, 시스템을 보호하기 위해 가장 메모리를 많이 먹는 프로세스를 강제로 죽이는 **OOM(Out Of Memory) Killer**를 작동시킵니다.
- **해결책**: t3.micro 같은 소형 인스턴스는 가용 메모리(Available Memory)가 100MB~300MB 수준으로 매우 적습니다. `400M` 이상의 메모리를 한 번에 요구하면 즉시 강제 종료 당하므로, `250M` 또는 인스턴스의 `free -m` 가용량보다 살짝 적은 수준으로 조절해야 안전하게 과부하 테스트를 진행할 수 있습니다.
