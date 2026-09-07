terraform {
  required_version = ">= 1.10.0"

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

  # Remote state, so a GitHub Actions runner and a laptop plan against the
  # same reality. use_lockfile is S3-native locking (Terraform >= 1.10) --
  # the old DynamoDB lock table was removed in 1.11, so don't reintroduce it.
  #
  # The bucket is created by infra/bootstrap/, which must be applied first.
  # A backend block cannot interpolate variables, so this literal name is
  # kept in sync with bootstrap's state_bucket_name by hand.
  backend "s3" {
    bucket       = "vibe-for-good-2026-tfstate-apse1"
    key          = "infra/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
