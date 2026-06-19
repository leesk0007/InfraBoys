############################################
# Auto Scaling Group (ASG)
############################################

# [1] WAS 서버 오토 스케일링
# → 트래픽이 몰릴 때 자동으로 서버를 복제해서 늘려주고(Scale-Out), 
#    트래픽이 줄어들면 다시 서버를 줄여주는(Scale-In) 핵심 리소스입니다.
# (2차 실행 시 주석 해제하여 사용)

module "asg" {
  source = "../../modules/asg"

  ami_id = data.aws_ami.project02_was.id

  asg_name = "project02-asg"

  instance_type = "t3.micro"

  # 최소 1대를 유지하고, 최대 7대까지 자동으로 늘어납니다.
  desired_capacity = var.desired_capacity
  min_size         = 1
  max_size         = 7

  # 인스턴스가 생성될 프라이빗 서브넷 위치 (AZ-a 단일 구성)
  subnet_ids = [
    module.project02_private_subnet_was.subnet_id
  ]

  # 생성된 인스턴스에 적용될 방화벽(보안 그룹)
  security_group_id = module.project02_was_sg.sg_id

  # 접속 키페어
  key_name = module.project02_was_ec2_key.key_name

  # 로드밸런서(ALB)의 타겟 그룹과 연동되어 새로 생성된 서버가 자동으로 로드밸런서에 등록됩니다.
  target_group_arns = [
    module.project02_alb.target_group_arn
  ]

  iam_instance_profile = aws_iam_instance_profile.ec2_discovery_profile.name

  user_data = <<-EOF
    #!/bin/bash
    until docker info >/dev/null 2>&1; do sleep 1; done

    aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin 644724502235.dkr.ecr.ap-northeast-2.amazonaws.com

    mkdir -p /home/ec2-user/app
    cd /home/ec2-user/app

    cat <<'NGINX' > nginx.conf
    upstream fastapi {
        server app:8000;
    }

    server {
        listen 80;

        location /timesale {
            proxy_pass         http://fastapi;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_read_timeout 5s;
        }

        location /orders {
            proxy_pass         http://fastapi;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_read_timeout 30s;
        }

        location / {
            proxy_pass         http://fastapi;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_read_timeout 10s;
        }

        location /health {
            proxy_pass http://fastapi/health;
            access_log off;
        }

        location /stub_status {
            stub_status;
            access_log off;
        }
    }
    NGINX

    cat <<'COMPOSE' > docker-compose.yml
    services:
      app:
        image: 644724502235.dkr.ecr.ap-northeast-2.amazonaws.com/project02-was-repo:latest
        environment:
          - DB_URL=postgresql://${var.db_user}:${var.db_password}@${module.project02_db_ec2.private_ip}:5432/eventdb
        restart: always
        deploy:
          resources:
            limits:
              memory: 512m
              cpus: "0.8"

      nginx:
        image: nginx:alpine
        ports:
          - "80:80"
        volumes:
          - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
        depends_on:
          - app
        restart: always

      node_exporter:
        image: prom/node-exporter:latest
        container_name: node-exporter
        ports:
          - "9100:9100"
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
        restart: always

      nginx_exporter:
        image: nginx/nginx-prometheus-exporter:latest
        container_name: nginx-exporter
        ports:
          - "9113:9113"
        command:
          - '--nginx.scrape-uri=http://nginx/stub_status'
        depends_on:
          - nginx
        restart: always

      process_exporter:
        image: ncabatoff/process-exporter:latest
        container_name: process-exporter
        ports:
          - "9256:9256"
        pid: host
        volumes:
          - /proc:/host/proc:ro
          - ./process-exporter.yml:/config/process-exporter.yml:ro
        command:
          - '--procfs=/host/proc'
          - '--config.path=/config/process-exporter.yml'
        restart: always
    COMPOSE

    cat <<'PROCEXP' > process-exporter.yml
    process_names:
      - name: "{{.Comm}}"
        cmdline:
          - '.+'
    PROCEXP

    chown -R ec2-user:ec2-user /home/ec2-user/app
    docker compose up -d
  EOF
}
