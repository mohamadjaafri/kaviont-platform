locals {
  name_base = "${var.name_prefix}-${var.environment}"

  common_tags = {
    project     = "kaviont"
    environment = var.environment
    managed_by  = "terraform"
    owner       = "platform-engineering"
  }
}

resource "azurerm_resource_group" "platform" {
  name     = "${local.name_base}-rg"
  location = var.location
  tags     = local.common_tags
}

module "network" {
  source = "../../modules/network"

  name                = "${local.name_base}-vnet"
  location            = azurerm_resource_group.platform.location
  resource_group_name = azurerm_resource_group.platform.name
  address_space       = var.vnet_address_space
  aks_subnet_cidr     = var.aks_subnet_cidr
  private_subnet_cidr = var.private_endpoint_subnet_cidr
  tags                = local.common_tags
}

resource "azurerm_container_registry" "platform" {
  name                = "${replace(local.name_base, "-", "")}${var.unique_suffix}"
  resource_group_name = azurerm_resource_group.platform.name
  location            = azurerm_resource_group.platform.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.common_tags
}

module "aks" {
  source = "../../modules/aks"

  cluster_name                    = "${local.name_base}-aks"
  dns_prefix                      = substr(replace("${local.name_base}-dns", "-", ""), 0, 54)
  location                        = azurerm_resource_group.platform.location
  resource_group_name             = azurerm_resource_group.platform.name
  kubernetes_version              = var.kubernetes_version
  system_pool_vm_size             = var.system_pool_vm_size
  system_pool_node_count          = var.system_pool_node_count
  system_pool_min_count           = var.system_pool_min_count
  system_pool_max_count           = var.system_pool_max_count
  aks_subnet_id                   = module.network.aks_subnet_id
  container_registry_id           = azurerm_container_registry.platform.id
  api_server_authorized_ip_ranges = var.api_server_authorized_ip_ranges
  pod_cidr                        = var.pod_cidr
  service_cidr                    = var.service_cidr
  dns_service_ip                  = var.dns_service_ip
  tags                            = local.common_tags
}
