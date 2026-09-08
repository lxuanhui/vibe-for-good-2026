"""AWS Lambda entrypoint for the Flask API.

The same `create_app()` factory backs both the local dev server (`wsgi.py`,
port 5001) and Lambda, so there is exactly one app definition. `apig-wsgi`
translates API Gateway HTTP API (payload format 2.0) events into WSGI calls
and the WSGI response back into an API Gateway response.

Deployed by infra/ -- see infra/README.md. The handler is referenced there as
`lambda_handler.handler`.
"""

from apig_wsgi import make_lambda_handler

from app import create_app

# Built once per cold start and reused across invocations in the same
# execution environment.
app = create_app()

# binary_support lets the API return gzip/binary payloads (base64-encoded by
# apig-wsgi) rather than mangling them as UTF-8 text.
handler = make_lambda_handler(app, binary_support=True)
