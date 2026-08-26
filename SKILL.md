---
name: codex-opencode-session
description: 在用户要求连接、启动、继续、监督、检查或排查本机 OpenCode 会话，或希望将 OpenCode 作为外部编码协作者时使用；覆盖 Windows 无头服务、模型选择、会话调用、真实验证和精确清理。不用于安装或升级 OpenCode。
---

# Codex OpenCode Session

将 OpenCode 作为本机外部编码协作者使用。Codex 负责理解任务、确认工作目录、检查现有改动并独立验证结果；OpenCode 在用户指定的目录中执行明确任务。

## 当前默认模型

默认模型从 [references/defaults.json](references/defaults.json) 读取。用户明确指定其他模型时，以用户选择为准。以后修改默认模型时，只改该 JSON 的 `model` 字段，不要在脚本或其他说明中复制默认值。

模型名称必须以 `opencode models <provider>` 的实时结果为准。OpenCode Go 使用 `opencode-go/...`，OpenCode Zen 使用 `opencode/...`；相似名称不代表两条线路可以共用模型 ID 或凭据。修改默认值前先用 `--model provider/model` 完成真实测试，修改后再次运行 `status --json`，确认 `default_model_available` 为 `true`。

## 开始前

1. 运行只读状态检查：

   ```powershell
   python <skill-dir>\scripts\opencode_session.py status --json
   ```

2. 使用 `opencode providers list` 确认默认模型所属 provider 已配置凭据。登录或替换 API Key 需要用户明确授权；密钥只通过 OpenCode 登录流程输入，不得出现在命令行参数、日志、提示词或仓库文件中。
3. 确认准确工作目录和用户希望 OpenCode 完成的任务。先阅读该目录适用的项目指令、`git status --short`、现有差异和测试命令，保留用户已有修改。
4. 安装、升级、登录、公开分享、提交、推送、发布、部署、批量删除会话或改动全局设置，需要用户明确授权。不要把普通会话任务扩展为这些操作。
5. 发现已有 OpenCode 服务时不要按进程名统一终止。辅助脚本会选择空闲端口，并且只关闭自己启动的进程树。

## 调用 OpenCode

短任务或单阶段任务使用辅助脚本。长提示先写入 UTF-8 文件：

```powershell
python <skill-dir>\scripts\opencode_session.py invoke `
  --dir <repo> --prompt-file <prompt.txt> --title <title> --json
```

脚本会显式设置本地服务账号、随机密码、回环地址直连和无人值守权限，启动隔离服务，创建会话并等待回复。成功后保留会话，返回 `session_id`、模型、回复和服务版本；临时服务随即关闭。继续指定会话时添加 `--session-id <id>`，并使用原会话的工作目录。

默认使用 `build` agent。只读分析使用 `--agent plan`。用户指定模型时使用 `--model provider/model`，这只影响当前调用。

首次配置或版本变化后运行无文件改动的真实测试：

```powershell
python <skill-dir>\scripts\opencode_session.py smoke-test --dir <safe-dir> --json
```

测试只创建一个精确命名的临时会话，确认回复所用模型后按准确会话 ID 删除，并关闭自己启动的服务。

更换模型时，先用临时覆盖验证候选模型：

```powershell
python <skill-dir>\scripts\opencode_session.py smoke-test `
  --dir <safe-dir> --model <provider/model> --agent plan --json
```

只有回复文本、`actual_model` 和会话清理都通过后，才修改 `defaults.json`。供应商目录中出现模型名称只说明模型可见，不能替代真实调用。

## 阶段协作

1. 给 OpenCode 的阶段说明应包含目标、已确认事实、允许修改的文件、不可执行的操作和验收命令。不要把用户内部说明原样写进产品内容。
2. 收到回复后检查实际文件差异、进程和测试结果。OpenCode 的自述、退出状态或任务清单不能单独证明任务完成。
3. 验证失败时，根据真实差异写下一阶段说明，并用同一 `session_id` 继续。不要用“最近会话”之类不确定选择。
4. 长任务可以增大 `--timeout`。若同步请求超时，先检查准确会话状态，再决定继续、中止或改用教程所述异步 API。

需要 API 端点、会话管理、权限与故障处理细节时，读取 [references/operation-protocol.md](references/operation-protocol.md)。

## 安全要求

- 服务只监听 `127.0.0.1`，每次使用随机密码；日志和最终回复不得显示密码或认证头。
- 自动化会话允许工具调用，因此只在用户授权的工作目录和任务范围内使用。不要让 OpenCode 修改工作目录以外的内容，除非用户明确要求。
- 删除测试数据时只使用脚本本次创建并记录的准确会话 ID。普通调用默认保留会话。
- 不要统一终止 OpenCode、桌面端、TUI 或其他端口上的服务。
- 保留用户已有文件与无关改动；不要擅自执行 commit、push、reset、clean、stash 或删除操作。
