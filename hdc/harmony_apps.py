"""
Convenience tools for opening common HarmonyOS apps.
"""

from typing import Dict, List

from .app_manager import launch_app, list_app


COMMON_HARMONY_APPS: Dict[str, str] = {
    "settings": "com.ohos.settings",
    "设置": "com.ohos.settings",
    "camera": "com.ohos.camera",
    "相机": "com.ohos.camera",
    "gallery": "com.ohos.photos",
    "图库": "com.ohos.photos",
    "browser": "ohos.samples.browser1",
    "浏览器": "ohos.samples.browser1",
    "contacts": "com.ohos.contacts",
    "联系人": "com.ohos.contacts",
    "phone": "com.ohos.contacts",
    "电话": "com.ohos.contacts",
    "messages": "com.ohos.mms",
    "短信": "com.ohos.mms",
    "files": "com.ohos.filemanager",
    "文件": "com.ohos.filemanager",
    "clock": "ohos.samples.etsclock",
    "时钟": "ohos.samples.etsclock",
    "notes": "com.ohos.note",
    "备忘录": "com.ohos.note",
    "music": "ohos.samples.distributedmusicplayer",
    "音乐": "ohos.samples.distributedmusicplayer",
    "recorder": "ohos.samples.recorder",
    "录音": "ohos.samples.recorder",
    "device_info": "org.ohosdev.deviceinfo",
    "设备信息": "org.ohosdev.deviceinfo",
    "bilibili": "com.wathinst.ohbili",
    "b站": "com.wathinst.ohbili",
    "tetris": "org.ohosdev.tetris",
    "俄罗斯方块": "org.ohosdev.tetris",
}


async def list_common_harmony_apps() -> Dict[str, str]:
    """
    List built-in aliases for common HarmonyOS apps.
    """
    return COMMON_HARMONY_APPS


async def launch_harmony_app(name_or_alias: str) -> str:
    """
    Launch a HarmonyOS app by alias, package name, or fuzzy package keyword.

    Args:
        name_or_alias: Examples: settings, 设置, weather, 天气, or a bundle name.
    """
    query = name_or_alias.strip()
    if not query:
        return "[Fail] app name or alias is empty."

    package_name = COMMON_HARMONY_APPS.get(query, query)
    apps = await list_app()

    if package_name in apps:
        return await launch_app(package_name)

    query_lower = query.lower()
    matches: List[str] = [app for app in apps if query_lower in app.lower()]
    if len(matches) == 1:
        return await launch_app(matches[0])
    if len(matches) > 1:
        return f"[Fail] multiple apps matched: {matches[:20]}"

    return (
        f"[Fail] app `{name_or_alias}` not found. "
        "Use `list_app` or `list_common_harmony_apps` to inspect available apps."
    )
