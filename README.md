# sessmark

给 Agent **Session 对象**打 tag、写 note，并输出可供自动化解引的引用包。
不修改 Agent transcript，不调用模型，不依赖 HerdR。Python 3.11+；Windows 优先，支持 macOS/Linux 的路径与终端接口。

来自 [herdr-dev-env-template issue #1](https://github.com/Cainiaooo/herdr-dev-env-template/issues/1)。
实现代码和环境配置仓库分开维护。

## 安装

从这个仓库安装，尚未发布到 PyPI。CLI 核心没有第三方运行时依赖。

```powershell
cd D:\Project\sessmark
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
.venv\Scripts\Activate.ps1
sessmark --help
```

macOS/Linux：`python3 -m venv .venv`，`source .venv/bin/activate`，再 `python -m pip install -e '.[ui,dev]'`。
只跑流水线可用 `python -m pip install .`，不装 UI 或 dev extras。

## 在任何终端使用

先明确真实的 native Session ID；工具不会把“当前目录最新的文件”猜成当前 Session。

```powershell
$id = sessmark tag review:problem --harness grok --session-id a1b2c3 --cwd D:\work\proj
sessmark note "工具超时后死循环，后续检查 backoff" --id $id
sessmark tag prio:p0 --id $id
sessmark show $id
sessmark context $id --json
sessmark resume $id --dry-run
sessmark resume $id
```

也可先 `sessmark register --harness grok --session-id a1b2c3`，或设置显式上下文：

```powershell
$env:SESSMARK_HARNESS = 'grok'
$env:SESSMARK_SESSION_ID = 'a1b2c3'
sessmark tag keep
sessmark note "以后回看"
sessmark mark   # 可选 UI：Space 选 tag，Tab 写 note，Enter 保存，Esc 取消
sessmark ui     # 查看已标 Session，/ 按 tag 过滤，Enter resume，y 复制 context 命令
```

`SESSMARK_ID` 可以直接绑定已有的 sessmark ID；显式 `--harness/--session-id` 优先于环境 ID。
`--id` 不能和 locator 参数混用。终端 UI 的 mark 是追加 tags/一条 note；移除 tag 用 `untag`。

## 流水线

`--json` 是 JSON **数组**；`--jsonl` 是一行一个对象。错误写 stderr 并退出 2，不污染 stdout。

```powershell
sessmark list --tag review:problem --since today --json |
  ConvertFrom-Json | ForEach-Object {
    sessmark context $_.id --tag review:problem --json
  }
```

`today` 是本机当天 00:00，`1d` 是滚动 24 小时。支持带时区 ISO 8601、`24h`、`30m`。
时间按人为标记的 `updated_at`；`--since` 包含边界，`--until` 不包含边界。重复 `--tag` 为 AND。
同一个 Session 可以同时属于多个流水线；同一次查询只返回一次。

```powershell
sessmark tag harvest:doc --id $id
sessmark context $id --tag harvest:doc --json
sessmark context $id --template review-problem --json
```

多个 tag 匹配不同模板时，不传 `--tag` / `--template` 会明确失败。只有 `keep` / `prio:p0` 时 `prompt` 为 null。

模板和词表放 TOML，可初始化后修改：

```powershell
sessmark config --init  # 已存在会拒绝覆盖
sessmark config        # 查看路径、词表和路由
```

默认词表：`review:problem`、`harvest:doc`、`fix:skill`、`fix:context`、`keep`、`prio:p0`。
未知 tag 在写入、过滤和 context 路由中均报错。原 issue 示例中的 `prio:p1` 不在冻结表中，默认拒绝。
新增 tag 须同时更新个人配置的 `allowed_tags` 和相关流水线；模板不自动插值 notes、路径或 transcript。

## HerdR 是可选适配

```powershell
.venv\Scripts\python.exe -m pip install -e adapters\herdr
herdr plugin link D:\Project\sessmark\plugins\herdr
```

在已配置 integration 的 HerdR pane 中可直接 `sessmark-herdr tag keep`。
`prefix+t` 标记、`prefix+shift+t` Viewer 的配置和联调步骤见 [HerdR 接入](docs/herdr.md)。
没有安装适配包时，`sessmark` 所有核心命令照常可用；核心既不导入适配模块，也不检查 `HERDR_*`。

## 库接口与目录

```python
from pathlib import Path
from sessmark import Locator, Store

with Store(Path.home() / ".local/share/sessmark/index.sqlite") as store:
    row = store.mark(locator=Locator("grok", "a1b2c3"),
                     cwd=str(Path.cwd()), tags=["keep"], note="以后回看")
    package = store.context(row["id"])
```

| 路径 | 职责 |
| --- | --- |
| `src/sessmark` | 通用库、CLI、可选终端 UI；零 HerdR import |
| `adapters/herdr` | 单独的 Python distribution；识别 pane、刷新身份、聚焦和打开新 tab |
| `plugins/herdr` | HerdR 清单和 Windows/macOS 启动层 |
| `schemas` | `sessmark.context.v1` 与 Session JSON Schema |
| `tests`、`adapters/herdr/tests` | 存储、CLI、UI 输入、适配契约测试 |

详细语义和取舍见 [设计与合同](docs/design.md)，验证与已知边界见 [测试说明](docs/testing.md)。

## 存储与 locator

Windows：`%LOCALAPPDATA%\sessmark\index.sqlite`；配置 `%APPDATA%\sessmark\templates.toml`。
macOS/Linux：`${XDG_DATA_HOME:-~/.local/share}/sessmark/index.sqlite`；配置 `${XDG_CONFIG_HOME:-~/.config}/sessmark/templates.toml`。
可用 `--db` / `SESSMARK_DB` 和 `--config` / `SESSMARK_CONFIG` 覆盖。

native 身份主键为 `(harness, session_id)`，path 只是可为空的提示。Grok/Claude/Codex/OpenCode/Pi 提供默认 resume argv，其他 harness 可显式传 `--resume-json`。
Windows 执行器要求原生 exe；对于仅有 `.cmd` 包装器的安装，可提供 `node.exe + CLI 脚本 + 参数` 的完整 argv。
`resume --dry-run` 或 `resume --json` 只展示计划，正常 `resume` 才启动进程。

HerdR 还没提供 native ID 时先存 pending；出现 ID 后以事务合并 tags/notes，旧 sessmark ID 永久作为别名保留。
若原 pane 已关闭，可显式修复：

```powershell
sessmark bind sm_旧ID --harness grok --session-id 真实ID
```

context 永远只引用 transcript；`partial: true` 表示无法保证原会话已完成或引用内容不会继续变化。
本地 note 和路径会原样出现在输出中；向外部服务发送前由消费侧决定脱敏与权限，不会自动上传。
