import os
import time
import central_controller_field as c

shared_key = os.environ.get("A9_EDGE_SHARED_KEY", "")
if not shared_key:
    raise RuntimeError("请先通过安全环境变量配置 A9_EDGE_SHARED_KEY")
print(time.time(), c.make_packet(0, 0, 1, key=shared_key.encode("utf-8")).hex())
