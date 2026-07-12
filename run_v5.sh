#!/bin/sh
cd /data/A9 || exit 1
export PATH=/data/A9/bin:/data/A9/python-portable/bin:/data/A9/python-portable/usr/bin:$PATH
export HOME=/data/A9
export LD_LIBRARY_PATH=/data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib:$LD_LIBRARY_PATH
export SSL_CERT_FILE=/data/A9/certs/cacert.pem
export DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-"your-deepseek-api-key"}
export DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL:-"https://api.deepseek.com"}
export DEEPSEEK_MODEL=${DEEPSEEK_MODEL:-"deepseek-v4-flash"}
export IFLYTEK_API_KEY=${IFLYTEK_API_KEY:-"your-iflytek-api-key"}
export ASTRON_API_KEY=${ASTRON_API_KEY:-"your-astron-api-key"}
export PYTHONPATH=/data/A9/smart_home:$PYTHONPATH
if [ -f /data/A9/oh_play ]; then chmod +x /data/A9/oh_play; fi
pkill -f gateway_v 2>/dev/null; pkill -f channel.py 2>/dev/null; sleep 1
nohup /data/A9/python-portable/lib/ld-musl-armhf.so.1 --library-path /data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib /data/A9/python-portable/usr/bin/python3.14 /data/A9/smart_home/gateway_v5.py > /data/A9/gateway_stdout.log 2>&1 &
echo v5 started PID:$!
