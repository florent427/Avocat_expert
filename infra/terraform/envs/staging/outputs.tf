output "alb_dns_name" {
  value = module.edge.alb_dns_name
}

output "repository_urls" {
  value = module.registry.repository_urls
}

output "database_endpoint" {
  value = module.database.endpoint
}
