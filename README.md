# Claude Code OpenAI API Wrapper

OpenAI API-compatible wrapper for Claude Code. Drop it in front of any OpenAI client library and talk to Claude instead.

## Features

- **Two API shapes.** OpenAI `/v1/chat/completions` and Anthropic `/v1/messages`, both with streaming.
- **JSON mode and function calling.** `response_format` with `json_object` or `json_schema`, plus `tools` and `tool_choice` simulated on top of Claude Code.
- **Sessions.** Pass a `session_id` to keep a conversation going; list and delete them under `/v1/sessions`.
- **Live model list.** `/v1/models` reads Anthropic's catalogue when an API key is set and falls back to a built-in list otherwise.
- **Quota reporting.** `/v1/usage` reports each Claude subscription window with its utilization and reset time. A 429 carries a `Retry-After` set to the real reset.
- **Retry, fallback and a circuit breaker.** Overloaded Opus requests fall back to Sonnet. Repeated upstream failures open a short-lived breaker instead of piling up.
- **Cost tracking and per-request controls.** Usage is priced per model, and `X-Claude-*` headers set effort, thinking, turns, tools and permission mode.
- **Auth options.** Claude CLI login, Anthropic API key, Bedrock or Vertex AI. Optional API key on the wrapper itself.
- **Tools are off by default** for speed. Send `enable_tools: true` to turn them on.

Release notes live in [CHANGELOG.md](./CHANGELOG.md) and on the GitHub releases page.

## Quick Start

```bash
# Clone and install
git clone https://github.com/ttlequals0/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install

# Authenticate (pick one)
export ANTHROPIC_API_KEY=your-api-key
# or: claude auth login

# Start
poetry run uvicorn src.main:app --reload --port 8000

# Test
poetry run pytest tests/
```

Server is at `http://localhost:8000`. Point your OpenAI client there.

## Prerequisites

1. **Python 3.10+**
2. **Poetry** for dependency management:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```
3. **Authentication** (pick one):
   - `export ANTHROPIC_API_KEY=your-api-key` (recommended)
   - `claude auth login` (CLI auth)
   - AWS Bedrock or Google Vertex AI (see Configuration)

The Claude Code CLI comes bundled with the SDK. No Node.js or npm needed.

## Installation

```bash
git clone https://github.com/ttlequals0/claude-code-openai-wrapper
cd claude-code-openai-wrapper
poetry install
cp .env.example .env  # edit with your preferences
```

## Configuration

Edit `.env`:

```env
# Auth (optional - auto-detects if not set)
# CLAUDE_AUTH_METHOD=cli|api_key|bedrock|vertex

# Optional client API key protection
# API_KEY=your-optional-api-key

PORT=8000
MAX_TIMEOUT=600000           # milliseconds (10 min default)
# CLAUDE_CWD=/path/to/workspace   # defaults to isolated temp dir
# DEFAULT_MODEL=claude-sonnet-5-5   # override default model
```

### Working Directory

By default, Claude Code runs in an isolated temporary directory so it can't access the wrapper's own source. Set `CLAUDE_CWD` to point it at a specific project instead.

### API Key Protection

If no `API_KEY` is set, the server prompts on startup whether to generate one. Useful for remote access over VPN or Tailscale.

### Rate Limiting

Per-IP rate limiting is on by default. Per-endpoint defaults and the env vars that override them:

| Endpoint group | Default | Env var |
|----------------|---------|---------|
| `/v1/chat/completions`, `/v1/messages` | 120/min | `RATE_LIMIT_CHAT_PER_MINUTE` |
| `/v1/debug/request` | 2/min | `RATE_LIMIT_DEBUG_PER_MINUTE` |
| `/v1/auth/status` | 10/min | `RATE_LIMIT_AUTH_PER_MINUTE` |
| `/v1/sessions/*` | 15/min | `RATE_LIMIT_SESSION_PER_MINUTE` |
| `/health`, `/healthz/deep` | 30/min | `RATE_LIMIT_HEALTH_PER_MINUTE` |
| everything else | 30/min | `RATE_LIMIT_PER_MINUTE` |

Disable entirely with `RATE_LIMIT_ENABLED=false`.

## Running the Server

```bash
# Development (auto-reload)
poetry run uvicorn src.main:app --reload --port 8000

# Production
poetry run claude-wrapper
```

## Docker

Pre-built image on Docker Hub: `ttlequals0/claude-code-openai-wrapper`.

```bash
# Pull and run
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  --name claude-wrapper \
  ttlequals0/claude-code-openai-wrapper:latest

# Pin to a specific version
docker run -d -p 8000:8000 \
  -v ~/.claude:/root/.claude \
  --name claude-wrapper \
  ttlequals0/claude-code-openai-wrapper:2.13.2

# Or build locally (prod stage is the default target)
docker build --platform linux/amd64 -t claude-wrapper:local .
```

Docker Compose (matches `docker-compose.yml` in the repo):

```yaml
version: '3.8'
services:
  claude-wrapper:
    image: ttlequals0/claude-code-openai-wrapper:latest
    pull_policy: always   # redeploy webhooks re-pull :latest
    build:
      context: .
      target: prod
    container_name: claude-wrapper
    ports:
      - "8000:8000"
    volumes:
      - ~/.claude:/root/.claude
    environment:
      - PORT=8000
      - MAX_TIMEOUT=600000
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### Environment variables

Listed in roughly the order you will reach for them.

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `CLAUDE_WRAPPER_HOST` | Bind address (`127.0.0.1` for local-only, `0.0.0.0` for all) | `0.0.0.0` |
| `MAX_TIMEOUT` | Per-request timeout (ms) | `600000` (10 min) |
| `MAX_REQUEST_SIZE` | Max request body size (bytes) | `10485760` (10 MB) |
| `CLAUDE_CWD` | Working directory Claude Code runs in | isolated temp dir |
| `CLAUDE_AUTH_METHOD` | `cli`, `api_key`, `bedrock`, `vertex` | auto-detect |
| `API_KEY` | Require this key on every request; prompts at startup if unset | interactive prompt |
| `CLAUDE_CODE_OAUTH_TOKEN` | Subscription OAuth token, read by the bundled Claude CLI (not the wrapper). Alternative to `ANTHROPIC_API_KEY` for `cli` auth. | - |
| `ANTHROPIC_API_KEY` | Direct API key (for `api_key` auth). Optional; also unlocks live `/v1/models` discovery and dynamic latest-Sonnet default. | - |
| `CLAUDE_CODE_USE_BEDROCK` | Enable AWS Bedrock backend | `false` |
| `AWS_REGION` / `AWS_DEFAULT_REGION` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Bedrock credentials | - |
| `CLAUDE_CODE_USE_VERTEX` | Enable Google Vertex AI backend | `false` |
| `ANTHROPIC_VERTEX_PROJECT_ID` / `CLOUD_ML_REGION` / `GOOGLE_APPLICATION_CREDENTIALS` | Vertex credentials | - |
| `DEFAULT_MODEL` | Default model id when request omits one. When unset and `ANTHROPIC_API_KEY` is configured, the wrapper resolves the latest Sonnet at startup; otherwise falls back to `claude-sonnet-5-5`. | auto |
| `FAST_MODEL` | Speed/cost-optimized model alias used internally. | `claude-haiku-5-5` |
| `CLAUDE_MODELS_OVERRIDE` | Comma-separated model IDs to advertise via `/v1/models`. Takes precedence over both live and static lists. | - |
| `MODEL_LIST_CACHE_TTL_SECONDS` | Cache TTL for live `/v1/models` results. | `3600` |
| `MODEL_LIST_ERROR_TTL_SECONDS` | Short cache TTL applied when the live fetch fails so transient outages don't suppress live discovery for the full hour. | `60` |
| `MODEL_LIST_REQUEST_TIMEOUT_SECONDS` | HTTP timeout for the live model fetch (seconds). | `5` |
| `ANTHROPIC_MODELS_URL` | Override the live models endpoint. Point at a proxy or staging URL during testing. | `https://api.anthropic.com/v1/models` |
| `ANTHROPIC_VERSION` | `anthropic-version` header sent to the Models API. | `2023-06-01` |
| `ANTHROPIC_BETA` / `ANTHROPIC_BETA_HEADER` | Optional `anthropic-beta` header forwarded to the Models API for beta-gated features. | - |
| `CLI_AUTH_PROBE_INTERVAL_SECONDS` | Background CLI-auth probe cadence when `CLAUDE_AUTH_METHOD=cli` (also accepts `claude_cli`). Each probe is a 1-turn `query` (~$0.001 at Sonnet pricing). Only a failure classified `auth_failure` flips `cli_health.ok` and returns 401; `quota_exhausted` and `unknown` fall through to the SDK. Set `0` to disable. Ignored for non-cli auth methods. | `600` (10 min) |
| `WRAPPER_QUOTA_ENFORCEMENT_ENABLED` | Refuse requests with 429 while a quota window is `rejected`, rather than forwarding a call that cannot succeed. Off by default, since refusing changes behaviour for existing callers. | `false` |
| `WRAPPER_QUOTA_PROBE_EVERY_N_REQUESTS` | Requests between quota refresh probes. The bundled CLI has no `usage` subcommand, so a probe is a real 1-turn call that spends the quota it measures. Set `0` to rely on live traffic alone. | `100` |
| `WRAPPER_QUOTA_PROBE_MIN_INTERVAL_SECONDS` | Floor between quota probes so a burst cannot trigger a run of them. | `300` (5 min) |
| `WRAPPER_QUOTA_STALE_AFTER_SECONDS` | Age at which a `/v1/usage` window reading is flagged `stale`. | `900` (15 min) |
| `DEBUG_MODE` | Enable debug logging and unlock `/v1/debug/request` | `false` |
| `VERBOSE` | Same unlock effect on `/v1/debug/request` | `false` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON array) | `["*"]` |
| `REQUEST_CACHE_ENABLED` | Enable request-dedup cache | `false` |
| `REQUEST_CACHE_TTL_SECONDS` | Cache entry TTL | `60` seconds |
| `REQUEST_CACHE_MAX_SIZE` | Max cached entries | `100` |
| `WRAPPER_CIRCUIT_BREAKER_ENABLED` | Enable the upstream failure circuit breaker | `true` |
| `WRAPPER_CIRCUIT_BREAKER_WINDOW_SECONDS` | Failure-rate measurement window | `60` seconds |
| `WRAPPER_CIRCUIT_BREAKER_THRESHOLD` | Failure ratio that opens the breaker | `0.75` |
| `WRAPPER_CIRCUIT_BREAKER_MIN_REQUESTS` | Minimum requests before the breaker can open | `20` |
| `WRAPPER_CIRCUIT_BREAKER_OPEN_SECONDS` | Time before the breaker allows a probe request | `30` seconds |
| `WRAPPER_DEFAULT_MAX_TURNS` | Default `max_turns` when caller does not enable tools | `3` |
| `WRAPPER_MAP_MAX_TOKENS_TO_THINKING` | Map OpenAI `max_tokens` to Claude `max_thinking_tokens` (legacy) | `false` |
| `WATCHDOG_ENABLED` | Enable CPU watchdog (for Docker) | `false` |
| `WATCHDOG_CPU_THRESHOLD` / `WATCHDOG_INTERVAL` / `WATCHDOG_STRIKES` | Watchdog tuning | see `src/cpu_watchdog.py` |
| `UVICORN_WORKERS` | Worker count for the prod image. Default 1: the quota tracker and circuit breaker are in-process state, split across workers above 1. Request handling is async around the SDK subprocess, so one worker still serves concurrent requests. | `1` |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_*_PER_MINUTE` | See rate-limit section above | - |

## Usage Examples

### curl

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [
      {"role": "user", "content": "What is 2 + 2?"}
    ]
  }'

# With API key protection (when enabled)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-generated-api-key" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [
      {"role": "user", "content": "Write a Python hello world script"}
    ],
    "stream": true
  }'

```

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-api-key-if-required"
)

# Basic completion
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What files are in the current directory?"}
    ]
)
print(response.choices[0].message.content)

# With tools enabled
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[
        {"role": "user", "content": "What files are in the current directory?"}
    ],
    extra_body={"enable_tools": True}
)

# Streaming
stream = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Claude-specific headers

Claude-specific options via HTTP headers:

| Header | Values | Description |
|--------|--------|-------------|
| `X-Claude-Max-Turns` | integer | Max conversation turns |
| `X-Claude-Allowed-Tools` | comma-separated | Tools to allow |
| `X-Claude-Permission-Mode` | `default`, `acceptEdits`, `bypassPermissions`, `plan` | Permission mode |
| `X-Claude-Effort` | `low`, `medium`, `high`, `max` | Model effort level |
| `X-Claude-Thinking` | `adaptive`, `enabled`, `disabled` | Extended thinking mode |
| `X-Claude-Max-Thinking-Tokens` | integer | Thinking token budget |
| `X-Enable-Cache` | `true` / `1` / `yes` | Opt in to response cache on this request |

## Supported Models

Model IDs, context windows, and pricing are sourced from the Anthropic models docs (`platform.claude.com/docs/en/models/overview`, pricing page) and mirrored in `src/constants.py`.

With `ANTHROPIC_API_KEY` set, `/v1/models` returns Anthropic's live catalogue (cached for `MODEL_LIST_CACHE_TTL_SECONDS`, default 1 hour) and the wrapper picks the latest Sonnet as `DEFAULT_MODEL` at startup. Without it (Bedrock, Vertex, or Claude CLI auth), the static list below is served and `claude-sonnet-5-5` is the fallback. `CLAUDE_MODELS_OVERRIDE=a,b,c` pins the list regardless of auth.

### Latest
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-fable-5-1` | 1M | 128K | $10 | $50 |
| `claude-opus-5-5` | 1M | 128K | $4 | $20 |
| `claude-sonnet-5-5` (static fallback) | 1M | 128K | $2 | $10 |
| `claude-haiku-5-5` | 1M | 128K | $0.10 | $0.50 |

Cache reads are 0.1x input except Fable 5.1 (0.025x, $0.25/MTok), Opus 5.5 (0.05x, $0.20/MTok), and Sonnet 5.5 (0.05x, $0.10/MTok). Haiku 5.5 prompts over 100K tokens bill at 5x the listed rate ($0.50/$2.50, cache read $0.05, cache write $0.625); the cost tracker uses the base tier.

### Legacy (active, consider migrating)
| Model | Context | Max Output | Input $/MTok | Output $/MTok |
|-------|---------|-----------|-------------|--------------|
| `claude-fable-5` | 1M | 128K | $10 | $50 |
| `claude-opus-5` | 1M | 128K | $5 | $25 |
| `claude-opus-4-8` | 1M | 128K | $5 | $25 |
| `claude-opus-4-7` | 1M | 128K | $5 | $25 |
| `claude-opus-4-6` | 1M | 128K | $5 | $25 |
| `claude-sonnet-5` | 1M | 128K | $2 | $10 |
| `claude-sonnet-4-6` | 1M | 64K | $3 | $15 |
| `claude-opus-4-5-20251101` | 200K | 64K | $5 | $25 |
| `claude-sonnet-4-5-20250929` | 200K | 64K | $3 | $15 |
| `claude-haiku-4-5-20251001` | 200K | 64K | $1 | $5 |

**Note:** Claude 3.x models are not supported by the Claude Agent SDK. The three Claude 4-generation models the Anthropic Models API no longer serves (`claude-opus-4-1-20250805`, `claude-sonnet-4-20250514`, `claude-opus-4-20250514`) have been removed from this catalogue; they remain reachable only via Bedrock or Google Cloud, which this wrapper does not query for model discovery.

## Session Continuity

Pass a `session_id` to keep conversation context across requests:

```python
# Start a conversation
response1 = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "My name is Alice."}],
    extra_body={"session_id": "my-session"}
)

# Continue it - Claude remembers the context
response2 = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "What's my name?"}],
    extra_body={"session_id": "my-session"}
)
```

Sessions expire after 1 hour of inactivity. Management endpoints:
- `GET /v1/sessions` - list active sessions
- `GET /v1/sessions/{id}` - session details
- `DELETE /v1/sessions/{id}` - delete session
- `GET /v1/sessions/stats` - session statistics

See `examples/session_continuity.py` for Python and curl examples.

## API Endpoints

### Core API
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page with API explorer |
| `/v1/chat/completions` | POST | OpenAI-compatible chat |
| `/v1/messages` | POST | Anthropic-compatible messages |

### Models
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List available models |
| `/v1/models/status` | GET | Model service status |
| `/v1/models/refresh` | POST | Refresh model catalogue |

### Sessions
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/sessions` | GET | List active sessions |
| `/v1/sessions/stats` | GET | Session statistics |
| `/v1/sessions/{id}` | GET | Get session by ID |
| `/v1/sessions/{id}` | DELETE | Delete session |

### Tools
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/tools` | GET | List available tools |
| `/v1/tools/config` | GET | Get tool configuration |
| `/v1/tools/config` | POST | Update tool configuration |
| `/v1/tools/stats` | GET | Tool usage statistics |

### MCP Servers
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/mcp/servers` | GET | List MCP servers |
| `/v1/mcp/servers` | POST | Register MCP server |
| `/v1/mcp/connect` | POST | Connect to MCP server |
| `/v1/mcp/disconnect` | POST | Disconnect MCP server |
| `/v1/mcp/stats` | GET | MCP statistics |

### Cache / Auth / System
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/cache/stats` | GET | Cache statistics |
| `/v1/cache/clear` | POST | Clear request cache |
| `/v1/auth/status` | GET | Auth status, including `cli_health` and a `quota` summary |
| `/v1/usage` | GET | Claude subscription quota per rate-limit window: status, utilization, reset time, staleness |
| `/v1/compatibility` | POST | Parameter compatibility check |
| `/v1/debug/request` | POST | Request debugging; **emits only `{"enabled": false}` unless `DEBUG_MODE` or `VERBOSE` is set** |
| `/health` | GET | Liveness probe (no upstream call) |
| `/healthz/deep` | GET | Deep readiness probe (performs an SDK round-trip) |
| `/version` | GET | Wrapper version |

## Function Calling

Pass OpenAI-format tool definitions. The wrapper injects them into Claude's system prompt and parses structured responses back into `tool_calls` format.

```python
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "What's the weather in NYC?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }],
    tool_choice="auto",
)

# Response includes tool_calls when Claude decides to call a function
if response.choices[0].finish_reason == "tool_calls":
    for tc in response.choices[0].message.tool_calls:
        print(f"Call: {tc.function.name}({tc.function.arguments})")
```

Supports `tool_choice`: `"auto"` (default), `"required"`, `"none"`, or `{"type": "function", "function": {"name": "..."}}`.

Multi-turn tool conversations work - pass assistant messages with `tool_calls` and `tool` role result messages back. The wrapper converts them to text for Claude.

## JSON Response Mode

Set `response_format` to get JSON back:

```python
response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "List 3 colors with hex codes"}],
    response_format={"type": "json_object"}
)
```

With `json_object` mode, the wrapper adds system prompt instructions for JSON output, strips preambles like "Here is the JSON:", and uses brace-matching extraction as a fallback. Works streaming and non-streaming. JSON schema is also accepted via `response_format={"type": "json_schema", "json_schema": {...}}`.

In either JSON mode the wrapper moves your system prompt to the front of the user turn. The Claude Agent SDK treats its system prompt slot as a persona, not as binding instructions, so a schema left there gets ignored, with field names coming back renamed and required fields missing. Relocating the text fixes that. It is a move, not a copy, so your token count does not change. Plain text requests are not affected.

## Quota and Rate Limits

`GET /v1/usage` reports what the Claude CLI last said about your subscription
quota. Windows appear only once the CLI has reported them, so a wrapper that
has served no traffic returns an empty set rather than a guess.

```bash
curl -s http://localhost:8000/v1/usage
```

```json
{
  "blocked": false,
  "blocked_until": null,
  "blocked_until_iso": null,
  "seconds_until_reset": null,
  "binding_window": "five_hour",
  "closest_to_limit": {
    "window": "seven_day",
    "utilization": 0.05,
    "resets_at": 1788732000,
    "resets_at_iso": "2026-09-06T22:00:00+00:00",
    "seconds_until_reset": 599454
  },
  "windows": {
    "five_hour": {
      "status": "allowed",
      "utilization": 0.29,
      "resets_at": 1788145200,
      "resets_at_iso": "2026-08-31T03:00:00+00:00",
      "seconds_until_reset": 12654,
      "representative": true,
      "observed_at": "2026-08-30T23:29:05.694090+00:00",
      "source": "passive",
      "stale": false
    },
    "seven_day": {
      "status": null,
      "utilization": 0.05,
      "resets_at": 1788732000,
      "resets_at_iso": "2026-09-06T22:00:00+00:00",
      "seconds_until_reset": 599454,
      "representative": false,
      "observed_at": "2026-08-30T23:29:05.694090+00:00",
      "source": "passive",
      "stale": false
    }
  },
  "observed_windows": 2
}
```

`closest_to_limit` names the window nearest its cap. That is the one that will
cut you off, and it is not always the window the CLI reports as
`binding_window`, so check it first.

Window keys are `five_hour`, `seven_day`, `seven_day_opus`, `seven_day_sonnet`
and `overage`. `status` is `allowed`, `allowed_warning` (close to the limit) or
`rejected`, and is set only on the window flagged `representative`: the CLI
reports one status per event, and inferring a status for the others from their
utilization would be making it up. `source` is `passive` for a reading from
live traffic and `probe` for one from a refresh probe. `stale` marks a reading
older than `WRAPPER_QUOTA_STALE_AFTER_SECONDS`.

A `rejected` window stops reporting as rejected once it is no longer live: a
known reset time that has passed, or, when the CLI named no reset hour, after
`WRAPPER_QUOTA_STALE_AFTER_SECONDS` since it was observed. Otherwise a single
reset-less rejection would read as blocked forever.

A `rejected` overage pool usually means pay-as-you-go is switched off rather
than exhausted; check `disabled_reason` (for example `org_level_disabled`)
before treating it as a quota problem.

The data comes from the SDK's `RateLimitEvent`, which the CLI emits whenever
rate-limit state changes. No proxy in front of the API is needed. State is
per-process, so with `UVICORN_WORKERS` above 1 each worker reports what its own
traffic has taught it.

When the upstream rejects a request for quota, the wrapper returns 429 with a
`Retry-After` derived from the real reset time, capped at 3600 seconds so a
week-long window cannot tell a client to sleep for days. The exact reset is in
the body:

```json
{"error": {"type": "rate_limit_exceeded", "code": "upstream_quota_exhausted",
           "resets_at": 1788135731, "seconds_until_reset": 1799}}
```

Set `WRAPPER_QUOTA_ENFORCEMENT_ENABLED=true` to refuse requests before the
round-trip while a window is rejected, instead of forwarding a call that cannot
succeed.

## Limitations

- Images in messages are converted to text placeholders.
- `temperature` and `top_p` are applied via system-prompt instructions (best-effort approximation, not native SDK parameters).
- `presence_penalty` and `frequency_penalty` are accepted but ignored.
- Multiple responses (`n > 1`) are not supported.

## Testing

The suite covers API endpoints, authentication, models, sessions, streaming,
caching, quota tracking, and tool and function calling.

```bash
# Run the full test suite
poetry run pytest tests/

# Quick endpoint test (server must be running)
poetry run python tests/test_endpoints.py
```

## Terms

You need your own Claude subscription or API access. This wrapper translates request formats - it does not provide Claude access.

| Use Case | Recommended Auth |
|----------|------------------|
| Personal projects | CLI Auth or API Key |
| Business / commercial | API Key, Bedrock, or Vertex AI |
| High-scale | Bedrock or Vertex AI |

See [Anthropic's Terms of Service](https://www.anthropic.com/legal).

## License

MIT

## Contributing

PRs welcome.
