# 智慧家居在线 TTS 语音合成 API 文档

> 版本: v3.1 | 更新: 2026-07-09
> 后端: 百度翻译语音合成 (fanyi.baidu.com/gettts)

## 1. 概述

在线 TTS 使用百度翻译公开 API，中文文本实时转 MP3，自动缓存，前端 HTTP 获取播放。

### TTS 后端模式

| 后端 | 说明 | 网络需求 |
|------|------|----------|
| online | 在线语音合成 (默认) | 需联网 |
| wav | 预录 WAV 文件 | 离线 |
| beep | 蜂鸣音 | 离线 |
| none | 静音 | - |

online 失败自动降级 wav -> beep。

## 2. API 端点

### GET /api/tts/config - 获取配置
### POST /api/tts/config - 更新配置
  body: {"speed":1.5, "volume":0.8, "enabled":true, "backend":"online"}

### POST /api/tts/speak - 在线文本转语音
  body: {"text":"客厅主灯已开启", "speed":5}
  resp: {"ok":true, "text":"...", "played":true, "backend":"online"}

### POST /api/tts/test - 测试语音
  body: {"key":"light_01_toggle"} 或 {"text":"自定义文本"}

### GET /api/tts/text_map - 语音文本映射表 (44条+21动态)
### GET /api/tts/cache - 查看MP3缓存
### GET /api/tts/audio/<hash>.mp3 - 获取音频文件 (audio/mpeg)
### GET /api/tts/list - 预录WAV列表

## 3. 语音映射表

### 查询类
ping=连通测试成功, get_server_status=服务状态正常, get_status=全量状态查询完成,
get_devices=设备列表查询完成, get_sensors=传感器数据查询完成, get_scenes=场景列表查询完成,
get_user=用户信息查询完成, get_operations=操作记录查询完成, get_chat_history=对话历史查询完成,
rag_search=知识搜索完成, update_user=用户信息已更新, get_alerts=告警信息查询完成,
get_cameras=摄像头状态查询完成

### 设备开关 (动态: is_on->开启/关闭)
light_01_toggle=客厅主灯, door_01_toggle=客厅大门(解锁/锁定),
alarm_01_toggle=蜂鸣警报, light_02_toggle=厨房灯,
curtain_01_toggle=智能窗帘, light_03_toggle=卧室灯,
fan_02_toggle=换气扇, light_04_toggle=卫生间灯,
nfc_01_toggle=NFC门禁, voice_01_toggle=语音中控,
radar_01_toggle=毫米波雷达, fan_01_toggle=客厅吊扇,
exhaust_01_toggle=抽风机, light_05_toggle=客厅氛围灯,
camera_01_toggle=客厅摄像头, ac_01_toggle=客厅空调

### 设备控制 (动态: primary_value->具体值)
ac_01_set_temp=空调温度已设置为N度, ac_01_set_mode=空调模式已切换为mode,
ac_01_set_speed=空调风速已设置为speed, light_set_brightness=灯光亮度已设置为N%,
curtain_01_ctrl=窗帘开合度已设置为N%

### 场景
s1_activate=欢迎回家，回家模式已激活, s2_activate=离家模式已激活，注意安全,
s3_activate=睡眠模式已激活，晚安, s4_activate=观影模式已激活，请享受,
s5_activate=用餐模式已激活，请慢用

### 特殊
add_device=新设备已添加, remove_device=设备已移除, send_chat=AI对话完成,
offline_generic=操作完成, channel_ok=通道连接正常

## 4. 百度 TTS API
URL: https://fanyi.baidu.com/gettts?lan=zh&text=...&spd=N&source=web
spd: 1-10 (5=正常), 缓存key=MD5(text+spd), 路径=tts_cache/<hash>.mp3

## 5. 前端集成
1. 后端操作自动合成语音
2. 前端WebSocket接收操作结果
3. 前端从/api/tts/audio/获取MP3播放
4. 首次合成后缓存，后续直接获取
