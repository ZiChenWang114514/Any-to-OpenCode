<p align="center">
  <picture>
    <source media="(max-width: 680px)" srcset="./assets/readme/hero-mobile.svg">
    <img src="./assets/readme/hero.svg" width="100%" alt="Any-to-OpenCode：把任意兼容编码助手接到准确的 OpenCode 会话">
  </picture>
</p>

<p align="center">
  <a href="./README.md">English</a> · <strong>简体中文</strong>
</p>

<p align="center">
  <a href="./LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-5eead4?style=flat-square"></a>
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/python-3.10%2B-7dd3fc?style=flat-square">
  <img alt="Tested on Windows" src="https://img.shields.io/badge/tested-Windows-94a3b8?style=flat-square">
  <img alt="OpenCode 1.18.23 verified" src="https://img.shields.io/badge/OpenCode-1.18.23-f8fafc?style=flat-square">
</p>

# Any-to-OpenCode

把任意兼容的编码助手接到本机 OpenCode 会话。它会读取当前可用的模型、用真实冒烟测试核对，再在指定目录创建或继续准确会话。

本仓库是本地会话适配器：一套 Python 命令行工具，外加 Codex Skill 封装。它不负责安装 OpenCode，也不是 OpenCode 官方产品。

## 它能做什么

- 刷新 OpenCode 的实时模型元数据，并区分 Go 与 Zen 两条线路。
- 找出公开输入、输出和缓存价格都为零的模型，再并发做冒烟测试。
- 在 `127.0.0.1` 上启动带一次性密码的无头服务，或按会话 ID 继续同一会话。
- 返回结构化结果（`session_id`、实际模型、回复、清理状态），由调用方自己检查仓库。

Codex、Claude Code、Grok Build 等工具都可以直接调用 Python 脚本。安装 Skill 后，Codex 也可以使用 `$codex-opencode-session`。

## 实测快照

记录于 2026-08-27，环境为 Windows、Python 3.14、OpenCode 1.18.23。免费模型会随地区、活动、额度和负载变化，下表只是一次真实快照。

| 路线 | 模型 | 本次结果 | 依据 |
| --- | --- | --- | --- |
| OpenCode Go | `muse-spark-1.2-contributor` | 通过 | 精确返回 `OPENCODE_SESSION_OK`，当前默认模型 |
| OpenCode Zen | `nemotron-3-ultra-free` | 通过 | 首次冒烟测试通过 |
| OpenCode Zen | `nemotron-3.5-lightning-free` | 通过 | 第二次冒烟测试通过 |
| OpenCode Zen | `big-pickle` | 当前额度受限 | 两次超时；官方端点返回 `FreeUsageLimitError` |
| OpenCode Zen | `hy3-free` | 当前额度受限 | 两次超时；官方端点返回 `FreeUsageLimitError` |
| OpenCode Zen | `mimo-v2.5-free` | 当前额度受限 | 两次超时；官方端点返回 `FreeUsageLimitError` |
| OpenCode Zen | `muse-spark-1.2-contributor-free` | 当前额度受限 | 两次超时；官方端点返回 `FreeUsageLimitError` |

Go 是付费订阅。当前默认的 Muse Contributor 属于 Go 阵容，不能当成零费用模型。Zen 才会列出公开标价为零的模型。价格以 [OpenCode Zen 说明](https://opencode.ai/docs/zen/) 和 [OpenCode Go 说明](https://opencode.ai/docs/go/) 为准。

## 安装

需要 Python 3.10 或更高版本，以及已经登录的 [OpenCode](https://opencode.ai/) CLI。

```powershell
git clone https://github.com/ZiChenWang114514/Any-to-OpenCode.git `
  "$env:USERPROFILE\.codex\skills\codex-opencode-session"
```

克隆目标目录是 Codex Skill 标识 `codex-opencode-session`。若要在 Codex 里使用 `$codex-opencode-session`，安装后重新打开任务。其他编码助手可以直接运行 `scripts/opencode_session.py`。

## 最快开始

### 1. 检查本机状态

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  status --json
```

### 2. 验证当前免费模型池

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  free-pool `
  --dir "C:\path\to\safe-dir" `
  --provider opencode `
  --parallel 3 `
  --timeout 300 `
  --json
```

`free-pool` 不靠模型名称里的 `free` 字样判断。它读取实时元数据，只保留 active 且输入、输出、缓存读写价格全部为零的模型，再核验回复、实际模型和测试会话清理。

### 3. 把任务交给已经通过的模型

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  invoke `
  --dir "C:\path\to\repo" `
  --model "opencode/nemotron-3-ultra-free" `
  --agent plan `
  --title "review-api" `
  --prompt "检查这个项目的 API，并给出可验证的修改建议。" `
  --json
```

每个真实任务使用独立的 `invoke` 进程、目录、模型、标题和提示。免费服务常有并发与额度限制，建议从 2–3 路开始。收到回复后，检查仓库差异并运行项目自己的测试。

### 4. 继续同一会话

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  invoke `
  --dir "C:\path\to\repo" `
  --session-id "ses_xxxxx" `
  --prompt "根据刚才的检查结果继续处理。" `
  --json
```

继续任务时使用创建该会话时的工作目录，并传入准确 `session_id`。

## 命令

| 命令 | 用途 | 会话处理 |
| --- | --- | --- |
| `status` | 检查 CLI、版本、数据库与默认模型 | 不创建会话 |
| `free-pool` | 发现零成本模型并并发试跑 | 测试会话自动删除 |
| `invoke` | 创建或继续真实 OpenCode 会话 | 正式会话保留 |
| `smoke-test` | 验证指定模型与本地 API | 测试会话自动删除 |

每次调用会选择空闲端口，服务只监听 `127.0.0.1`，并生成随机密码。脚本只关闭自己启动的进程树，不会终止桌面端、TUI 或其他 OpenCode 服务。

## 默认模型

默认配置在 [`references/defaults.json`](./references/defaults.json)：

```json
{
  "model": "opencode-go/muse-spark-1.2-contributor"
}
```

单次调用的 `--model provider/model` 优先于默认值。只有实时元数据里存在对应变体时，才使用 `--variant high` 这类参数。

OpenCode Go 使用 `opencode-go/...`，OpenCode Zen 使用 `opencode/...`。两条线路的模型 ID、订阅方式和凭据不能混用。

## 在编码助手中使用

向助手说明仓库路径、权限模式和期望结果即可。在 Codex 中可以这样写：

```text
使用 $codex-opencode-session，在 C:\path\to\repo 检查状态，
然后开一个 plan 模式会话，审查 API 并报告可验证的问题，不要改文件。
```

请求里写任务本身。发现模型、隔离会话和返回 JSON 由适配器完成。

## 使用须知

- Zen 免费模型属于限时服务。批量任务前重新运行 `free-pool`。
- `429`、超时、空回复或模型不一致都表示当次未通过。不要通过多账户规避额度限制。
- 部分免费端点会收集提示词和回复用于模型改进；NVIDIA Nemotron 试用端点还可能记录请求。详见 [Zen Privacy](https://opencode.ai/docs/zen/#privacy)。不要向这些线路发送密钥或私密内容。
- 无人值守 `build` 会允许工具执行，只应在已经授权的目录和任务中使用；只读检查使用 `--agent plan`。
- API Key 由 OpenCode 自己的登录流程保存，不要出现在命令行、日志、README 或 Git 提交中。

## 仓库结构

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

## 验证

```powershell
python -m py_compile .\scripts\opencode_session.py
python -m unittest discover -s .\tests -v
python .\scripts\opencode_session.py status --json
```

## 机器可读结果

每个命令都支持 `--json`。统一字段包括 `schema_version`、`ok`、`target`、`command`、`provider`、`workdir`、`session_id`、`requested_model`、`actual_model`、`result`、`warnings` 和 `error`，并保留各适配器自己的验证信息。

## 同系列适配器

| 仓库 | 目标 |
| --- | --- |
| [Any-to-Grok-Build](https://github.com/ZiChenWang114514/Any-to-Grok-Build) | Grok Build |
| [Any-to-Kimi-Code](https://github.com/ZiChenWang114514/Any-to-Kimi-Code) | Kimi Code |
| [Any-to-ZCode](https://github.com/ZiChenWang114514/Any-to-ZCode) | ZCode / GLM |
| [Any-to-DeepSeek-Harness](https://github.com/ZiChenWang114514/Any-to-DeepSeek-Harness) | DeepSeek Harness |
| [Any-to-Codex](https://github.com/ZiChenWang114514/Any-to-Codex) | Codex CLI |
| [Any-to-Claude-Code](https://github.com/ZiChenWang114514/Any-to-Claude-Code) | Claude Code |
| [Any-to-Pi](https://github.com/ZiChenWang114514/Any-to-Pi) | Pi |

## 许可证

[MIT](./LICENSE) © 2026 Zichen Wang
