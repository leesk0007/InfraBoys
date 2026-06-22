module "project02_route53" {
  source = "../../modules/route53"

  domain_name = "tuby.shop"
  
  # ALB 모듈에서 출력된 값들을 받아옴
  alb_arn          = module.project02_alb.alb_arn
  alb_dns_name     = module.project02_alb.alb_dns_name
  alb_zone_id      = module.project02_alb.alb_zone_id
  target_group_arn = module.project02_alb.target_group_arn
}
