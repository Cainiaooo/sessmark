# 设计与 v1 合同

输入规格：[issue #1](https://github.com/Cainiaooo/herdr-dev-env-template/issues/1) 与其 horizon 评审。
目标是人标记 Session，自动化读取引用并按 tag 分流。不是选中文字批注、全文导出、会话浏览器或 handoff。

## 解耦

依赖方向为 `sessmark-herdr -> sessmark`。核心包没有 HerdR 依赖、环境变量检测或主机选择。
外部宿主只提供 `Locator`、绝对 cwd、可选 `Binding(source, key, generation, metadata)`。
`sessmark mark/ui` 复用通用终端 UI；HerdR 把保存前的身份复核和打开动作作为回调传入。
HerdR adapter 是单独可安装的 distribution，插件 manifest 不进入核心 wheel。

## 身份、并发和失败

- native 唯一键为 `(harness, session_id)`，本地不跨机器同步。cwd/path 不决定 native 身份。
- 没有 native ID 时按外部 binding 创建 pending；没有 binding 的核心 CLI 要求显式 native ID。
- HerdR binding 的 key 是 JSON 编码 `[endpoint, pane_id]`，generation 是 `terminal_id`。
  endpoint 优先 `HERDR_SOCKET_PATH`，否则 `HERDR_SESSION/default`，对应 CLI 的实际路由优先级。
- 同 incarnation 的 pending 遇到 native ID 会升级；若 native 已存在，保留最早创建的 `sm_<uuid4>` ID，
  tags 取并集、notes 全保留，所有旧 ID 变成直达别名，直到用户删除该标注。ID 为不透明字符串，不承诺 ULID 排序。
- 已有 native A 遇到 B、不同 harness、不同 terminal_id，不能把旧标记迁到新 Session。
- 每次写入使用一个 SQLite `BEGIN IMMEDIATE` 事务，native 唯一约束负责跨进程竞争；15 秒 busy timeout。
  Schema 创建也在事务中。使用 SQLite 默认 rollback journal / FULL 同步，不关闭崩溃恢复。
- 一个 `Store` 对应一个线程；跨线程/进程各开自己的连接。存储应在本机磁盘，不支持网络共享目录并发承诺。
- `tag`/`untag` 的集合操作幂等，但再次手工标记会推进 updated_at；`note` 是追加事件，重试会再追加。
  `observe` / 自动 rebind 只刷新 observed_at，保留人标记的 updated_at；显式 `bind` 也不重置时间。
- 自动 hook 只更新已标记的 binding，不把所有 pane 收录为历史。原 pane 丢失后仍可离线读取。

pending 不是已确认的 native 身份：如果没有 integration、事件丢失，且同一终端内在首次上报前换了多个 Session，
宿主没有提供足够信息来证明它们的边界。不要依赖 pending 做自动恢复；启用 integration 并检查 `locator.kind`。
无法自动证明时保留记录，用 `bind` 显式修复。path-only 的 Pi reference 不被当成全局主键，跨 pane 不按路径合并。

## JSON

`list --json` 输出一个数组，`--jsonl` 输出 NDJSON。原 issue 的文字和 jq 示例矛盾，选择与 `.[].id` 一致的数组。
字段见 [Session schema](../schemas/session.v1.schema.json) 和 [context schema](../schemas/context.v1.schema.json)。
时间统一为 UTC、带 offset 的 ISO 8601，按字符串也能比较；`today` 用本机本地日界，`1d` 是 86400 秒。
重复 tag 过滤是 AND；按 updated_at 降序，同时间按 ID 稳定排序。`notes_preview` 是最新一条 note，最多 160 字符。

context 的 `partial` 保守地恒为 true，因为不解析 transcript，也不把 HerdR 的 idle/done 当“会话永不再变化”的保证。
`prompt` 是单个模板或 null。多路由报错要求显式选择；没有路由不伪造流水线任务。notes 永远保留为单独字段。
后续增加字段允许向后兼容，改字段含义或类型须升级 schema。

## 原计划的调整

| 原描述 | 实现决定 |
| --- | --- |
| 核心 CLI 无参数读取 focused pane | 核心显式 ID/环境；`sessmark-herdr` 专门负责宿主检测 |
| `HERDR_PANE_ID` 作为 popup 当前 pane | popup 读取 launch context/active pane，不会标到 popup 自己 |
| `herdr pane current --json` | 官方 pane 查询默认返回 JSON，不传不支持的 `--json` |
| `agent_session.id/path` 假设 | 读取官方 `kind/value/agent/source` |
| 临时键只有 session + pane | 加 terminal incarnation，降低 pane ID 重用导致的串标风险 |
| Path 看起来固定 | 只保存明确提供的路径；未知时 null，不扫描或猜最近 transcript |
| 多 tag 默认选 prompt | 多个不同模板要求显式选择，保证自动化可预测 |
| 所有 resume 都回原 pane | 先验证同 native 身份；否则 HerdR 新建 tab，通用 CLI 在当前终端启动 |

HerdR 聚焦的验证与 focus 两次调用之间仍有宿主 API 的竞态窗口；没有原子的“检查身份并聚焦”接口。
本工具只聚焦，不往原 pane 注入消息或按键。Popup 保存前复核身份，但同样无法让宿主与本地 SQLite 成为一个跨系统事务。
复核只能判断宿主上报的身份；Grok `/new` 后宿主若继续报告旧 ID，不能由本地去重逻辑识别。
该已复现的 integration 限制及临时操作方式见 [HerdR 接入](herdr.md)。

## 边界

不保存全文、不改 Agent 原始数据、不执行模板、不调用模型、不自动更改 Skill/上下文。
命令以 argv 执行且不使用 shell。Windows `.cmd/.bat` 可能隐式进入 cmd.exe，因此执行器拒绝此类入口并提示使用 exe argv。
未知 harness 仍可存储和输出 context；没有配置 resume argv 时恢复明确报错。
不承诺通用自动脱敏，避免破坏 locator；消费侧必须决定哪些内容可以送给下游。
