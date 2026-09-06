# 验证

2026-09-06 本机 Windows / Python 3.14：36 项自动测试通过；Ruff 检查通过；核心与适配的 wheel/sdist 构建通过。
另在全新 venv 仅安装核心 wheel（`--no-deps`），确认未安装 HerdR adapter 或 prompt-toolkit，
仍可完整运行中文 tag/note/context 和 resume dry-run。跨平台 CI 已配置。
随后安装的 HerdR 0.8.2 已完成真实 plugin link，清单无警告；Windows PowerShell 启动命令也使用
HerdR 实际返回的 `\\?\` 路径前缀执行通过。server 尚未运行，交互验收仍待进行。

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

## HerdR 实机验收（尚待运行）

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
合成 HerdR 响应测试未替代交互验收；真实插件清单加载已检查，尚未启动 Agent 或验证 popup。
