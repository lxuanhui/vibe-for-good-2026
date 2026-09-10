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

If the input ends with previous_reply_rejected, a reply to this exact input was
rejected for the reason it states. Correct that and return the complete
assessment, every hypothesis included.

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


# --- Prompt caching (#147) ---------------------------------------------------
#
# All four provider calls in one assessment (two roles, two rounds) share the
# system framing, the evidence pack, its ID list and the hypotheses: ~19k of
# the ~19.5k input tokens each call sends. Bedrock bills a cached prefix at
# $0.10/1M against $1.00/1M fresh, so the shared part is sent as its own text
# block followed by a cache point, and only the per-call tail (role, round,
# phase, prior and opponent assessments) is fresh input.
#
# The split must not change what the model reads. `AgentInput.to_dict()`
# serializes the shared fields first (#245), and the two blocks below are the
# one JSON document `_prompt` builds, cut just before the first per-call key:
# block one ends after the hypotheses, block two starts with `,"role":`.
# Joined, they are byte-for-byte the uncached string. A test pins that.
#
# Two facts about the arithmetic, so nobody re-derives them:
# - Both roles in a round run in parallel (investigator_skeptic.py), and a
#   cache entry is readable only once the response that wrote it has begun,
#   so the two round-1 calls both write and the two round-2 calls both read.
#   Per assessment that is two writes at 1.25x and two reads at 0.1x rather
#   than one write and three reads: roughly $0.13 instead of $0.15, with the
#   ~3.5k output tokens per call now the larger share. Sequential round 1
#   would reach ~$0.10 for ~9s more wall time on a job the auditor already
#   waits ~51s for. Not taken; see the decision log.
# - Haiku 4.5's minimum cacheable prefix is 4,096 tokens. A sparse pack
#   under that is ignored by Bedrock without an error and bills as before.
#
# BEDROCK_PROMPT_CACHE=0 sends the same text as one block with no cache
# point. It exists to measure before and after on the same pack, and as the
# switch if a model or region turns out not to accept cache points; a
# ValidationException naming the cache point is also retried once without it,
# so a provider that rejects it degrades to today's cost, not to a failure.
_CACHE_POINT = {"cachePoint": {"type": "default"}}


def _prompt_cache_enabled() -> bool:
    return os.environ.get("BEDROCK_PROMPT_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def _prompt_blocks(agent_input: AgentInput) -> tuple[str, str]:
    """The serialized input cut at the first per-call key: (shared, per_call).

    `shared + per_call` is exactly the string `_prompt` builds. The cut is
    found by serializing the shared fields alone and dropping their closing
    brace, so it cannot land inside an evidence value that happens to contain
    a key called "role". If the serialization ever stops matching, the whole
    text is returned as the shared part with an empty tail and no cache point
    is sent, which is today's behaviour rather than a wrong prompt.
    """
    text = _prompt(agent_input)
    payload = agent_input.to_dict()
    shared = json.dumps(
        {key: payload[key] for key in AgentInput.SHARED_FIELDS}, separators=(",", ":"), default=str
    )
    head = _PROMPT + shared[:-1]
    if not text.startswith(head) or not text[len(head):].startswith(',"'):
        return text, ""
    return head, text[len(head):]


def _message_content(agent_input: AgentInput) -> list[dict[str, Any]]:
    if not _prompt_cache_enabled():
        return [{"text": _prompt(agent_input)}]
    shared, per_call = _prompt_blocks(agent_input)
    if not per_call:
        return [{"text": shared}]
    return [{"text": shared}, dict(_CACHE_POINT), {"text": per_call}]


def _without_cache_point(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"text": "".join(block.get("text", "") for block in content if "text" in block)}]


def _rejects_cache_point(exc: Exception) -> bool:
    error = getattr(exc, "response", {}).get("Error", {}) if hasattr(exc, "response") else {}
    return error.get("Code") == "ValidationException" and "cache" in str(error.get("Message", "")).lower()


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

    def converse(content: list[dict[str, Any]]) -> Mapping[str, Any]:
        return _bedrock_client().converse(
            modelId=model_id,
            messages=[{"role": "user", "content": content}],
            # 2200 truncated a real four-hypothesis pack mid-array
            # (stopReason max_tokens), which surfaced only as a JSON parse
            # error. A full assessment measures ~3.5k output tokens.
            inferenceConfig={"maxTokens": 6000, "temperature": 0},
        )

    content = _message_content(agent_input)
    try:
        try:
            response = converse(content)
        except ClientError as exc:
            if len(content) == 1 or not _rejects_cache_point(exc):
                raise
            # Same text, one block, no cache point: the cost of before #147,
            # not a failed assessment the auditor pays to retry.
            logger.warning(
                "Bedrock rejected the prompt cache point for model %s; retrying uncached", model_id
            )
            content = _without_cache_point(content)
            response = converse(content)
    except (BotoCoreError, ClientError) as exc:
        # The caller gets a deliberately generic message, but discarding the
        # cause entirely made a 503 unreadable in CloudWatch: a missing model
        # entitlement, a throttle and an IAM denial all looked identical.
        logger.exception("Bedrock Converse failed for model %s", model_id)
        raise AnalysisProviderUnavailable("Bedrock could not generate investigation analysis.") from exc
    # The only place the cache's effect is observable. Read and write token
    # counts are what turn the cost estimate in docs/infra.md into a measured
    # figure; both are absent from the response when nothing was cached.
    usage = response.get("usage", {}) or {}
    logger.info(
        "Bedrock usage model=%s role=%s round=%s cached=%s input=%s output=%s cache_read=%s cache_write=%s",
        model_id,
        agent_input.role.value,
        agent_input.round_number,
        len(content) > 1,
        usage.get("inputTokens"),
        usage.get("outputTokens"),
        usage.get("cacheReadInputTokens"),
        usage.get("cacheWriteInputTokens"),
    )
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
