# Sync + SDK 0.2.134 Upgrade + GLM-5.2 Passthrough — Design

**Date:** 2026-08-10
**Author:** brainstorming session
**Status:** Approved (pending implementation plan)
**Branch (planned):** `feat/sync-sdk-upgrade-glm`

---

## 1. Context

`claude-code-openai-wrapper` (this repo) is a GitHub fork. The fork's `origin` is
`gustavokch/claude-code-openai-wrapper`; the true GitHub parent (upstream) is
`RichardAtCT/claude-code-openai-wrapper`. The local working copy is fully in sync
with `origin` (0 commits ahead / behind). The fork is **20 commits ahead** and
**2 commits behind** upstream.

The wrapper exposes Claude Code (via the `claude-agent-sdk` Python package) as an
OpenAI-compatible API. It pins `claude-agent-sdk = "^0.1.18"`. The locally
installed Claude Code CLI is `2.1.226`.

The user's Claude Code installation runs on the **GLM-5.2** model through a custom
endpoint (the active session reports `glm-5.2[1m]`). The wrapper must expose that
model without rejecting it.

### 1.1 Version reality (verified 2026-08-10)

| Component | Fork current | Latest available | Note |
|---|---|---|---|
| `claude-agent-sdk` (PyPI) | `0.1.18` | `0.2.134` (released 2026-08-08) | Real upgrade available |
| `@anthropic-ai/claude-code` (npm) | `2.1.226` (installed) | `2.1.226` | `2.1.266` **does not exist** on npm |

The request to "match Claude Code v2.1.266" targets a version that is not
published. The agreed target is therefore **"current"**: upgrade the SDK to
`0.2.134` and keep the CLI at `2.1.226`.

---

## 2. Goals

1. **Sync** the fork with upstream `RichardAtCT`, integrating the 2 missing
   commits while preserving the 20 local commits.
2. **Upgrade** `claude-agent-sdk` `0.1.18 → 0.2.134`, fixing any message-handling
   drift, and harden the SDK message parser against future field changes.
3. **Enable GLM-5.2** as a passthrough model so clients can send
   `model: "glm-5.2"` and have it forwarded to a Claude Code backend that is
   pointed at GLM.

## 3. Non-goals

- Do **not** change the Claude Code CLI version (stay `2.1.226`).
- Do **not** build a direct GLM backend. GLM is served **through** Claude Code.
- Do **not** rewrite the wrapper architecture; touch only version-coupled and
  GLM-relevant code.
- Do **not** force-push. History is preserved via a merge.

---

## 4. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sync method | **Merge** `upstream/main` (not rebase) | Preserves the 20-commit PR history; no force-push on a published fork |
| Work order | Sync → SDK bump → GLM | Sync brings the dynamic-model-list foundation GLM builds on |
| Version target | SDK `0.2.134`, CLI `2.1.226` | `2.1.266` is unpublished; `2.1.226` is current |
| GLM path | **Passthrough** via Claude Code | User's Claude Code already serves GLM; wrapper only forwards the name |
| SDK parser | **Rewrite** to typed `isinstance` checks | Robust against future SDK message-field changes |

---

## 5. Verified facts (grounding for the plan)

- **Model flow already passes the model end-to-end:**
  - `src/models.py:200-201` — `to_claude_options()` sets `options["model"] = self.model`.
  - `src/main.py:488,539` — streaming path builds options and passes them to `run_completion`.
  - `src/claude_cli.py:142-144` — generic `setattr` loop sets `model` on `ClaudeAgentOptions` when present.
- **Validation never rejects a model:** `src/parameter_validator.py:23-30` — `validate_model()` logs a warning then returns `True` (graceful degradation).
- **Routing already sends GLM to the Claude path:** `src/main.py:439-446` — `get_cli_for_model()` returns `gemini_cli` only for `gemini*` / `pro` / `flash` / `flash-lite` / `auto`; everything else (including `glm-5.2`) returns `claude_cli`.
- **SDK 0.2.134 public API (verified against repo README):** `query`, `ClaudeAgentOptions` survive. Typed message classes are first-class: `AssistantMessage`, `UserMessage`, `SystemMessage`, `ResultMessage`, `TextBlock`, `ToolUseBlock`, `ToolResultBlock`. New: `ClaudeAgentOptions(cli_path=...)`, `ClaudeSDKClient`, `HookMatcher`, in-process MCP (`tool`, `create_sdk_mcp_server`).
- **The 2 missing upstream commits:**
  - `ba9b039e` "feat: dynamically refresh Anthropic model list (#46)" — touches `.env.example`, `README.md`, `src/constants.py`, `src/main.py`, `src/models.py`, adds `tests/test_dynamic_models.py`, touches `tests/test_sdk_migration.py`.
  - `74951748` "chore: release v2.3.0" — touches `README.md`, `pyproject.toml`, `src/__init__.py`.

---

## 6. Part 1 — Sync with `RichardAtCT`

### 6.1 Steps
1. `git remote add upstream https://github.com/RichardAtCT/claude-code-openai-wrapper.git`
2. `git fetch upstream`
3. From `main`, create `feat/sync-sdk-upgrade-glm`.
4. `git merge upstream/main` on the feature branch.

### 6.2 Conflict resolution policy
- **`src/constants.py`** — keep **both**: upstream's dynamic model-fetch logic **and** the fork's static `GEMINI_MODELS` list and env-driven `DEFAULT_MODEL`. This is the main conflict.
- **`src/main.py`** — accept upstream's dynamic `/v1/models` implementation; re-merge the fork's Gemini routing (`get_cli_for_model`) and both API surface paths (OpenAI chat completions + Anthropic Messages).
- **`src/models.py`** — accept upstream's dynamic-list changes; preserve the fork's `to_claude_options()` model passthrough and Claude-4 thinking-token default.
- **`pyproject.toml`** — both already at `2.3.0`; trivial.
- **`README.md`, `src/__init__.py`, `.env.example`, `tests/test_sdk_migration.py`** — take upstream, re-apply fork-specific wording.

### 6.3 Verify (gate before Part 2)
- `pytest` is green on the merged tree.
- New upstream test `tests/test_dynamic_models.py` passes.

---

## 7. Part 2 — SDK `0.1.18 → 0.2.134` + parser hardening

### 7.1 Dependency bump
- `pyproject.toml`: `claude-agent-sdk = ">=0.2.134,<0.3"`.
- `poetry lock && poetry install`.
- Confirm: `poetry show claude-agent-sdk` reports `0.2.134`.

### 7.2 Parser hardening (in scope)
Replace the fragile generic object→dict conversion in `src/claude_cli.py:159-176`
(the `dir()`-walk that copies every public attribute) with typed checks:

- Import `AssistantMessage`, `ResultMessage`, `SystemMessage`, `TextBlock` from `claude_agent_sdk`.
- In the message loop, branch on `isinstance(message, ...)` instead of the attribute walk.
- Preserve the existing field extraction contract used by `parse_claude_message()` and `extract_metadata()`:
  - `ResultMessage` (`subtype == "success"`): `result`, `total_cost_usd`, `duration_ms`, `num_turns`, `session_id`, `usage`, `stop_reason`.
  - `SystemMessage` (`subtype == "init"`): `session_id`, `model` (under `data`).
  - `AssistantMessage`: `content` list of `TextBlock` (use `.text`).
- Keep a minimal fallback for any unexpected message shape so the wrapper never crashes on an unknown type.

Behavior is unchanged for currently-working cases; robustness improves for future SDK field renames.

### 7.3 Fix drift found during testing
Patch any field-name or shape differences between 0.1.18 and 0.2.134 discovered by the test suite. Expected low volume given the verified API stability.

### 7.4 Docs
- `README.md`: update SDK version references `0.1.18 → 0.2.134`.
- `docs/UPGRADE_PLAN.md`: mark the SDK-migration phase complete; record the new target version.

### 7.5 Verify
- Full `pytest` suite green on `0.2.134`.
- Manual smoke: streaming response, session continuity (`session_id` resume), tool use (enable/disable).

---

## 8. Part 3 — GLM-5.2 passthrough

Passthrough already works (Section 5). Remaining work is advertisement and documentation.

### 8.1 Code
- `src/constants.py`: add `GLM_MODELS = ["glm-5.2"]`.
- `src/main.py` `/v1/models` handler (~line 1338): advertise the union
  `CLAUDE_MODELS + GEMINI_MODELS + GLM_MODELS` so `glm-5.2` is discoverable and
  no "unknown model" warning fires.
- `DEFAULT_MODEL` is already env-driven (`src/constants.py:108`); document
  `DEFAULT_MODEL=glm-5.2` for users who want GLM as the default.
- No change to `get_cli_for_model` (GLM already routes to `claude_cli`).
- No change to `validate_model` (already graceful).

### 8.2 Docs
- New README section: **"Non-Claude models via passthrough (e.g. GLM-5.2)."**
  Explain that the user points Claude Code at GLM by setting
  `ANTHROPIC_BASE_URL` (and, if their proxy requires it, `ANTHROPIC_AUTH_TOKEN` /
  `ANTHROPIC_API_KEY`) on the Claude Code process to a GLM-serving proxy. The
  wrapper only forwards the model name to Claude Code; it does not configure the
  endpoint. These env vars are the user's prerequisite, not wrapper code.

### 8.3 Verify
- Unit test: `get_cli_for_model("glm-5.2")` returns the Claude CLI instance.
- Unit test: `glm-5.2` appears in the `/v1/models` response.
- Live smoke (user-run): against a Claude Code pointed at GLM, send a chat
  completion with `model: "glm-5.2"` and confirm a response.

---

## 9. Testing & verification summary

| Layer | Check |
|---|---|
| Post-merge | `pytest` green; `test_dynamic_models.py` passes |
| Post-SDK-bump | `pytest` green on `0.2.134`; streaming + session + tool smoke |
| GLM | Unit: routing + model-list; live: GLM chat completion |
| New tests added | `glm-*` routing to `claude_cli`; `glm-5.2` in `/v1/models`; dynamic list still populates after merge |

---

## 10. Rollback

All work is on `feat/sync-sdk-upgrade-glm`. If any part fails badly:
- Abandon the branch (`git checkout main && git branch -D feat/sync-sdk-upgrade-glm`).
- Revert `pyproject.toml` to `claude-agent-sdk = "^0.1.18"` and `poetry lock && poetry install`.
- `main` is untouched until the PR merges; no production impact during development.

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `constants.py` merge conflict is messy | High | Low | Documented resolution policy (Section 6.2); merge on an isolated branch |
| SDK 0.2.134 message-field drift breaks parsing | Medium | Medium | Typed-parser rewrite + full test suite; fallback path preserved |
| Dynamic model list (upstream) excludes GLM/Gemini | Medium | Low | Static `GLM_MODELS`/`GEMINI_MODELS` appended to the advertised union |
| GLM backend env misconfigured by user | Medium | Low | README documents prerequisites; wrapper-side change is independent of user env |

---

## 12. Out of scope

- Direct GLM backend (bypassing Claude Code).
- CLI version change beyond `2.1.226`.
- Adopting `ClaudeSDKClient`, hooks, or in-process MCP from SDK 0.2.x (future work).
- Rebasing / force-pushing.
