# Grants the CI role gives itself, applied by CI.
#
# `bootstrap/` creates the GitHub Actions role and holds the grants CI cannot
# give itself: the role's existence, its trust policy, and the state bucket.
# That stack keeps local state and is applied by hand, so every grant that
# lived there was a hand apply the day a main-stack resource needed it, and a
# main-stack PR that could not merge until someone's laptop had run
# `terraform apply` (#246, first attempt). That is the wrong place for a
# routine change: the owner's rule is that CI is where everything is applied,
# so nothing is applied from a laptop by accident.
#
# The role already holds iam:PutRolePolicy on every `${var.project}-*` role,
# which includes itself, so a grant it needs for a main-stack resource can be
# an inline policy declared here, planned on the PR and applied on merge like
# any other resource. Bootstrap's own policy is untouched.
#
# The cost of this is stated plainly: any PR merged to `main` can widen what
# CI is allowed to do. That was already true (the role could grant itself
# anything within the project-role pattern); this file is where it now
# happens in the open, with a plan comment, rather than not at all.

data "aws_iam_role" "github_actions" {
  name = "${var.project}-github-actions"
}

# api.tf's aws_s3_bucket.cache, the shared live-layer cache (#186). The
# pattern requires `-cache-` in the name so the state bucket, which also
# matches `${var.project}-*`, keeps its object-only grant from bootstrap
# rather than gaining DeleteBucket by accident. Enumerated rather than `s3:*`
# because trivy flags a wildcard S3 action at HIGH (AWS-0345), and because
# the S3 namespace holds object actions this role has no business with. The
# Get* list is what the provider reads on every refresh of an
# `aws_s3_bucket`, whether or not api.tf configures the feature. If a
# provider upgrade adds a read, the plan fails with AccessDenied on a bucket
# that already exists, and the action gets added here.
data "aws_iam_policy_document" "ci_cache_buckets" {
  statement {
    sid = "LiveCacheBucket"
    actions = [
      "s3:CreateBucket", "s3:DeleteBucket", "s3:ListBucket", "s3:GetBucketLocation",
      "s3:GetBucketAcl", "s3:GetBucketCORS", "s3:GetBucketWebsite", "s3:GetBucketVersioning",
      "s3:GetAccelerateConfiguration", "s3:GetBucketRequestPayment", "s3:GetBucketLogging",
      "s3:GetReplicationConfiguration", "s3:GetBucketObjectLockConfiguration",
      "s3:GetBucketPolicy", "s3:GetBucketOwnershipControls",
      "s3:GetEncryptionConfiguration", "s3:PutEncryptionConfiguration",
      "s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock",
      "s3:GetLifecycleConfiguration", "s3:PutLifecycleConfiguration",
      # The provider's default_tags land on buckets too.
      "s3:GetBucketTagging", "s3:PutBucketTagging",
    ]
    resources = ["arn:aws:s3:::${var.project}-*-cache-*"]
  }
}

resource "aws_iam_role_policy" "ci_cache_buckets" {
  name   = "${var.project}-ci-cache-buckets"
  role   = data.aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.ci_cache_buckets.json
}
