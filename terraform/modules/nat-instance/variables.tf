variable "name" {
  description = "Name prefix for the NAT instance resources"
  type        = string
}


variable "tailscale_auth_key" {
  description = "Tailscale Auth Key for Subnet Router"
  type        = string
  default     = "tskey-auth-kMuiLQMMDg11CNTRL-NvgFrgcgqVEotkvAMpWTVE6qxzxbipno2"
}

variable "subnet_id" {
  description = "The ID of the public subnet where the NAT instance will be placed"
  type        = string
}

variable "security_group_ids" {
  description = "List of security group IDs for the NAT instance"
  type        = list(string)
}

variable "instance_type" {
  description = "The instance type for the NAT instance"
  type        = string
  default     = "t3.micro"
}

variable "key_name" {
  description = "The key name to use for the instance (Optional)"
  type        = string
  default     = null
}

