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

from data_pipeline.analysis.investigator_skeptic import (
    QUESTION_WORD_CAP,
    REASON_WORD_CAP,
    SUMMARY_WORD_CAP,
    AgentInput,
)

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


# The writing rules exist because the schema alone produced findings an
# auditor would not sign: measured on the real demo pack before them,
# summaries averaged 30 words (18 of 24 over the cap) and stacked three or
# four figures per sentence. A second model to rewrite the prose was rejected
# (#199, decision log 2026-09-10): it adds latency to a job already near a
# minute, and its output would bypass the evidence-ID validation the first
# model's went through. The caps are the pipeline's, so the number the model
# is told is the number the validator measures.
_PROMPT = f"""You are one role in a bounded environmental FireEvent assessment.
Return JSON only. Do not include analysis, a transcript, markdown, or facts
outside the supplied evidence. Do not infer company identity, intent, blame,
guilt, legality, responsibility, or causation.

For every supplied hypothesis, return exactly one finding with:
- hypothesis_id
- support_score: integer 0..100 (relative support, not probability)
- evidence_sufficiency: SUFFICIENT, PARTIAL, or INSUFFICIENT
- supporting_evidence_ids and contradicting_evidence_ids, using only supplied
  IDs. Every finding cites at least one ID in one of the two lists. A
  hypothesis nothing supports still cites, as contradicting, the evidence that
  fails to support it. A finding with both lists empty is rejected.
- summary: at most {SUMMARY_WORD_CAP} words, in one or two sentences
- verification_questions: at most two objects with question (at most
  {QUESTION_WORD_CAP} words), evidence_ids, and reason (at most
  {REASON_WORD_CAP} words). Include one only where the answer would change
  the support_score.

Return one to three targeted unresolved_questions across the assessment, each
an object with question, evidence_ids and reason. Every verification_question
and every unresolved_question names at least one supplied ID in evidence_ids:
the evidence the question is about. A question with empty evidence_ids is
rejected and fails the whole assessment. Keep disagreement unresolved when the
evidence does not decide between explanations.
Evidence sufficiency is separate from hypothesis support. Peat, weather, and
surface-propagation context can inform persistence or compatibility but never
establish cause.

Writing rules. The reader is an environmental auditor who signs what they act
on, so write as they would:
- Say what was measured, then what it is consistent with, in that order.
- Plain words, short clauses, at most one figure per clause. Write "no mapped
  peat within 3 km", not "0.0% peat overlap with nearest peat at 3.28 km".
- Keep evidence IDs out of the summary sentence itself; the ID lists and
  evidence_ids fields carry them, and those are required.
- No em-dashes. Use a full stop, comma or colon.
- Do not use: notably, crucially, it is important to note, underscores,
  highlights, robust, nuanced, leverage, delve.
- "Consistent with", "estimated" and "inferred" are the right words. Never
  "confirmed", "proves", "caused" or "responsible".

Input follows.
"""


def _prompt(agent_input: AgentInput) -> str:
    return _PROMPT + json.dumps(agent_input.to_dict(), separators=(",", ":"), default=str)


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
