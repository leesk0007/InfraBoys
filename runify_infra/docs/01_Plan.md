# GCP 테스트 인프라 및 CI/CD 구축 계획서

## 1. 프로젝트 목표

AWS 대신 GCP를 기반으로 팀의 통합 테스트 환경을 구축한다.

Terraform을 이용해 GCP 인프라를 코드로 관리하고, GitHub Actions를 통해 인프라의 생성·변경·삭제를 자동화한다. 이후 각 애플리케이션 레포지토리에 CI/CD 파이프라인을 추가하여 애플리케이션 빌드부터 GCP 서버 배포까지 자동화한다.

### 최종 목표

```text
GitHub
│
├── Infrastructure Repository
│   └── Terraform
│
├── Backend Repository
│   └── CI/CD
│
└── Route Worker Repository
    └── CI/CD
          │
          ▼
        GCP
          │
       ┌──┴──────────────────────┐
       │                          │
    VPC Network               Artifact Registry
       │                          │
   ┌───┼────────┐                 │
   │   │        │                 │
Backend Kafka Route Worker ◀──────┘
                  │
                  ▼
          PostgreSQL
          + PostGIS
          + pgRouting
```

---

# 2. 전체 작업 범위

전체 작업은 다음 세 단계로 진행한다.

### Phase 1. Terraform 기반 GCP 인프라 구축

GCP에 테스트에 필요한 네트워크와 서버를 Terraform으로 프로비저닝한다.

### Phase 2. GitHub Actions 기반 인프라 수명주기 관리

GitHub Actions에서 원하는 시점에 Terraform을 실행하여 인프라를 생성하거나 삭제할 수 있도록 구성한다.

### Phase 3. 애플리케이션 CI/CD 구축

각 애플리케이션 레포지토리에 GitHub Actions를 추가하여 Docker 이미지 빌드 → Artifact Registry 업로드 → GCP 서버 배포를 자동화한다.

---

# 3. Phase 1 — Terraform으로 GCP 인프라 구축

## 3.1 목표

다음 명령만으로 테스트 환경을 생성할 수 있도록 구성한다.

```bash
terraform init
terraform plan
terraform apply
```

Terraform이 관리할 리소스:

```text
GCP Project
│
├── VPC
├── Subnet
├── Firewall Rules
│
├── Backend VM
├── Kafka VM
├── Route Worker VM
│
├── Artifact Registry
│
└── IAM / Workload Identity Federation
```

---

## 3.2 네트워크 구성

Backend, Kafka, Route Worker를 동일한 VPC에 배치한다.

```text
GCP VPC
└── Test Subnet
    ├── Backend VM
    ├── Kafka VM
    └── Route Worker VM
```

서비스 간 통신은 사설 IP를 우선 사용한다.

예:

```text
Backend
  │
  │ Kafka :9092
  ▼
Kafka
  │
  ▼
Route Worker :8081
  │
  ▼
PostgreSQL :5432
```

외부에 직접 공개할 필요가 없는 포트는 Firewall에서 외부 접근을 차단한다.

---

## 3.3 Firewall 정책

최소한의 포트만 허용한다.

| 대상 | 포트 | 허용 대상 | 목적 |
|---|---:|---|---|
| Backend | 8080 등 | 필요한 범위 | Backend API |
| Route Worker | 8081 | Backend | 내부 API |
| Kafka | 9092 | Backend / Worker | Kafka 통신 |
| PostgreSQL | 5432 | Route Worker | DB 통신 |
| SSH | 22 | 관리자 IP 또는 관리 경로 | 서버 관리 |

PostgreSQL과 Kafka를 인터넷 전체에 공개하지 않는다.

---

## 3.4 Compute Engine 구성

초기 테스트 환경에서는 Compute Engine VM 기반으로 구성한다.

예시:

```text
Backend VM
Kafka VM
Route Worker VM
```

Route Worker 서버에는:

```text
Docker
Docker Compose
PostgreSQL
PostGIS
pgRouting
graph-loader
route-worker
```

를 구성한다.

실제 수도권 Routing DB 적재는 Route Worker 환경에서 수행한다.

```text
OSM 데이터
    ↓
graph-loader
    ↓
PostgreSQL
    ↓
PostGIS + pgRouting
    ↓
Routing DB
```

---

## 3.5 Artifact Registry

애플리케이션 Docker 이미지를 저장하기 위한 Artifact Registry를 생성한다.

```text
Backend Repository
       ↓
Docker Build
       ↓
Artifact Registry
       ↓
Backend VM
```

Route Worker도 동일한 방식으로 관리한다.

```text
Route Worker Repository
       ↓
Docker Build
       ↓
Artifact Registry
       ↓
Route Worker VM
```

---

## 3.6 Terraform 디렉터리 구조

초기에는 다음과 같이 구성한다.

```text
infra/
└── terraform/
    ├── providers.tf
    ├── backend.tf
    ├── variables.tf
    ├── terraform.tfvars
    ├── network.tf
    ├── firewall.tf
    ├── compute.tf
    ├── artifact-registry.tf
    ├── iam.tf
    └── outputs.tf
```

역할:

| 파일 | 역할 |
|---|---|
| `providers.tf` | GCP Provider 설정 |
| `backend.tf` | Terraform State 저장 위치 |
| `variables.tf` | 변수 정의 |
| `terraform.tfvars` | 환경별 값 |
| `network.tf` | VPC / Subnet |
| `firewall.tf` | 방화벽 |
| `compute.tf` | Compute Engine |
| `artifact-registry.tf` | Docker 이미지 저장소 |
| `iam.tf` | IAM / 배포 권한 |
| `outputs.tf` | VM IP, Registry 주소 등 출력 |

---

# 4. Phase 2 — GitHub Actions 기반 인프라 수명주기 관리

## 4.1 목표

GCP 테스트 환경을 항상 켜두지 않고 필요할 때 생성하고 테스트가 끝나면 삭제한다.

```text
GitHub Actions
      │
      ├── plan
      │
      ├── provision
      │      ↓
      │   terraform apply
      │
      └── destroy
             ↓
         terraform destroy
```

GitHub Actions의 `workflow_dispatch`를 사용하여 수동 실행한다.

---

## 4.2 Terraform State 관리

Terraform State는 GitHub Actions 실행 환경의 로컬 파일로 관리하지 않는다.

GCS Bucket을 Terraform Backend로 사용한다.

```text
GCS
└── terraform-state
       └── test/terraform.tfstate
```

이를 통해 여러 사람이 GitHub Actions를 실행해도 동일한 인프라 상태를 공유한다.

---

## 4.3 GCP 인증

GitHub Actions에서 GCP에 접근할 때 장기 서비스 계정 키 파일을 저장하는 방식은 사용하지 않는다.

Workload Identity Federation을 사용한다.

```text
GitHub Actions
      │
      │ OIDC
      ▼
Workload Identity Federation
      │
      ▼
GCP Service Account
      │
      ▼
Terraform / Deploy
```

---

## 4.4 GitHub Actions Workflow

```text
.github/
└── workflows/
    └── terraform.yml
```

Workflow는 다음 작업을 지원한다.

### Plan

```text
terraform init
terraform validate
terraform plan
```

### Provision

```text
terraform init
terraform plan
terraform apply
```

### Destroy

```text
terraform init
terraform plan
terraform destroy
```

---

## 4.5 실행 방식

GitHub Repository:

```text
Actions
  ↓
Terraform Infrastructure
  ↓
Run workflow
```

예:

```text
Action:
  provision
```

선택 시:

```text
GitHub Actions
      ↓
terraform apply
      ↓
GCP 인프라 생성
```

테스트 종료 후:

```text
Action:
  destroy
```

선택:

```text
GitHub Actions
      ↓
terraform destroy
      ↓
GCP 테스트 인프라 삭제
```

---

# 5. Phase 3 — Backend CI/CD 구축

## 5.1 목표

Backend Repository에 코드를 push하면 자동으로 Docker 이미지를 만들고 GCP에 배포한다.

```text
Backend Repository
       │
       │ push
       ▼
GitHub Actions
       │
       ├── Checkout
       ├── Test
       ├── Build
       ├── Docker Build
       ├── Docker Push
       │
       ▼
Artifact Registry
       │
       ▼
Backend VM
       │
       └── Docker Container 재배포
```

---

## 5.2 Backend Workflow

예상 파일:

```text
.github/
└── workflows/
    └── deploy.yml
```

실행 단계:

```text
1. Checkout
2. JDK 설정
3. 테스트
4. Spring Boot Build
5. Docker Image Build
6. Artifact Registry Push
7. GCP 인증
8. Backend VM 접속
9. 새로운 Image Pull
10. 기존 Container 교체
11. Health Check
```

---

# 6. Route Worker CI/CD 구축

Route Worker Repository에도 별도의 배포 파이프라인을 추가한다.

```text
Route Worker Repository
       │
       │ push
       ▼
GitHub Actions
       │
       ├── Test
       ├── Docker Build
       └── Artifact Registry Push
                    │
                    ▼
             Route Worker VM
                    │
                    └── Container 재배포
```

단, Routing DB 적재 과정은 일반적인 CI/CD 배포와 분리한다.

### 애플리케이션 배포

```text
Docker Image
    ↓
Route Worker VM
```

### Routing 데이터 적재

```text
OSM
 ↓
graph-loader
 ↓
PostgreSQL
 ↓
Routing DB
```

실제 데이터 적재는 최초 구축 시 별도의 작업으로 수행한다.

---

# 7. 전체 배포 흐름

최종적으로 다음 구조를 만든다.

```text
                   GitHub
                      │
          ┌───────────┴────────────┐
          │                        │
    Infrastructure              Apps
       Repository             Repositories
          │                        │
          ▼                        ▼
    Terraform Actions          CI/CD Actions
          │                        │
          ▼                        ▼
       GCP Infra             Docker Image
          │                        │
          │                  Artifact Registry
          │                        │
          └────────────┬───────────┘
                       ▼
                  GCP VPC
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Backend        Kafka      Route Worker
          │                         │
          │                         ▼
          └────── Kafka ──────→ PostgreSQL
                                  │
                                  ▼
                            Routing Graph
```

---

# 8. 최종 작업 순서

## Step 1 — GCP 기본 환경

- [ ] GCP Project 생성
- [ ] Billing 연결
- [ ] 필요한 API 활성화
- [ ] Terraform 실행 계정 준비
- [ ] GitHub Actions용 WIF 구성

## Step 2 — Terraform

- [ ] Terraform Provider 구성
- [ ] GCS Terraform State 구성
- [ ] VPC 생성
- [ ] Subnet 생성
- [ ] Firewall 구성
- [ ] Compute Engine 생성
- [ ] Artifact Registry 생성
- [ ] IAM 구성
- [ ] Terraform Output 구성

## Step 3 — 서버 환경

- [ ] Backend VM 기본 환경 구성
- [ ] Kafka VM 기본 환경 구성
- [ ] Route Worker VM 기본 환경 구성
- [ ] Docker 설치
- [ ] Docker Compose 구성
- [ ] PostgreSQL + PostGIS + pgRouting 구성
- [ ] Route Worker 구성

## Step 4 — Routing 데이터 적재

- [ ] OSM 데이터 확보
- [ ] graph-loader 실행
- [ ] 수도권 데이터 적재
- [ ] Routing Graph 생성
- [ ] 실제 경로 탐색 테스트
- [ ] DB 백업/복구 방법 확보

## Step 5 — Infrastructure GitHub Actions

- [ ] `terraform.yml` 작성
- [ ] `plan` workflow 구현
- [ ] `provision` workflow 구현
- [ ] `destroy` workflow 구현
- [ ] GitHub Actions → GCP 인증 검증
- [ ] 실제 생성/삭제 테스트

## Step 6 — Backend CI/CD

- [ ] Backend Dockerfile 확인
- [ ] 테스트 workflow 추가
- [ ] Docker Image Build
- [ ] Artifact Registry Push
- [ ] GCP 인증
- [ ] Backend VM 배포
- [ ] Health Check
- [ ] 롤백 방법 확인

## Step 7 — Route Worker CI/CD

- [ ] Route Worker Dockerfile 확인
- [ ] 테스트 workflow 추가
- [ ] Docker Image Build
- [ ] Artifact Registry Push
- [ ] Route Worker VM 배포
- [ ] Health Check

## Step 8 — 통합 테스트

- [ ] Backend → Kafka 연결
- [ ] Kafka → Route Worker 연결
- [ ] Route Worker → PostgreSQL 연결
- [ ] 실제 Routing 데이터 조회
- [ ] 실제 경로 탐색
- [ ] 전체 API 테스트
- [ ] 인프라 Destroy
- [ ] 다시 Provision
- [ ] 다시 Deploy
- [ ] 동일하게 정상 동작하는지 확인

---

# 9. 최종적으로 달성할 것

최종 목표는 단순히 GCP에 서버를 한 번 만들어놓는 것이 아니다.

다음 과정을 반복 가능하게 만드는 것이다.

```text
[필요할 때]

GitHub Actions
      ↓
  Provision
      ↓
Terraform Apply
      ↓
GCP 테스트 환경 생성
      ↓
Application Deploy
      ↓
통합 테스트


[테스트 종료]

GitHub Actions
      ↓
    Destroy
      ↓
Terraform Destroy
      ↓
GCP 리소스 삭제
```

이를 통해 **인프라 생성 → 애플리케이션 배포 → 통합 테스트 → 인프라 삭제**까지 전체 테스트 환경의 수명주기를 코드와 GitHub Actions로 관리한다.

## 핵심 역할 분리

| 영역 | 담당 기술 | 책임 |
|---|---|---|
| 인프라 | Terraform | GCP 리소스 생성/변경/삭제 |
| 인프라 수명주기 | GitHub Actions | Provision / Plan / Destroy |
| 인증 | Workload Identity Federation | GitHub → GCP 인증 |
| 이미지 저장 | Artifact Registry | Docker Image 관리 |
| 애플리케이션 CI/CD | GitHub Actions | Test / Build / Push / Deploy |
| 실행 환경 | Compute Engine | Backend / Kafka / Worker 실행 |
| 컨테이너 | Docker | 애플리케이션 실행 |
| Routing DB | PostgreSQL + PostGIS + pgRouting | 실제 도로망 데이터 및 경로 계산 |
| 데이터 적재 | graph-loader | OSM → Routing DB |

### 구현 우선순위

**① Terraform으로 GCP 인프라를 먼저 정상적으로 만들 수 있게 한다.**

↓

**② GitHub Actions에서 Terraform을 실행해 Provision/Destroy가 가능하게 한다.**

↓

**③ Backend/Route Worker 각각에 CI/CD를 붙인다.**

↓

**④ 실제 Routing 데이터 적재 후 전체 통합 테스트를 수행한다.**

이 순서를 지키면 인프라 문제와 애플리케이션 배포 문제를 섞지 않고 단계별로 검증할 수 있다.