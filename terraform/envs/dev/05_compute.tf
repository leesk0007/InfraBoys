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


# [2] DB 데이터 영구 보존용 EBS 볼륨
# → EC2를 destroy/재생성해도 이 볼륨은 삭제되지 않아 DB 데이터가 유지됩니다.
resource "aws_ebs_volume" "db_data" {
  availability_zone = data.aws_availability_zones.available.names[0]
  size              = 20
  type              = "gp3"
  tags              = { Name = "project02-db-data" }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "db_data" {
  device_name  = "/dev/sdf"
  volume_id    = aws_ebs_volume.db_data.id
  instance_id  = module.project02_db_ec2.instance_id
  force_detach = true
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
    mkdir -p /home/ec2-user/.ssh
    chmod 700 /home/ec2-user/.ssh
    touch /home/ec2-user/.ssh/authorized_keys
    chmod 600 /home/ec2-user/.ssh/authorized_keys

    ANSIBLE_KEY="${trimspace(file(var.ansible_public_key_path))}"
    if ! grep -qF "$ANSIBLE_KEY" /home/ec2-user/.ssh/authorized_keys; then
      printf '\n%s\n' "$ANSIBLE_KEY" >> /home/ec2-user/.ssh/authorized_keys
    fi
    chown -R ec2-user:ec2-user /home/ec2-user/.ssh

    dnf install -y docker
    systemctl enable --now docker
    usermod -aG docker ec2-user

    until docker info >/dev/null 2>&1; do sleep 1; done

<<<<<<< HEAD
    # EBS 볼륨 마운트 (데이터 영속성)
    DEVICE=/dev/nvme1n1
    MOUNT_POINT=/data/postgres
    until lsblk $DEVICE >/dev/null 2>&1; do sleep 2; done
    if ! blkid $DEVICE | grep -q xfs; then
      mkfs -t xfs $DEVICE
    fi
    mkdir -p $MOUNT_POINT
    mount $DEVICE $MOUNT_POINT
    echo "$DEVICE $MOUNT_POINT xfs defaults 0 0" >> /etc/fstab

=======
>>>>>>> feature/1/monitoring
    aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 644724502235.dkr.ecr.ap-northeast-2.amazonaws.com

    # 컨테이너 간 통신용 네트워크
    docker network create db-net

    # postgres
    docker run -d \
      --name postgres \
      --network db-net \
      --restart always \
      -e POSTGRES_USER=${var.db_user} \
      -e POSTGRES_PASSWORD=${var.db_password} \
      -e POSTGRES_DB=eventdb \
      -p 5432:5432 \
      -v /data/postgres:/var/lib/postgresql/data \
      644724502235.dkr.ecr.ap-northeast-2.amazonaws.com/project02-db-repo:latest

    # postgres_exporter
    docker run -d \
      --name postgres-exporter \
      --network db-net \
      --restart always \
      -e DATA_SOURCE_NAME="postgresql://${var.db_user}:${var.db_password}@postgres:5432/eventdb?sslmode=disable" \
      -p 9187:9187 \
      prometheuscommunity/postgres-exporter:latest

    # node_exporter
    docker run -d \
      --name node-exporter \
      --restart always \
      --network host \
      --pid host \
      -v /proc:/host/proc:ro \
      -v /sys:/host/sys:ro \
      -v /:/rootfs:ro \
      prom/node-exporter:latest \
      --path.procfs=/host/proc \
      --path.rootfs=/rootfs \
      --path.sysfs=/host/sys \
      '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
  EOF
}