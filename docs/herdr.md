# HerdR 接入

要求 Python 3.11+、HerdR 0.8.2+ 和所用 harness 的官方 integration。核心 CLI 不需要这些宿主条件。

## 安装与快捷键

Windows，在 sessmark 根目录：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[ui]" -e adapters\herdr
herdr plugin link "$PWD\plugins\herdr"
herdr integration install grok
# 按实际使用的 harness 安装，例如：herdr integration install codex
```

加入 `%APPDATA%\herdr\config.toml`（先检查是否已占用这两个键）：

```toml
[[keys.command]]
key = "prefix+t"
type = "plugin_action"
command = "sessmark.mark-windows"
description = "tag and note the current session"

[[keys.command]]
key = "prefix+shift+t"
type = "plugin_action"
command = "sessmark.ui-windows"
description = "browse marked sessions"
```

```powershell
herdr config check
herdr server reload-config
```

Windows 清单经 PowerShell 调项目 `.venv\Scripts\python.exe`；不要求激活 venv 或修改 HerdR server 的 PATH。
启动前剥掉 HerdR 返回的 Windows `\\?\` 路径前缀，兼容 Windows PowerShell 5.1 的 Join-Path。
若没有项目 venv，回退到 PATH 上独立安装的 `sessmark-herdr`。
macOS/Linux 使用 `.venv/bin/python`；快捷键 action 分别为 `sessmark.mark` / `sessmark.ui`，要求系统有 python3。
两个平台使用独立 action/pane ID，避免清单重名。

## 人的路径

在 Agent pane 按 `prefix+t`：Space 勾选 tag，Tab 写一行 note，Enter 原子保存，Esc 取消。
标记窗打开时捕获目标 pane；保存前重新核对 terminal 和 native 身份。已确认的会话若改变，则拒绝保存并提示重新打开。

`prefix+shift+t` 打开 Viewer：上下选中，`/` 输入一个或多个 tag（空格分隔，AND），Enter 应用过滤；
在列表按 Enter 回到已验证的原 Agent pane，或在新的 HerdR tab 恢复。`y` 复制带数据库路径的 context 命令。
Windows 复制结果是 PowerShell 命令。UI 不编辑旧 notes，移除 tag 用 CLI。

从已激活 sessmark venv 的 HerdR pane 也可运行：

```powershell
sessmark-herdr tag review:problem
sessmark-herdr note "后面复盘"
sessmark-herdr sync --json
sessmark-herdr resume sm_某个ID --dry-run
```

`pane.agent_detected` / `pane.agent_status_changed` hook 为已标 pane 补充 native 身份。hook 读取事件中的 pane，不会误用当时的焦点。
没有匹配标记时不再调用 HerdR。Viewer 启动和显式 `sync` 也会刷新当前 endpoint 的已标记录。
流水线可先 `sessmark-herdr sync`，再用纯 `sessmark list/context`；离线消费不调用宿主。

## 接口依据与限制

依据官方 [CLI reference](https://herdr.dev/docs/cli-reference/)、[plugins](https://herdr.dev/docs/plugins/)、
[socket API](https://herdr.dev/docs/socket-api/) 和 [configuration](https://herdr.dev/docs/configuration/)。
所有交互调用 `HERDR_BIN_PATH` 指向的 CLI，不直连 socket/命名管道。
`pane get/current/list` 默认 JSON，native reference 是 `agent_session: {source, agent, kind, value}`。
popup 本身没有 pane ID，读取 `HERDR_PLUGIN_CONTEXT_JSON.focused_pane_id` 或 `HERDR_ACTIVE_PANE_ID`。

Grok native ID 足够生成 `grok --resume ID`。官方只给 ID 时，transcript_path 为 null；
不会臆造 cwd slug。显式传入完整路径可补齐 `~/.grok/sessions/<encoded-cwd>/<id>/chat_history.jsonl` 提示。

若原 pane 关闭而 pending 未绑定，执行 `sessmark bind sm_ID --harness grok --session-id REAL_ID`。
不同 HerdR endpoint、不同 terminal、不同 native ID 不直接聚焦旧 pane。
HerdR 外使用 `sessmark resume`，不需要安装/启动该插件。

2026-09-06 已在本机 HerdR 0.8.2 执行真实 plugin link。该版本不支持插件事件 `pane.updated`，
因此使用 agent detected/status changed 事件，并保留显式 sync 和 Viewer 启动刷新作为补偿。
当前 server 尚未运行；Windows popup/剪贴板、integration 上报和 macOS 仍需按测试文档联调。
适配行为测试使用官方 JSON 形状的合成响应，plugin link 不等同于交互端到端验收。
