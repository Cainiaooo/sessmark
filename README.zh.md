# sessmark

[English](README.md) | [中文](README.zh.md)

给 Agent **Session 对象**打 tag、写 note，并输出可供自动化解引的引用包。
不修改 Agent transcript，不调用模型，不依赖 HerdR。Python 3.11+；Windows 优先，支持 macOS/Linux 的路径与终端接口。

来自 [herdr-dev-env-template issue #1](https://github.com/Cainiaooo/herdr-dev-env-template/issues/1)。
实现代码和环境配置仓库分开维护。

终端 UI 和首次写出的词表跟随系统语言，也可用 `SESSMARK_LANG=en` / `SESSMARK_LANG=zh`。已有的 `templates.toml` 不会被覆盖。

## 安装

`sessmark` 是用户级 CLI：数据在 `~/.local/share/sessmark/`（可用 `XDG_DATA_HOME` 覆盖），不跟某个项目走。尚未发布到 PyPI。不要把 `sessmark-herdr` 装到全局；HerdR 插件自带运行时。

### 日常使用（推荐）

需要 [uv](https://docs.astral.sh/uv/)。命令会进 `~/.local/bin`（Windows 上是 `%USERPROFILE%\.local\bin`），该目录应已在 `PATH` 里。

```powershell
cd path\to\sessmark
uv tool install -e ".[ui]"
sessmark --help
```

macOS/Linux 同样命令。这是 editable 安装，改本仓库源码后不用重装；依赖或 extras 变了再跑一次同一条命令。

只要跑流水线、不要 TUI：`uv tool install -e .`

卸装：`uv tool uninstall sessmark`。

### 开发本仓库

测试、打包、本地 `herdr plugin link` 仍用仓库 `.venv`：

```powershell
cd path\to\sessmark
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[ui,dev]"
.venv\Scripts\Activate.ps1
sessmark --help
```

macOS/Linux：`python3 -m venv .venv`，`source .venv/bin/activate`，再 `python -m pip install -e '.[ui,dev]'`。
激活 venv 后当前 shell 也能打 `sessmark`，这不能代替上面的用户级安装。

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
sessmark mark   # / 实时搜索标签，Space 多选，Tab 写 note，Enter 保存
sessmark ui     # / 搜索备注/路径/ID，F2 时间，F3 Agent，Enter resume，y 复制摘要
```

`SESSMARK_ID` 可以直接绑定已有的 sessmark ID；显式 `--harness/--session-id` 优先于环境 ID。
`--id` 不能和 locator 参数混用。终端 UI 的 mark 是追加 tags/一条 note；移除 tag 用 `untag`。
删除整条 Session 的标注：在 `sessmark ui` 中选中条目，按 `d` 或点击「删除」，确认窗默认选中取消。删除包括该条目的标签、备注和关联记录，原始 Session / transcript 文件保留。命令行可用 `sessmark delete <sm_ID> --yes`（支持 `--json`）。删除后无法通过旧 sessmark ID 读取；再次标记同一原始 Session 会得到新 ID。

## 流水线

`--json` 是 JSON **数组**；`--jsonl` 是一行一个对象。错误写 stderr 并退出 2，不污染 stdout。

Agent 看今天的标注（推荐）：

```powershell
sessmark export --since today --json
```

`sessmark` 不在 `PATH` 上时，说明还没做用户级安装，不要猜测某个仓库的 `.venv` 路径。在本仓库里开发时，Agent 仍按 `AGENTS.md`（venv）调用。

不传 `--json` 时 `export` 打印给人看的摘要。按 tag 收窄：`export --tag review:problem --since today --json`。
`export --tag` 同时筛选 Session 和流水线；多个 `--tag` 要求 Session 全部具备这些标签，并只在这些标签中选择 Prompt。仍匹配多个模板时，JSON 中 `prompt` 为 null。

单条 context 仍可用：

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

多个 tag 匹配不同模板时，不传 `--tag` / `--template` 会明确失败。只有 `keep` / `prio:p0` 时 `prompt` 为 null（`keep:archive` 会走存档流水线）。

词表（tag / 流水线 / Prompt）是个人配置，不必为加一条预设去敲命令。

HerdR 里：`prefix+shift+c` 打开词表窗；标记窗里 `n` 新增、`e` 打开同一套编辑器。
`n` 填标签名，Prompt 留空 = 仅检索（如 `keep`），填写 = 流水线（如 `review:ux`）。
词表窗里 `Enter` 改 Prompt，`d` 删除，`o` 用系统编辑器打开 `~/.config/sessmark/templates.toml`。
标记窗和词表窗都支持 `/` 或 `Ctrl+F` 搜索标签名、流水线和 Prompt；`Ctrl+L` 清空，搜索框内 `Enter` / `↓` 回到结果。筛选不会丢失已勾选的标签。
宽窗口左右分栏，窄窗口上下排列；`F4` 切到详情后用方向键 / PageDown 阅读长内容，`Esc` 返回列表。常用操作也有可点击按钮。编辑 Prompt 时 `Alt+Enter` 换行，`Ctrl+S` 保存。

Session 浏览窗搜索所有历史备注、标签、目录和 ID，空格分隔的关键词同时满足；`tag:review:problem` 可精确筛选标签。时间按钮（`F2`）切换全部 / 今天 / 近 7 天，Agent 按钮（`F3`）切换来源，`Ctrl+L` 重置全部筛选，`r` 刷新。

```powershell
sessmark config --ui              # 同上的 TUI
sessmark config                   # 查看路径、词表和路由
sessmark config --init            # 写出可编辑副本；已存在会拒绝覆盖
sessmark config --add-tag later   # 可选：脚本里追加
```

默认词表：

| tag | 流水线 |
| --- | --- |
| `review:problem` | 延后问题复盘 |
| `fix:tool` | 审查本次用到的自研工具，是否要优化/修复/补齐 |
| `review:context` | 审查本次用到的记忆文档、Skill 等上下文是否偏差 |
| `write:doc` | 编写与本次 Session 相关的文档 |
| `harvest:asset` | 把方案、经验、调研沉淀成可复用资产 |
| `harvest:doc` | 提炼个人技术积累（不写回项目 README） |
| `keep:archive` | 重要 Session 存档说明，供单独备份和日后审阅 |
| `fix:skill` | 改 Skill 行为 |
| `fix:context` | 改项目上下文/规则缺口 |
| `keep` | 仅检索，不进流水线 |
| `prio:p0` | 今晚优先，不进流水线 |

未知 tag 在新增、过滤中报错；退出词表的历史标签仍可用 `untag` 移除。原 issue 示例中的 `prio:p1` 不在默认表中。模板不自动插值 notes、路径或 transcript。不要改仓库 `defaults.toml` / `defaults.en.toml`，除非在改默认词表。

## HerdR 是可选适配

```powershell
.venv\Scripts\python.exe -m pip install -e adapters\herdr
herdr plugin link $PWD\plugins\herdr
```

在已配置 integration 的 HerdR pane 中可直接 `sessmark-herdr tag keep`。
`prefix+t` 标记、`prefix+shift+t` Viewer 的配置和联调步骤见 [HerdR 接入](docs/herdr.md)（[English](docs/herdr.en.md)）。
HerdR 0.8.2 须先移开默认 `rename_tab` 对 `prefix+shift+t` 的占用，接入文档有完整配置。
没有安装适配包时，`sessmark` 所有核心命令照常可用；核心既不导入适配模块，也不检查 `HERDR_*`。

### 插件市场

HerdR 的 [插件市场](https://herdr.dev/plugins/) 是公开 GitHub 仓库的自动索引，不是审核队列，没有投稿表。

要被收录：

1. 仓库必须是 **public**。
2. 给仓库加上 GitHub 主题标签 **`herdr-plugin`**。
3. 默认分支上至少有一份可解析的 `herdr-plugin.toml`（必需字段：`id`、`name`、`version`、`min_herdr_version`）。文件可以在仓库根或子目录。

本仓库清单在 [`plugins/herdr/herdr-plugin.toml`](plugins/herdr/herdr-plugin.toml)。索引大约每 30 分钟刷新，默认分支有新 commit 时也会重扫。Fork、已归档仓库和无效清单会被排除。被列出不等于 HerdR 审查过，见官方 [信任指南](https://herdr.dev/zh-cn/docs/plugins/#信任与安全)。

从 GitHub 安装（仓库已是公开且带上该 topic 之后）：

```powershell
herdr plugin install Cainiaooo/sessmark/plugins/herdr
```

安装时会跑 `plugins/herdr/bootstrap.py`：在插件目录建 venv，并从同一份 checkout 安装 `sessmark[ui]` 和 `sessmark-herdr`。需要 PATH 上有 Python 3.11+（Windows 用 `python`，macOS/Linux 用 `python3`）。本地开发仍用 `herdr plugin link` 和仓库 `.venv`；`plugin link` 不会跑 build。

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
已知限制：Grok 同进程 `/new` 时宿主可能仍上报旧 ID；修正 hook 前请重启 Grok 或在核心 CLI 显式指定新 ID。

## 存储与 locator

数据：`${XDG_DATA_HOME:-~/.local/share}/sessmark/index.sqlite`。配置：`${XDG_CONFIG_HOME:-~/.config}/sessmark/templates.toml`。
Windows 会从 `%LOCALAPPDATA%\sessmark` / `%APPDATA%\sessmark` 做一次拷贝，包括 Microsoft Store 版 Python 的 `LocalCache`；设置了 `XDG_DATA_HOME` / `XDG_CONFIG_HOME` 则不做拷贝。Store 版 Python 会虚拟化 AppData，用户级 CLI 和基于 Store 的 venv 无法共用放在那里的库。
可用 `--db` / `SESSMARK_DB` 和 `--config` / `SESSMARK_CONFIG` 覆盖。

native 身份主键为 `(harness, session_id)`，path 只是可为空的提示。Grok/Claude/Codex/OpenCode/Pi 提供默认 resume argv，其他 harness 可显式传 `--resume-json`。
Windows 执行器要求原生 exe；对于仅有 `.cmd` 包装器的安装，可提供 `node.exe + CLI 脚本 + 参数` 的完整 argv。
`resume --dry-run` 或 `resume --json` 只展示计划，正常 `resume` 才启动进程。

HerdR 还没提供 native ID 时先存 pending；出现 ID 后以事务合并 tags/notes，旧 sessmark ID 作为别名保留，直到用户删除该条标注。
若原 pane 已关闭，可显式修复：

```powershell
sessmark bind sm_旧ID --harness grok --session-id 真实ID
```

context 永远只引用 transcript；`partial: true` 表示无法保证原会话已完成或引用内容不会继续变化。
本地 note 和路径会原样出现在输出中；向外部服务发送前由消费侧决定脱敏与权限，不会自动上传。
