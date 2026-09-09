# The Flask API, packaged as a single Lambda behind an API Gateway HTTP API.
#
# Every /api/* route is proxied to one function rather than split across
# per-route Lambdas: the app is one Flask blueprint, splitting it would mean
# N cold starts instead of one, and routing already exists inside Flask.
#
# There is one exception, and it is not a route split: `analysis_worker` runs
# Investigator/Skeptic analysis, which measures ~51s and therefore cannot be
# delivered inside API Gateway's 30s response cap at all. Both functions are
# the same zip with a different handler -- so they cannot drift apart -- and a
# second function rather than one longer timeout on `api` is deliberate: a
# stuck synchronous request would otherwise bill the worker's whole budget
# for a response the client stopped waiting for at 30s.

locals {
  name = "${var.project}-${var.environment}"

  # Built by scripts/build_lambda.sh -- dependencies vendored next to the
  # backend source. Terraform zips it rather than the script, so the
  # source_code_hash below tracks content and redeploys only on real changes.
  lambda_build_dir = "${path.module}/build/lambda"
}

data "archive_file" "api" {
  type        = "zip"
  source_dir  = local.lambda_build_dir
  output_path = "${path.module}/build/api.zip"
}

# --- Execution role -------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# Grants only CreateLogGroup/CreateLogStream/PutLogEvents. Anything the API
# later needs (S3, DynamoDB, Secrets Manager) gets its own scoped policy
# attached here rather than widening this one.
resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Audit ids are followed by later register, graph, evidence, and pack calls.
# Process-local dictionaries therefore fail whenever Lambda serves those calls
# from a different warm container.  This small table persists only anonymous
# audit scope/session state; the regional FIRMS artifact remains packaged and
# immutable. No TTL is configured yet -- rows are few and small, and an expiry
# policy wants a decision about how long an audit session may be resumed,
# which is not settled (see docs/decision-log.md, 2026-09-09).
resource "aws_dynamodb_table" "audit_state" {
  name         = "${local.name}-audit-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "audit_id"

  attribute {
    name = "audit_id"
    type = "S"
  }
}

data "aws_iam_policy_document" "audit_state" {
  statement {
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [aws_dynamodb_table.audit_state.arn]
  }
}

resource "aws_iam_role_policy" "audit_state" {
  name   = "${local.name}-audit-state"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.audit_state.json
}

# Bedrock Converse authorizes against bedrock:InvokeModel. The model/profile
# is a Terraform variable because availability differs by account and region;
# this role receives no other Bedrock permissions.
data "aws_iam_policy_document" "bedrock_inference" {
  statement {
    actions   = ["bedrock:InvokeModel"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "bedrock_inference" {
  name   = "${local.name}-bedrock-inference"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.bedrock_inference.json
}

# Scoped to the worker function alone -- the API may hand off analysis and
# nothing else. Analysis is the one thing this account's Lambda is allowed to
# invoke on its own behalf.
data "aws_iam_policy_document" "invoke_analysis_worker" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.analysis_worker.arn]
  }
}

resource "aws_iam_role_policy" "invoke_analysis_worker" {
  name   = "${local.name}-invoke-analysis-worker"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.invoke_analysis_worker.json
}

# Declared explicitly so retention is enforced and the group is destroyed
# with the stack. Lambda would otherwise create it on first invocation with
# never-expire retention, outliving `terraform destroy`.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = var.log_retention_days
}

# --- Function -------------------------------------------------------------

resource "aws_lambda_function" "api" {
  function_name = "${local.name}-api"
  role          = aws_iam_role.api.arn

  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256

  runtime = "python3.13"
  handler = "lambda_handler.handler"

  # arm64 (Graviton) is cheaper per GB-second than x86_64 and every
  # dependency here is pure Python -- see scripts/build_lambda.sh.
  architectures = ["arm64"]

  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_seconds

  environment {
    variables = {
      SECRET_KEY        = var.flask_secret_key
      CORS_ORIGINS      = var.cors_origins
      AUDIT_STATE_TABLE = aws_dynamodb_table.audit_state.name
      BEDROCK_MODEL_ID  = var.bedrock_model_id

      # Unset locally, which is what makes `analysis_jobs.dispatch` run the
      # work inline for the dev server instead of reporting a job nothing
      # will ever pick up.
      ANALYSIS_WORKER_FUNCTION = aws_lambda_function.analysis_worker.function_name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.api_logs,
    aws_iam_role_policy.audit_state,
    aws_iam_role_policy.bedrock_inference,
    aws_iam_role_policy.invoke_analysis_worker,
    aws_cloudwatch_log_group.api,
  ]
}

# --- Analysis worker ------------------------------------------------------

# Same artifact, same role, different handler and timeout. The role is shared
# because both functions read the same table and call the same Bedrock model;
# the only grant the worker does not need is InvokeFunction, and holding it
# changes nothing because the worker never dispatches.
resource "aws_cloudwatch_log_group" "analysis_worker" {
  name              = "/aws/lambda/${local.name}-analysis-worker"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "analysis_worker" {
  function_name = "${local.name}-analysis-worker"
  role          = aws_iam_role.api.arn

  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256

  runtime = "python3.13"
  handler = "lambda_handler.analysis_worker"

  architectures = ["arm64"]

  memory_size = var.lambda_memory_mb
  timeout     = var.analysis_worker_timeout_seconds

  environment {
    variables = {
      SECRET_KEY        = var.flask_secret_key
      CORS_ORIGINS      = var.cors_origins
      AUDIT_STATE_TABLE = aws_dynamodb_table.audit_state.name
      BEDROCK_MODEL_ID  = var.bedrock_model_id
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.api_logs,
    aws_iam_role_policy.audit_state,
    aws_iam_role_policy.bedrock_inference,
    aws_cloudwatch_log_group.analysis_worker,
  ]
}

# Lambda retries a failed async invocation twice by default. For this
# function that means paying for the same two-round assessment three times
# over, and the job row already records the failure truthfully for the
# auditor to retry deliberately -- which is the only retry that should ever
# spend provider tokens.
resource "aws_lambda_function_event_invoke_config" "analysis_worker" {
  function_name          = aws_lambda_function.analysis_worker.function_name
  maximum_retry_attempts = 0
}

# --- HTTP API -------------------------------------------------------------

# No cors_configuration block on purpose: flask-cors already sets the CORS
# headers inside the app. Configuring it here too makes API Gateway append a
# second Access-Control-Allow-Origin, and browsers reject a response carrying
# two of them -- which looks exactly like CORS being "not configured".
resource "aws_apigatewayv2_api" "api" {
  name          = "${local.name}-api"
  protocol_type = "HTTP"
  description   = "Environmental Assurance Console API (Flask on Lambda)"
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

# One catch-all route -- Flask owns routing and 404s for unknown paths, so
# mirroring each blueprint route in Terraform would just be a second place to
# forget to update.
resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      httpMethod     = "$context.httpMethod"
      path           = "$context.path"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
      integrationErr = "$context.integrationErrorMessage"
      requestTime    = "$context.requestTime"
    })
  }
}

# Scoped to this API's ARN so no other API Gateway can invoke the function.
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
