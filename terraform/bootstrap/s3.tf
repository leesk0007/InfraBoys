resource "aws_s3_bucket" "tfstate" {
  bucket = "project02-tfstate-bucket-mk"

  # 실수 방지 (삭제 방지)
  force_destroy = false

  tags = {
    Name = "project02-tfstate"
  }
}

# 버전 관리
resource "aws_s3_bucket_versioning" "tfstate_versioning" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

# 암호화
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate_enc" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
