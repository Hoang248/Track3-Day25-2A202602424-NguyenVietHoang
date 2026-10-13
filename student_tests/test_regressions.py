"""Additional boundary checks; original assignment tests stay untouched."""

from dataclasses import replace

import pytest

from gameday_lab.cache import SemanticCache
from gameday_lab.client import ResilientClient
from gameday_lab.sim.contracts import Answer, Attempt, CallContext, GiveUp, ProviderError, ProviderInfo, Request, Send
from gameday_lab.workflows.executor import WorkflowExecutor, checkpoint_key, idempotency_key
from gameday_lab.workflows.runner import RefundRequest
from gameday_lab.workflows.services import DurableStore, FaultProfile, ServiceError, Services


def limited_client(**settings):
    provider = ProviderInfo("single", "family", "us", True, 1.0)
    return ResilientClient({"single": provider}, ["single"], settings)


def rate_limit(client, call, action, now):
    return client.on_error(Attempt(call, action.provider, 1, 0.0, action.tag),
                           ProviderError("single", 429, "rate_limit_exceeded", retry_after=1.0), now)


def test_all_rate_limited_wait_honors_header_and_deadline():
    client = limited_client()
    call = CallContext(1, 1, "tool", 0.0, 30.0)
    first = client.start(call, 0.0)
    action = rate_limit(client, call, first, 0.1)
    assert isinstance(action, Send)
    assert action.delay_s >= 1.0
    assert 0.1 + action.delay_s + action.timeout_s <= call.deadline


@pytest.mark.parametrize("settings", [
    {"retry_budget_ratio": 0, "retry_budget_min_per_s": 0, "retry_budget_max_tokens": 0},
    {"max_attempts_per_provider": 1},
])
def test_short_wait_cannot_bypass_retry_budget_or_attempt_limit(settings):
    client = limited_client(**settings)
    call = CallContext(1, 1, "tool", 0.0, 30.0)
    first = client.start(call, 0.0)
    assert isinstance(rate_limit(client, call, first, 0.1), GiveUp)


def test_quota_cooldown_is_never_used_as_short_wait():
    client = limited_client(quota_cooldown_s=2.0)
    call = CallContext(1, 1, "tool", 0.0, 30.0)
    first = client.start(call, 0.0)
    action = client.on_error(Attempt(call, "single", 1, 0.0, first.tag),
                             ProviderError("single", 429, "insufficient_quota"), 0.1)
    assert isinstance(action, GiveUp)


def test_revisiting_ladder_cannot_reset_exhausted_provider_attempts():
    providers = {name: ProviderInfo(name, "family", "us", True, 1.0) for name in ["single", "fallback"]}
    client = ResilientClient(providers, list(providers), {"max_attempts_per_provider": 2})
    call = CallContext(1, 1, "tool", 0.0, 30.0)
    first = client.start(call, 0.0)
    fallback = rate_limit(client, call, first, 0.1)
    assert isinstance(fallback, Send) and fallback.provider == "fallback"
    error = ProviderError("fallback", 500, "api_error")
    second = client.on_error(Attempt(call, "fallback", 2, 0.1, fallback.tag), error, 0.2)
    assert isinstance(second, Send) and second.provider == "fallback"
    revisit = client.on_error(Attempt(call, "fallback", 3, 0.2, second.tag), error, 0.3)
    assert isinstance(revisit, Send) and revisit.provider == "single"
    assert isinstance(rate_limit(client, call, revisit, 1.2), GiveUp)
    assert call.state["provider_tries"] == {"single": 2, "fallback": 2}


def test_cache_rejects_answer_from_different_prompt_scope():
    cache = SemanticCache()
    req = Request("faq", "u", False, "v2", (1.0, 0.0))
    cache.store(req, Answer(1, "v1", ("policy",), 0), 0)
    assert cache.entries == []


def test_identity_keys_have_no_delimiter_collision():
    req = RefundRequest("session:issue", "order", 100, "a@example.com")
    other = replace(req, session_id="session")
    assert idempotency_key(req, "refund") != idempotency_key(other, "issue:refund")


def test_failed_step_is_not_checkpointed():
    services = Services.build(1, FaultProfile(0, 0, 0))
    services.payments.faults = FaultProfile(1, 0, 0)
    store = DurableStore()
    req = RefundRequest("s", "o", 100, "a@example.com")
    with pytest.raises(ServiceError):
        WorkflowExecutor(services, store, max_attempts=2).run(req)
    assert store.get(checkpoint_key(req, "classify_request")) is not None
    assert store.get(checkpoint_key(req, "issue_refund")) is None
    assert services.payments.ledger == []
