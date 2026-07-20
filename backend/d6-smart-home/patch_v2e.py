#!/usr/bin/env python3
"""Patch v2e: Fix _DEVICE_NAMES reference in gateway_v3.py"""

with open("/data/A9/smart_home/gateway_v3.py", "r", encoding="utf-8") as f:
    gw = f.read()

# Fix: _DEVICE_NAMES should be _HW_DEV_NAMES in gateway_v3.py
# The import is: from hardware_bridge import ... _DEVICE_NAMES as _HW_DEV_NAMES
# But _detect_device_control uses _DEVICE_NAMES which doesn't exist

# Option 1: Change the import to also create _DEVICE_NAMES
# Option 2: Change the function to use _HW_DEV_NAMES
# Let's do option 1 - add _DEVICE_NAMES = _HW_DEV_NAMES after the import

old_import = '''    from hardware_bridge import hw_toggle, hw_control, hw_sensor_read, hw_scene_execute, _DEVICE_NAMES as _HW_DEV_NAMES'''
new_import = '''    from hardware_bridge import hw_toggle, hw_control, hw_sensor_read, hw_scene_execute, _DEVICE_NAMES as _HW_DEV_NAMES
    _DEVICE_NAMES = _HW_DEV_NAMES'''

if old_import in gw:
    gw = gw.replace(old_import, new_import)
    print("[1] Added _DEVICE_NAMES = _HW_DEV_NAMES after import")
else:
    print("[1] WARNING: import pattern not found")

with open("/data/A9/smart_home/gateway_v3.py", "w", encoding="utf-8") as f:
    f.write(gw)
print("gateway_v3.py saved")
