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
