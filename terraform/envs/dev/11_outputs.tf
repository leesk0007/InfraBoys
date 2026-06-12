output "vpc_id" {
  value = module.project02_vpc.vpc_id
}

# Bastion이 삭제되었으므로, NAT 인스턴스의 퍼블릭 IP를 출력합니다.
output "nat_instance_public_ip" {
  description = "The public IP of the NAT instance"
  value       = module.project02_nat_instance.public_ip
}

output "alb_dns_name" {
  value = module.project02_alb.alb_dns_name
}

output "aws_ecr_repository_url" {
  description = "The URL of the ECR repository for the WAS application"
  value       = aws_ecr_repository.was_repo.repository_url
}

output "db_private_ip" {
  description = "The Private IP of the DB instance (Accessible via Tailscale)"
  value       = module.project02_db_ec2.private_ip
}
