"""Amazon Bedrock adapter for bounded Investigator/Skeptic analysis.

The pipeline owns the schema and evidence validation.  This module only turns
an ``AgentInput`` into one concise JSON assessment from Claude; it neither
inventories evidence nor exposes a transcript to callers.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from data_pipeline.analysis.investigator_skeptic import AgentInput

# A cross-region inference profile avoids pinning the Lambda to a model's
# home region. Operators can replace it with an approved model/profile ARN.
DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-5"


class AnalysisProviderUnavailable(RuntimeError):
    """Raised when a real provider cannot be used for an explicit request."""


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


def bedrock_runner(agent_input: AgentInput) -> Mapping[str, Any]:
    """Invoke Claude through Bedrock using Lambda's IAM role, not an API key."""

    try:
        import boto3  # Lambda supplies boto3; local installs need it only to invoke analysis.
        from botocore.exceptions import BotoCoreError, ClientError
    except ModuleNotFoundError as exc:
        raise AnalysisProviderUnavailable("Bedrock support is unavailable in this local Python environment.") from exc
    try:
        response = boto3.client("bedrock-runtime").converse(
            modelId=os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
            messages=[{"role": "user", "content": [{"text": _prompt(agent_input)}]}],
            inferenceConfig={"maxTokens": 2200, "temperature": 0},
        )
    except (BotoCoreError, ClientError) as exc:
        raise AnalysisProviderUnavailable("Bedrock could not generate investigation analysis.") from exc
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    text = "".join(block.get("text", "") for block in blocks if isinstance(block, dict))
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnalysisProviderUnavailable("Bedrock returned invalid structured output.") from exc
    if not isinstance(parsed, Mapping):
        raise AnalysisProviderUnavailable("Bedrock returned an invalid assessment shape.")
    return parsed
