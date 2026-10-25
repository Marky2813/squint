"""Judge ambiguous candidates with a local Gemma model served by Ollama.

Gemma only answers "is this candidate sensitive?". It never sees files or locates text.
Any failure (timeout, server down, malformed reply) counts as sensitive.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

from squint.core.types import Candidate

# Locked to loopback so a misconfigured environment can never send secrets off-machine.
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "gemma3:4b"
MAX_CANDIDATES = 4
MAX_CONTEXT_CHARS = 200
TIMEOUT_SECONDS = 10.0
# A cold model load takes ~5 s on its own.
WARM_UP_TIMEOUT_SECONDS = 60.0

INSTRUCTIONS = (
    "You judge whether text found in a screenshot is sensitive to share publicly. "
    "Sensitive: real-looking passwords, tokens, API keys, and private people's emails or phone numbers. "
    "Not sensitive: placeholders, defaults like 'changeme', commit hashes, UUIDs, image digests, dates, "
    "no-reply or generic support addresses. "
    "Output an object mapping 'c<id>' to true if sensitive, false if not.\n\n"
    "Examples:\n"
    '{"rule":"assignment","value":"password123","context":"# example: password=password123"} -> false\n'
    '{"rule":"assignment","value":"Kx9#mPq2-FAKE","context":"REDIS_PASSWORD=Kx9#mPq2-FAKE"} -> true\n'
    '{"rule":"high_entropy","value":"a94a8fe5ccb19ba61c4c0873d391e987982fbbd3",'
    '"context":"Merge commit a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"} -> false\n'
    '{"rule":"high_entropy","value":"6ba7b810-9dad-11d1-80b4-00c04fd430c8",'
    '"context":"trace=6ba7b810-9dad-11d1-80b4-00c04fd430c8"} -> false\n'
    '{"rule":"high_entropy","value":"Qm4Lx8Rt2Vn6Bz0Kp3Wd7Hs9","context":"STRIPE_SECRET=Qm4Lx8Rt2Vn6Bz0Kp3Wd7Hs9"} -> true\n'
    '{"rule":"assignment","value":"<TOKEN>","context":"token: <TOKEN>"} -> false\n'
    '{"rule":"email","value":"bob.smith.fake@yahoo.com","context":"email bob.smith.fake@yahoo.com"} -> true\n'
    '{"rule":"email","value":"no-reply@service.io","context":"Sent by no-reply@service.io"} -> false\n\n'
    "Candidate:\n"
)


@dataclass(frozen=True)
class Verdicts:
    sensitive: dict[int, bool]
    classifier_offline: bool


def build_request(candidate: Candidate, model: str = DEFAULT_MODEL) -> dict:
    key = f"c{candidate.id}"
    item = {
        "id": candidate.id,
        "rule": candidate.rule,
        "value": candidate.value,
        "context": candidate.context[:MAX_CONTEXT_CHARS],
    }
    return {
        "model": model,
        "prompt": INSTRUCTIONS + json.dumps(item),
        "stream": False,
        "keep_alive": "30m",
        "format": {
            "type": "object",
            "properties": {key: {"type": "boolean"}},
            "required": [key],
        },
        "options": {"temperature": 0, "num_predict": 20},
    }


def parse_verdict(candidate_id: int, response_text: str) -> bool:
    """Return Gemma's verdict, or True (sensitive) if the reply is unusable."""
    try:
        value = json.loads(response_text)[f"c{candidate_id}"]
    except (ValueError, KeyError, TypeError):
        return True
    return value if isinstance(value, bool) else True


class OllamaClassifier:
    def __init__(
        self, session: requests.Session | None = None, model: str = DEFAULT_MODEL
    ):
        self.session = session or requests.Session()
        self.model = model

    def judge(
        self, candidate: Candidate, timeout: float = TIMEOUT_SECONDS
    ) -> bool | None:
        """Return the verdict, or None if Ollama could not be reached."""
        try:
            resp = self.session.post(
                OLLAMA_URL,
                json=build_request(candidate, self.model),
                timeout=timeout,
            )
            resp.raise_for_status()
            return parse_verdict(candidate.id, resp.json().get("response", ""))
        except (requests.RequestException, ValueError):
            return None

    def judge_all(self, candidates: list[Candidate]) -> Verdicts:
        asked = candidates[:MAX_CANDIDATES]
        sensitive = {c.id: True for c in candidates[MAX_CANDIDATES:]}
        offline = False
        if asked:
            with ThreadPoolExecutor(len(asked)) as pool:
                results = list(pool.map(self.judge, asked))
            for candidate, verdict in zip(asked, results):
                if verdict is None:
                    offline = True
                sensitive[candidate.id] = True if verdict is None else verdict
        return Verdicts(sensitive=sensitive, classifier_offline=offline)

    def warm_up(self) -> bool:
        """Load the model, then prime every parallel slot so the first screenshot isn't slow."""
        probe = Candidate(id=0, rule="warmup", value="x", context="x")
        if self.judge(probe, timeout=WARM_UP_TIMEOUT_SECONDS) is None:
            return False
        with ThreadPoolExecutor(MAX_CANDIDATES) as pool:
            results = list(
                pool.map(
                    lambda _: self.judge(probe, timeout=WARM_UP_TIMEOUT_SECONDS),
                    range(MAX_CANDIDATES),
                )
            )
        return all(r is not None for r in results)
