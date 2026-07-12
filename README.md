<div align="center">
<h1>HarmonyOS MCP Server</h1>

 <a href='LICENSE'><img src='https://img.shields.io/badge/License-MIT-orange'></a> &nbsp;&nbsp;&nbsp;
 <a><img src='https://img.shields.io/badge/python-3.14-blue'></a>
</div>

<div align="center">
    <img style="max-width: 500px; width: 60%;" width="1111" alt="image" src="https://github.com/user-attachments/assets/7c2e6879-f583-48d7-b467-c4c6d99c5fab" />
</div>

## Intro

This is a MCP server for manipulating HarmonyOS Device, plus a **Smart Home Gateway v5** running on HarmonyOS A9 board.

---

## Smart Home Gateway v5

A complete smart home backend running on **HarmonyOS A9 (ARM32)**, controlling 4 edge devices (10 real devices + 5 sensors) via TCP/UDP.

### Architecture

```
A9 Board (192.168.1.81:8080)
├── gateway_v5.py (:8080)      ← HTTP API
├── hardware_bridge.py          ← Hardware bridge
├── connect/                    ← central_controller + devices.json
├── rag/rag_service.py          ← RAG (65 exact commands + 44 TF-IDF)
├── channel.py (:8081)          ← WebSocket + TTS output
└── data_pusher.py              ← Data push

Edge Devices (2.4GHz Wi-Fi)
├── Living Room Hi3861   192.168.1.62:8000  (text protocol)
├── Kitchen H3863        192.168.1.23:8000  (binary) + UDP 8001
├── Bathroom H3863       192.168.1.63:8000  (binary)
└── Bedroom H3863        192.168.1.64:8000  (binary)
```

### Key Features

- **12-category stats API**: `GET /api/stats` — device online rate, area connectivity, temperature, humidity, smoke, thermal, alarm, fan, curtain, lights, alarm linkage, poll config
- **Real hardware only**: No mock/simulated data. Offline = `null`
- **Kitchen alarm linkage**: alarm rising edge → `BEEP ALARM`, falling edge → `BEEP OFF`, no repeat trigger
- **1s kitchen polling**: Smoke/thermal/alarm + UDP 8001 broadcast
- **AI chat with device control**: Intent detection → hardware execution → TTS voice confirmation
- **RAG knowledge base**: 65 exact command mappings + 44 TF-IDF entries
- **Auto-start on boot**: `/etc/init/smart_home.cfg`

### Quick Start

```bash
# Start gateway
hdc shell "sh /data/A9/run_v5.sh"

# Health check
hdc shell "cd /data/A9 && /data/A9/python-portable/lib/ld-musl-armhf.so.1 --library-path /data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib /data/A9/python-portable/usr/bin/python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/health\", timeout=5).read().decode())'"

# Stats API
curl http://192.168.1.81:8080/api/stats

# Stop
hdc shell "pkill -f gateway_v5"
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check `{v:5, hardware:true}` |
| `/api/stats` | GET | 12-category statistics |
| `/api/devices` | GET | 10 devices (offline=null) |
| `/api/sensors` | GET | 5 sensors (offline=null) |
| `/api/check` | GET | Connectivity check + voice broadcast |
| `/api/hardware/status` | GET | 4-area connectivity |
| `/api/alerts` | GET | Active alerts |
| `/api/sensors/history` | GET | Sensor history (24h) |
| `/api/devices/{id}/toggle` | POST | Toggle device |
| `/api/devices/{id}/control` | POST | Parameter control |
| `/api/door/control` | POST | Door control |
| `/api/chat/send` | POST | AI chat |
| `/api/voice/input` | POST | Voice input (ASR→backend) |
| `/api/tts/speak` | POST | TTS voice output |

### Documentation

- [接口对齐文档](docs/接口对齐文档.md) — Full API & protocol alignment
- [统计接口文档](docs/统计接口文档.md) — Stats API field reference

### File Structure

```
smart_home/
├── gateway_v5.py              ← Main HTTP gateway
├── channel.py                 ← WebSocket + TTS output
├── hardware_bridge.py         ← Hardware bridge
├── data_pusher.py             ← Data push service
├── connect/
│   ├── central_controller.py  ← Edge device controller
│   └── devices.json           ← Device configuration
├── rag/
│   └── rag_service.py         ← RAG knowledge base
└── scenes/
    └── scene_config.py        ← Scene configuration
run_v5.sh                      ← Startup script
```

---

## MCP Server (Device Control)

### Installation

1. Clone this repo

```bash
git clone https://github.com/xyls999/HarmonyOS-mcp-server.git
cd HarmonyOS-mcp-server
```

2. Setup the environment.

```bash
uv python install 3.13
uv sync
```

### Usage

#### 1. Claude Desktop

You can use [Claude Desktop](https://modelcontextprotocol.io/quickstart/user) to try our tool.

#### 2. OpenAI SDK

DeepSeek-compatible endpoint example:

```bash
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-flash"
uv run python examples/deepseek_agents_mcp.py "查看本地天气"
```

Extra tools:
- `get_local_weather`: get current weather by IP location or city name.
- `list_common_harmony_apps`: list friendly aliases for common HarmonyOS apps.
- `launch_harmony_app`: open an app by alias, package name, or fuzzy package keyword.

#### 3. LangGraph

See [langgraph_mcp.py](langgraph_mcp.py) for a complete LangGraph + MCP integration example.

---

## License

MIT
