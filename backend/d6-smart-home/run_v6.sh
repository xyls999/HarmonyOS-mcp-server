#!/system/bin/sh
set -u
umask 077

BASE=/data/A9
APP_DIR=$BASE/smart_home
ENV_FILE=$BASE/.a9_backend.env
PYTHON=$BASE/python-portable/usr/bin/python3.14
LOADER=$BASE/python-portable/lib/ld-musl-armhf.so.1
LIB_PATH=$BASE/python-portable/lib:$BASE/python-portable/usr/lib:/system/lib
LOG_FILE=$BASE/gateway_stdout.log
PID_FILE=$BASE/gateway_v6.pid

cd "$BASE" || exit 1
export PATH=$BASE/bin:$BASE/python-portable/bin:$BASE/python-portable/usr/bin:$PATH
export HOME=$BASE
export LD_LIBRARY_PATH=$LIB_PATH:${LD_LIBRARY_PATH:-}
export SSL_CERT_FILE=$BASE/certs/cacert.pem
export PYTHONPATH=$APP_DIR:${PYTHONPATH:-}
export A9_CONTEXT_MAX_CHARS=${A9_CONTEXT_MAX_CHARS:-48000}
export A9_MCP_ALLOWED_ORIGINS=${A9_MCP_ALLOWED_ORIGINS:-http://127.0.0.1:8080,http://localhost:8080}

if [ ! -f "$ENV_FILE" ]; then
    echo "missing root-only runtime environment: $ENV_FILE" >&2
    exit 1
fi
. "$ENV_FILE"

chmod 600 "$ENV_FILE"
if [ -d "$APP_DIR/keys" ]; then
    chmod 700 "$APP_DIR/keys"
    chmod 600 "$APP_DIR"/keys/* 2>/dev/null || true
fi
if [ -f "$BASE/oh_play" ]; then chmod +x "$BASE/oh_play"; fi

# OpenHarmony 偶发保留 STA 配置但未拉起接口；网关启动前恢复现场网段。
ifconfig wlan0 up 2>/dev/null || true
sleep 2

if [ -f "$PID_FILE" ]; then
    old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$old_pid" ]; then kill "$old_pid" 2>/dev/null || true; fi
fi
pkill -f '/data/A9/smart_home/gateway_v6.py' 2>/dev/null || true
sleep 1

nohup "$LOADER" --library-path "$LIB_PATH" "$PYTHON" "$APP_DIR/gateway_v6.py" > "$LOG_FILE" 2>&1 &
gateway_pid=$!
echo "$gateway_pid" > "$PID_FILE"
chmod 600 "$PID_FILE"
echo "gateway_v6 started PID:$gateway_pid"

# 公网 App 依赖 WebSocket 隧道；网关启动时一并恢复转发链路。
if ! ps -ef | grep '/data/A9/tunnel_client_fast.py' | grep -v grep >/dev/null 2>&1; then
    nohup sh "$BASE/run_tunnel.sh" > "$BASE/tunnel_boot.log" 2>&1 &
    echo "tunnel startup requested"
fi
