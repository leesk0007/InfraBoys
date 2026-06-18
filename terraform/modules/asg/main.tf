# modules/asg/main.tf

data "aws_ami" "was_ami" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

locals {
  ami_id = coalesce(var.ami_id, data.aws_ami.was_ami.id)
}

# Launch Template
resource "aws_launch_template" "lt" {
  name_prefix   = "project02-was01-ec2-"

  #image_id      = data.aws_ami.was_ami.id
  image_id      = local.ami_id   #jin 추가

  instance_type = var.instance_type

  vpc_security_group_ids = [var.security_group_id]
  key_name               = var.key_name

  dynamic "iam_instance_profile" {
    for_each = var.iam_instance_profile != null ? [var.iam_instance_profile] : []
    content {
      name = iam_instance_profile.value
    }
  }

  user_data = base64encode(var.user_data)

  # 시작 템플릿을 통해 생성될 리소스에 대한 상태 태그 설정
  tag_specifications {
    # 태그를 적용할 리소스의 종류
    resource_type = "instance"
    # asg가 인스턴스를 생성할때 마다 이 이름을 붙여준다
    tags = {
       Name = "project02-was-ec2"
       Role = "WAS" 
    }
  }

  lifecycle {
    ignore_changes = [
      image_id,
      user_data
    ]
  }
}

# Auto Scaling Group
resource "aws_autoscaling_group" "asg" {
  name = var.asg_name

  vpc_zone_identifier = var.subnet_ids

  desired_capacity = var.desired_capacity
  max_size         = var.max_size
  min_size         = var.min_size
  
  target_group_arns = var.target_group_arns

  launch_template {
    id      = aws_launch_template.lt.id
    version = "$Latest"
  }

  # Launch Template 버전이 바뀌면 자동으로 인스턴스 롤링 교체 시작
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 50
      #instance_warmup        = 60
	  instance_warmup        = 20
    }
    triggers = ["tag"]
  }

  #default_cooldown = 60
  default_cooldown = 15
}

# ASG에 의해 생성된 실제 인스턴스의 정보를 조회

data "aws_instances" "asg_nodes" {
  # ASG가 먼저 생성되어야 된다 
  # ASG 생성이 완료될 때까지 이 조회를 기다리도록 순서를 강제합니다.
  depends_on = [aws_autoscaling_group.asg]

  # 필터링 조건: 수많은 인스턴스 중 어떤 녀석을 골라낼지 정합니다.
  instance_tags = {
    # AWS가 ASG 소속 인스턴스에 자동으로 붙여주는 "소속 태그"를 이용합니다.
    # "이 ASG 이름(lecture-asg)을 가진 그룹에 속한 애들 다 모여!" 라는 뜻입니다.
    "aws:autoscaling:groupName" = aws_autoscaling_group.asg.name
  }

  # 상태 필터: 꺼져 있거나(stopped) 생성 중인 애들은 빼고, 
  # 지금 바로 접속해서 일할 수 있는 'running' 상태인 애들만 쏙 골라냅니다.
  instance_state_names = ["running"]
}

# 8. 동적 스케일링 정책
resource "aws_autoscaling_policy" "cpu_scaling_policy" {
  name = "cpu-target-tracking"
  # 대상 추적 방식 : 특정 지표를 정해진 수치로 유지하도록 aws 알아서 조종
  autoscaling_group_name = aws_autoscaling_group.asg.name
  # 대상 추적 설정
  policy_type = "TargetTrackingScaling"  
  
  estimated_instance_warmup = 60

  target_tracking_configuration {
    # 무엇을 기준으로 추적할것인가?
    predefined_metric_specification {
      # asg 그룹 내의 모든 인스턴스의 cpu 사용 평균값
      predefined_metric_type = "ASGAverageCPUUtilization"
    }
    # 기준이 되는 사용률 50% (테스트를 위해낮게 잡음)
    # 50%를 넘어가면 -> scale out -> ec2 개수가 늘어남 (max 까지)
    # 50% 아래로 떨어지면 -> scale in -> ec2 개수가 줄어듬 (min까지)
    #target_value = 50
	target_value = 30	
  }

}