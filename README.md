# 🚀 인프라 청년들 (Infra Boys)

> **하이브리드 아키텍처에서의 선제적 대응과 AIOps 기반 무중단/비용 최적화 운영 파이프라인**
> 온프레미스 제어 노드와 퍼블릭 클라우드를 연결하는 통합 모니터링 및 스케일링 전략

<br/>

## 📖 1. 프로젝트 개요 (Executive Summary)

기존의 클라우드 인프라 운영은 트래픽이 폭주하거나 장애가 발생한 후에야 서버를 늘리고 복구하는 **사후 대응 방식**에 머물러 있었으며, 이는 필연적으로 서비스 지연과 불필요한 클라우드 리소스 낭비를 초래했습니다.

본 프로젝트는 이러한 한계를 극복하고 **예방적이고 관리자 친화적인 자율형 하이브리드 인프라**를 구축하는 것을 목표로 합니다.

- **선제적 스케일링**: Prometheus의 내장된 예측 함수 기능과 정기적 트래픽을 대비한 일정 기반 스케일링 방식을 융합하여, 트래픽 피크 이전에 자원을 확보합니다.
- **AIOps 판단**: CPU 과부하나 OOM 같은 단일 지표의 이상을 넘어, 여러 원인이 얽힌 복합적인 장애 상황에서도 AIOps를 통해 대응합니다. 
- **보안 강화**: AI 모델로 전송되는 민감한 로그 데이터는 Regex 기반 전처리 파이프라인을 거쳐 보호됩니다.
- **비용 관리(FinOps)**: 자동화 파이프라인에 `Infracost`를 연동하여 인프라 변경 및 프로비저닝 단계에서 예상되는 클라우드 비용을 사전에 산출합니다.
- **통합 제어**: 관리자는 통합 모니터링 대시보드를 통해 인프라 상태를 파악하고, GUI 버튼 이벤트를 통해 실시간으로 서버를 제어할 수 있습니다.

### 🎯 주요 목표
- AIOps 기반 장애 대응체계 구축
- 예측 기반 오토스케일링
- IaC(Infa as Code) 기반 CI/CD 파이프라인 정립
- 가시성(Observability) 확보

### ✨ 기대 효과
- 장애 징후를 사전에 탐지하고 선제적으로 자원을 할당하여, 트래픽 폭주 시에도 서비스 안정화
- 인프라 프로비저닝 시간 단축
- 클라우드 운영 비용 최적화
- 운영 효율성 및 관리자 피로도 감소
- 로그를 AI에게 그대로 노출하지 않고 Regex 필터를 거쳐 보안 확보
- 인프라 생성되기 전 예산을 미리 예측하고 통제하는 FinOps 문화 구현

<br/>

## 🛠️ 2. 사용 기술 및 도구 (Tech Stack)

### ⚙️ Technology
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=FastAPI&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white)
![Ansible](https://img.shields.io/badge/Ansible-EE0000?style=flat-square&logo=ansible&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat-square&logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-232F3E?style=flat-square&logo=amazon-aws&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![VMware](https://img.shields.io/badge/VMware-607078?style=flat-square&logo=vmware&logoColor=white)

### 🧰 Tools
`GitHub` `GitHub Actions` `LLM API` `Notion` `Discord` `Telegram` `Figma` `VS Code`

<br/>

## ✨ 3. 주요 기능 (Core Features)

1. **AIOps 기반 장애 감지 및 자율 복구 (Closed-loop AIOps)**
   - **Prometheus**를 통한 5대 장애(Nginx 다운, 디스크 풀, 좀비 프로세스, DB 커넥션 풀 고갈, DB 다운) 모니터링
   - 알람 발생 시 FastAPI가 대상 서버에 접속하여 `docker logs` 수집 및 개인정보(PII) 마스킹 처리
   - **LLM(Gemini AI)**을 활용한 로그 분석 및 런북(Runbook) 추천
   - Discord 챗봇 알림 및 관리자의 승인(Human-in-the-loop)으로 **GitHub Actions** 복구 파이프라인 실행

2. **예측 모델을 활용한 오토스케일링 (Predictive Auto-scaling)**
   - Prometheus의 `predict_linear` 함수를 활용해 **5분 뒤의 리소스(CPU, Memory) 상태 예측**
   - 트래픽 증가 전에 사전에 Scale-Out을 수행하여 서비스 안정성 확보

3. **IaC 및 CI/CD 파이프라인 (GitOps & CI/CD)**
   - 인프라 생성(Terraform)부터 구성 관리(Ansible) 및 컨테이너 빌드(Packer/Docker) 과정을 코드로 관리
   - **GitHub Actions Self-Hosted Runner**를 활용하여 배포 워크플로우를 자동화하고 인프라 변경 이력 추적(Audit Trail)

4. **FinOps 및 DevSecOps 연동**
   - CI/CD 파이프라인 실행 시 `Infracost`를 연동하여 AWS 인프라 변경 전 **예상 클라우드 비용 산출**
   - `Trivy` 스캐너를 통해 배포 전 컨테이너 이미지 취약점 점검

5. **통합 모니터링 및 대시보드 제어 (Observability & Control)**
   - **Grafana** 대시보드를 통해 하이브리드 인프라의 트래픽, 자원, 로그 시각화
   - 대시보드 내에 예약 스케일링(시간/방향/수량 지정) 및 인프라 제어 버튼 삽입으로 운영 편의성 향상

<br/>

## 🗺️ 4. 아키텍처 및 수행 절차 (Execution Plan)

<img width="1184" height="993" alt="아키텍처 drawio (2)" src="https://github.com/user-attachments/assets/da9e0015-446a-4ce4-b699-1ca533dca9bd" />


<img width="1184" height="993" alt="아키텍처 drawio (2)" src="https://github.com/user-attachments/assets/da9e0015-446a-4ce4-b699-1ca533dca9bd" />


### 📌 주요 수행 단계
1. **인프라 코드화 및 보안 관리**: 모든 인프라 변경을 GitHub → MGMT 서버 경유로 하여 AWS 키 노출 차단 및 `tfstate` 일원화 관리
2. **IaC 기반 프로비저닝**: Terraform으로 AWS 인프라(VPC, ALB, ASG, EC2) 프로비저닝, Ansible로 구성 관리 자동화
3. **컨테이너화**: Docker를 활용해 애플리케이션을 컨테이너 이미지로 빌드하고, 스케일링 시 즉시 구동할 수 있는 컨테이너 이미지 풀 구축
4. **DevSecOps & FinOps**: GitHub Actions self-hosted runner 기반 CI/CD 파이프라인에 Infracost·Trivy 연동해 비용·보안 사전 검증
5. **통합 관제 및 AIOps 추천**: Prometheus·Grafana로 트래픽·자원 메트릭 실시간 수집 및 관제 환경 구성, 로컬 AI 서버가 분석 후 3가지 스케일링 옵션 추천
6. **GUI 기반 제어**: Grafana 대시보드 커스터마이징으로 시간·방향·수량을 지정하는 운영자 수동 스케일링 인터페이스 구현

<br/>

## 📺 5. 시나리오 시연 영상 (Demo Video)

[![Demo Video](https://img.youtube.com/vi/ddEJIfbR9Ag/0.jpg)](https://youtu.be/ddEJIfbR9Ag)


## 👥 6. 팀원 및 역할 분담 (Team Roles)

| 이름 | 역할 | 담당 업무 |
| :---: | :---: | :--- |
| **이성규** | 팀장<br/>(Cloud Infra) | - MGMT 서버 기반 AWS 자원(VPC, ALB, ASG, EC2) 코드화(IaC) 프로비저닝<br/>- `tfstate` 파일 중앙 집중화 및 AWS 접근 제어(보안) 정책 수립<br/>- 하이브리드 인프라 전체의 논리적/물리적 네트워크 아키텍처 뼈대 구축 |
| **최진제** | 부팀장<br/>(Container & Config) | - 애플리케이션 Docker 이미지 빌드 및 경량화 컨테이너 풀 마련<br/>- Ansible Playbook을 통한 신규 EC2 운영체제/환경 구성 자동화<br/>- Auto Scaling 시 무개입 컨테이너 배포 및 서비스 세팅 자동화 |
| **박영헌** | 팀원<br/>(AIOps) | - 복합적 장애 징후 사전 탐지 로직 적용 (로컬 AI 분석 모델)<br/>- 최적의 스케일링 옵션(보수적·공격적·현상유지) 도출<br/>- 지능형 인프라 제어 의사결정을 위한 실시간 알림/추천 연동 |
| **송민기** | 팀원<br/>(Observability) | - 인프라 트래픽/시스템 자원 메트릭 실시간 수집 파이프라인 연동<br/>- 운영자 맞춤형 통합 시각화 대시보드 (Grafana) 설계<br/>- 스케일링 직접 제어용 GUI 인터페이스 및 외부 API 트리거 구현 |
| **이창수** | 팀원<br/>(CI/CD Pipeline) | - Self-hosted runner 환경 구축 및 GitHub Actions 배포 자동화<br/>- Infracost(비용) & Trivy(보안) 검증 자동화 파이프라인 구성<br/>- 안전한 형상 관리 및 지속적 통합/배포(CI/CD) 환경 확립 |

<br/>

## 📚 7. 참고 자료 (References)
- [테라폼으로 시작하는 IaC]
- [AWS로 시작하는 인프라 구축의 정석]
- [한 권으로 배우는 Docker & Kubernetes]

---
*본 프로젝트는 인프라 청년들 팀에 의해 기획 및 개발되었습니다.*
