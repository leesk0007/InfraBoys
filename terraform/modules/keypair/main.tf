# 1. AWS Key Pair 등록 (로컬에 저장된 static public key 로드)
resource "aws_key_pair" "this" {
  key_name   = var.key_name
  public_key = file("${path.module}/../../keys/${var.key_name}.pub")
}

# 2. Private Key 파일 로컬 저장 (Ansible 실행 환경을 위해 ~/.ssh/ 복사)
resource "local_file" "private_key" {
  content         = file("${path.module}/../../keys/${var.key_name}.pem")
  filename        = pathexpand("~/.ssh/${var.key_name}.pem")
  file_permission = "0400"
}