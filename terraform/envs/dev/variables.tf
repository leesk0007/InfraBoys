
variable "tailscale_auth_key" {
  description = "Tailscale Auth Key for Subnet Router"
  type        = string
  sensitive   = true
}

variable "db_user" {
  description = "PostgreSQL 사용자명"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL 비밀번호"
  type        = string
  sensitive   = true
}

variable "desired_capacity" {
  description = "원하는 ec2 대수"
  type        =  number
  default     = 1
}

variable "ansible_public_key_path" {
  description = "ansible 공개키 경로"
  type = string
  default = "../../keys/ansible_key.pub"
}