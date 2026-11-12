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

output "key_vault_name" {
  description = "Azure Key Vault name for the sample workload."
  value       = azurerm_key_vault.platform.name
}

output "key_vault_uri" {
  description = "Azure Key Vault URI used by the sample workload."
  value       = azurerm_key_vault.platform.vault_uri
}

output "hello_api_identity_client_id" {
  description = "Client ID annotated on the hello-api Kubernetes service account."
  value       = azurerm_user_assigned_identity.hello_api.client_id
}

output "azure_tenant_id" {
  description = "Microsoft Entra tenant ID used by the development environment."
  value       = data.azurerm_client_config.current.tenant_id
}
