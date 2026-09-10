# Gemini OpenAI Compatibility Thinking Level

Research date: 2026-08-25. Scope: Gemini API's OpenAI-compatible
`/v1beta/openai/chat/completions` endpoint. No live API calls were made.

## Conclusion

Yes. `gemini-3.7-flash` can use low thinking through this endpoint. The
preferred OpenAI-compatible request is `reasoning_effort="low"`; it does **not**
need `extra_body`.

Google's compatibility documentation shows this exact model and parameter, and
states that an omitted effort uses the model default. Gemini 3.7 Flash defaults
to `medium`; it supports `low`, `medium`, and `high` only. `minimal` returns an
error for this model.

Sources: [Google OpenAI compatibility: thinking](https://ai.google.dev/gemini-api/docs/openai#thinking),
[Gemini 3.7 Flash model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash).

## Recommended Python Syntax

This works with the application's structured-output call shape when the installed
OpenAI Python SDK supports `reasoning_effort` on `parse`:

```python
completion = client.beta.chat.completions.parse(
    model="gemini-3.7-flash",
    messages=messages,
    response_format=response_model,
    reasoning_effort="low",
)
```

The current locked `openai` version, 2.30.0, exposes both
`reasoning_effort` and `extra_body` on `chat.completions.parse`. The helper
converts the Pydantic response model to JSON Schema, sends it as
`response_format`, then parses the returned message.

Sources: [OpenAI Python 2.30.0 parser source](https://github.com/openai/openai-python/blob/v2.30.0/src/openai/resources/chat/completions/completions.py),
[Google OpenAI compatibility: structured output](https://ai.google.dev/gemini-api/docs/openai#structured-output).

## Gemini-Specific Alternative

Google also supports its native thinking configuration through the compatibility
endpoint. `extra_body` is required for this route, and the Python SDK value is
intentionally nested one level deeper:

```python
completion = client.beta.chat.completions.parse(
    model="gemini-3.7-flash",
    messages=messages,
    response_format=response_model,
    extra_body={
        "extra_body": {
            "google": {
                "thinking_config": {
                    "thinking_level": "low",
                },
            },
        },
    },
)
```

Why the apparent double `extra_body`:

- The outer `extra_body=` is an OpenAI Python SDK request option. The SDK merges
  its dictionary into the JSON request body.
- The inner `"extra_body"` is the property expected by Gemini's compatibility
  endpoint. The resulting HTTP JSON contains exactly one top-level
  `"extra_body"` property.

Do not set both `reasoning_effort` and the Gemini `thinking_level`/
`thinking_budget` configuration in one request. Google documents them as
overlapping controls that cannot be combined. `include_thoughts` is optional and
is not needed to reduce thinking latency.

Sources: [Google OpenAI compatibility: Gemini-specific thinking config](https://ai.google.dev/gemini-api/docs/openai#thinking),
[OpenAI Python request-body merge source](https://github.com/openai/openai-python/blob/v2.30.0/src/openai/_base_client.py).

## Structured-Output and Version Caveats

- Gemini officially documents `client.beta.chat.completions.parse(...)` with a
  Pydantic model and `gemini-3.7-flash`; structured output is supported by the
  model. The current application call shape is therefore supported by the
  compatibility endpoint.
- `reasoning_effort` is an SDK keyword, not a Gemini-specific passthrough.
  OpenAI Python 2.30.0 supports it on `parse`. The repository's lock file uses
  2.30.0, so the recommended syntax is available in its locked environment.
- The declared dependency floor is `openai>=1.51.0`. In the official 1.51.0
  source, `beta.chat.completions.parse` has `extra_body` but no
  `reasoning_effort` parameter. A fresh install that resolves that old version
  would reject the preferred syntax with `TypeError`.
- If preserving compatibility with the declared 1.51.0 minimum matters, use the
  nested Gemini-specific `extra_body` form. Otherwise, raise/pin the minimum SDK
  version to one that exposes `reasoning_effort` on `parse` (2.30.0 is verified
  here) and use the simpler direct form.
- The OpenAI parsing helper is client-side convenience around a Chat Completions
  request. It remains important to keep application-level validation of the
  parsed candidate set, as already done by the game service.

Sources: [Google structured-output example](https://ai.google.dev/gemini-api/docs/openai#structured-output),
[OpenAI Python 1.51.0 beta parser source](https://github.com/openai/openai-python/blob/v1.51.0/src/openai/resources/beta/chat/completions.py),
[OpenAI Python 2.30.0 parser source](https://github.com/openai/openai-python/blob/v2.30.0/src/openai/resources/chat/completions/completions.py).
