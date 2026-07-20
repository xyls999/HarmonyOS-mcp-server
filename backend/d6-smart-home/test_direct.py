#!/usr/bin/env python3
"""Direct test of execute_command() - no WebSocket needed"""
import json
import sys
import os
import time

sys.path.insert(0, "/data/A9/smart_home")
if not os.environ.get("DEEPSEEK_API_KEY"):
    raise RuntimeError("请先通过安全环境变量配置 DEEPSEEK_API_KEY")
os.environ.setdefault("PYTHONPATH", "/data/A9/smart_home")

from channel import execute_command, tts_offline_alert, _device_offline_msg, _DEVICE_NAMES, _ACTION_NAMES

# All 22 test commands
ALL_COMMANDS = [
    {"action": "ping", "msgId": 1},
    {"action": "get_server_status", "msgId": 2},
    {"action": "get_status", "msgId": 3},
    {"action": "get_devices", "msgId": 4},
    {"action": "get_sensors", "msgId": 5},
    {"action": "get_scenes", "msgId": 6},
    {"action": "get_user", "msgId": 7},
    {"action": "get_operations", "msgId": 8},
    {"action": "get_chat_history", "msgId": 9},
    {"action": "get_alerts", "msgId": 10},
    {"action": "get_cameras", "msgId": 11},
    {"action": "toggle_device", "msgId": 12, "deviceId": "light_01", "isOn": True},
    {"action": "control_device", "msgId": 13, "deviceId": "ac_01", "subAction": "set_temp", "params": {"value": 26}},
    {"action": "control_device", "msgId": 14, "deviceId": "light_05", "subAction": "set_brightness", "params": {"value": 80}},
    {"action": "control_device", "msgId": 15, "deviceId": "ac_01", "subAction": "set_mode", "params": {"mode": "cool"}},
    {"action": "activate_scene", "msgId": 16, "sceneId": "s1"},
    {"action": "add_device", "msgId": 17, "id": "test_dev_01", "name": "test_light", "type": "light", "room": "living"},
    {"action": "remove_device", "msgId": 18, "deviceId": "test_dev_01"},
    {"action": "update_user", "msgId": 19, "nickname": "test_user"},
    {"action": "send_chat", "msgId": 20, "content": "hello"},
    {"action": "activate_scene_by_name", "msgId": 21, "name": "home"},
    {"action": "rag_search", "msgId": 22, "query": "how to use ac"},
]

CONTROL_ACTIONS = {"toggle_device", "control_device", "activate_scene",
                   "activate_scene_by_name", "add_device", "remove_device",
                   "send_chat", "get_alerts", "get_cameras"}

def main():
    print("=" * 70)
    print("Smart Home - Direct execute_command() Test")
    print("=" * 70)

    results = []
    for i, cmd in enumerate(ALL_COMMANDS):
        action = cmd["action"]
        msg_id = cmd["msgId"]

        print("\n--- Command {:2d}: {} (msgId={}) ---".format(i+1, action, msg_id))

        try:
            response = execute_command(cmd)
        except Exception as e:
            print("  XX Exception: {}".format(e))
            results.append({"action": action, "status": "EXCEPTION", "error": str(e)})
            continue

        # Analyze
        success = response.get("success", False)
        has_hw = "hardwareOnline" in response
        hw_val = response.get("hardwareOnline", None)
        has_offline = response.get("offline", False)
        has_ch_ok = response.get("channelOk", False)
        has_msg = bool(response.get("message", ""))
        msg_text = response.get("message", "")
        is_control = action in CONTROL_ACTIONS

        # Print response summary
        print("  success: {}".format(success))
        if has_hw:
            print("  hardwareOnline: {}".format(hw_val))
        if has_offline:
            print("  offline: True")
        if has_ch_ok:
            print("  channelOk: True")
        if has_msg:
            print("  message: {}".format(msg_text))
        if "data" in response:
            data = response["data"]
            if isinstance(data, dict):
                keys = list(data.keys())[:5]
                print("  data keys: {}{}".format(keys, "..." if len(data) > 5 else ""))
            elif isinstance(data, list):
                print("  data: list[{}]".format(len(data)))

        # Check requirements
        issues = []
        if is_control and success:
            if hw_val is not False:
                issues.append("MISSING hardwareOnline:false")
            if not has_msg:
                issues.append("MISSING message field")
        if not success and not has_offline and not has_msg:
            issues.append("MISSING offline fallback")

        status = "OK" if not issues else "ISSUE"
        icon = "OK" if not issues else "!!"
        print("  {} {}".format(icon, "All good" if not issues else " | ".join(issues)))

        results.append({
            "action": action,
            "status": status,
            "success": success,
            "hardwareOnline": hw_val,
            "hasMessage": has_msg,
            "message": msg_text,
            "offline": has_offline,
            "channelOk": has_ch_ok,
            "issues": issues,
        })

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    issue_count = sum(1 for r in results if r["status"] == "ISSUE")
    hw_offline = sum(1 for r in results if r.get("hardwareOnline") == False)
    has_msg = sum(1 for r in results if r.get("hasMessage"))

    print("  Total: {} | OK: {} | Issues: {}".format(len(results), ok_count, issue_count))
    print("  hardwareOnline:false: {}".format(hw_offline))
    print("  Has message: {}".format(has_msg))

    if issue_count > 0:
        print("\nCommands with issues:")
        for r in results:
            if r["status"] == "ISSUE":
                print("  !! {}: {}".format(r["action"], " | ".join(r.get("issues", []))))
    else:
        print("\n  ALL COMMANDS PASS! Every command has proper fallback.")

    # Check TTS WAV files
    tts_dir = "/data/A9/smart_home/tts_cache"
    if os.path.isdir(tts_dir):
        wav_files = [f for f in os.listdir(tts_dir) if f.endswith(".wav")]
        print("\n  TTS WAV files generated: {}".format(len(wav_files)))
        for f in wav_files[-5:]:
            fpath = os.path.join(tts_dir, f)
            size = os.path.getsize(fpath)
            print("    {} ({} bytes)".format(f, size))
    else:
        print("\n  No tts_cache directory found")

    print("\nTest complete!")

if __name__ == "__main__":
    main()
