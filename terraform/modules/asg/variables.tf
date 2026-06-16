variable "instance_type" {
  type = string
}

variable "desired_capacity" {
  type = number
}

variable "max_size" {
  type = number
}

variable "min_size" {
  type = number
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "key_name" {
  type = string
}

variable "asg_name" {
  type = string
}

variable "target_group_arns" {
  type = list(string)
}

variable "ami_id" {
  type = string
}

variable "user_data" {
  description = "The user data script to run on instances"
  type        = string
  default     = ""
}

variable "iam_instance_profile" {
  description = "IAM instance profile name for ECR pull and EC2 discovery"
  type        = string
  default     = null
}