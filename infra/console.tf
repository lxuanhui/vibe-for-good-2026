# The React console, hosted on Amplify.
#
# Amplify rather than S3 + CloudFront (issue #91). Both serve from CloudFront,
# so what is delivered is identical; the difference is what has to be built and
# operated. Amplify carries the SPA rewrite, the managed certificate and the
# build, which here is ~40 lines against ~100 for a bucket, an origin access
# control, a distribution, custom error responses and an invalidation step in
# CI. The deciding factor was pull-request previews: branch-and-pr records that
# static checks cannot tell you the app runs -- a maplibre-gl major once passed
# every check and then rendered nothing -- and two people driving separate
# agents at the same frontend files need to see each other's branch.
#
# The cost is a second build system: npm run build runs here as well as in
# GitHub Actions. Accepted, because the preview URLs are the point.

# --- Service role ---------------------------------------------------------

# The connect-repository wizard asks for a service role and offers to create
# one. Letting it do so is the third instance of the same trap as
# _LIVE_UPDATES (#108) and AMPLIFY_MONOREPO_APP_ROOT (#110): the ARN lands on
# an attribute Terraform manages, so the next apply strips it. A
# wizard-created role is also named by the wizard, absent from this repository
# and left behind by `terraform destroy`, which docs/environments.md relies on
# for moving accounts.
#
# Strictly this app needs no service role -- it is a static SPA with no SSR and
# no backend, and Amplify uses the role for those. It is declared anyway
# because that is cheaper than re-deciding it every time the console asks.

data "aws_iam_policy_document" "amplify_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["amplify.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "console" {
  name               = "${local.name}-amplify-console"
  assume_role_policy = data.aws_iam_policy_document.amplify_assume_role.json
}

# The four permissions AWS documents for a self-created service role. Scoped to
# Amplify's own log groups; DescribeLogGroups takes no resource qualifier, so
# it is the one statement that has to be account-wide.
data "aws_iam_policy_document" "console_logs" {
  statement {
    sid     = "AmplifyLogStreams"
    actions = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:*:*:log-group:/aws/amplify/*",
      "arn:aws:logs:*:*:log-group:/aws/amplify/*:*",
    ]
  }

  statement {
    sid       = "AmplifyDescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "console_logs" {
  name   = "logs"
  role   = aws_iam_role.console.id
  policy = data.aws_iam_policy_document.console_logs.json
}

# --- App ------------------------------------------------------------------

resource "aws_amplify_app" "console" {
  name                 = "${local.name}-console"
  iam_service_role_arn = aws_iam_role.console.arn

  # No repository, no oauth_token, no access_token -- and the first two are a
  # consequence of the third. CreateApp answers a repository with no token
  # "You should at least provide one valid token" (issue #96); the API
  # reference is explicit that one of accessToken or oauthToken is required
  # when a new app names a repository. A PAT would satisfy it and would then
  # sit in Terraform state, which is the one credential this stack has avoided
  # everywhere else -- there are no AWS keys either, CI assumes a role over
  # OIDC. So Terraform creates the app and stops at the connection.
  #
  # The repository is attached once, by hand, through the Amplify GitHub App:
  # open the app in the console, connect lxuanhui/vibe-for-good-2026 on `main`,
  # and tick auto-build and pull-request previews there. Nothing builds until
  # that is done. docs/environments.md carries the walkthrough.
  #
  # ignore_changes then keeps Terraform from stripping what the wizard wrote
  # back onto the app on the next plan.
  lifecycle {
    ignore_changes = [repository, oauth_token, access_token]
  }

  # appRoot is what makes this work in a monorepo -- without it Amplify looks
  # for package.json at the repository root and fails before installing.
  build_spec = <<-YAML
    version: 1
    applications:
      - appRoot: frontend
        frontend:
          phases:
            preBuild:
              commands:
                - npm ci
            build:
              commands:
                - npm run build
          artifacts:
            baseDirectory: dist
            files:
              - '**/*'
          cache:
            paths:
              - node_modules/**/*
  YAML

  # The console is a single-page app: every route is served by index.html and
  # resolved client-side. 404-200 rewrites a miss instead of redirecting it, so
  # a deep link keeps its URL. The negative lookahead excludes real asset
  # extensions, otherwise a missing image would return the HTML document and
  # surface as a confusing parse error rather than a 404.
  custom_rule {
    source = "/<*>"
    target = "/index.html"
    status = "404-200"
  }

  environment_variables = {
    # Baked in at build time by Vite. trimsuffix matters: invoke_url ends with
    # a slash and the client appends "/api${path}", which would otherwise
    # produce a double slash.
    VITE_API_BASE_URL = trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")

    # The monorepo root, and the second setting the console stores as an
    # environment variable rather than as app state -- the connect-repository
    # wizard writes exactly this when you tell it the app lives in a
    # subdirectory. Terraform replaces this map wholesale, so a value typed
    # into the wizard would survive only until the next infra merge, and the
    # build would then fail looking for package.json at the repository root.
    #
    # It agrees with appRoot in the build spec above on purpose. Either
    # mechanism works alone; having both disagree is the failure worth
    # preventing, so they are set from the same literal and change together.
    AMPLIFY_MONOREPO_APP_ROOT = "frontend"

    # Amplify's "live package updates" -- the Build image settings panel in the
    # console writes exactly this variable, which is why the setting has to
    # live here: environment_variables is Terraform's, so a value set by hand
    # would be reverted on the next apply and the build would start failing
    # again with nothing in the repository to explain it.
    #
    # The default build image ships Node 18 and 20. This frontend is vite 8 and
    # typescript 7, which will not run on 18, and CI builds it on 24 -- an
    # Amplify build on a different major is the "passes in Actions, breaks in
    # hosting" gap that previews exist to catch, so both should be 24. Keep
    # this in step with node-version in .github/workflows/ci.yml.
    #
    # An exact version, not "latest": AWS documents that latest makes builds
    # fail.
    _LIVE_UPDATES = jsonencode([
      { name = "Node.js version", pkg = "node", type = "nvm", version = "24" }
    ])
  }
}

# There is deliberately no aws_amplify_branch here. The console wizard that
# performs the GitHub App connection makes you pick a branch and creates it, so
# a Terraform branch resource would race it and then fail on a branch that
# already exists. Auto-build and pull-request previews are set in that same
# wizard. Losing them from code is the cost of the decision above; previews are
# still the reason Amplify was chosen over S3 + CloudFront, they are just
# configured once by a human rather than declared here.
