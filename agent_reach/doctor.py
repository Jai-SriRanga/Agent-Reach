# -*- coding: utf-8 -*-
"""Environment health checker — powered by channels.

Each channel knows how to check itself. Doctor just collects the results.
"""

from typing import Dict

from rich.markup import escape

from agent_reach.channels import get_all_channels
from agent_reach.config import Config
from agent_reach.utils.text import scrub_url_credentials


def _english_enabled() -> bool:
    import os
    value = os.environ.get("AGENT_REACH_LANG", "").strip().lower()
    return value.startswith("en") or value.startswith("english")


_ENGLISH_NAMES = {
    "GitHub 仓库和代码": "GitHub repositories and code",
    "YouTube 视频和字幕": "YouTube videos and subtitles",
    "V2EX 节点、主题与回复": "V2EX nodes, topics, and replies",
    "RSS/Atom 订阅源": "RSS/Atom feeds",
    "全网语义搜索": "Semantic web search",
    "任意网页": "Any web page",
    "Twitter/X 推文": "Twitter/X posts",
    "Reddit 帖子和评论": "Reddit posts and comments",
    "Facebook 帖子、主页和群组": "Facebook posts, pages, and groups",
    "Instagram 用户、主页和指定用户帖子": "Instagram users, profiles, and posts",
    "B站视频、字幕和搜索": "Bilibili videos, subtitles, and search",
    "小红书笔记": "Xiaohongshu notes",
    "小宇宙播客转文字": "Xiaoyuzhou podcast transcription",
    "雪球股票行情与社区动态": "Xueqiu market data and community posts",
    "LinkedIn 职业社交": "LinkedIn professional networking",
    "Boss直聘 职位搜索与 JD": "Boss Zhipin job search and job descriptions",
}


def _localize(name: str, message: str) -> tuple[str, str]:
    if not _english_enabled():
        return name, message
    replacements = {
        "体检异常：": "Doctor error: ",
        "公开 API 可用": "Public API available",
        "连接失败（可能需要代理）": "Connection failed (a proxy may be required)",
        "未安装": "Not installed",
        "已安装": "Installed",
        "需要配置/登录": "needs configuration/login",
        "需要人工审批": "requires manual approval",
        "需要登录态": "requires a login session",
        "需要代理": "requires a proxy",
        "安装：": "Install: ",
        "运行：": "Run: ",
        "未配置": "not configured",
        "未检测到": "not detected",
        "无法安全读取": "cannot be read safely",
        "当前不标记为可用": "not marked as available",
        "可读取": "can read",
        "完整功能建议": "For full functionality, install",
        "还有": "There are",
        "个可选渠道可以解锁": " optional channels available to unlock",
        "告诉你的 Agent": "Tell your Agent",
    }
    for source, target in replacements.items():
        message = message.replace(source, target)
    return _ENGLISH_NAMES.get(name, name), message


def _english_status_message(status: str, message: str) -> str:
    """Avoid leaking untranslated adapter text into an English report."""
    if not _english_enabled() or not any("\u4e00" <= char <= "\u9fff" for char in message):
        return message
    if status == "ok":
        return "Backend is available."
    if status == "warn":
        return "Backend is installed but needs configuration or login."
    if status == "off":
        return "Backend is not installed."
    return "Backend check failed."


def check_all(config: Config) -> Dict[str, dict]:
    """Check all channels and return status dict.

    A single misbehaving channel must never take the whole report down,
    so per-channel exceptions degrade to status="error".
    """
    results = {}
    for ch in get_all_channels():
        try:
            status, message = ch.check(config)
            active = getattr(ch, "active_backend", None)
        except Exception as e:  # noqa: BLE001 — doctor must survive any channel
            # Channels are registry singletons: a stale active_backend from a
            # previous check must not leak into an errored result.
            status = "error"
            message = f"体检异常：{e}"
            active = None
        # Doctor is the final output boundary for both expected channel
        # messages and unexpected exceptions. Upstream probe output can echo a
        # configured URL, so scrub every path before JSON/text rendering.
        message = scrub_url_credentials(message)
        name, message = _localize(ch.description, message)
        message = _english_status_message(status, message)
        results[ch.name] = {
            "status": status,
            "name": name,
            "message": message,
            "tier": ch.tier,
            "backends": ch.backends,
            "active_backend": active,
        }
    return results


def _name_msg(r: dict, escape) -> str:
    """Render one channel line; show the active backend when there is a choice."""
    name, message = _localize(r["name"], r["message"])
    message = _english_status_message(r["status"], message)
    text = f"[bold]{escape(name)}[/bold] — {escape(message)}"
    active = r.get("active_backend")
    if active and len(r.get("backends", [])) > 1:
        suffix = (
            " [dim](active backend configured)[/dim]"
            if _english_enabled()
            else f" [dim]（当前后端：{escape(active)}）[/dim]"
        )
        text += suffix
    return text


def format_report(results: Dict[str, dict]) -> str:
    """Format results as a readable text report (with Rich markup)."""
    english = _english_enabled()
    lines = []
    lines.append("[bold cyan]Agent Reach Status[/bold cyan]" if english else "[bold cyan]Agent Reach 状态[/bold cyan]")
    lines.append("[cyan]" + "=" * 40 + "[/cyan]")
    lines.append("[green]✅[/green] Available  [yellow][!][/yellow] Installed but needs configuration/login  [red][X][/red] Not installed" if english else "图例：[green]✅[/green] 可用  [yellow][!][/yellow] 已装但需配置/登录  [red][X][/red] 未安装")

    ok_count = sum(1 for r in results.values() if r["status"] == "ok")
    total = len(results)

    # Tier 0 — zero config
    lines.append("")
    lines.append("[bold]✅ Ready to use:[/bold]" if english else "[bold]✅ 装好即用：[/bold]")
    for key, r in results.items():
        if r["tier"] == 0:
            name_msg = _name_msg(r, escape)
            if r["status"] == "ok":
                lines.append(f"  [green]✅[/green] {name_msg}")
            elif r["status"] == "warn":
                lines.append(f"  [yellow][!][/yellow]  {name_msg}")
            elif r["status"] in ("off", "error"):
                lines.append(f"  [red][X][/red]  {name_msg}")

    # Tier 1 — needs free key / login
    tier1 = {k: r for k, r in results.items() if r["tier"] == 1}
    tier1_active = {k: r for k, r in tier1.items() if r["status"] == "ok"}
    tier1_inactive = {k: r for k, r in tier1.items() if r["status"] != "ok"}
    if tier1_active:
        lines.append("")
        lines.append("[bold]Optional channels (installed):[/bold]" if english else "[bold]可选渠道（已安装）：[/bold]")
        for key, r in tier1_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape)}")

    # Tier 2 — optional complex setup
    tier2 = {k: r for k, r in results.items() if r["tier"] == 2}
    tier2_active = {k: r for k, r in tier2.items() if r["status"] == "ok"}
    tier2_inactive = {k: r for k, r in tier2.items() if r["status"] != "ok"}
    if tier2_active:
        if not tier1_active:
            lines.append("")
            lines.append("[bold]Optional channels (installed):[/bold]" if english else "[bold]可选渠道（已安装）：[/bold]")
        for key, r in tier2_active.items():
            lines.append(f"  [green]✅[/green] {_name_msg(r, escape)}")

    lines.append("")
    status_color = "green" if ok_count == total else ("yellow" if ok_count > 0 else "red")
    lines.append(f"Status: [{status_color}]{ok_count}/{total}[/{status_color}] channels available" if english else f"状态：[{status_color}]{ok_count}/{total}[/{status_color}] 个渠道可用")

    # Summarize inactive optional channels in one line instead of listing each
    all_inactive = list(tier1_inactive.values()) + list(tier2_inactive.values())
    if all_inactive:
        names = [_ENGLISH_NAMES.get(r["name"], r["name"]) if english else r["name"] for r in all_inactive]
        lines.append(
            f"{len(names)} optional channels can be unlocked ({', '.join(names)}). "
            "Tell your Agent to install the channel."
            if english
            else f"还有 {len(names)} 个可选渠道可以解锁（{'、'.join(names)}），"
            "告诉你的 Agent「帮我装 XXX」即可"
        )

    # Security check: config file permissions (Unix only)
    import stat
    import sys

    config_path = Config.CONFIG_DIR / "config.yaml"
    if config_path.exists() and sys.platform != "win32":
        try:
            mode = config_path.stat().st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                lines.append("")
                lines.append(
                    "[bold red][!] Security warning: config.yaml is readable by other users[/bold red]"
                    if english
                    else "[bold red][!]  安全提示：config.yaml 权限过宽（其他用户可读）[/bold red]"
                )
                lines.append("   修复：chmod 600 ~/.agent-reach/config.yaml")
        except OSError:
            pass

    return "\n".join(lines)
