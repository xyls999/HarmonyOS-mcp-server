#!/bin/sh
cd /data/A9 || exit 1
export PATH=/data/A9/bin:/data/A9/python-portable/bin:$PATH
export HOME=/data/A9
export LD_LIBRARY_PATH=/data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib:$LD_LIBRARY_PATH
export SSL_CERT_FILE=/data/A9/certs/cacert.pem
: "${DEEPSEEK_API_KEY:?请先通过安全环境变量配置 DEEPSEEK_API_KEY}"
export DEEPSEEK_BASE_URL=https://api.deepseek.com
export DEEPSEEK_MODEL=deepseek-v4-flash
nohup python3 /data/A9/smart_home_gateway_v2.py > /data/A9/gateway_stdout.log 2>&1 &
echo "网关v2已启动 PID:$!"
