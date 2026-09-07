variable "aws_region" {
  description = "Region for the state bucket. Must match the region in the main stack's backend block."
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Name prefix applied to every resource."
  type        = string
  default     = "vibe-for-good-2026"
}

variable "state_bucket_name" {
  description = "S3 bucket holding the main stack's Terraform state. Must match the literal bucket name in ../versions.tf -- a backend block cannot interpolate variables, so the two are kept in sync by hand."
  type        = string
  default     = "vibe-for-good-2026-tfstate-apse1"
}

variable "github_repository" {
  description = "owner/repo allowed to assume the CI role."
  type        = string
  default     = "lxuanhui/vibe-for-good-2026"
}

variable "create_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. AWS allows exactly one per account, so this defaults to false: any account already using GitHub Actions has one, and creating a second fails with EntityAlreadyExists. Set true only in a fresh account."
  type        = bool
  default     = false
}
