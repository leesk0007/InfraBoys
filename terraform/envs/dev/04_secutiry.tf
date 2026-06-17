############################################
# 4. SECURITY GROUP (방화벽 역할)
############################################

# [1] NAT 인스턴스 보안 그룹 (NAT Instance SG)
# → 프라이빗 서브넷 안에 있는 서버들이 인터넷(패키지 업데이트 등)으로 
#    나갈 수 있도록 트래픽을 중계해주는 NAT 인스턴스용 방화벽입니다.
module "project02_nat_sg" {
  source = "../../modules/security-group"
  name   = "project02-nat-sg"
  vpc_id = module.project02_vpc.vpc_id

  # 인바운드(들어오는 트래픽) 규칙: 프라이빗 내부망(10.0.0.0/16)에서 오는 모든 트래픽을 허용합니다.
  ingress_rules = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["10.0.0.0/16", "100.64.0.0/10"]
    },
    {
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
      description = "Temporary SSH access for debugging"
    }
  ]
  # 아웃바운드(나가는 트래픽) 규칙: 어디로든 자유롭게 나갈 수 있도록 허용합니다.
  egress_rules = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
      description = "Allow all outbound traffic to internet"
    }
  ]
}

# [2] 웹 애플리케이션 서버 보안 그룹 (WAS SG)
# → 실제 서비스(FastAPI)가 동작하는 서버용 방화벽입니다.
module "project02_was_sg" {
  source = "../../modules/security-group"
  name   = "project02-was-sg"
  vpc_id = module.project02_vpc.vpc_id

  ingress_rules = [
    # 1. 외부에서 직접 접근할 수 없고, 오직 ALB(로드밸런서)를 통해서만 HTTP(80) 접근이 가능합니다.
    {
      from_port       = 80
      to_port         = 80
      protocol        = "tcp"
      security_groups = [module.project02_alb_sg.sg_id]
      description     = "ALB to WAS HTTP Access"
    },
    # 2. 관리자가 관리 및 모니터링을 하기 위해 내부망(10.0.0.0/16)을 통한 SSH 및 Tailscale 접근을 허용합니다.
    {
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = ["10.0.0.0/16", "100.64.0.0/10"]
      description = "Internal VPC SSH Access (Tailscale or mgmt)"
    },
    # 3. 메트릭 수집을 위한 내부망의 Prometheus Node Exporter(9100) 접근을 허용합니다.
    {
      from_port   = 9100
      to_port     = 9100
      protocol    = "tcp"
      cidr_blocks = ["10.0.0.0/16", "100.64.0.0/10"]
      description = "Prometheus Node Exporter access from internal VPC and Tailscale"
    }
  ]
  egress_rules = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
      description = "Allow all outbound traffic"
    }
  ]
}

# [3] 데이터베이스 보안 그룹 (DB SG)
# → 가장 안전하게 보호되어야 하는 DB 서버용 방화벽입니다.
module "project02_db_sg" {
  source = "../../modules/security-group"
  name   = "project02-db-sg"
  vpc_id = module.project02_vpc.vpc_id

  ingress_rules = [
    # 1. 오직 WAS(웹 서버)만이 DB(PostgreSQL 기본 포트 5432)에 접근할 수 있도록 제한합니다.
    {
      from_port       = 5432
      to_port         = 5432
      protocol        = "tcp"
      security_groups = [module.project02_was_sg.sg_id]
      description     = "WAS to DB Access"
    },
    # 1.5. Tailscale 및 내부망을 통한 DB(5432) 접근을 추가로 허용합니다. (개발/디버깅용)
    {
      from_port   = 5432
      to_port     = 5432
      protocol    = "tcp"
      cidr_blocks = ["10.0.0.0/16", "100.64.0.0/10"]
      description = "DB Access from Tailscale and Internal VPC"
    },
    # 2. 내부망을 통한 관리자 SSH 접근 허용 (장애 조치 및 세팅 목적)
    {
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = ["10.0.0.0/16", "100.64.0.0/10"]
      description = "Internal VPC SSH Access (Tailscale or mgmt)"
    },
    # 3. 성능 모니터링을 위한 내부망 접근 허용 (Node Exporter 9100, Postgres Exporter 9187)
    {
      from_port   = 9100
      to_port     = 9100
      protocol    = "tcp"
      cidr_blocks = ["10.0.0.0/16", "100.64.0.0/10"]
      description = "Prometheus Node Exporter access from internal VPC and Tailscale"
    },
    {
      from_port   = 9187
      to_port     = 9187
      protocol    = "tcp"
      cidr_blocks = ["10.0.0.0/16", "100.64.0.0/10"]
      description = "Prometheus Postgres Exporter access from internal VPC and Tailscale"
    }
  ]
  egress_rules = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
      description = "Allow all outbound traffic"
    }
  ]
}

# [4] 로드밸런서 보안 그룹 (ALB SG)
# → 사용자(인터넷)가 서비스에 최초로 들어오는 관문 역할을 합니다.
module "project02_alb_sg" {
  source = "../../modules/security-group"
  name   = "project02-alb-sg"
  vpc_id = module.project02_vpc.vpc_id

  ingress_rules = [
    # 1. 전 세계 어디서든 HTTP(80) 트래픽을 허용합니다.
    {
      from_port   = 80
      to_port     = 80
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
      description = "HTTP External Traffic"
    },
    # 2. 전 세계 어디서든 HTTPS(443) 트래픽을 허용합니다. (보안 연결)
    {
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
      description = "HTTPS External Traffic"
    }
  ]
  egress_rules = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
      description = "Allow all outbound traffic"
    }
  ]
}