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

variable "analysis_worker_timeout_seconds" {
  description = "Timeout for the analysis worker Lambda. It runs off the API Gateway request path, so the 30s response cap does not apply; a two-round Investigator/Skeptic assessment measures ~51s and this leaves room for a cold start and a slow provider without letting a wedged run bill for Lambda's full 900s ceiling."
  type        = number
  default     = 300
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

variable "nasa_firms_map_key" {
  description = "NASA FIRMS MAP_KEY. Used server-side by GET /api/firms/live so the landing map's live regional layer never ships the key to the browser -- a FIRMS key cannot be restricted to a domain, unlike the Carto key the console does publish. Empty leaves that route reporting the layer unavailable, which is the honest render rather than an empty region. NOTE: like flask_secret_key, whatever is passed here is stored in plain text in Terraform state -- acceptable for a free, re-issuable key on a dev stack, not for a credential with a real blast radius."
  type        = string
  default     = ""
  sensitive   = true
}

variable "carto_api_key" {
  description = "Carto API key for the basemap raster tiles. This one IS meant to reach the browser -- Vite bakes it into the bundle and Carto restricts it by origin -- so it is deliberately not marked sensitive: masking it in the plan would imply a secrecy it does not have, and it is readable in the published JS either way. It has to be declared here because environment_variables in console.tf is replaced wholesale on every apply, so a key typed into the Amplify console is deleted by the next infra merge. Empty falls back to unauthenticated tiles, which Carto rate-limits."
  type        = string
  default     = ""
}
