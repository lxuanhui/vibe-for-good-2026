"""AWS Lambda entrypoint for the Flask API.

The same `create_app()` factory backs both the local dev server (`wsgi.py`,
port 5001) and Lambda, so there is exactly one app definition. `apig-wsgi`
translates API Gateway HTTP API (payload format 2.0) events into WSGI calls
and the WSGI response back into an API Gateway response.

Deployed by infra/ -- see infra/README.md. The handler is referenced there as
`lambda_handler.handler`.

This module exports a second entrypoint, `analysis_worker`, for the Lambda
that runs Investigator/Skeptic analysis past API Gateway's 30s response cap.
Both functions are deployed from this one artifact so the API and the worker
cannot drift apart -- the worker is not a separate service, only a second
door into the same code with a longer timeout.
"""

import logging

from apig_wsgi import make_lambda_handler

from app import analysis_jobs, create_app

# The runtime attaches its CloudWatch handler to the root logger but leaves
# the level at WARNING, so an INFO record from `app.*` is dropped before it
# reaches the handler. The one INFO record that matters is the per-call
# Bedrock usage line in `analysis_provider` (cache read/write tokens), which
# is how the cost figure in docs/infra.md gets measured rather than
# estimated. Scoped to this package, not the root, so boto3 and urllib3 stay
# quiet.
logging.getLogger("app").setLevel(logging.INFO)

# Built once per cold start and reused across invocations in the same
# execution environment.
app = create_app()

# binary_support lets the API return gzip/binary payloads (base64-encoded by
# apig-wsgi) rather than mangling them as UTF-8 text.
handler = make_lambda_handler(app, binary_support=True)


def analysis_worker(event, context):
    """Run one analysis job asynchronously and record the outcome.

    Invoked with InvocationType='Event' by the API function, so there is no
    caller to return to and no HTTP status to carry: `analysis_jobs.run`
    writes COMPLETE or FAILED to the job row, and the console reads it back
    through GET /api/audits/{id}/events/{id}/analyse.
    """
    audit_id = event.get("auditId")
    event_id = event.get("eventId")
    if not audit_id or not event_id:
        # Raising is right here: Lambda records the failure and the payload,
        # and there is no job row to mark failed -- nothing valid was named.
        raise ValueError("analysis worker payload requires auditId and eventId")
    return analysis_jobs.run(audit_id, event_id)
