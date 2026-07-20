import base64,zlib
with open("/data/A9/smart_home/gateway_v6.gz.b64","r") as f: data=f.read()
compressed=base64.b64decode(data)
raw=zlib.decompress(compressed)
with open("/data/A9/smart_home/gateway_v6.py","wb") as f: f.write(raw)
print(f"Decompressed: {len(raw)} bytes, {len(raw.decode("utf-8"))} chars")
