data "azurerm_client_config" "current" {}

resource "azurerm_user_assigned_identity" "control_plane" {
  name                = "${var.cluster_name}-control-plane"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_role_assignment" "network_contributor" {
  scope                = var.aks_subnet_id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.control_plane.principal_id
}

resource "azurerm_kubernetes_cluster" "this" {
  name                              = var.cluster_name
  location                          = var.location
  resource_group_name               = var.resource_group_name
  dns_prefix                        = var.dns_prefix
  kubernetes_version                = var.kubernetes_version
  sku_tier                          = "Free"
  automatic_upgrade_channel         = "patch"
  node_os_upgrade_channel           = "SecurityPatch"
  local_account_disabled            = true
  role_based_access_control_enabled = true
  run_command_enabled               = false

  default_node_pool {
    name                        = "system"
    vm_size                     = var.system_pool_vm_size
    node_count                  = var.system_pool_node_count
    auto_scaling_enabled        = true
    min_count                   = var.system_pool_min_count
    max_count                   = var.system_pool_max_count
    vnet_subnet_id              = var.aks_subnet_id
    os_sku                      = "AzureLinux3"
    temporary_name_for_rotation = "tmpnp"

    upgrade_settings {
      max_surge = "33%"
    }
  }

  node_provisioning_profile {
    mode = "Manual"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.control_plane.id]
  }

  azure_active_directory_role_based_access_control {
    tenant_id          = data.azurerm_client_config.current.tenant_id
    azure_rbac_enabled = true
  }

  oidc_issuer_enabled       = true
  workload_identity_enabled = true

  api_server_access_profile {
    authorized_ip_ranges = var.api_server_authorized_ip_ranges
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_data_plane  = "cilium"
    network_policy      = "cilium"
    pod_cidr            = var.pod_cidr
    service_cidr        = var.service_cidr
    dns_service_ip      = var.dns_service_ip
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }

  tags = var.tags

  depends_on = [azurerm_role_assignment.network_contributor]
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id

  skip_service_principal_aad_check = true
}
