import json
import json as json_module
import threading

import pytest
import requests

from squint.core.classify import (
    MAX_CANDIDATES,
    MAX_CONTEXT_CHARS,
    OLLAMA_URL,
    PREFIX,
    SUFFIX,
    TIMEOUT_SECONDS,
    VERDICT_SCHEMA,
    WARM_UP_TIMEOUT_SECONDS,
    OllamaClassifier,
    build_prime_request,
    build_request,
    parse_verdict,
)
from squint.core.types import Candidate


def cand(id, value="FAKE-secret-value", context="TOKEN=FAKE-secret-value"):
    return Candidate(id=id, rule="assignment", value=value, context=context)


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"status {self.status}")

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeSession:
    """Answers via reply(candidate_id, or "prime" for prefix requests) -> FakeResponse | Exception."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self.lock = threading.Lock()

    def post(self, url, json, timeout):
        with self.lock:
            self.calls.append((url, json, timeout))
        prompt = json["prompt"]
        if prompt == PREFIX:
            result = self.reply("prime")
        else:
            result = self.reply(
                json_module.loads(prompt[len(PREFIX) : -len(SUFFIX)])["id"]
            )
        if isinstance(result, Exception):
            raise result
        return result


def answer(verdicts):
    def reply(cid):
        if cid == "prime":
            return FakeResponse({"response": "x"})
        return FakeResponse({"response": json.dumps({"sensitive": verdicts[cid]})})

    return reply


def test_build_request_constrains_output_to_one_required_boolean():
    req = build_request(cand(7))
    assert req["format"] == VERDICT_SCHEMA
    assert VERDICT_SCHEMA["required"] == ["sensitive"]
    assert req["options"]["temperature"] == 0
    assert req["stream"] is False


def test_build_request_shares_exact_prefix_in_raw_mode():
    req = build_request(cand(7))
    assert req["raw"] is True
    assert req["prompt"].startswith(PREFIX)
    assert req["prompt"].endswith(SUFFIX)


def test_build_prime_request_is_prefix_only():
    req = build_prime_request()
    assert req["prompt"] == PREFIX
    assert req["raw"] is True
    assert req["options"]["num_predict"] == 1


def test_build_request_includes_candidate_and_truncates_context():
    req = build_request(cand(1, context="x" * 500))
    item = json.loads(req["prompt"][len(PREFIX) : -len(SUFFIX)])
    assert item["value"] == "FAKE-secret-value"
    assert item["rule"] == "assignment"
    assert len(item["context"]) == MAX_CONTEXT_CHARS


def test_build_request_uses_given_model():
    assert build_request(cand(1), model="gemma3:1b")["model"] == "gemma3:1b"


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"sensitive": false}', False),
        ('{"sensitive": true}', True),
        ("not json", True),
        ('{"other": false}', True),
        ('{"sensitive": "false"}', True),
        ("[]", True),
        ("", True),
    ],
)
def test_parse_verdict_fails_safe(text, expected):
    assert parse_verdict(text) is expected


def test_url_is_loopback_only():
    assert OLLAMA_URL.startswith("http://127.0.0.1:")


def test_judge_returns_model_verdict():
    session = FakeSession(answer({1: False}))
    assert OllamaClassifier(session).judge(cand(1)) is False
    assert session.calls[0][0] == OLLAMA_URL


def test_judge_returns_none_when_unreachable():
    session = FakeSession(lambda cid: requests.ConnectionError("refused"))
    assert OllamaClassifier(session).judge(cand(1)) is None


def test_judge_returns_none_on_http_error():
    session = FakeSession(lambda cid: FakeResponse({}, status=500))
    assert OllamaClassifier(session).judge(cand(1)) is None


def test_judge_returns_none_on_non_json_body():
    session = FakeSession(lambda cid: FakeResponse(ValueError("bad json")))
    assert OllamaClassifier(session).judge(cand(1)) is None


def test_judge_all_maps_verdicts_by_id():
    session = FakeSession(answer({1: True, 2: False, 3: False}))
    result = OllamaClassifier(session).judge_all([cand(1), cand(2), cand(3)])
    assert result.sensitive == {1: True, 2: False, 3: False}
    assert result.classifier_offline is False


def test_judge_all_flags_overflow_without_asking():
    n = MAX_CANDIDATES + 2
    session = FakeSession(answer({i: False for i in range(n)}))
    result = OllamaClassifier(session).judge_all([cand(i) for i in range(n)])
    assert len(session.calls) == MAX_CANDIDATES
    assert all(result.sensitive[i] is False for i in range(MAX_CANDIDATES))
    assert all(result.sensitive[i] is True for i in range(MAX_CANDIDATES, n))


def test_judge_all_flags_everything_and_reports_offline_when_server_down():
    session = FakeSession(lambda cid: requests.ConnectionError("refused"))
    result = OllamaClassifier(session).judge_all([cand(1), cand(2)])
    assert result.sensitive == {1: True, 2: True}
    assert result.classifier_offline is True


def test_judge_all_with_no_candidates_makes_no_calls():
    session = FakeSession(answer({}))
    result = OllamaClassifier(session).judge_all([])
    assert result.sensitive == {}
    assert session.calls == []


def test_warm_up_reports_reachability():
    assert OllamaClassifier(FakeSession(answer({0: False}))).warm_up() is True
    down = FakeSession(lambda cid: requests.ConnectionError("refused"))
    assert OllamaClassifier(down).warm_up() is False


def test_warm_up_primes_every_parallel_slot_with_long_timeout():
    session = FakeSession(answer({0: False, 1: False}))
    classifier = OllamaClassifier(session)
    classifier.warm_up()
    assert len(session.calls) == 1 + MAX_CANDIDATES
    assert all(timeout == WARM_UP_TIMEOUT_SECONDS for _, _, timeout in session.calls)
    assert all(body["prompt"] == PREFIX for _, body, _ in session.calls)
    classifier.judge(cand(1))
    assert session.calls[-1][2] == TIMEOUT_SECONDS


def test_warm_up_skips_slot_priming_when_server_down():
    session = FakeSession(lambda cid: requests.ConnectionError("refused"))
    assert OllamaClassifier(session).warm_up() is False
    assert len(session.calls) == 1
