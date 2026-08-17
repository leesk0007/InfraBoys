variable "project_id" {
  description = "The ID of the GCP project"
  type        = string
}

variable "region" {
  description = "The region to deploy resources in"
  type        = string
  default     = "asia-northeast3" # Seoul region
}

variable "zone" {
  description = "The zone to deploy resources in"
  type        = string
  default     = "asia-northeast3-a"
}
