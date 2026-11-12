variable "cluster_name" {
  description = "AKS cluster name."
  type        = string
}

variable "dns_prefix" {
  description = "AKS DNS prefix."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group name."
  type        = string
}

variable "kubernetes_version" {
  description = "Optional Kubernetes minor version. Null uses the Azure recommendation at creation time."
  type        = string
  default     = null
  nullable    = true
}

variable "system_pool_vm_size" {
  description = "System node pool VM SKU."
  type        = string
}

variable "system_pool_node_count" {
  description = "Initial system node count."
  type        = number
}

variable "system_pool_min_count" {
  description = "Minimum system node count."
  type        = number
}

variable "system_pool_max_count" {
  description = "Maximum system node count."
  type        = number
}

variable "aks_subnet_id" {
  description = "Subnet ID for AKS nodes."
  type        = string
}

variable "container_registry_id" {
  description = "ACR resource ID to grant AcrPull access to the AKS kubelet identity."
  type        = string
}

variable "api_server_authorized_ip_ranges" {
  description = "Public client CIDRs allowed to reach the AKS API server."
  type        = list(string)
}

variable "pod_cidr" {
  description = "Azure CNI Overlay pod address range."
  type        = string
}

variable "service_cidr" {
  description = "Kubernetes service address range."
  type        = string
}

variable "dns_service_ip" {
  description = "DNS service IP inside service_cidr."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
