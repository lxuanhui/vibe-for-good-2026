"""Amazon Bedrock adapter for bounded Investigator/Skeptic analysis.

The pipeline owns the schema and evidence validation.  This module only turns
an ``AgentInput`` into one concise JSON assessment from Claude; it neither
inventories evidence nor exposes a transcript to callers.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from typing import Any

from data_pipeline.analysis.investigator_skeptic import AgentInput

logger = logging.getLogger(__name__)

# A cross-region inference profile avoids pinning the Lambda to a model's
# home region. Operators can replace it with an approved model/profile ARN.
#
# Haiku 4.5 rather than a larger model for two measured reasons, both from
# ap-southeast-1 on 2026-09-10: the Claude 5 family this previously named is
# not entitled for this account (Converse returns AccessDenied, "not available
# for this account"), and a two-round assessment must fit API Gateway's 30s
# response cap. Measured on a representative pack, Haiku 4.5 answers in ~8.8s
# against Sonnet 4.5's ~17s -- two parallel rounds of Haiku land near 18s,
# where Sonnet lands near 34s and cannot fit however the rounds are arranged.
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"

class AnalysisProviderUnavailable(RuntimeError):
    """Raised when a real provider cannot be used for an explicit request."""


# Clients are safe to share across threads once built, but building them
# concurrently is not; the two roles of a round now run in parallel.
_client_lock = threading.Lock()
_client = None


def _bedrock_client():
    global _client
    with _client_lock:
        if _client is None:
            try:
                import boto3  # Lambda supplies boto3; local installs need it only to invoke analysis.
            except ModuleNotFoundError as exc:
                raise AnalysisProviderUnavailable(
                    "Bedrock support is unavailable in this local Python environment."
                ) from exc
            _client = boto3.client("bedrock-runtime")
        return _client


def _prompt(agent_input: AgentInput) -> str:
    return """You are one role in a bounded environmental FireEvent assessment.
Return JSON only. Do not include analysis, a transcript, markdown, or facts
outside the supplied evidence. Do not infer company identity, intent, blame,
guilt, legality, responsibility, or causation.

For every supplied hypothesis, return exactly one finding with:
- hypothesis_id
- support_score: integer 0..100 (relative support, not probability)
- evidence_sufficiency: SUFFICIENT, PARTIAL, or INSUFFICIENT
- supporting_evidence_ids and contradicting_evidence_ids (only supplied IDs)
- summary: one concise evidence-grounded sentence
- verification_questions: zero or more objects with question, evidence_ids, reason

Return one to three targeted unresolved_questions across the assessment. Keep
disagreement unresolved when the evidence does not decide between explanations.
Evidence sufficiency is separate from hypothesis support. Peat, weather, and
surface-propagation context can inform persistence or compatibility but never
establish cause.

Input follows.\n""" + json.dumps(agent_input.to_dict(), separators=(",", ":"), default=str)


def _unfenced(text: str) -> str:
    """Strip a markdown code fence the model wraps JSON in despite the prompt.

    Asking for bare JSON is not reliable enough to depend on: Claude returns a
    ```json fence often enough that parsing without this fails intermittently,
    which is worse than failing always. Non-fenced text is returned untouched.
    """

    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    if body.lower().startswith("json"):
        body = body[4:]
    return body.rsplit("```", 1)[0].strip()


def bedrock_runner(agent_input: AgentInput) -> Mapping[str, Any]:
    """Invoke Claude through Bedrock using Lambda's IAM role, not an API key."""

    try:
        from botocore.exceptions import BotoCoreError, ClientError
    except ModuleNotFoundError as exc:
        raise AnalysisProviderUnavailable("Bedrock support is unavailable in this local Python environment.") from exc
    model_id = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)
    try:
        response = _bedrock_client().converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": _prompt(agent_input)}]}],
            # 2200 truncated a real four-hypothesis pack mid-array
            # (stopReason max_tokens), which surfaced only as a JSON parse
            # error. A full assessment measures ~3.5k output tokens.
            inferenceConfig={"maxTokens": 6000, "temperature": 0},
        )
    except (BotoCoreError, ClientError) as exc:
        # The caller gets a deliberately generic message, but discarding the
        # cause entirely made a 503 unreadable in CloudWatch: a missing model
        # entitlement, a throttle and an IAM denial all looked identical.
        logger.exception("Bedrock Converse failed for model %s", model_id)
        raise AnalysisProviderUnavailable("Bedrock could not generate investigation analysis.") from exc
    if response.get("stopReason") == "max_tokens":
        # Truncated output parses as invalid JSON, which reads like a model
        # fault rather than a budget one. Name the real cause.
        raise AnalysisProviderUnavailable("Bedrock response hit the output token limit before completing.")
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(block.get("text", "") for block in blocks if isinstance(block, dict))
    try:
        parsed = json.loads(_unfenced(text))
    except json.JSONDecodeError as exc:
        raise AnalysisProviderUnavailable("Bedrock returned invalid structured output.") from exc
    if not isinstance(parsed, Mapping):
        raise AnalysisProviderUnavailable("Bedrock returned an invalid assessment shape.")
    return parsed
