output "virtual_network_id" {
  description = "Virtual network resource ID."
  value       = azurerm_virtual_network.this.id
}

output "aks_subnet_id" {
  description = "Subnet ID assigned to AKS nodes."
  value       = azurerm_subnet.aks.id
}

output "private_endpoint_subnet_id" {
  description = "Reserved private endpoint subnet ID."
  value       = azurerm_subnet.private_endpoints.id
}
