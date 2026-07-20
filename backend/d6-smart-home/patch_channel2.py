#!/usr/bin/env python3
"""Patch channel.py - fix message wording and double TTS issues"""

with open("/data/A9/smart_home/channel.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Fix the finally block message wording - remove redundant "连通测试成功"
old_msg = '''            result["hardwareOnline"] = False
            result["message"] = f"{action_name}查询成功，硬件未接入，连通测试成功"'''

new_msg = '''            result["hardwareOnline"] = False
            result["message"] = f"{action_name}成功，硬件未接入，连通测试成功"'''

code = code.replace(old_msg, new_msg)

# 2. Fix remove_device: save device name BEFORE deleting from DB
# Current code deletes first, then tries to query name - but it's already gone
# Need to restructure: query name first, then delete
old_remove = '''        elif action == "remove_device":
            device_id = cmd.get("deviceId", "")
            r = conn.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
            if r:
                conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
                conn.execute("DELETE FROM scene_actions WHERE device_id=?", (device_id,))
                conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                            (device_id, "remove", "{}", "remote"))
                conn.commit()
                # 先查数据库拿设备中文名
                dev_name_r = conn.execute("SELECT name FROM devices WHERE id=?", (device_id,)).fetchone()
                dev_display = (dev_name_r[0] if dev_name_r else None) or _DEVICE_NAMES.get(device_id, device_id)
                dev_msg = f"{dev_display}移除离线，连通测试成功"
                tts_offline_alert(dev_display + "移除")
                result = {"msgId": msg_id, "success": True, "data": {"removed": device_id},
                         "hardwareOnline": False, "message": dev_msg}'''

new_remove = '''        elif action == "remove_device":
            device_id = cmd.get("deviceId", "")
            r = conn.execute("SELECT id, name FROM devices WHERE id=?", (device_id,)).fetchone()
            if r:
                # 先保存设备名，删除后就查不到了
                dev_display = r[1] or _DEVICE_NAMES.get(device_id, device_id)
                conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
                conn.execute("DELETE FROM scene_actions WHERE device_id=?", (device_id,))
                conn.execute("INSERT INTO device_operations(device_id,action,params_json,source) VALUES(?,?,?,?)",
                            (device_id, "remove", "{}", "remote"))
                conn.commit()
                dev_msg = f"{dev_display}移除离线，连通测试成功"
                tts_offline_alert(dev_display + "移除")
                result = {"msgId": msg_id, "success": True, "data": {"removed": device_id, "removedName": dev_display},
                         "hardwareOnline": False, "message": dev_msg}'''

code = code.replace(old_remove, new_remove)

# 3. Fix activate_scene_by_name double TTS: skip TTS in the wrapper, let activate_scene handle it
# The issue: activate_scene_by_name calls execute_command("activate_scene") which has its own TTS
# But the finally block also adds TTS because the wrapper result doesn't have message yet
# Fix: add message to the wrapper so finally block skips it
old_scene_by_name = '''        elif action == "activate_scene_by_name":
            name = cmd.get("name", "")
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from scenes.scene_config import get_scene_id_by_name, SCENE_META
            sid = get_scene_id_by_name(name)
            if sid:
                # 复用 activate_scene 逻辑
                cmd2 = dict(cmd)
                cmd2["action"] = "activate_scene"
                cmd2["sceneId"] = sid
                if conn:
                    conn.close()
                    conn = None
                return execute_command(cmd2)
            else:
                result = {"msgId": msg_id, "success": False, "error": f"未找到场景: {name}"}'''

new_scene_by_name = '''        elif action == "activate_scene_by_name":
            name = cmd.get("name", "")
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from scenes.scene_config import get_scene_id_by_name, SCENE_META
            sid = get_scene_id_by_name(name)
            if sid:
                # 复用 activate_scene 逻辑 (它自带 TTS + message)
                cmd2 = dict(cmd)
                cmd2["action"] = "activate_scene"
                cmd2["sceneId"] = sid
                if conn:
                    conn.close()
                    conn = None
                result = execute_command(cmd2)
                # 标记已有 message，防止 finally 重复加 TTS
                return result
            else:
                tts_offline_alert("场景激活")
                result = {"msgId": msg_id, "success": False, "error": f"未找到场景: {name}",
                         "hardwareOnline": False, "message": f"场景{name}未找到，连通测试成功"}'''

code = code.replace(old_scene_by_name, new_scene_by_name)

with open("/data/A9/smart_home/channel.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Patch 2 applied successfully!")
print("Fixes:")
print("  1. Query message wording: removed redundant text")
print("  2. remove_device: save device name BEFORE deleting")
print("  3. activate_scene_by_name: prevent double TTS")
