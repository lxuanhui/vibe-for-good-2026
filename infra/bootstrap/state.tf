# Remote state for the main stack. Needed the moment CI applies anything:
# a GitHub runner is ephemeral, so local state would mean every run planning
# against an empty state and trying to recreate the whole stack.

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  # Deleting this bucket destroys the record of every resource the main stack
  # manages, leaving them orphaned and un-manageable.
  lifecycle {
    prevent_destroy = true
  }
}

# Terraform overwrites the state object on every apply. Versioning is what
# makes a corrupt or truncated write recoverable.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# State contains every attribute of every resource, including anything marked
# sensitive. It must never be reachable publicly.
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Old state versions accumulate one object per apply forever otherwise.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-noncurrent-state"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  depends_on = [aws_s3_bucket_versioning.state]
}
