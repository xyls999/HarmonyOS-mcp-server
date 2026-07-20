import time
import central_controller_field as c

c.next_nonce = lambda: (int(time.time() * 1000) + 15000) & 0xFFFFFFFF
config = c.load_config("devices.json")
print(c.living_door(config, "query", 3.0))
