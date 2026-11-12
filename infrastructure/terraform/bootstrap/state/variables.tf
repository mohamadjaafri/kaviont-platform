variable "subscription_id" {
  description = "Azure subscription ID. Leave null to use ARM_SUBSCRIPTION_ID or the Azure CLI context."
  type        = string
  default     = null
  nullable    = true
}

variable "location" {
  description = "Azure region for the Terraform state resource group and storage account."
  type        = string
  default     = "westeurope"
}

variable "name_prefix" {
  description = "Short project prefix used for state resource names."
  type        = string
  default     = "kaviont"
}

variable "unique_suffix" {
  description = "Globally unique 4-8 character lowercase alphanumeric suffix for the state storage account."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{4,8}$", var.unique_suffix))
    error_message = "unique_suffix must contain 4-8 lowercase letters or numbers."
  }
}
