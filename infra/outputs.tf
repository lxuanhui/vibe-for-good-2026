output "api_base_url" {
  description = "Base URL of the deployed API. The Flask blueprint is mounted at /api, so health is <api_base_url>/api/health."
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_health_url" {
  description = "Convenience URL for a post-apply smoke test."
  value       = "${aws_apigatewayv2_stage.default.invoke_url}api/health"
}

output "lambda_function_name" {
  description = "Useful for `aws logs tail /aws/lambda/<name> --follow`."
  value       = aws_lambda_function.api.function_name
}

output "lambda_log_group" {
  description = "CloudWatch log group carrying the Flask application logs."
  value       = aws_cloudwatch_log_group.api.name
}

output "console_url" {
  description = "Live console. Set var.cors_origins to this (or the custom domain) to narrow the API's CORS from `*` once the final origin is fixed."
  value       = "https://${aws_amplify_branch.main.branch_name}.${aws_amplify_app.console.default_domain}"
}

output "console_app_id" {
  description = "Amplify app id -- needed to finish the one-time GitHub App connection in the console."
  value       = aws_amplify_app.console.id
}
