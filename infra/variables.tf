variable "aws_region" {
  description = "AWS region to deploy into. ap-southeast-1 (Singapore) is closest to the Indonesian data and users this tool serves."
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Name prefix applied to every resource."
  type        = string
  default     = "vibe-for-good-2026"
}

variable "environment" {
  description = "Deployment environment, used in resource names and tags."
  type        = string
  default     = "dev"
}

variable "lambda_memory_mb" {
  description = "Lambda memory. CPU scales with memory on Lambda, so this is the main latency dial; 512 MB keeps Flask cold starts around a second."
  type        = number
  default     = 512
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout. API Gateway HTTP API caps a response at 30s regardless, so going above that only burns billed time on requests the client has already given up on."
  type        = number
  default     = 29
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention. Without this, log groups default to never expiring and bill forever."
  type        = number
  default     = 14
}

variable "cors_origins" {
  description = "Value for the app's CORS_ORIGINS env var -- the origin the deployed frontend is served from. CORS is handled inside Flask (flask-cors), not by API Gateway, so this is the single place it is configured."
  type        = string
  default     = "*"
}

variable "flask_secret_key" {
  description = "Flask SECRET_KEY. NOTE: whatever is passed here is stored in plain text in Terraform state -- fine for a hackathon dev stack, but move it to AWS Secrets Manager (and read it at runtime) before anything real depends on it."
  type        = string
  default     = "dev"
  sensitive   = true
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID or inference-profile ID used by the structured investigation-analysis provider."
  type        = string
  default     = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}
