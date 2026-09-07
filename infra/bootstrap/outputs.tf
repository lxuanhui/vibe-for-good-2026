output "state_bucket" {
  description = "Bucket holding the main stack's state. Must match the backend block in ../versions.tf."
  value       = aws_s3_bucket.state.id
}

output "github_actions_role_arn" {
  description = "Set this as the AWS_ROLE_ARN repository variable in GitHub -- the infra workflow assumes it."
  value       = aws_iam_role.github_actions.arn
}
