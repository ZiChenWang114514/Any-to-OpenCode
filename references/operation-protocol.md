# OpenCode 操作说明

## 模型与会话

辅助脚本读取同目录的 `defaults.json`。默认模型需要调整时，只修改该文件的 `model` 字段。单次调用可用 `--model provider/model` 临时覆盖。

模型 ID 应从 `opencode models <provider>` 的当前输出中选择。`opencode-go` 与 `opencode` 分别表示 OpenCode Go 和 OpenCode Zen，二者的模型目录和认证信息相互独立。目录可见之后仍需做一次实际回复测试，再将候选模型设为默认值。

OpenCode 会话集中保存在 `opencode db path` 显示的 SQLite 数据库中，并根据服务启动目录记录项目归属。继续会话时，`--dir` 应保持为创建该会话时的目录。

## 本地服务

无头服务使用 HTTP Basic Auth。每次启动都应显式设置：

- `OPENCODE_SERVER_USERNAME`
- `OPENCODE_SERVER_PASSWORD`
- `OPENCODE_PERMISSION`

本地请求需让 `NO_PROXY` 包含 `127.0.0.1`、`localhost` 和 `::1`。不要清空模型访问所需的代理变量。

常用端点：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/global/health` | 服务版本与健康状态 |
| `POST` | `/session` | 创建会话 |
| `POST` | `/session/:id/message` | 同步发送消息 |
| `POST` | `/session/:id/prompt_async` | 异步发送消息 |
| `GET` | `/session/:id/message` | 读取消息历史 |
| `POST` | `/session/:id/abort` | 中止运行中的任务 |
| `PATCH` | `/session/:id` | 修改标题 |
| `POST` | `/session/:id/fork` | 从会话或指定消息创建分支 |
| `DELETE` | `/session/:id` | 删除准确会话 ID |
| `GET` | `/doc` | 当前版本 OpenAPI 文档 |

消息请求中的模型字段格式为：

```json
{
  "model": {
    "providerID": "<provider-id>",
    "modelID": "<model-id>"
  },
  "agent": "build",
  "parts": [
    { "type": "text", "text": "任务说明" }
  ]
}
```

示例中的模型仅说明字段格式；实际调用以 `defaults.json` 或用户的临时选择为准。

## 长任务与观察

同步 `/message` 会等待模型完成。普通长任务可增加 `--timeout`。需要持续事件或多会话并行时，使用 `prompt_async`，再从 `/event` 读取 SSE 事件，并以消息历史、工具状态和文件差异共同判断进度。

服务停止前若请求仍在运行，先调用 `/session/:id/abort`。不要因 HTTP 客户端超时就断言模型失败，也不要对不确定的会话重复发送相同任务。

## 权限

无人值守服务中，默认的 `external_directory` 或重复工具确认可能长期等待交互。辅助脚本按 `defaults.json` 设置权限。因为该设置允许工具自动执行，必须先确认用户已经授权对应目录和任务。

交互式 TUI 可保留人工确认；单次 CLI 也可以使用 `--auto`。这些方式的风险不同，不要修改用户的全局 OpenCode 配置来追求一致。

## 凭据

使用 `opencode providers list` 只确认凭据类型和 provider 是否存在，不读取或显示密钥内容。用户授权登录或更换密钥时，使用 `opencode providers login --provider <provider>` 的交互输入；不要把 API Key 放入命令行参数、脚本、日志、README 或 Git 提交。测试输出也不得包含认证头和原始供应商响应正文。

## 会话管理

使用 `opencode session list --format json` 或 API 获取准确 ID。继续任务时明确传入 ID；探索其他方案时使用 fork。

测试会话可以在回复和模型核验后删除。删除多个正式会话前，应把准确 ID 清单展示给用户并获得确认；严禁根据标题模糊匹配后直接批量删除。

## Windows 常见问题

- 401：通常是服务继承了其他客户端的密码，或目标端口属于旧进程。新服务必须使用显式随机密码和空闲端口。
- 中文乱码：控制台使用 UTF-8，请求使用 `application/json; charset=utf-8`。
- 本地请求异常经过代理：补全 `NO_PROXY`，保留访问模型供应商所需的代理设置。
- 工具一直等待：检查 `/config` 返回的权限设置，以及会话是否在等待人工确认。
- 服务端口冲突：查看监听 PID 和命令行，只处理本次脚本启动的准确进程。
- 供应商错误或空回复：辅助脚本会以非零状态退出。`assistant_error` 仅保留会话 ID、错误名称、消息、状态码和是否可重试，不包含响应头、响应正文或认证信息。
