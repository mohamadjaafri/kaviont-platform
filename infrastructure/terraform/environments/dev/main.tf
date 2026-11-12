data "azurerm_client_config" "current" {}

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

resource "azurerm_key_vault" "platform" {
  name                = "kv${replace(local.name_base, "-", "")}${var.unique_suffix}"
  location            = azurerm_resource_group.platform.location
  resource_group_name = azurerm_resource_group.platform.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  rbac_authorization_enabled    = true
  soft_delete_retention_days    = 7
  purge_protection_enabled      = true
  public_network_access_enabled = true

  tags = local.common_tags
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

resource "azurerm_user_assigned_identity" "hello_api" {
  name                = "${local.name_base}-hello-api"
  location            = azurerm_resource_group.platform.location
  resource_group_name = azurerm_resource_group.platform.name
  tags                = local.common_tags
}

resource "azurerm_federated_identity_credential" "hello_api" {
  name                = "${local.name_base}-hello-api"
  resource_group_name = azurerm_resource_group.platform.name
  parent_id           = azurerm_user_assigned_identity.hello_api.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = module.aks.oidc_issuer_url
  subject             = "system:serviceaccount:demo:hello-api"
}

resource "azurerm_role_assignment" "hello_api_key_vault_secrets_user" {
  scope                = azurerm_key_vault.platform.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.hello_api.principal_id

  skip_service_principal_aad_check = true
}
