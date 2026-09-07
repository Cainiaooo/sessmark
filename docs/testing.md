# 验证

2026-09-07 弹窗交互优化：86 项自动测试通过，Ruff 和差异检查通过。覆盖实时搜索、历史备注查询、时间 / Agent 组合筛选、跨筛选保留勾选、多行 Prompt、子窗口返回和取消按钮；四个界面均检查了 120×32、80×24、64×20 的终端渲染。HerdR popup 启动请求成功；桌面截图工具因 native pipe 不可用，实机视觉验收仍待补充。

2026-09-06 本机 Windows / Python 3.14：41 项自动测试通过；Ruff 检查通过。首版核心与适配的 wheel/sdist 构建通过。
另在全新 venv 仅安装核心 wheel（`--no-deps`），确认未安装 HerdR adapter 或 prompt-toolkit，
仍可完整运行中文 tag/note/context 和 resume dry-run。跨平台 CI 已配置。
随后安装的 HerdR 0.8.2 已完成真实 plugin link，清单无警告；Windows PowerShell 启动命令也使用
HerdR 实际返回的 `\\?\` 路径前缀执行通过。server 已由用户启动并完成以下实机验证。

## 实机报告与修复状态

用户委托 Grok 的 Windows / HerdR 0.8.2 验证报告：

| 项目 | 证据与边界 |
| --- | --- |
| 独立 CLI、中文 context、多模板/未知 tag 错误 | 通过；终端字形/编码显示问题与 UTF-8 内容正确性分开判断 |
| 标记、Viewer 过滤/Enter、pending sync | 在 overlay 驱动同一套 TUI 通过 |
| 关闭 pane 后从 Viewer 恢复 | 新 tab 恢复正确会话，通过 |
| mark popup action | 原来因 `--target-pane` 失败；已删除该参数，保留环境 pin 与身份校验 |
| Viewer 复制命令 | 原来依赖 PATH；已改为绝对 Python 路径，空 PATH/未激活 venv 的新 shell 执行测试通过。2026-09-07：`y` 改为复制可读摘要，不再复制 PowerShell 命令 |
| Viewer 快捷键 | 与默认 rename_tab 冲突；文档补充先改绑 rename_tab |
| 同 pane 新进程 | 通过；新会话不继承旧 note |
| Grok 同进程 `/new` | 未通过；宿主 hook 上报旧 ID，见 herdr.md 的限制说明 |
| 物理 Ctrl+B、popup IME、macOS 实机 | 未验证 |

修复后，本轮实际调用 `herdr plugin action invoke mark-windows --plugin sessmark`，
`plugin-log-19` 为 `succeeded`、exit code 0、stdout `{"type":"ok"}`、stderr 空；
对应 `sessmark_herdr mark` 进程仍在运行。目标为当前测试会话 `w1:p6`。
这证明同一 plugin action 的 popup 启动路径已恢复，不等同于物理按键和 IME 验收。

## 自动测试

```powershell
.venv\Scripts\python.exe -m pip install -e ".[ui,dev]" -e adapters\herdr
New-Item -ItemType Directory -Force .test-runs | Out-Null
$testRun = Join-Path .test-runs ([guid]::NewGuid().ToString('N'))
.venv\Scripts\python.exe -m pytest -q --basetemp $testRun
.venv\Scripts\ruff.exe check src tests adapters/herdr/src adapters/herdr/tests plugins/herdr conftest.py
.venv\Scripts\python.exe -m build
.venv\Scripts\python.exe -m build adapters/herdr
```

默认 pytest 临时目录在这台机器上出现 `PermissionError: [WinError 5]`，故测试用新的项目内 basetemp；
没有修改系统 Temp ACL。不要复用包含有价值文件的 basetemp，pytest 会清理该目录。

自动覆盖：native 去重、两个方向的 pending 合并、永久 ID alias、跨进程竞争、事务中断回滚、
pane incarnation/native 变化、手动 bind、未知 tag、模板歧义、日界/滚动窗口、中文 JSON、
argv/cwd 执行、standalone import、UI 保存/取消/选择键盘流程，以及 HerdR JSON/launch 命令契约。

## HerdR 实机验收步骤

1. 安装 adapter、link 插件、启用实际 harness integration、添加快捷键并 reload。
2. 在一个测试 Agent pane 跑真实 Session。`herdr pane get <pane>` 确认有 terminal_id 和 agent_session。
3. 按 `prefix+t` 选 review:problem、写中文 note 并保存；`sessmark list --since today --json` 应只有一条该 Session。
4. 加第二个 tag harvest:doc；两次按 tag 列表都可找到。context 不选 route 应报歧义，显式 `--tag` 可获得对应模板。
5. 在真实 native ID 尚未上报时创建标记，等上报后 `sessmark-herdr sync`；ID 保留、tags/notes 保留、时间不因 sync 改变。
6. 在同 pane 切新 native Session；新标记必须是另一个 ID，旧 notes 不继承。
7. Viewer `/` 过滤；Enter 能回原 Session；`y` 在 PowerShell 粘贴后生成正确 context，中文路径完整。
8. 关闭原 pane，Viewer Enter 在新 tab 执行正确 resume argv；不向其它活 pane 注入命令。
9. 卸载/禁用 adapter 后，在普通 PowerShell 用显式 ID 做 tag/note/list/context/resume，确认仍工作。
10. 在 macOS 重复 CLI 和 popup 验收，尤其本地日界、python3、pbcopy、harness 可执行入口。

## 非承诺

pipe-input UI 测试验证了交互逻辑，未替代真实终端视觉、IME 和剪贴板验收。
合成 HerdR 响应测试未替代交互验收；用户报告中的 overlay 验证不等于 popup 内物理键盘/IME 验证。
