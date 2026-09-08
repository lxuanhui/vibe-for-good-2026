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

resource "aws_amplify_app" "console" {
  name = "${local.name}-console"

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
  }
}

# There is deliberately no aws_amplify_branch here. The console wizard that
# performs the GitHub App connection makes you pick a branch and creates it, so
# a Terraform branch resource would race it and then fail on a branch that
# already exists. Auto-build and pull-request previews are set in that same
# wizard. Losing them from code is the cost of the decision above; previews are
# still the reason Amplify was chosen over S3 + CloudFront, they are just
# configured once by a human rather than declared here.
