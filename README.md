<p align="center">
  <picture>
    <source media="(max-width: 680px)" srcset="./assets/readme/hero-mobile.svg">
    <img src="./assets/readme/hero.svg" width="100%" alt="Any-to-OpenCode: route work from any compatible harness to exact OpenCode sessions">
  </picture>
</p>

<p align="center">
  <strong>English</strong> · <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="./LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-5eead4?style=flat-square"></a>
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/python-3.10%2B-7dd3fc?style=flat-square">
  <img alt="Tested on Windows" src="https://img.shields.io/badge/tested-Windows-94a3b8?style=flat-square">
  <img alt="OpenCode 1.18.23 verified" src="https://img.shields.io/badge/OpenCode-1.18.23-f8fafc?style=flat-square">
</p>

# Any-to-OpenCode

Connect any compatible coding harness to local OpenCode sessions. The adapter discovers currently available models, verifies them with real smoke tests, then creates or resumes an exact session in a directory you choose.

This repository is a local session adapter: a Python CLI, plus a Codex Skill wrapper. It does not install OpenCode, and it is not an official OpenCode product.

## What it does

- Refresh live OpenCode model metadata and keep Go / Zen routes distinct.
- Find models whose public input, output, and cache prices are all zero, then smoke-test them in parallel.
- Start a headless OpenCode session on `127.0.0.1` with a one-time password, or resume the same session by ID.
- Return structured results (`session_id`, actual model, reply, cleanup status) so the calling harness can inspect the repository itself.

Codex, Claude Code, Grok Build, and other tools can call the Python CLI. Codex users can also invoke `$codex-opencode-session` after installing the Skill.

## Live snapshot

Recorded on 2026-08-27 with Windows, Python 3.14, and OpenCode 1.18.23. Free-model availability changes with region, promotions, quota, and load. Treat the table as one real snapshot, not a guarantee.

| Route | Model | Result | Evidence |
| --- | --- | --- | --- |
| OpenCode Go | `muse-spark-1.2-contributor` | Passed | Exact reply `OPENCODE_SESSION_OK`; current default model |
| OpenCode Zen | `nemotron-3-ultra-free` | Passed | First smoke test passed |
| OpenCode Zen | `nemotron-3.5-lightning-free` | Passed | Second smoke test passed |
| OpenCode Zen | `big-pickle` | Quota limited | Two timeouts; endpoint returned `FreeUsageLimitError` |
| OpenCode Zen | `hy3-free` | Quota limited | Two timeouts; endpoint returned `FreeUsageLimitError` |
| OpenCode Zen | `mimo-v2.5-free` | Quota limited | Two timeouts; endpoint returned `FreeUsageLimitError` |
| OpenCode Zen | `muse-spark-1.2-contributor-free` | Quota limited | Two timeouts; endpoint returned `FreeUsageLimitError` |

Go is a paid subscription. The current default Muse Contributor model is on the Go roster, so it is not a zero-cost model. Zen is the route that currently lists publicly zero-priced models. Confirm prices in the [OpenCode Zen docs](https://opencode.ai/docs/zen/) and [OpenCode Go docs](https://opencode.ai/docs/go/).

## Install

You need Python 3.10+ and a logged-in [OpenCode](https://opencode.ai/) CLI.

```powershell
git clone https://github.com/ZiChenWang114514/Any-to-OpenCode.git `
  "$env:USERPROFILE\.codex\skills\codex-opencode-session"
```

The clone destination is the Codex Skill id, `codex-opencode-session`. Reopen Codex after installing if you want `$codex-opencode-session`. Other harnesses can run `scripts/opencode_session.py` directly.

## First use

### 1. Check the local CLI

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  status --json
```

### 2. Verify the current free model pool

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  free-pool `
  --dir "C:\path\to\safe-dir" `
  --provider opencode `
  --parallel 3 `
  --timeout 300 `
  --json
```

`free-pool` does not guess from the word `free` in a model name. It reads live metadata, keeps only active models whose public prices are all zero, then checks reply, actual model, and test-session cleanup.

### 3. Run a real task on a model that passed

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  invoke `
  --dir "C:\path\to\repo" `
  --model "opencode/nemotron-3-ultra-free" `
  --agent plan `
  --title "review-api" `
  --prompt "Review this project's API and list verifiable change suggestions." `
  --json
```

Each real task should use its own `invoke` process, directory, model, title, and prompt. Free endpoints often throttle concurrent work; start with two or three jobs. After the reply, inspect the repository and run its own tests.

### 4. Resume the same session

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  invoke `
  --dir "C:\path\to\repo" `
  --session-id "ses_xxxxx" `
  --prompt "Continue from the previous review." `
  --json
```

Use the original working directory and the exact `session_id`.

## Commands

| Command | Purpose | Sessions |
| --- | --- | --- |
| `status` | Check CLI, version, database, and default model | None created |
| `free-pool` | Discover zero-cost models and smoke-test them in parallel | Test sessions are deleted |
| `invoke` | Create or resume a real OpenCode session | Formal sessions are kept |
| `smoke-test` | Verify one model and the local API | Test session is deleted |

Each call picks a free port, listens only on `127.0.0.1`, and generates a random password. The helper stops only the process tree it started. It does not kill the OpenCode desktop app, TUI, or other services.

## Default model

The default is stored in [`references/defaults.json`](./references/defaults.json):

```json
{
  "model": "opencode-go/muse-spark-1.2-contributor"
}
```

A `--model provider/model` flag on one call overrides the default. Use `--variant high` only when that variant exists in live metadata.

OpenCode Go uses `opencode-go/...`. OpenCode Zen uses `opencode/...`. Model IDs, subscriptions, and credentials are not interchangeable.

## Using it from a coding agent

Give the agent the repository path, the permission mode, and the outcome you want. For Codex:

```text
Use $codex-opencode-session in C:\path\to\repo.
Check status, then start a plan-mode session that reviews the API
and reports verifiable issues. Do not edit files.
```

Keep the request to the task. The adapter already knows how to discover models, isolate sessions, and return JSON.

## Notes

- Zen free models are promotional. Refresh `free-pool` before a batch of jobs.
- `429`, timeouts, empty replies, or a mismatched `actual_model` mean that attempt failed. Do not rotate accounts to bypass provider limits.
- Some free endpoints collect prompts and replies for model improvement. NVIDIA Nemotron trial endpoints may log requests for safety and product work. See [Zen Privacy](https://opencode.ai/docs/zen/#privacy). Do not send secrets or private data to those routes.
- Unattended `build` allows tool execution. Use it only in a directory and task the user has already authorized. Read-only review uses `--agent plan`.
- OpenCode stores API keys in its own login flow. Do not put keys in command arguments, logs, README files, or git commits.

## Repository layout

```text
.
├─ SKILL.md
├─ agents/openai.yaml
├─ references/defaults.json
├─ references/operation-protocol.md
├─ scripts/opencode_session.py
├─ tests/test_opencode_session.py
└─ assets/readme/
```

## Verify

```powershell
python -m py_compile .\scripts\opencode_session.py
python -m unittest discover -s .\tests -v
python .\scripts\opencode_session.py status --json
```

## Machine-readable contract

Every command accepts `--json`. The shared fields are `schema_version`, `ok`, `target`, `command`, `provider`, `workdir`, `session_id`, `requested_model`, `actual_model`, `result`, `warnings`, and `error`. Adapter-specific evidence remains alongside them.

## Related adapters

| Repository | Target |
| --- | --- |
| [Any-to-Grok-Build](https://github.com/ZiChenWang114514/Any-to-Grok-Build) | Grok Build |
| [Any-to-Kimi-Code](https://github.com/ZiChenWang114514/Any-to-Kimi-Code) | Kimi Code |
| [Any-to-ZCode](https://github.com/ZiChenWang114514/Any-to-ZCode) | ZCode / GLM |
| [Any-to-DeepSeek-Harness](https://github.com/ZiChenWang114514/Any-to-DeepSeek-Harness) | DeepSeek Harness |
| [Any-to-Codex](https://github.com/ZiChenWang114514/Any-to-Codex) | Codex CLI |
| [Any-to-Claude-Code](https://github.com/ZiChenWang114514/Any-to-Claude-Code) | Claude Code |
| [Any-to-Pi](https://github.com/ZiChenWang114514/Any-to-Pi) | Pi |
| [Any-to-Antigravity](https://github.com/ZiChenWang114514/Any-to-Antigravity) | Google Antigravity CLI |

## License

[MIT](./LICENSE) © 2026 Zichen Wang
