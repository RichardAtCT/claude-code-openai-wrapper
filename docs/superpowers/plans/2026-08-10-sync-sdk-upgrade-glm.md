# Sync + SDK 0.2.134 Upgrade + GLM-5.2 Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the 2 missing upstream commits from `RichardAtCT`, upgrade `claude-agent-sdk` 0.1.18 → 0.2.134 with a hardened typed message parser, and enable `glm-5.2` as a passthrough model — all on branch `feat/sync-sdk-upgrade-glm`.

**Architecture:** Three sequential layers on one feature branch. (1) `git merge upstream/main` to bring in upstream's dynamic model-list code while preserving the fork's Gemini additions. (2) Bump the SDK dependency and replace the fragile `dir()`-walk message converter in `src/claude_cli.py` with typed `isinstance` dispatch against SDK 0.2.x message classes. (3) Advertise `glm-5.2` in `/v1/models` and confirm it routes through the existing Claude passthrough path.

**Tech Stack:** Python 3.10+, FastAPI, Poetry, `claude-agent-sdk` 0.2.134, pytest/pytest-asyncio, Claude Code CLI 2.1.226.

## Global Constraints

- **Do not** change the Claude Code CLI version. It stays at `2.1.226` (installed). No `npm install -g @anthropic-ai/claude-code` step.
- **Do not** build a direct GLM backend. GLM is served *through* Claude Code via the operator's `ANTHROPIC_BASE_URL` proxy. The wrapper only forwards the model name.
- **Do not** rebase or force-push. Sync via `git merge`. `main` is untouched until the final PR.
- SDK version pin after Task 2: `claude-agent-sdk = ">=0.2.134,<0.3"` in `pyproject.toml`.
- All work is on branch `feat/sync-sdk-upgrade-glm` (already created, currently holds only the spec commit).
- Conventional commit prefixes (`feat:`, `fix:`, `chore:`, `docs:`), matching the repo's history.
- Every task ends with `pytest` green before committing.

**Spec:** `docs/superpowers/specs/2026-08-10-sync-sdk-upgrade-glm-design.md`

---

## File Structure

| File | Responsibility | Touched by |
|---|---|---|
| `pyproject.toml` | Dependency pin for `claude-agent-sdk` | Task 2 |
| `src/claude_cli.py` | SDK query + message normalization; `_message_to_dict` parser | Task 3 |
| `src/constants.py` | Model lists (dynamic + static), `GLM_MODELS`, `PASSTHROUGH_MODELS` | Task 1 (merge), Task 4 |
| `src/main.py` | `/v1/models` endpoint + `_append_passthrough` + `get_cli_for_model` | Task 1 (merge), Task 4 |
| `src/models.py` | `to_claude_options()` model passthrough | Task 1 (merge, preserve) |
| `tests/test_message_parser_unit.py` | NEW — typed parser unit tests | Task 3 |
| `tests/test_glm_passthrough_unit.py` | NEW — GLM advertise + routing tests | Task 4 |
| `README.md`, `docs/UPGRADE_PLAN.md` | Version refs + GLM docs | Task 5 |

---

## Task 1: Merge `upstream/main` into the feature branch

**Files:**
- Modify (via merge resolution): `src/constants.py`, `src/main.py`, `src/models.py`, `README.md`, `src/__init__.py`, `pyproject.toml`, `.env.example`, `tests/test_sdk_migration.py`
- Add (from upstream): `tests/test_dynamic_models.py`

**Interfaces:**
- Consumes: current branch `feat/sync-sdk-upgrade-glm` (spec commit only).
- Produces: a merged tree where upstream's dynamic model-list code is present AND the fork's Gemini routing (`get_cli_for_model`), Anthropic Messages endpoint, and `to_claude_options()` model passthrough still work.

- [ ] **Step 1: Add the upstream remote and fetch**

```bash
git remote add upstream https://github.com/RichardAtCT/claude-code-openai-wrapper.git
git fetch upstream
git remote -v   # confirm: origin -> gustavokch, upstream -> RichardAtCT
```
Expected: `upstream` appears; fetch prints the 2 new commits (`ba9b039e`, `74951748`).

- [ ] **Step 2: Merge upstream/main**

```bash
git merge upstream/main --no-edit
```
Expected: merge reports conflicts in `src/constants.py` (and possibly `src/main.py`, `README.md`, `pyproject.toml`). The merge stops for manual resolution.

- [ ] **Step 3: Resolve `src/constants.py`**

Resolution policy — **take upstream's dynamic structure, re-add the fork's static additions**:
- Keep upstream's `DEFAULT_CLAUDE_MODELS`, the `CLAUDE_MODELS_OVERRIDE`/`CLAUDE_MODELS` block, `DEFAULT_MODEL_ENV`/`DEFAULT_MODEL_FALLBACK`/`DEFAULT_MODEL`/`RESOLVED_DEFAULT_MODEL`, `FAST_MODEL` env override, and the `ANTHROPIC_MODELS_URL`/`ANTHROPIC_VERSION`/`MODEL_LIST_*` config.
- **Re-add** the fork's `GEMINI_MODELS` list (upstream does not have it):
```python
# Gemini Models
# Models supported by Gemini CLI
GEMINI_MODELS = [
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "pro",        # Alias for gemini-3-pro-preview
    "flash",      # Alias for gemini-2.5-flash
    "flash-lite", # Alias for gemini-2.5-flash-lite
    "auto",       # Alias for gemini-3-pro-preview (recommended)
]
```
  Place it after the `CLAUDE_MODELS` block. (Do **not** add `GLM_MODELS` here — that is Task 4.)
- Verify the file imports cleanly: `python -c "import src.constants as c; print(c.CLAUDE_MODELS[:2], c.GEMINI_MODELS[:2])"`.

- [ ] **Step 4: Resolve `src/main.py`**

Resolution policy — **accept upstream's dynamic model-listing code; keep the fork's Gemini + Anthropic-Messages code**:
- Keep upstream's `_model_list_cache`, `_fetch_anthropic_models`, `get_available_models`, `_pick_latest_sonnet`, `_resolve_default_model_at_startup`, `_fallback_model_payload`, and the `@app.get("/v1/models")` → `list_models` endpoint.
- Keep the fork's `get_cli_for_model` (Gemini routing) and both API surface paths (OpenAI `/v1/chat/completions` + Anthropic `/v1/messages`).
- After resolving, confirm `get_cli_for_model` is intact:
```bash
python -c "from src.main import get_cli_for_model; print(get_cli_for_model('glm-5.2') is not None)"
```
Expected: `True`.

- [ ] **Step 5: Resolve `src/models.py`**

Resolution policy — **accept upstream's dynamic-list changes; preserve the fork's `to_claude_options()` model passthrough**. Confirm:
```bash
python -c "from src.models import ChatCompletionRequest; r=ChatCompletionRequest(messages=[{'role':'user','content':'hi'}], model='glm-5.2'); print(r.to_claude_options().get('model'))"
```
Expected: `glm-5.2`.

- [ ] **Step 6: Resolve remaining trivial conflicts**

- `pyproject.toml` — both sides are `version = "2.3.0"` and `claude-agent-sdk = "^0.1.18"`; keep either side (identical).
- `README.md`, `src/__init__.py`, `.env.example`, `tests/test_sdk_migration.py` — take upstream's version, re-apply any fork-specific wording (e.g. the fork's Gemini references in README).

- [ ] **Step 7: Stage and continue the merge**

```bash
git add -A
git status   # confirm "All conflicts fixed"
git merge --continue
```
Expected: merge commit created.

- [ ] **Step 8: Run the full test suite (gate)**

```bash
poetry install --sync   # ensure deps match merged pyproject
poetry run pytest -q
```
Expected: all tests pass, including upstream's new `tests/test_dynamic_models.py`. If a fork test fails because of the merge, fix the merge resolution (do not delete the test).

- [ ] **Step 9: Commit verification note (merge is already committed)**

```bash
git log --oneline -3
```
Expected: top commit is the merge. No extra commit needed; proceed to Task 2.

---

## Task 2: Bump `claude-agent-sdk` to 0.2.134

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: merged tree from Task 1.
- Produces: `claude-agent-sdk` 0.2.134 installed and importable (`query`, `ClaudeAgentOptions`, `AssistantMessage`, `ResultMessage`, `SystemMessage`, `TextBlock`).

- [ ] **Step 1: Update the dependency pin**

In `pyproject.toml`, change:
```toml
claude-agent-sdk = "^0.1.18"
```
to:
```toml
claude-agent-sdk = ">=0.2.134,<0.3"
```

- [ ] **Step 2: Lock and install**

```bash
poetry lock
poetry install --sync
```
Expected: lock updates; install completes.

- [ ] **Step 3: Verify the installed version and imports**

```bash
poetry show claude-agent-sdk | head -3
poetry run python -c "from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, SystemMessage, TextBlock; print('imports ok')"
```
Expected: version reports `0.2.134`; imports print `imports ok`.

- [ ] **Step 4: Run the suite, record any breakage**

```bash
poetry run pytest -q
```
Expected: most tests pass. If SDK message-shape drift breaks a test, note it — Task 3 fixes the parser. Do not patch ad-hoc here; capture the failure output for Task 3.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "chore: bump claude-agent-sdk 0.1.18 -> 0.2.134

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Harden the SDK message parser with typed `isinstance` dispatch

**Files:**
- Modify: `src/claude_cli.py` (imports line 10; the message loop at lines 152-176)
- Test: `tests/test_message_parser_unit.py` (NEW)

**Interfaces:**
- Consumes: SDK 0.2.134 classes `AssistantMessage`, `ResultMessage`, `SystemMessage`, `TextBlock`.
- Produces: module-level `_message_to_dict(message) -> Dict[str, Any]` that normalizes any SDK message into the dict shape consumed by `parse_claude_message()` and `extract_metadata()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_message_parser_unit.py`:
```python
"""Unit tests for the typed SDK message parser (_message_to_dict)."""

from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock

from src.claude_cli import _message_to_dict


def test_assistant_message_keeps_textblock_content():
    msg = AssistantMessage(content=[TextBlock(text="hello world")], model="glm-5.2")
    d = _message_to_dict(msg)
    assert d["type"] == "assistant"
    assert isinstance(d["content"], list)
    assert d["content"][0].text == "hello world"


def test_result_message_fields_preserved():
    msg = ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=2,
        session_id="sess-1",
        result="done",
        total_cost_usd=0.01,
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    d = _message_to_dict(msg)
    assert d["type"] == "result"
    assert d["subtype"] == "success"
    assert d["result"] == "done"
    assert d["session_id"] == "sess-1"
    assert d["total_cost_usd"] == 0.01
    assert d["num_turns"] == 2
    assert d["is_error"] is False
    assert d["stop_reason"] == "end_turn"


def test_system_message_init_data_preserved():
    msg = SystemMessage(
        subtype="init",
        data={"session_id": "sess-1", "model": "glm-5.2"},
    )
    d = _message_to_dict(msg)
    assert d["type"] == "system"
    assert d["subtype"] == "init"
    assert d["data"]["session_id"] == "sess-1"
    assert d["data"]["model"] == "glm-5.2"


def test_dict_passthrough_unchanged():
    original = {
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "error_message": "boom",
    }
    assert _message_to_dict(original) is original


def test_unknown_object_falls_back_to_attr_copy():
    class Unknown:
        type = "weird"
        foo = "bar"

    d = _message_to_dict(Unknown())
    assert d.get("foo") == "bar"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/test_message_parser_unit.py -q
```
Expected: FAIL — `ImportError: cannot import name '_message_to_dict' from 'src.claude_cli'`.

- [ ] **Step 3: Add the typed imports**

In `src/claude_cli.py`, replace line 10:
```python
from claude_agent_sdk import query, ClaudeAgentOptions
```
with:
```python
from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
)
```

- [ ] **Step 4: Add the `_message_to_dict` helper**

Add this module-level function immediately after the `logger = logging.getLogger(__name__)` line (after line 12), before `class ClaudeCodeCLI`:
```python
def _message_to_dict(message: Any) -> Dict[str, Any]:
    """Normalize an SDK message into the dict shape the downstream parser expects.

    Uses typed isinstance checks against the SDK 0.2.x message classes so a
    field rename does not silently break extraction. Dicts pass through
    unchanged (e.g. injected error results). Unknown message types fall back to
    copying public, non-callable attributes.
    """
    if isinstance(message, dict):
        return message

    if isinstance(message, ResultMessage):
        return {
            "type": "result",
            "subtype": message.subtype,
            "result": message.result,
            "total_cost_usd": message.total_cost_usd,
            "duration_ms": message.duration_ms,
            "num_turns": message.num_turns,
            "session_id": message.session_id,
            "usage": message.usage,
            "stop_reason": message.stop_reason,
            "is_error": message.is_error,
        }

    if isinstance(message, SystemMessage):
        return {
            "type": "system",
            "subtype": message.subtype,
            "data": message.data,
        }

    if isinstance(message, AssistantMessage):
        return {
            "type": "assistant",
            "content": list(message.content or []),
        }

    # Generic fallback for any other SDK message type (UserMessage, etc.).
    message_dict: Dict[str, Any] = {}
    for attr_name in dir(message):
        if attr_name.startswith("_"):
            continue
        try:
            value = getattr(message, attr_name)
        except Exception:
            continue
        if not callable(value):
            message_dict[attr_name] = value
    return message_dict or {"type": "unknown"}
```

- [ ] **Step 5: Replace the inline `dir()`-walk with the helper**

In `src/claude_cli.py`, inside `_run_completion_inner`, replace the message-conversion block (the `async for message in query(...)` body that currently does the `hasattr(message, "__dict__")` + `dir()` walk) with:
```python
            async with asyncio.timeout(self.timeout):
                async for message in query(prompt=prompt, options=options):
                    logger.debug(f"Raw SDK message type: {type(message)}")
                    logger.debug(f"Raw SDK message: {message}")
                    yield _message_to_dict(message)
```
Leave the surrounding `try/except` and the error-yield dict in the `except` block unchanged (it already yields a plain dict, which `_message_to_dict` passes through if ever routed through it).

- [ ] **Step 6: Run the parser tests — verify pass**

```bash
poetry run pytest tests/test_message_parser_unit.py -q
```
Expected: 5 passed.

- [ ] **Step 7: Run the full suite — verify no regression**

```bash
poetry run pytest -q
```
Expected: all green. Any test that broke under Task 2's SDK bump should now pass (the typed parser handles the 0.2.x message shapes).

- [ ] **Step 8: Commit**

```bash
git add src/claude_cli.py tests/test_message_parser_unit.py
git commit -m "refactor: harden SDK message parser with typed isinstance dispatch

Replace the dir()-walk object->dict conversion with explicit checks against
AssistantMessage/ResultMessage/SystemMessage so SDK 0.2.x field shapes are
handled reliably. Unknown types fall back to attribute copy.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: GLM-5.2 passthrough (advertise + verify routing)

**Files:**
- Modify: `src/constants.py` (add `GLM_MODELS`, `PASSTHROUGH_MODELS`)
- Modify: `src/main.py` (add `_append_passthrough`, apply at `/v1/models`)
- Test: `tests/test_glm_passthrough_unit.py` (NEW)

**Interfaces:**
- Consumes: merged `constants.py` (has `CLAUDE_MODELS`, `GEMINI_MODELS`) and `main.py` (`get_cli_for_model`, `list_models`).
- Produces: `glm-5.2` advertised in `/v1/models`; `PASSTHROUGH_MODELS` constant; `_append_passthrough(models)` helper in `main.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_glm_passthrough_unit.py`:
```python
"""Unit tests for GLM-5.2 passthrough: advertisement + routing."""

from src.constants import GLM_MODELS, PASSTHROUGH_MODELS
from src.main import _append_passthrough, get_cli_for_model, claude_cli, gemini_cli


def test_glm_model_listed():
    assert "glm-5.2" in GLM_MODELS
    assert "glm-5.2" in PASSTHROUGH_MODELS


def test_append_passthrough_adds_glm():
    result = _append_passthrough([{"id": "claude-sonnet-4-6", "object": "model"}])
    ids = [m["id"] for m in result]
    assert "glm-5.2" in ids
    assert "claude-sonnet-4-6" in ids


def test_append_passthrough_dedupes():
    models = [{"id": "glm-5.2", "object": "model"}]
    result = _append_passthrough(models)
    assert sum(1 for m in result if m["id"] == "glm-5.2") == 1


def test_glm_routes_to_claude_cli():
    assert get_cli_for_model("glm-5.2") is claude_cli
    assert get_cli_for_model("glm-5.2") is not gemini_cli
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
poetry run pytest tests/test_glm_passthrough_unit.py -q
```
Expected: FAIL — `ImportError: cannot import name 'GLM_MODELS'` (and `_append_passthrough`).

- [ ] **Step 3: Add `GLM_MODELS` and `PASSTHROUGH_MODELS` to `constants.py`**

In `src/constants.py`, immediately after the `GEMINI_MODELS` block (added in Task 1), add:
```python
# GLM Models
# Served through Claude Code via a custom ANTHROPIC_BASE_URL proxy. The wrapper
# only forwards the model name; it never calls a GLM endpoint directly.
GLM_MODELS = [
    "glm-5.2",
]

# Non-Anthropic models advertised in /v1/models in addition to the live list.
# They never appear in Anthropic's live Models API response, so they are
# appended at the /v1/models edge (see _append_passthrough in main.py).
PASSTHROUGH_MODELS = GLM_MODELS + GEMINI_MODELS
```

- [ ] **Step 4: Add `_append_passthrough` to `main.py`**

In `src/main.py`, first update the constants import (around line 61) to include the new names. Add `GLM_MODELS` and `PASSTHROUGH_MODELS` to the existing `from src.constants import (...)` line.

Then add this helper near `get_available_models` (after that function's definition):
```python
def _append_passthrough(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Append non-Anthropic passthrough models (GLM, Gemini) to a model list.

    These models are served through Claude Code or the Gemini proxy and are
    never returned by Anthropic's live Models API, so they are merged in here
    at the /v1/models edge. Already-present ids are not duplicated.
    """
    existing_ids = {m.get("id") for m in models}
    augmented = list(models)
    for model_id in PASSTHROUGH_MODELS:
        if model_id not in existing_ids:
            augmented.append(
                {"id": model_id, "object": "model", "created": 0, "owned_by": "passthrough"}
            )
    return augmented
```

- [ ] **Step 5: Apply `_append_passthrough` at the `/v1/models` endpoint**

In `src/main.py`, find the `list_models` endpoint (the `@app.get("/v1/models")` handler). Change its return from:
```python
    return {"object": "list", "data": await get_available_models()}
```
to:
```python
    return {"object": "list", "data": _append_passthrough(await get_available_models())}
```

- [ ] **Step 6: Run the GLM tests — verify pass**

```bash
poetry run pytest tests/test_glm_passthrough_unit.py -q
```
Expected: 4 passed.

- [ ] **Step 7: Run the full suite — verify no regression**

```bash
poetry run pytest -q
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/constants.py src/main.py tests/test_glm_passthrough_unit.py
git commit -m "feat: advertise glm-5.2 as a passthrough model in /v1/models

GLM-5.2 is served through Claude Code via ANTHROPIC_BASE_URL. Add GLM_MODELS,
append passthrough models (GLM + Gemini) at the /v1/models edge so they are
discoverable even though they never appear in Anthropic's live Models API.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/UPGRADE_PLAN.md`

**Interfaces:**
- Consumes: final state of Tasks 1–4.
- Produces: accurate version references + a GLM passthrough setup section.

- [ ] **Step 1: Update SDK version references in README**

In `README.md`, replace every occurrence of `0.1.18` with `0.2.134` (search: `grep -n "0\.1\.18" README.md`). Common locations: the "powered by the official Claude Agent SDK" line and the installation/prerequisites notes.

- [ ] **Step 2: Add a GLM passthrough section to README**

Add this section near the existing model/configuration docs:
```markdown
## Using non-Claude models via passthrough (e.g. GLM-5.2)

The wrapper can serve any model that your Claude Code installation can reach,
including non-Anthropic models such as **GLM-5.2**. The wrapper does not call
the model provider directly — it forwards the model name to Claude Code, which
must already be configured to reach the provider.

**Prerequisite — point Claude Code at the provider.** Set these on the Claude
Code process (your environment, not wrapper code):
- `ANTHROPIC_BASE_URL` — your proxy that speaks the Anthropic API format and
  forwards to the provider (e.g. a GLM endpoint).
- `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` — the credential your proxy
  requires, if any.

**Use it through the wrapper.** Send the model name in the request:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-5.2","messages":[{"role":"user","content":"hello"}]}'
```

To make GLM the default, set `DEFAULT_MODEL=glm-5.2` for the wrapper. `glm-5.2`
is advertised in `GET /v1/models`.
```

- [ ] **Step 3: Mark the SDK migration complete in UPGRADE_PLAN**

In `docs/UPGRADE_PLAN.md`, update the header target version from `claude-agent-sdk 0.1.6` / `0.1.18` references to `0.2.134`, and add a one-line status under the title:
```markdown
**Status:** SDK upgraded to claude-agent-sdk 0.2.134 (2026-08-10). CLI remains 2.1.226.
```

- [ ] **Step 4: Verify docs build/links are not broken**

```bash
grep -rn "0\.1\.18" README.md docs/UPGRADE_PLAN.md
```
Expected: no matches (all updated to `0.2.134`).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/UPGRADE_PLAN.md
git commit -m "docs: update SDK version to 0.2.134 and document GLM-5.2 passthrough

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Final verification + manual smoke

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

```bash
poetry run pytest -q
```
Expected: all green, including `test_dynamic_models.py`, `test_message_parser_unit.py`, `test_glm_passthrough_unit.py`.

- [ ] **Step 2: Confirm dependency + CLI versions**

```bash
poetry show claude-agent-sdk | head -3   # 0.2.134
claude --version                         # 2.1.226
```

- [ ] **Step 3: Manual smoke — streaming + session continuity**

Start the server and run a streaming chat completion against a Claude model, then a second request reusing the returned `session_id`. Confirm the assistant remembers the first turn.

- [ ] **Step 4: Manual smoke — GLM-5.2 (operator-run)**

With Claude Code pointed at GLM via `ANTHROPIC_BASE_URL`, send a chat completion with `model: "glm-5.2"` and confirm a response. Then `GET /v1/models` and confirm `glm-5.2` is listed.

- [ ] **Step 5: Push the branch and open a PR**

```bash
git push -u origin feat/sync-sdk-upgrade-glm
gh pr create --title "Sync upstream + upgrade SDK to 0.2.134 + GLM-5.2 passthrough" \
  --body "Merges RichardAtCT upstream (dynamic model list), bumps claude-agent-sdk 0.1.18 -> 0.2.134 with a hardened typed message parser, and advertises glm-5.2 as a passthrough model. See docs/superpowers/specs/2026-08-10-sync-sdk-upgrade-glm-design.md."
```
Expected: PR opens against `main`.

---

## Self-Review (completed during authoring)

- **Spec coverage:** Part 1 (sync) → Task 1. Part 2 (SDK bump + hardening) → Tasks 2–3. Part 3 (GLM passthrough) → Task 4. Docs → Task 5. Verify → Task 6. All spec sections mapped.
- **Placeholders:** none. Each code step contains the actual code; merge steps contain exact git commands + per-file resolution policy.
- **Type consistency:** `_message_to_dict` is defined in Task 3 Step 4 and tested in Task 3 Step 1 with matching signatures. `_append_passthrough`, `GLM_MODELS`, `PASSTHROUGH_MODELS` are defined and tested consistently in Task 4. `get_cli_for_model` is the existing name from `main.py:439`.
