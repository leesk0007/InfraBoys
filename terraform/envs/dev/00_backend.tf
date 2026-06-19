terraform {
  backend "s3" {
    bucket         = "project02-tfstate-bucket-mk"
    key            = "dev/terraform.tfstate"
    region         = "ap-northeast-2"
    use_lockfile   = true
	encrypt = true # tstate 에는 민감한 정보가 들어있어 암호화
  }
}