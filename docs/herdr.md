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

加入 `%APPDATA%\herdr\config.toml`。0.8.2 默认 `rename_tab` 使用 `prefix+shift+t`，
先将它移到其它未占用键，再给 Viewer 使用。已有 `[keys]` 时合并字段，不要重复声明该表：

```toml
[keys]
rename_tab = "prefix+shift+y"

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

[[keys.command]]
key = "prefix+shift+c"
type = "plugin_action"
command = "sessmark.config-windows"
description = "edit sessmark tags, pipelines and prompts"
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

在 Agent pane 按 `prefix+t`：`/` 搜索标签名或 Prompt，Space 勾选 tag，`n` 新增预设，`e` 打开词表，Tab 写一行 note，Enter / Ctrl+S 原子保存，Esc 取消。搜索时按 Enter 或 ↓ 返回列表；跨筛选保留勾选，底部显示已选标签和隐藏数量。
`prefix+shift+c` 直接打开词表（不必先打开标记窗）。
标记窗打开时捕获目标 pane；保存前重新核对 terminal 和 native 身份。已确认的会话若改变，则拒绝保存并提示重新打开。

`prefix+shift+t` 打开 Viewer：上下选中，`/` 实时搜索所有备注、标签、路径或 ID（空格分隔，AND）；用 `tag:keep` 精确筛选标签。时间按钮 / `F2` 切换全部、今天、近 7 天，Agent 按钮 / `F3` 切换来源；`Ctrl+L` 清空全部筛选，`r` 刷新。
在列表按 Enter 回到已验证的原 Agent pane，或在新的 HerdR tab 恢复。`y` 复制当前条目的可读摘要（id / tags / notes / locator / prompt），不是 PowerShell 命令。
按 `d` 或点击「删除」删除选中 Session 的全部标注；确认窗显示目标 ID、标签和备注，默认取消。删除后保留筛选并刷新列表，原始对话文件保留。若确认期间标注发生变化，会要求刷新后重新确认。
Agent 批量读取今天的标记用 `sessmark export --since today --json`。UI 不编辑旧 notes，移除 tag 用 CLI。

三个弹窗都采用简短列表 + 完整详情，宽窗口左右分栏、窄窗口上下排列；`F4` 切换到详情滚动阅读，`Esc` 返回列表。底部按钮可点击，焦点区域和当前行有高亮。Prompt 编辑支持 `Alt+Enter` 换行、`Ctrl+S` 保存。
默认 popup 使用固定终端单元格尺寸：标记 / 词表 `120 列 × 32 行`，Session 浏览 `132 列 × 36 行`，替代原来的 `92% × 88%`，避免大屏下接近全屏。

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
0.8.2 的 popup/overlay 不允许 `--target-pane`；标记入口只通过 `SESSMARK_TARGET_PANE` 环境变量
固定标注对象，打开前和保存前仍验证身份。

Grok native ID 足够生成 `grok --resume ID`。官方只给 ID 时，transcript_path 为 null；
不会臆造 cwd slug。显式传入完整路径可补齐 `~/.grok/sessions/<encoded-cwd>/<id>/chat_history.jsonl` 提示。

若原 pane 关闭而 pending 未绑定，执行 `sessmark bind sm_ID --harness grok --session-id REAL_ID`。
不同 HerdR endpoint、不同 terminal、不同 native ID 不直接聚焦旧 pane。
HerdR 外使用 `sessmark resume`，不需要安装/启动该插件。

2026-09-06 已在本机 HerdR 0.8.2 执行真实 plugin link。该版本不支持插件事件 `pane.updated`，
因此使用 agent detected/status changed 事件，并保留显式 sync 和 Viewer 启动刷新作为补偿。
用户提供的 Grok 实机报告已验证 overlay 内的标记/Viewer、pending sync 和关 pane 后新 tab resume。
报告发现的 popup 参数与复制命令 PATH 依赖已修复并增加回归测试。物理快捷键、popup 内 IME 和 macOS 仍需验收。

### Grok `/new` 的宿主限制

报告显示：同一 Grok 进程 `/new` 后，HerdR 可能仍返回旧 native ID。已核对本机
`~/.grok/hooks/herdr-agent-state.ps1` 优先取 `GROK_SESSION_ID`，只有其为空才读 hook payload。
这时 sessmark 无法从相同的宿主响应识别新会话，`sync` 也不会纠正旧 ID。
暂用退出并重启 Grok 的方式切会话，或通过纯 CLI 显式指定真实的新 native ID。
已误写到旧 native 记录的 note 不会自动迁移，`bind` 也不会改写已确立的 native 身份。
本工具未修改 HerdR 安装管理的 hook；不要将 `/new` 的同进程切换列为通过。
