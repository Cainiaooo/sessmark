# sessmark

给 Agent Session 打 tag / 写 note。数据在 sidecar SQLite，不改 transcript。

## 看今天的标注

在仓库根：

```
.venv/Scripts/python.exe -m sessmark export --since today --json
```

macOS/Linux：`.venv/bin/python -m sessmark export --since today --json`

输出是 `sessmark.context.v1` 数组。先读 `notes` 和 `tags`，再按 `locator` 打开原 Session。不要重做原任务。`prompt` 为 null 表示多个流水线模板，用 `--tag` 显式选。

单条：

```
.venv/Scripts/python.exe -m sessmark context <sm_ID> --json
```

按 tag：`export --tag review:problem --since today --json`

## 加 tag 类型

人在 HerdR 里用 `prefix+shift+c`（或标记窗的 `n` / `e`）改词表，不要替用户去跑 `--add-tag`，除非他们明确要求脚本化。

配置文件：`%APPDATA%\sessmark\templates.toml`。不要改仓库 `defaults.toml`，除非在改默认词表。
