############################################
# 3. ROUTING LAYER (라우팅 테이블)
############################################

# [1] Public Route Table
# → 인터넷 게이트웨이(IGW)를 향하는 기본 라우팅(0.0.0.0/0)을 설정합니다.
# → 이 라우팅 테이블에 연결된 서브넷은 외부 인터넷과 직접 통신이 가능합니다.
resource "aws_route_table" "project02_public_rt" {
  vpc_id = module.project02_vpc.vpc_id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = module.igw.igw_id
  }

  tags = {
    Name = "project02-public-rt"
  }
}

# Public Subnet 연결
# → A와 B 두 개의 퍼블릭 서브넷을 위에서 만든 라우팅 테이블에 연결합니다.
resource "aws_route_table_association" "public_a_rt" {
  subnet_id      = module.project02_public_subnet_a.subnet_id
  route_table_id = aws_route_table.project02_public_rt.id
}

resource "aws_route_table_association" "public_b_rt" {
  subnet_id      = module.project02_public_subnet_b.subnet_id
  route_table_id = aws_route_table.project02_public_rt.id
}


# [2] NAT 인스턴스 (NAT Gateway 대체)
# → 퍼블릭 서브넷 A에 위치하며, 프라이빗 서브넷 안의 서버들이 
#    외부 인터넷(패키지 다운로드 등)으로 나갈 수 있도록 징검다리 역할을 합니다.
module "project02_nat_instance" {
  source             = "../../modules/nat-instance"
  name               = "project02-nat-instance"
  subnet_id          = module.project02_public_subnet_a.subnet_id
  security_group_ids = [module.project02_nat_sg.sg_id]
  tailscale_auth_key = var.tailscale_auth_key
  key_name           = module.project02_was_ec2_key.key_name
}


# [3] Private Route Table
# → 프라이빗 서브넷 전용 라우팅 테이블입니다.
# → 인터넷으로 나가는 모든 아웃바운드 트래픽(0.0.0.0/0)을 NAT 인스턴스로 보냅니다.
resource "aws_route_table" "project02_private_rt" {
  vpc_id = module.project02_vpc.vpc_id

  route {
    cidr_block           = "0.0.0.0/0"
    # NAT 인스턴스의 네트워크 인터페이스 ID를 목적지로 지정
    network_interface_id = module.project02_nat_instance.primary_network_interface_id
  }

  depends_on = [module.project02_nat_instance]

  tags = {
    Name = "project02-private-rt"
  }
}

# Private Subnet 연결
# → WAS 서브넷과 DB 서브넷을 프라이빗 라우팅 테이블에 연결합니다.
resource "aws_route_table_association" "was_rt" {
  subnet_id      = module.project02_private_subnet_was.subnet_id
  route_table_id = aws_route_table.project02_private_rt.id
}

resource "aws_route_table_association" "db_rt" {
  subnet_id      = module.project02_private_subnet_db.subnet_id
  route_table_id = aws_route_table.project02_private_rt.id
}