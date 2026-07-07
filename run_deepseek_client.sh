#!/bin/sh
cd /data/A9/HarmonyOS-mcp-server || exit 1

export PATH=/data/A9/bin:$PATH
export HOME=/data/A9
export UV_CACHE_DIR=/data/A9/.cache/uv
export LD_LIBRARY_PATH=/data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib:$LD_LIBRARY_PATH
export SSL_CERT_FILE=/data/A9/certs/cacert.pem

if [ -f /data/A9/HarmonyOS-mcp-server/.deepseek_env ]; then
  . /data/A9/HarmonyOS-mcp-server/.deepseek_env
fi

exec python3 /data/A9/HarmonyOS-mcp-server/local_deepseek_mcp_client.py "$@"
