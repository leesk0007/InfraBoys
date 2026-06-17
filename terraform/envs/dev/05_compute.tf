############################################
# 5. COMPUTE (EC2 인스턴스)
############################################

# [1] SSH 키페어 생성
# → EC2 인스턴스에 안전하게 접속하기 위한 열쇠를 만듭니다. (Bastion용은 삭제됨)
module "project02_was_ec2_key" {
  source   = "../../modules/keypair"
  key_name = "project02-was-key"
}

module "project02_db_ec2_key" {
  source   = "../../modules/keypair"
  key_name = "project02-db-key"
}


# [3] DB (데이터베이스 서버)
# → PostgreSQL 등 데이터베이스를 구동할 단일 서버입니다. (데이터 정합성을 위해 1대만 운영)
module "project02_db_ec2" {
  source               = "../../modules/ec2"
  instance_type        = "t3.micro"
  subnet_id            = module.project02_private_subnet_db.subnet_id
  security_group_ids   = [module.project02_db_sg.sg_id]
  key_name             = module.project02_db_ec2_key.key_name
  iam_instance_profile = aws_iam_instance_profile.ec2_discovery_profile.name
  name                 = "project02_db_ec2"
  tags                 = { Role = "DB" }

  root_volume_size = 30

  # 스키마가 bake된 커스텀 postgres 이미지 사용 (AWS ECR에서 가져옴)
  user_data = <<-EOF
    #!/bin/bash
    dnf install -y docker
    systemctl enable --now docker
    usermod -aG docker ec2-user

    until docker info >/dev/null 2>&1; do sleep 1; done

    aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 644724502235.dkr.ecr.ap-northeast-2.amazonaws.com

    mkdir -p /home/ec2-user/db
    cd /home/ec2-user/db

    cat <<'COMPOSE' > docker-compose.yml
    services:
      postgres:
        image: 644724502235.dkr.ecr.ap-northeast-2.amazonaws.com/project02-db-repo:latest
        container_name: postgres
        restart: always
        environment:
          POSTGRES_USER: ${var.db_user}
          POSTGRES_PASSWORD: ${var.db_password}
          POSTGRES_DB: eventdb
        ports:
          - "5432:5432"

      postgres_exporter:
        image: prometheuscommunity/postgres-exporter:latest
        container_name: postgres-exporter
        restart: always
        environment:
          DATA_SOURCE_NAME: postgresql://${var.db_user}:${var.db_password}@postgres:5432/eventdb?sslmode=disable
        ports:
          - "9187:9187"
        depends_on:
          - postgres

      node_exporter:
        image: prom/node-exporter:latest
        container_name: node-exporter
        restart: always
        network_mode: host
        pid: host
        volumes:
          - /proc:/host/proc:ro
          - /sys:/host/sys:ro
          - /:/rootfs:ro
        command:
          - '--path.procfs=/host/proc'
          - '--path.rootfs=/rootfs'
          - '--path.sysfs=/host/sys'
          - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    COMPOSE

    chown -R ec2-user:ec2-user /home/ec2-user/db
    docker compose up -d
  EOF
}