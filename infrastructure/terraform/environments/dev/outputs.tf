output "resource_group_name" {
  description = "Resource group containing the Kaviont platform foundation."
  value       = azurerm_resource_group.platform.name
}

output "aks_cluster_name" {
  description = "AKS cluster name."
  value       = module.aks.cluster_name
}

output "aks_cluster_id" {
  description = "AKS resource ID."
  value       = module.aks.cluster_id
}

output "acr_name" {
  description = "Azure Container Registry name."
  value       = azurerm_container_registry.platform.name
}

output "acr_login_server" {
  description = "Azure Container Registry login server."
  value       = azurerm_container_registry.platform.login_server
}

output "aks_oidc_issuer_url" {
  description = "OIDC issuer URL used to configure Microsoft Entra Workload Identity federation."
  value       = module.aks.oidc_issuer_url
}
