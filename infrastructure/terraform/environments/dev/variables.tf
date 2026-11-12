variable "subscription_id" {
  description = "Azure subscription ID. Leave null to use ARM_SUBSCRIPTION_ID."
  type        = string
  default     = null
  nullable    = true
}

variable "location" {
  description = "Azure region for the development environment."
  type        = string
  default     = "westeurope"
}

variable "environment" {
  description = "Short environment identifier used in resource names and tags."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z0-9]{2,8}$", var.environment))
    error_message = "environment must be 2-8 lowercase letters or numbers."
  }
}

variable "name_prefix" {
  description = "Short project prefix for Azure resources."
  type        = string
  default     = "kaviont"
}

variable "unique_suffix" {
  description = "Globally unique alphanumeric suffix for the Azure Container Registry name."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{4,8}$", var.unique_suffix))
    error_message = "unique_suffix must contain 4-8 lowercase letters or numbers."
  }
}

variable "kubernetes_version" {
  description = "Optional AKS Kubernetes minor version. Null lets Azure choose its recommended version."
  type        = string
  default     = null
  nullable    = true
}

variable "system_pool_vm_size" {
  description = "VM SKU for the AKS system node pool. Check regional availability and pricing before deployment."
  type        = string
  default     = "Standard_D2s_v5"
}

variable "system_pool_node_count" {
  description = "Initial system node count."
  type        = number
  default     = 1

  validation {
    condition     = var.system_pool_node_count >= 1 && var.system_pool_node_count <= 3
    error_message = "system_pool_node_count must be between 1 and 3 for this development profile."
  }
}

variable "system_pool_min_count" {
  description = "Minimum autoscaled system nodes."
  type        = number
  default     = 1
}

variable "system_pool_max_count" {
  description = "Maximum autoscaled system nodes."
  type        = number
  default     = 3
}

variable "api_server_authorized_ip_ranges" {
  description = "CIDR allowlist for the public AKS API endpoint. Supply your fixed public egress IP as /32."
  type        = list(string)

  validation {
    condition     = length(var.api_server_authorized_ip_ranges) > 0
    error_message = "At least one API-server authorized CIDR is required."
  }
}

variable "vnet_address_space" {
  description = "Address space for the platform virtual network."
  type        = list(string)
  default     = ["10.40.0.0/16"]
}

variable "aks_subnet_cidr" {
  description = "Subnet for AKS nodes."
  type        = string
  default     = "10.40.0.0/20"
}

variable "private_endpoint_subnet_cidr" {
  description = "Reserved subnet for private endpoints in a later iteration."
  type        = string
  default     = "10.40.32.0/24"
}

variable "pod_cidr" {
  description = "Non-overlapping pod CIDR for Azure CNI Overlay."
  type        = string
  default     = "10.41.0.0/16"
}

variable "service_cidr" {
  description = "Kubernetes service CIDR. It must not overlap connected networks."
  type        = string
  default     = "10.42.0.0/16"
}

variable "dns_service_ip" {
  description = "DNS service IP inside service_cidr."
  type        = string
  default     = "10.42.0.10"
}
