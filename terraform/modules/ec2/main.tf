data "aws_ami" "latest_al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_instance" "this" {
  ami                    = data.aws_ami.latest_al2023.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = var.security_group_ids
  key_name               = var.key_name
  iam_instance_profile = var.iam_instance_profile
  user_data_base64     = var.user_data != null ? base64encode(var.user_data) : null
  user_data_replace_on_change = true

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  lifecycle {
    ignore_changes = [
      ami,
      user_data
    ]
  }

  tags = merge(
    {
      Name = var.name
    },
    var.tags
  )
}