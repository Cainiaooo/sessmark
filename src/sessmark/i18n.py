"""UI language: SESSMARK_LANG, then locale. zh and en catalogs."""

import os
import sys


def _is_chinese(value: str) -> bool:
    lowered = value.replace("-", "_").lower()
    return lowered.startswith("zh") or "chinese" in lowered


def _system_language() -> str:
    if sys.platform == "win32":
        try:
            import ctypes

            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF == 0x04:
                return "zh"
        except (AttributeError, OSError, ValueError):
            pass
    try:
        import locale

        loc = locale.getlocale()[0] or locale.getdefaultlocale()[0] or ""
        if _is_chinese(loc):
            return "zh"
    except (TypeError, ValueError):
        pass
    return "en"


def language() -> str:
    explicit = os.environ.get("SESSMARK_LANG", "").strip()
    if explicit:
        return "zh" if _is_chinese(explicit) else "en"
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(key, "").strip()
        if value and value.split(".")[0] not in {"C", "POSIX"}:
            return "zh" if _is_chinese(value) else "en"
    return _system_language()


def packaged_defaults() -> str:
    return "defaults.toml" if language() == "zh" else "defaults.en.toml"


def t(key, **kwargs):
    catalog = ZH if language() == "zh" else EN
    text = catalog.get(key) or EN[key]
    return text.format(**kwargs) if kwargs else text


EN = {
    "tag.pipeline": "→ pipeline",
    "tag.lookup": "· lookup",
    "tag.empty_detail": "No matching tags.\n\nTry a shorter query, or Ctrl+L to clear search.",
    "tag.lookup_detail": "{tag}\n\nLookup only\n\nFor saving and finding sessions. Does not start a pipeline.",
    "tag.pipeline_detail": "{tag}\nPipeline · {route}\n\n{text}",
    "empty_rows": "No matches · Ctrl+L to clear",
    "editor.status": "Enter / Ctrl+S save · Alt+Enter newline · Tab switch · Esc cancel",
    "editor.title_new": "sessmark  ·  New tag",
    "editor.title_edit": "sessmark  ·  Edit  {tag}",
    "editor.hint": "  Empty prompt = lookup only; filled prompt = pipeline.",
    "editor.panel_name": "Tag name · e.g. review:ux / keep / harvest:wiki",
    "editor.panel_prompt": "Pipeline prompt · multiline",
    "btn.save": "Save Enter",
    "btn.cancel": "Cancel Esc",
    "config.status": "Enter edit · / search · F4 detail · d delete · Esc back",
    "config.count": "  {shown} / {total} tags · search names, pipelines, or prompts",
    "config.deleted": "Deleted {tag} · existing marks are kept",
    "config.opened_file": "Opened the config file · press r after saving to reload",
    "config.reloaded": "Reloaded config",
    "config.add": "New n",
    "config.edit": "Edit Enter",
    "config.open_file": "Open file o",
    "config.back": "Back Esc",
    "config.title": "sessmark  /  Tags and pipelines",
    "config.search": "Search · Ctrl+L to clear",
    "config.panel_tags": "Tags",
    "config.panel_detail": "Use / full prompt",
    "mark.pending_id": "waiting for session ID",
    "mark.status": "Space select · Tab note · Enter save · F4 detail · Esc cancel",
    "mark.count": "  {shown} / {total} tags · F4 for detail · filter keeps checks",
    "mark.added_tag": "Checked {tag} · add more tags or type a note",
    "mark.need_input": "Check a tag or type a note · / search tags, Tab for note",
    "mark.add": "New n",
    "mark.vocab": "Vocab e",
    "mark.title": "sessmark  /  Mark this session",
    "mark.search": "Search tags / prompts · Ctrl+L to clear",
    "mark.panel_tags": "Tags · Space to multi-select",
    "mark.panel_detail": "Use / full prompt",
    "mark.note": "Note · what you will need when you come back",
    "mark.hidden": " · {hidden} selected outside the filter",
    "mark.selected": "  Selected {count}{suffix}  {tags}",
    "mark.none": "none yet",
    "row.tags_only": "(tags only)",
    "detail.tags": "Tags  {tags}",
    "detail.none": "none",
    "detail.notes": "Notes",
    "detail.no_notes": "  No notes yet",
    "detail.source": "Source",
    "detail.cwd": "  Dir    {cwd}",
    "detail.id": "  ID     {id}",
    "detail.session": "  Session  {session}",
    "detail.pending_bind": "waiting to bind",
    "detail.transcript": "  Transcript  {path}",
    "detail.missing_path": "not provided",
    "detail.pipeline": "Pipeline · {name}",
    "delete.cancel": "Cancel",
    "delete.confirm": "Delete marks",
    "delete.title": "sessmark  /  Delete marks for this session?",
    "delete.body": "  This deletes {tags} tags and {notes} notes. This cannot be undone.",
    "delete.keep_files": "  The original session / transcript files are kept.",
    "delete.panel": "Confirm target",
    "delete.status": "Tab switch · Enter confirms the focused button · Esc cancel",
    "delete.cwd": "Dir      {cwd}",
    "viewer.status": "Enter open · F4 detail · / search · d delete · Esc close",
    "viewer.empty": (
        "No matching sessions\n\n"
        "Try a shorter query, or clear the time / agent filters.\n\n"
        "Search covers notes, tags, working directories, and session IDs.\n"
        "Examples: timeout backoff   or   tag:review:problem"
    ),
    "viewer.all": "all",
    "viewer.today": "today",
    "viewer.week": "7 days",
    "viewer.count": "  {n} results · {window} · {agent} · newest first",
    "viewer.all_agents": "all agents",
    "viewer.time_button": "Time {window} F2",
    "viewer.agent_button": "Agent {agent} F3",
    "viewer.reloaded": "Refreshed marks · / search · Enter open · y copy summary",
    "viewer.deleted": "Deleted marks for this session · original chat files are kept",
    "viewer.copied": "Copied summary: tags, notes, source, and pipeline prompt",
    "viewer.clipboard_error": "Could not write clipboard: {exc}",
    "viewer.clear": "Clear",
    "viewer.refresh": "Reload",
    "viewer.open": "Open",
    "viewer.copy": "Copy y",
    "viewer.vocab": "Vocab e",
    "viewer.delete": "Delete d",
    "viewer.close": "Close",
    "viewer.title": "sessmark  /  Marked sessions",
    "viewer.search": "Search notes / tags / path / ID · tag:keep exact tag",
    "viewer.panel_list": "Session",
    "viewer.panel_detail": "Notes / source / pipeline",
}

ZH = {
    "tag.pipeline": "→ 流水线",
    "tag.lookup": "· 仅检索",
    "tag.empty_detail": "没有匹配的标签。\n\n换个关键词，或按 Ctrl+L 清空搜索。",
    "tag.lookup_detail": "{tag}\n\n仅检索\n\n用于收藏和查找，不触发流水线。",
    "tag.pipeline_detail": "{tag}\n流水线 · {route}\n\n{text}",
    "empty_rows": "没有匹配结果 · Ctrl+L 清空",
    "editor.status": "Enter / Ctrl+S 保存 · Alt+Enter 换行 · Tab 切换 · Esc 取消",
    "editor.title_new": "sessmark  ·  新标签",
    "editor.title_edit": "sessmark  ·  编辑  {tag}",
    "editor.hint": "  留空 Prompt = 仅用于检索；填写 Prompt = 进入对应流水线。",
    "editor.panel_name": "标签名 · 例如 review:ux / keep / harvest:wiki",
    "editor.panel_prompt": "流水线 Prompt · 支持多行",
    "btn.save": "保存 Enter",
    "btn.cancel": "取消 Esc",
    "config.status": "Enter 编辑 · / 搜索 · F4 详情 · d 删除 · Esc 返回",
    "config.count": "  {shown} / {total} 个标签 · 搜索标签名、流水线或 Prompt",
    "config.deleted": "已删除 {tag} · 历史标注仍保留",
    "config.opened_file": "已打开配置文件 · 保存后按 r 重新加载",
    "config.reloaded": "已重新加载配置",
    "config.add": "新增 n",
    "config.edit": "编辑 Enter",
    "config.open_file": "打开文件 o",
    "config.back": "返回 Esc",
    "config.title": "sessmark  /  标签与流水线",
    "config.search": "搜索 · Ctrl+L 清空",
    "config.panel_tags": "标签",
    "config.panel_detail": "用途 / 完整 Prompt",
    "mark.pending_id": "等待 Session ID",
    "mark.status": "Space 选 · Tab 备注 · Enter 保存 · F4 详情 · Esc 取消",
    "mark.count": "  {shown} / {total} 个标签 · F4 查看详情 · 筛选保留勾选",
    "mark.added_tag": "已勾选 {tag} · 可继续添加标签或填写备注",
    "mark.need_input": "请先勾选标签或填写备注 · / 搜索标签，Tab 填备注",
    "mark.add": "新增 n",
    "mark.vocab": "词表 e",
    "mark.title": "sessmark  /  标记当前 Session",
    "mark.search": "搜索标签 / Prompt · Ctrl+L 清空",
    "mark.panel_tags": "标签 · Space 多选",
    "mark.panel_detail": "用途 / 完整 Prompt",
    "mark.note": "备注 · 写下以后回看时最需要知道的事",
    "mark.hidden": " · {hidden} 项在筛选结果外",
    "mark.selected": "  已选 {count}{suffix}  {tags}",
    "mark.none": "尚未勾选",
    "row.tags_only": "（仅标签，无备注）",
    "detail.tags": "标签  {tags}",
    "detail.none": "无",
    "detail.notes": "备注",
    "detail.no_notes": "  暂无备注",
    "detail.source": "来源",
    "detail.cwd": "  目录  {cwd}",
    "detail.id": "  ID    {id}",
    "detail.session": "  Session  {session}",
    "detail.pending_bind": "等待绑定",
    "detail.transcript": "  Transcript  {path}",
    "detail.missing_path": "未提供",
    "detail.pipeline": "流水线 · {name}",
    "delete.cancel": "取消",
    "delete.confirm": "删除标注",
    "delete.title": "sessmark  /  删除这条 Session 的标注？",
    "delete.body": "  将删除 {tags} 个标签、{notes} 条备注。此操作不可撤销。",
    "delete.keep_files": "  原始 Session / transcript 文件保留。",
    "delete.panel": "确认删除对象",
    "delete.status": "Tab 切换 · Enter 确认所选按钮 · Esc 取消",
    "delete.cwd": "目录     {cwd}",
    "viewer.status": "Enter 打开 · F4 详情 · / 搜索 · d 删除 · Esc 关闭",
    "viewer.empty": (
        "没有匹配的 Session\n\n"
        "试试更短的关键词，或清空时间 / Agent 筛选。\n\n"
        "搜索会覆盖所有备注、标签、工作目录及 Session ID。\n"
        "例如：工具 超时   或   tag:review:problem"
    ),
    "viewer.all": "全部",
    "viewer.today": "今天",
    "viewer.week": "近 7 天",
    "viewer.count": "  {n} 条结果 · {window} · {agent} · 最新标注在前",
    "viewer.all_agents": "全部 Agent",
    "viewer.time_button": "时间 {window} F2",
    "viewer.agent_button": "Agent {agent} F3",
    "viewer.reloaded": "已刷新标注 · / 搜索 · Enter 打开 · y 复制摘要",
    "viewer.deleted": "已删除该 Session 的标注 · 原始对话文件保留",
    "viewer.copied": "已复制摘要：标签、备注、来源和流水线 Prompt",
    "viewer.clipboard_error": "无法写入剪贴板: {exc}",
    "viewer.clear": "清空",
    "viewer.refresh": "刷新",
    "viewer.open": "打开",
    "viewer.copy": "复制 y",
    "viewer.vocab": "词表 e",
    "viewer.delete": "删除 d",
    "viewer.close": "关闭",
    "viewer.title": "sessmark  /  已标记的 Session",
    "viewer.search": "搜索备注 / 标签 / 路径 / ID · tag:keep 精确筛选",
    "viewer.panel_list": "Session",
    "viewer.panel_detail": "备注 / 来源 / 流水线",
}
