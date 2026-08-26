<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="Codex OpenCode Skill creates isolated local OpenCode sessions with verified models and exact session IDs">
</p>

<p align="center">
  <a href="./LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-5eead4?style=flat-square"></a>
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/python-3.10%2B-7dd3fc?style=flat-square">
  <img alt="Tested on Windows" src="https://img.shields.io/badge/tested-Windows-94a3b8?style=flat-square">
  <img alt="OpenCode 1.18.23 verified" src="https://img.shields.io/badge/OpenCode-1.18.23-f8fafc?style=flat-square">
</p>

一个面向 Codex 的个人 Skill：让 Codex 通过本地 HTTP 服务创建、继续和检查 OpenCode 会话，并把模型选择、随机认证、临时端口与会话清理封装为可复用脚本。

## 真实试运行

下面是 Muse Spark 1.2 贡献者免费版的实际结果。公开示例省略了临时会话 ID；测试会话在核验完成后已删除。

```json
{
  "ok": true,
  "requested_model": "opencode-go/muse-spark-1.2-contributor",
  "actual_model": "muse-spark-1.2-contributor",
  "reply": "OPENCODE_SESSION_OK",
  "server_version": "1.18.23",
  "test_session_deleted": true
}
```

## 它解决什么问题

直接操作 `opencode serve` 时，需要自行处理认证、端口、代理、权限、会话 ID 和进程清理。这个 Skill 将这些容易出错的部分整理为三个稳定命令：

| 命令 | 用途 | 是否保留会话 |
| --- | --- | --- |
| `status` | 检查 CLI、版本、数据库与默认模型 | 不创建会话 |
| `invoke` | 创建或继续真实 OpenCode 会话 | 保留 |
| `smoke-test` | 验证本地 API 与当前默认模型 | 删除测试会话 |

每次调用都会选择空闲端口，服务仅监听 `127.0.0.1`，认证密码随机生成。脚本只关闭自己启动的进程树，不会统一终止桌面端、TUI 或其他 OpenCode 服务。

## 工作方式

```text
Codex
  └─ opencode_session.py
       ├─ 读取 defaults.json
       ├─ 选择空闲端口并生成随机密码
       ├─ 启动 127.0.0.1 上的临时 opencode serve
       ├─ 创建或继续准确的 session ID
       ├─ 等待模型回复并返回结构化结果
       └─ 关闭本次服务；普通会话继续保留
```

## 安装

需要本机已经安装并登录 [OpenCode](https://opencode.ai/)，同时具备 Python 3.10 或更新版本。

PowerShell：

```powershell
git clone https://github.com/ZiChenWang114514/codex-opencode-skill.git `
  "$env:USERPROFILE\.codex\skills\codex-opencode-session"
```

重新打开 Codex 任务后，可以直接调用：

```text
Use $codex-opencode-session to start an OpenCode session for this project.
```

## 快速使用

### 1. 检查状态

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  status --json
```

### 2. 创建真实会话

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  invoke `
  --dir "D:\path\to\repo" `
  --title "review-api" `
  --prompt "检查这个项目的 API 实现，并给出可验证的修改建议。" `
  --json
```

长任务建议将提示词保存为 UTF-8 文件，再使用 `--prompt-file`：

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  invoke --dir "D:\path\to\repo" --prompt-file ".\phase-01.txt" --json
```

### 3. 继续准确会话

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  invoke `
  --dir "D:\path\to\repo" `
  --session-id "ses_xxxxx" `
  --prompt "根据刚才的检查结果继续处理。" `
  --json
```

继续会话时，应使用创建该会话时的工作目录，并明确传入 `session_id`。

### 4. 运行测试

```powershell
python "$env:USERPROFILE\.codex\skills\codex-opencode-session\scripts\opencode_session.py" `
  smoke-test --dir "D:\safe\test-dir" --json
```

## 默认模型

当前默认模型保存在 [`references/defaults.json`](./references/defaults.json)：

```json
{
  "model": "opencode-go/muse-spark-1.2-contributor"
}
```

这是 OpenCode Go 的贡献者免费条目。Go provider 的准确 ID 以 `opencode models opencode-go` 为准；Zen provider 使用 `opencode/...` 形式，并有独立的模型目录与认证信息。

需要更换默认模型时，只修改 `model` 字段。单次调用也可以使用：

```powershell
--model provider/model
```

用户在任务中明确指定的模型优先于默认配置。

## Agent 与超时

- 默认使用 `build` agent，允许执行编码任务。
- 只读分析可使用 `--agent plan`。
- 同步请求的默认等待时间为 600 秒，可用 `--timeout` 调整。
- 长时间并行任务可以进一步使用 OpenCode 的 `prompt_async` 与 SSE API；相关说明见 [`references/operation-protocol.md`](./references/operation-protocol.md)。

## 安全设计

- 服务固定监听本地回环地址 `127.0.0.1`。
- 每次调用生成新的随机密码，不写入配置文件或输出。
- `NO_PROXY` 自动包含 `127.0.0.1`、`localhost` 和 `::1`，现有外部代理设置继续保留。
- 测试数据仅按脚本本次记录的准确会话 ID 删除。
- 失败日志保存在系统临时目录，错误信息不会显示认证密码。
- 模型供应商返回错误或没有生成文本时，命令以非零状态退出，并提供经过删减的 `assistant_error`，便于准确重试对应会话。
- 无人值守模式会允许 OpenCode 工具自动执行，因此应在用户已经授权的目录与任务中使用。

## 当前限制

- 每个 `invoke` 进程一次处理一个任务；可以并行启动多个进程，但仓库目前没有批量调度命令。
- 当前实现使用同步消息 API，长任务需要设置足够的等待时间。
- 已在 Windows、Python 3.14 和 OpenCode 1.18.23 上真实验证；其他系统仍需自行测试。
- Skill 不负责安装、升级或登录 OpenCode。

## 仓库结构

```text
.
├─ SKILL.md
├─ agents/
│  └─ openai.yaml
├─ references/
│  ├─ defaults.json
│  └─ operation-protocol.md
├─ scripts/
│  └─ opencode_session.py
├─ tests/
│  └─ test_opencode_session.py
└─ assets/readme/
   └─ hero.svg
```

## 验证

```powershell
python -m py_compile .\scripts\opencode_session.py
python -m unittest discover -s .\tests -v
python .\scripts\opencode_session.py status --json
```

Skill 的 YAML、目录名称和模板残留可用 Codex 内置的 `quick_validate.py` 检查。

## License

[MIT](./LICENSE)
