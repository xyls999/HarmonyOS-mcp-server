# 智慧家居后端开发日志

> 部署位置: /data/A9/smart_home/ (鸿蒙设备 hdc 内)  
> 日期: 2026-07-07  
> 运行环境: HarmonyOS ARM32 + Python 3.14.5 (纯标准库, 无第三方依赖)  
> 前端对齐: D:/Harmon (ArkTS/ArkUI) + D:/Harmon_LandscapeControl  

---

## 1. 部署位置

所有后端代码部署在 **鸿蒙设备 /data/A9/smart_home/** 目录下：

```
/data/A9/smart_home/
├── gateway_v3.py          # HTTP 网关 v3 (替代 v2)
├── mcp_server_enhanced.py # MCP Server 增强版 (23个tools)
├── db/
│   └── schema.sql         # 数据库建表 SQL (8表+6索引)
├── scenes/
│   └── scene_config.py    # 场景配置 (与前端完全对齐)
├── rag/
│   └── rag_service.py     # 本地 RAG 知识库 (纯Python TF-IDF)
├── graph/                 # LangGraph Agent (预留)
└── api/                   # 额外API (预留)

/data/A9/control/data/
└── smart_home.db          # SQLite 数据库文件
```

启动脚本: `/data/A9/run_v3.sh`  
启动命令: `sh /data/A9/run_v3.sh`

---

## 2. MCP 服务补全

原有 4 个 tools → 新增 19 个 → **总计 23 个 MCP Tools**

### 原有 (4)
| Tool | 说明 |
|------|------|
| list_app | 获取已安装应用列表 |
| list_common_harmony_apps | 常见应用别名映射 |
| launch_harmony_app | 通过别名启动应用 |
| get_local_weather | 本地天气查询 |

### 新增 (19)
| Tool | 说明 | 参数 |
|------|------|------|
| list_devices | 获取所有设备列表 | - |
| get_device | 获取单设备详情 | device_id |
| toggle_device | 开关设备 | device_id, is_on, source |
| control_device | 控制设备参数 | device_id, action, value, mode |
| add_device | 添加新设备 | name, device_type, room |
| remove_device | 移除设备 | device_id |
| list_scenes | 获取所有场景 | - |
| activate_scene | 激活场景 | scene_id |
| activate_scene_by_name | 通过名称激活 | name |
| get_scene_summary | 场景摘要 | - |
| get_sensors | 获取所有传感器 | - |
| get_sensor_history | 传感器历史 | sensor_id, hours |
| get_device_operations | 操作记录 | device_id, days |
| get_user_profile | 用户信息 | user_id |
| update_user_profile | 更新用户 | nickname, homeName, memberCount |
| rag_search | RAG搜索 | query, n_results |
| rag_context | RAG上下文 | query |
| rag_stats | RAG统计 | - |
| bearpi_command | BearPi命令 | command, room, value |

---

## 3. 本地 RAG 服务

### 架构
- **实现方式**: 纯 Python TF-IDF + 关键词匹配 (无需 chromadb/sentence-transformers)
- **知识库**: 45 条文档, 6 个类别
- **分词**: 中文 2-gram + 英文空格分词

### 知识库内容
| 类别 | 条数 | 示例 |
|------|------|------|
| device_control | 20 | "打开灯 开灯" → light/on |
| scene | 5 | "回家模式" → s1 |
| sensor | 7 | "现在温度" → temperature |
| faq | 5 | "今天天气" → get_local_weather |
| bearpi | 3 | "设置亮度" → brightness |
| room | 5 | "客厅" → 客厅 |

### 实测结果
```
搜索"我要回家" → {'scene_id': 's1', 'scene_name': '回家'}  ✅
搜索"开客厅灯" → {'device_type': 'light', 'action': 'on'}  ✅
搜索"watch movie" → {'scene_id': 's4', 'scene_name': '观影'} ✅
```

---

## 4. 场景设备开关配置 (与前端完全对齐)

| 场景 | ID | 设备数 | 开 | 关 | 详细动作 |
|------|----|--------|-----|-----|----------|
| **回家** | s1 | 4 | 4 | 0 | 灯80%+空调24°C+窗帘全开+门禁解锁 |
| **离家** | s2 | 12 | 0 | 12 | 全关灯5+关空调/风扇3+窗帘关+锁门+NFC关 |
| **睡眠** | s3 | 7 | 1 | 6 | 全关灯5+空调26°C+窗帘全关 |
| **观影** | s4 | 4 | 2 | 2 | 灯20%+氛围灯关+窗帘关+空调24°C |
| **用餐** | s5 | 3 | 3 | 0 | 灯60%+厨房灯80%+抽风机开 |

### 场景别名
- 回家: 到家/我回来了/welcome/home
- 离家: 出门/走了/leave/away
- 睡眠: 睡觉/晚安/休息/sleep/night
- 观影: 看电影/电视/movie/film
- 用餐: 吃饭/晚餐/dinner/meal

---

## 5. 数据库 (SQLite)

### 表结构
| 表 | 行数 | 用途 |
|----|------|------|
| devices | 16 | 设备信息与状态 |
| sensors | 9 | 传感器配置与当前值 |
| device_operations | 自动增长 | 操作日志(设备ID/动作/来源/场景) |
| sensor_readings | 自动增长 | 传感器历史读数 |
| scenes | 5 | 场景定义 |
| scene_actions | 30 | 场景动作(5场景×4~12动作) |
| users | 1 | 用户信息 |
| chat_history | 自动增长 | 对话记录(含场景关联) |

### 实测数据
```
设备操作记录: 15条 (场景切换触发)
  ac_01 scene_toggle scene s4
  curtain_01 scene_toggle scene s4
  light_01 scene_toggle scene s1
  door_01 scene_toggle scene s1
  ...
```

---

## 6. HTTP API 网关 v3

### 替代原 smart_home_gateway_v2.py
- 框架: http.server.ThreadingHTTPServer (纯标准库)
- 监听: 0.0.0.0:8080
- 完全兼容前端 Http.ets 的 BASE_CANDIDATES

### API 端点 (20+)
| 路径 | 方法 | 说明 |
|------|------|------|
| /health | GET | 健康检查 → `{"ok":true,"v":3}` |
| /api/devices | GET | 16台设备列表 |
| /api/devices/{id}/toggle | POST | 开关设备 |
| /api/devices/{id}/control | POST | 控制设备参数 |
| /api/devices | POST | 添加设备 |
| /api/sensors | GET | 9个传感器列表 |
| /api/cameras | GET | 摄像头列表 |
| /api/alerts | GET | 告警消息 |
| /api/scenes | GET | 5个场景(含动作) |
| /api/scenes/{id}/activate | POST | 激活场景 |
| /api/user/profile | GET/PUT | 用户信息 |
| /api/server/status | GET | 服务端状态 |
| /api/chat/send | POST | RAG增强+DeepSeek对话 |
| /api/bearpi/command | POST | BearPi开发板命令 |
| /api/operations | GET | 操作记录 |
| /api/rag/search | POST | RAG知识库搜索 |
| /api/rag/stats | GET | RAG统计 |

---

## 7. 实测验证

### 场景激活
```
POST /api/scenes/s3/activate → "已切换到「睡眠」模式，控制 7 台设备"
  客厅空调: ON 26°C ✅
  客厅主灯: OFF ✅
  所有5盏灯: OFF ✅
  窗帘: OFF 全关 ✅
```

### 对话场景联动
```
POST /api/chat/send {"messages":[{"role":"user","content":"watch movie"}]}
→ "已切换到「观影」模式，控制 4 台设备" ✅
→ RAG自动匹配 s4 观影场景并执行
```

### RAG搜索
```
POST /api/rag/search {"query":"watch movie"}
→ scene: 观影(s4) score=6.14 ✅
```

---

## 8. 启动方式

```bash
# 在 hdc shell 内
sh /data/A9/run_v3.sh

# 或手动启动
cd /data/A9
export PATH=/data/A9/bin:$PATH
export LD_LIBRARY_PATH=/data/A9/python-portable/lib:/data/A9/python-portable/usr/lib:/system/lib
export SSL_CERT_FILE=/data/A9/certs/cacert.pem
export PYTHONPATH=/data/A9/smart_home
export DEEPSEEK_API_KEY=sk-...
nohup python3 /data/A9/smart_home/gateway_v3.py > gateway_stdout.log 2>&1 &
```

---

## 9. 技术选型说明

| 需求 | 方案 | 原因 |
|------|------|------|
| MCP | 纯标准库 JSON-RPC | ARM32 musl 无法装 fastmcp |
| RAG | TF-IDF + 关键词匹配 | ARM32 无法装 chromadb/sentence-transformers |
| LangGraph | 预留 graph/ 目录 | ARM32 无法装 langgraph，但网关内已实现意图分类+多节点分发逻辑 |
| 数据库 | SQLite (标准库) | Python 3.14 自带 sqlite3 |
| HTTP | http.server | 纯标准库，v2已验证可用 |
| 对话增强 | RAG场景匹配 + DeepSeek | 无需本地LLM，先RAG匹配场景，再调DeepSeek |
