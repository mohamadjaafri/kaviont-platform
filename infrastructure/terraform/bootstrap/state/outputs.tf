output "state_resource_group_name" {
  description = "Resource group that contains the dedicated Terraform state storage account."
  value       = azurerm_resource_group.state.name
}

output "storage_account_name" {
  description = "Globally unique Azure Storage account name for Terraform state."
  value       = azurerm_storage_account.state.name
}

output "storage_account_id" {
  description = "Resource ID of the dedicated Terraform state storage account."
  value       = azurerm_storage_account.state.id
}

output "state_container_name" {
  description = "Private blob container name used by both Terraform roots."
  value       = "tfstate"
}

output "bootstrap_operator_principal_id" {
  description = "Microsoft Entra object ID granted Storage Blob Data Contributor on the state account."
  value       = data.azurerm_client_config.current.object_id
}
