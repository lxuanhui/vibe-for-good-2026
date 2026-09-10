# GitHub Actions authenticates to AWS with a short-lived OIDC token exchanged
# for this role. No long-lived access keys are stored in GitHub secrets --
# there is nothing to leak or rotate.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"

  project_role_arn = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${var.project}-*"

  github_owner = split("/", var.github_repository)[0]
  github_repo  = split("/", var.github_repository)[1]

  # GitHub issues OIDC tokens in two subject formats. The widely documented
  # one is name-based:
  #
  #     repo:owner/repo:pull_request
  #
  # but this repository receives the hardened immutable form, which appends
  # the numeric owner and repository ids:
  #
  #     repo:owner@73178128/repo@1358849204:pull_request
  #
  # The immutable form is the stronger of the two -- it does not follow a
  # rename, so a repo deleted and recreated under the same name cannot
  # inherit this role. Both are allowed here so the pipeline keeps working
  # whichever format GitHub sends, and both stay pinned to this repository.
  github_repo_immutable = "${local.github_owner}@${var.github_owner_id}/${local.github_repo}@${var.github_repository_id}"

  # Pushes to main (which apply) and pull requests (which only plan).
  # Deliberately not "repo:...:*" -- that would let any branch in the repo
  # assume a role that can write to the account.
  allowed_oidc_subjects = flatten([
    for repo_ref in [var.github_repository, local.github_repo_immutable] : [
      "repo:${repo_ref}:ref:refs/heads/main",
      "repo:${repo_ref}:pull_request",
    ]
  ])
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to this repository, and within it to pushes on main and to pull
    # requests. An arbitrary branch in this repo cannot assume the role, which
    # otherwise would let anyone who can push a branch run an apply.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.allowed_oidc_subjects
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name                 = "${var.project}-github-actions"
  description          = "Assumed by GitHub Actions to plan and apply infra/."
  assume_role_policy   = data.aws_iam_policy_document.github_assume_role.json
  max_session_duration = 3600
}

# Scoped by service and, where the service supports it, by resource name
# prefix. Not least-privilege to the individual action -- see the note in
# infra/README.md; the intent is that this role cannot touch resources
# outside this project.
data "aws_iam_policy_document" "github_actions" {
  statement {
    sid       = "TerraformState"
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning"]
    resources = [aws_s3_bucket.state.arn]
  }

  statement {
    sid       = "TerraformStateObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = ["arn:${data.aws_partition.current.partition}:lambda:*:${data.aws_caller_identity.current.account_id}:function:${var.project}-*"]
  }

  statement {
    sid       = "LambdaList"
    actions   = ["lambda:GetAccountSettings", "lambda:ListFunctions"]
    resources = ["*"]
  }

  # API Gateway resource ARNs are path-based (/apis/{id}) and the id is not
  # known until creation, so this cannot be name-scoped the way Lambda is.
  statement {
    sid       = "ApiGateway"
    actions   = ["apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE", "apigateway:TagResource", "apigateway:UntagResource"]
    resources = ["arn:${data.aws_partition.current.partition}:apigateway:*::/*"]
  }

  statement {
    sid = "IamForProjectRoles"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
      "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
      "iam:UpdateAssumeRolePolicy",
    ]
    resources = [local.project_role_arn]
  }

  # Amplify ARNs are id-based (apps/{id}) and the id is not known until
  # creation, so this cannot be name-scoped the way Lambda is -- same reason
  # the API Gateway statement above is broad. Scoped to this account.
  statement {
    sid       = "AmplifyConsoleHosting"
    actions   = ["amplify:*"]
    resources = ["arn:${data.aws_partition.current.partition}:amplify:*:${data.aws_caller_identity.current.account_id}:apps/*"]
  }

  # api.tf's aws_dynamodb_table.audit_state needs the CI role to be able to
  # create/manage the table itself -- separate from aws_iam_role_policy.audit_state
  # in api.tf, which grants the Lambda's own execution role read/write on
  # table *items* at request time. Table-lifecycle actions have no
  # fine-grained resource condition beyond the ARN, same reason Lambda above
  # is scoped by name prefix rather than to individual functions.
  statement {
    sid = "DynamoDb"
    actions = [
      "dynamodb:CreateTable", "dynamodb:DeleteTable", "dynamodb:DescribeTable",
      "dynamodb:UpdateTable", "dynamodb:TagResource", "dynamodb:UntagResource",
      "dynamodb:ListTagsOfResource",
      # Not optional, and not obvious from the resource block: the provider
      # reads a table's TTL and continuous-backups state on *every* refresh,
      # even though api.tf configures neither. CloudTrail for the apply that
      # created this table shows the CI role calling DescribeTimeToLive and
      # DescribeContinuousBackups; without them the next plan fails with
      # AccessDenied on a table that already exists. The Update* pair is here
      # so that turning on a TTL later -- an open question in the decision
      # log -- does not need another bootstrap round trip.
      "dynamodb:DescribeTimeToLive", "dynamodb:UpdateTimeToLive",
      "dynamodb:DescribeContinuousBackups", "dynamodb:UpdateContinuousBackups",
    ]
    resources = ["arn:${data.aws_partition.current.partition}:dynamodb:*:${data.aws_caller_identity.current.account_id}:table/${var.project}-*"]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy", "logs:TagResource", "logs:UntagResource",
      "logs:ListTagsForResource",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project}-*",
      "arn:${data.aws_partition.current.partition}:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/aws/apigateway/${var.project}-*",
    ]
  }

  # DescribeLogGroups has no resource-level permission; Terraform calls it to
  # read the state of a managed group.
  statement {
    sid       = "LogsDescribe"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "${var.project}-github-actions"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions.json
}
