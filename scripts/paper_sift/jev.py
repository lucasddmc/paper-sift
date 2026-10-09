"""TypeSafe Jev client. paper-sift only asks Noul questions (probability that the answer is yes)."""
import time

from .net import request_json

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-1.13.0"
PRICE_PER_MTOK = 0.042  # USD per million input tokens, output free; published price, September 2026


def nouls(questions):
    """{name: {instructions, true, false, ...}} -> the API's question map."""
    return {name: {"type": "noul", "instructions": q["instructions"],
                   "criteria": {"true": q["true"], "false": q["false"]}}
            for name, q in questions.items()}


def ask(state, questions, *, key, model=DEFAULT_MODEL, transport=None, sleep=time.sleep, retries=8, timeout=60):
    """One call with every question (fan-out). Returns {"answers": {name: P(yes)}, "tokens", "model"}."""
    body = request_json("POST", ENDPOINT, headers={"Authorization": f"Bearer {key}"},
                        payload={"model": model, "state": state, "questions": nouls(questions)},
                        transport=transport, sleep=sleep, retries=retries, timeout=timeout)
    return {"answers": {name: float(body["answers"][name]["noul"]) for name in questions},
            "tokens": int((body.get("usage") or {}).get("input_tokens", 0)),
            "model": body.get("model") or model}


def check_key(key, *, model=DEFAULT_MODEL, transport=None, sleep=time.sleep):
    """The smallest useful call. Returns the model that answered; raises AuthError for a rejected key."""
    probe = {"probe": {"instructions": "Is `text` about the sky?", "true": "Yes", "false": "No"}}
    return ask({"text": "The sky is blue."}, probe, key=key, model=model, transport=transport, sleep=sleep,
               retries=2, timeout=30)["model"]


def cost(tokens):
    return tokens / 1_000_000 * PRICE_PER_MTOK
