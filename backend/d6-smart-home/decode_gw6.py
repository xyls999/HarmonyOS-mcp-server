
import base64, sys
with open('/data/A9/smart_home/gateway_v6.b64','r') as f:
    data = f.read()
decoded = base64.b64decode(data).decode('utf-8')
with open('/data/A9/smart_home/gateway_v6.py','w',encoding='utf-8') as f:
    f.write(decoded)
print(f'Decoded: {len(decoded)} chars')
