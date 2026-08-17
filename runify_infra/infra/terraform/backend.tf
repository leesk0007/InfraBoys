terraform {
  backend "gcs" {
    bucket = "runify-tf-state-bucket"
    prefix = "terraform/state"
  }
}
