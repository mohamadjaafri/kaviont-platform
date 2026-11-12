variable "name" {
  description = "Virtual network name."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group name."
  type        = string
}

variable "address_space" {
  description = "Virtual network address space."
  type        = list(string)
}

variable "aks_subnet_cidr" {
  description = "AKS node subnet CIDR."
  type        = string
}

variable "private_subnet_cidr" {
  description = "Subnet reserved for future private endpoints."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
