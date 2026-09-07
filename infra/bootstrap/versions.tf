terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Deliberately local state. This module creates the bucket that holds the
  # *main* stack's state, so it cannot store its own state there. It is
  # applied once, by hand, and is idempotent -- losing this state file costs
  # a `terraform import`, not an outage.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Component = "bootstrap"
      Repo      = "vibe-for-good-2026"
    }
  }
}
