terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # State is local by default so a hackathon clone works with no bootstrap
  # step. Before more than one person runs apply, move it to S3 with state
  # locking -- two people applying against separate local state files will
  # fight over the same AWS resources.
  #
  # backend "s3" {
  #   bucket       = "vibe-for-good-2026-tfstate"
  #   key          = "infra/terraform.tfstate"
  #   region       = "ap-southeast-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}
