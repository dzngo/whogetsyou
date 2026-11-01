"""THROWAWAY: launch Phoenix and emit one Question Bank batch trace."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
WORKING_DIR = ROOT / "storage" / "phoenix_prototype"
os.environ.setdefault("PHOENIX_WORKING_DIR", str(WORKING_DIR))

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from phoenix.otel import register


ENDPOINT = "http://127.0.0.1:6006/v1/traces"
PROJECT = "question-bank-observability-prototype"
UI = "http://127.0.0.1:6006"


def ensure_server():
    try:
        urlopen(UI, timeout=1).close()
        return
    except Exception:
        pass
    binary = ROOT / ".phoenix-prototype-venv" / "bin" / "phoenix"
    WORKING_DIR.mkdir(parents=True, exist_ok=True)
    log = (WORKING_DIR / "server.log").open("ab")
    env = {**os.environ, "PHOENIX_PORT": "6006", "PHOENIX_GRPC_PORT": "4319"}
    subprocess.Popen([str(binary), "serve"], cwd=ROOT, env=env,
                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(60):
        try:
            urlopen(UI, timeout=1).close()
            return
        except Exception:
            time.sleep(.5)
    raise RuntimeError(f"Phoenix did not start; inspect {WORKING_DIR / 'server.log'}")


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def record(tracer, name, *, provider, model, prompt, output=None, error=None,
           thinking="medium", input_tokens=0, output_tokens=0, cost=0.0,
           fallback_attempt=0):
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("openinference.span.kind", "LLM")
        span.set_attribute("input.value", packed(prompt))
        span.set_attribute("input.mime_type", "application/json")
        span.set_attribute("llm.provider", provider)
        span.set_attribute("llm.model_name", model)
        span.set_attribute("llm.token_count.prompt", input_tokens)
        span.set_attribute("llm.token_count.completion", output_tokens)
        span.set_attribute("llm.token_count.total", input_tokens + output_tokens)
        span.set_attribute("question_bank.thinking_level", thinking)
        span.set_attribute("question_bank.cost_usd", cost)
        span.set_attribute("question_bank.fallback_attempt", fallback_attempt)
        if error:
            span.set_attribute("output.value", packed({"error": error}))
            span.set_attribute("output.mime_type", "application/json")
            span.set_status(Status(StatusCode.ERROR, error))
        else:
            span.set_attribute("output.value", packed(output))
            span.set_attribute("output.mime_type", "application/json")
            span.set_status(Status(StatusCode.OK))


def main():
    ensure_server()
    provider = register(endpoint=ENDPOINT, project_name=PROJECT, protocol="http/protobuf",
                        batch=False, auto_instrument=False, verbose=False)
    tracer = trace.get_tracer("question-bank-observability-prototype")
    missions = [
        {"agent_slot": 0, "level": "shallow", "brief": "Everyday preferences"},
        {"agent_slot": 1, "level": "shallow", "brief": "Unexpected free time"},
        {"agent_slot": 2, "level": "shallow", "brief": "Small social situations"},
        {"agent_slot": 3, "level": "shallow", "brief": "Harmless habits"},
    ]
    with tracer.start_as_current_span("Campaign v21 prototype / Batch 0") as batch:
        batch.set_attribute("openinference.span.kind", "CHAIN")
        batch.set_attribute("question_bank.campaign_id", "phoenix-prototype")
        batch.set_attribute("question_bank.batch_index", 0)
        record(tracer, "Diversity / mission agent", provider="google", model="gemini-3.5-flash",
               thinking="high", input_tokens=920, output_tokens=180, cost=.003,
               prompt={"instructions": "Write four varied shallow creative missions.",
                       "input": {"recent_aspects": ["food", "weekends", "phone habits"]},
                       "output_schema": {"missions": "exactly four mission objects"},
                       "model_settings": {"thinking_level": "high"}},
               output={"missions": missions})
        questions = ["What snack do I reach for first?", "What would I do with a free afternoon?",
                     "How would I react if a friend arrived early?", "What do I check before leaving home?"]
        for slot, (mission, question) in enumerate(zip(missions, questions)):
            record(tracer, f"Creative agent {slot}", provider="google", model="gemini-3.5-flash",
                   thinking="high", input_tokens=640, output_tokens=95, cost=.002,
                   prompt={"instructions": "Generate five light, immediately answerable questions.",
                           "mission": mission, "input": {"level": "shallow"},
                           "output_schema": {"questions": "five strings"},
                           "model_settings": {"thinking_level": "high"}},
                   output={"questions": [question, "Example question 2?", "Example question 3?",
                                         "Example question 4?", "Example question 5?"]})
        record(tracer, "Quality agent", provider="openai", model="gpt-5.4-mini",
               input_tokens=1150, output_tokens=230, cost=.004,
               prompt={"instructions": "Evaluate clarity, answerability, safety, and shallow level fit.",
                       "input": {"questions": questions},
                       "output_schema": {"records": "one quality record per question"},
                       "model_settings": {"reasoning_effort": "medium"}},
               output={"records": [{"question": q, "verdict": "pass"} for q in questions]})
        record(tracer, "Semantic agent / chunk 1", provider="openai", model="gpt-5.4-mini",
               thinking="high", input_tokens=1360, output_tokens=310, cost=.006,
               prompt={"instructions": "Determine whether each pair is a semantic repeat.",
                       "input": {"pairs": [{"candidate": questions[1],
                                             "neighbor": "What do I usually do on a free Sunday?"}]},
                       "output_schema": {"pairs": "scenario, perspective, answer space, verdict"},
                       "model_settings": {"reasoning_effort": "high"}},
               output={"pairs": [{"scenario": "different", "perspective": "overlapping",
                                   "answer_space": "overlapping", "verdict": "distinct"}]})
        record(tracer, "Metadata agent", provider="openai", model="gpt-5.4-mini",
               input_tokens=870, output_tokens=190, cost=.003,
               prompt={"instructions": "Assign zero or more named themes and descriptive metadata.",
                       "input": {"questions": questions},
                       "output_schema": {"records": "themes, aspect, perspective, scenario"},
                       "model_settings": {"reasoning_effort": "medium"}},
               output={"records": [{"question": q, "themes": ["Yourself"],
                                     "aspect": "everyday behavior"} for q in questions]})
        record(tracer, "Creative fallback example", provider="google", model="gemini-3.5-flash",
               thinking="high", fallback_attempt=0,
               prompt={"instructions": "Generate five questions.", "input": missions[0]},
               error="503 UNAVAILABLE: model experiencing high demand")
        record(tracer, "Creative fallback example / retry", provider="google", model="gemini-3-flash",
               thinking="high", fallback_attempt=1, input_tokens=640, output_tokens=90, cost=.001,
               prompt={"instructions": "Generate five questions.", "input": missions[0]},
               output={"questions": ["What is my favorite drink?"]})
    provider.force_flush()
    provider.shutdown()
    print(f"Prototype trace sent. Open {UI}/projects and choose {PROJECT}")


if __name__ == "__main__":
    main()
