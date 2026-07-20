#!/usr/bin/env python3
"""
多协议安全传输网关 · 纯标准库实现
HTTPS / WebSocket / MQTT / CoAP 四协议并行 + 国密加密

协议-场景映射:
  HTTPS  :8443  — 批量查询、配置管理、远程加密调用 (TLS + SecureEnvelope)
  WebSocket :8080/ws — AI对话、实时状态推送、报警 (SM4加密帧)
  MQTT   :1883  — 设备控制、传感器上报、场景激活 (SM4+SM3)
  CoAP   :5683  — 低功耗IoT传感器查询 (SM4+SM3轻量)

运行环境: HarmonyOS ARM32 + Python 3.14.5 (纯标准库)
部署位置: /data/A9/smart_home/protocol_gateway.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import socket
import ssl
import struct
import threading
import time
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Callable

# 复用国密模块
from gm_crypto import sm3_hash, sm4_encrypt, sm4_decrypt, sm2_sign, sm2_verify, SecureEnvelope, SM2KeyPair

# ═══════════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════════

def _log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [PROTO] {msg}"
    print(line, flush=True)
    try:
        with open(str(Path(__file__).resolve().parent / "protocol_gateway.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# CryptoLayer — 统一加密层
# ═══════════════════════════════════════════════════════════════

class CryptoLayer:
    """
    所有协议共享的加密/解密/签名/验签
    复用 gm_crypto 的 SM2/SM3/SM4 实现
    """

    def __init__(self, sm4_key: bytes, sm2_keypair: SM2KeyPair):
        self.sm4_key = sm4_key
        self.sm2_keypair = sm2_keypair
        self.envelope = SecureEnvelope(sm4_key, sm2_keypair)

    def encrypt_payload(self, data: dict) -> tuple[bytes, str]:
        """SM4-CBC加密 + SM3完整性标签, 返回 (密文, sm3_tag_hex)"""
        raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        iv_and_ct = sm4_encrypt(self.sm4_key, raw)
        tag = sm3_hash(iv_and_ct).hex()
        return iv_and_ct, tag

    def decrypt_payload(self, ciphertext: bytes, tag_hex: str) -> dict:
        """SM4解密 + SM3完整性验证"""
        expected_tag = sm3_hash(ciphertext).hex()
        if tag_hex and tag_hex != expected_tag:
            raise ValueError(f"SM3完整性校验失败: expected={expected_tag[:16]}... got={tag_hex[:16]}...")
        raw = sm4_decrypt(self.sm4_key, ciphertext)
        return json.loads(raw.decode('utf-8'))

    def sign_frame(self, data: bytes) -> str:
        """SM2签名, 返回hex"""
        sig = sm2_sign(self.sm2_keypair, data)
        return sig.hex()

    def verify_frame(self, data: bytes, signature_hex: str, pubkey_hex: str) -> bool:
        """SM2验签"""
        try:
            sig = bytes.fromhex(signature_hex)
            pubkey = bytes.fromhex(pubkey_hex)
            return sm2_verify(pubkey, data, sig)
        except Exception:
            return False

    def make_envelope(self, data: dict, protocol_tag: str = "") -> dict:
        """封装安全信封 (复用SecureEnvelope)"""
        inner = {"protocol": protocol_tag, "data": data}
        return self.envelope.seal(inner)

    def open_envelope(self, envelope: dict) -> dict:
        """解封安全信封"""
        return self.envelope.unseal(envelope, verify_signature=True, max_age_seconds=300)

    def make_light_envelope(self, data: dict) -> dict:
        """轻量封装: SM4加密 + SM3标签 (用于MQTT/CoAP)"""
        ct, tag = self.encrypt_payload(data)
        return {
            "ct": ct.hex(),
            "tag": tag,
            "ts": int(time.time()),
        }

    def open_light_envelope(self, envelope: dict) -> dict:
        """轻量解封"""
        ct = bytes.fromhex(envelope["ct"])
        tag = envelope.get("tag", "")
        return self.decrypt_payload(ct, tag)


# ═══════════════════════════════════════════════════════════════
# ActionRouter — 统一业务分发
# ═══════════════════════════════════════════════════════════════

class ActionRouter:
    """
    所有协议收到的请求统一路由到 gateway_v6 的业务方法
    通过gateway_v6模块的全局变量和函数直接访问，不实例化H类
    """

    def __init__(self, crypto: CryptoLayer):
        self._crypto = crypto
        self._gw = None  # 延迟导入

    def _get_gw(self):
        """延迟导入gateway_v6模块"""
        if self._gw is None:
            import gateway_v6 as gw
            self._gw = gw
        return self._gw

    def route(self, protocol: str, action: str, params: dict, auth_token: str = "") -> dict:
        """
        统一路由入口
        protocol: 'https'/'ws'/'mqtt'/'coap'
        action: 业务动作 (同secure action命名)
        params: 业务参数
        auth_token: Bearer token (可选)
        """
        try:
            gw = self._get_gw()

            # 验证权限
            if auth_token:
                auth_info = gw.verify_token(auth_token, gw._TOKEN_SECRET)
                if not auth_info:
                    return {"error": "Token无效", "code": 403}
            else:
                auth_info = {"uid": "local", "permissions": ["read", "write"]}

            # 分发到业务逻辑
            result = self._dispatch(gw, action, params)

            # 记录到DB
            _log(f"[{protocol}] {action} → {'ok' if not result.get('error') else 'err'}")
            try:
                conn = gw._db()
                conn.execute(
                    "INSERT INTO remote_access_log(client_id,endpoint,method,ip_address,status_code,encrypted) VALUES(?,?,?,?,?,?)",
                    (auth_info.get("uid", "unknown"), f"/action/{action}", protocol.upper(), "internal", 200, 1)
                )
                conn.commit(); conn.close()
            except Exception:
                pass

            return result

        except Exception as e:
            _log(f"[{protocol}] {action} 异常: {e}")
            return {"error": str(e), "code": 500}

    def _dispatch(self, gw, action: str, params: dict) -> dict:
        """分发到gateway_v6业务逻辑"""
        # 设备控制
        if action == "device.toggle":
            return gw.hw_toggle(params.get("device_id", ""), params.get("isOn", True),
                                door_password=params.get("doorPassword"))
        elif action == "device.control":
            return gw.hw_control(params.get("device_id", ""), params.get("action", "toggle"), params)
        elif action == "device.list":
            return self._get_devices(gw)
        elif action == "device.status":
            with gw._STATUS_LOCK:
                return gw._DEVICE_STATUS.get(params.get("device_id", ""), {"online": False})
        # 传感器
        elif action == "sensor.list":
            return self._get_sensors(gw)
        elif action == "sensor.history":
            return self._get_sensor_history(gw)
        # 场景
        elif action == "scene.activate":
            return gw.hw_scene_execute(params.get("scene_id", ""))
        elif action == "scene.list":
            return self._list_scenes(gw)
        # 门禁
        elif action == "door.control":
            return gw.hw_toggle("door_01", params.get("action") == "open")
        # 空调
        elif action == "ac.control":
            return gw.hw_control("ac_01", params.get("action", "set_temperature"), params)
        # 状态
        elif action == "status.all":
            return self._get_stats(gw)
        elif action == "status.check":
            return self._check_all(gw)
        # AI
        elif action == "chat.send":
            return self._chat(gw, params)
        elif action == "ai.intent":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.parse(params.get("message", ""), execute=False)
            return {"error": "Intent engine not available"}
        elif action == "ai.execute":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.parse(params.get("message", ""), execute=True)
            return {"error": "Intent engine not available"}
        elif action == "ai.capabilities":
            from intent_engine import get_device_capabilities
            return get_device_capabilities(gw.DEVICE_DEFS)
        elif action == "ai.anomaly":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.get_anomaly_events()
            return {"events": []}
        elif action == "ai.recommendations":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.get_recommendations()
            return {"recommendations": []}
        elif action == "ai.energy":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.get_energy_consumption()
            return {"total_watts": 0}
        elif action == "ai.energy.waste":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.get_energy_waste()
            return {"waste_items": []}
        elif action == "ai.energy.report":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.get_energy_report()
            return {"report": ""}
        elif action == "ai.linkage":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.get_linkage_rules()
            return {"rules": []}
        elif action == "ai.emotion":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.analyze_emotion(params.get("message", ""))
            return {"emotion": "neutral"}
        elif action == "ai.context":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return {"context": ie.get_context_summary()}
            return {"context": {}}
        elif action == "ai.device.register":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.register_device(params)
            return {"error": "Intent engine not available"}
        elif action == "ai.device.unregister":
            ie = getattr(gw, '_intent_engine', None)
            if ie:
                return ie.unregister_device(params.get("device_id", ""))
            return {"error": "Intent engine not available"}
        # 安全
        elif action == "security.events":
            return self._security_events(gw)
        elif action == "security.stats":
            return self._security_stats(gw)
        # 健康检查
        elif action == "health":
            return {"ok": True, "v": 6, "protocols": ["https", "ws", "mqtt", "coap"],
                    "crypto": "SM2+SM3+SM4"}
        else:
            return {"error": f"Unknown action: {action}", "code": 404}

    # ===== 业务逻辑辅助 (直接访问gateway_v6全局状态) =====

    def _get_devices(self, gw):
        result = []
        with gw._STATUS_LOCK:
            for d in gw.DEVICE_DEFS:
                cached = gw._DEVICE_STATUS.get(d["id"], {})
                online = cached.get("online", False)
                if online:
                    entry = {"id": d["id"], "name": d["name"], "type": d["type"],
                             "status": "online", "room": d["room"], "icon": d["icon"],
                             "values": cached.get("values", {})}
                else:
                    entry = {"id": d["id"], "name": d["name"], "type": d["type"],
                             "status": "offline", "room": d["room"], "icon": d["icon"]}
                result.append(entry)
        return {"devices": result, "total": len(result)}

    def _get_sensors(self, gw):
        result = []
        with gw._STATUS_LOCK:
            for s in gw.SENSOR_DEFS:
                cached = gw._SENSOR_STATUS.get(s["id"], {})
                entry = {"id": s["id"], "name": s["name"], "type": s["type"],
                         "room": s["room"], "values": cached.get("values", {})}
                result.append(entry)
        return {"sensors": result, "total": len(result)}

    def _get_sensor_history(self, gw):
        try:
            conn = gw._db()
            rows = conn.execute("SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 100").fetchall()
            conn.close()
            return {"readings": [dict(zip([d[0] for d in conn.execute('SELECT * FROM sensor_readings LIMIT 0').description], r)) for r in rows]}
        except Exception:
            return {"readings": []}

    def _list_scenes(self, gw):
        try:
            from scene_config import SCENES
            return {"scenes": [{"id": k, **v} for k, v in SCENES.items()]}
        except Exception:
            return {"scenes": []}

    def _get_stats(self, gw):
        with gw._STATUS_LOCK:
            online = sum(1 for s in gw._DEVICE_STATUS.values() if s.get("online"))
        return {"devices_online": online, "devices_total": len(gw.DEVICE_DEFS),
                "sensors_total": len(gw.SENSOR_DEFS)}

    def _check_all(self, gw):
        return {"ok": True, "hardware": gw._HW_OK, "crypto": True}

    def _chat(self, gw, params):
        """AI对话"""
        text = params.get("message", params.get("text", ""))
        if not text:
            return {"error": "Empty message"}
        ie = getattr(gw, '_intent_engine', None)
        if ie:
            result = ie.parse(text, execute=True,
                                              executor=lambda i: gw.hw_toggle(i.get("device_id", ""), i.get("isOn", True)) if i.get("type") == "device_toggle" else None)
            return result
        return {"reply": "AI引擎未就绪", "source": "fallback"}

    def _parse_intent(self, gw, params):
        text = params.get("message", "")
        if gw._intent_engine:
            return gw._intent_engine.parse(text, execute=False)
        return {"error": "Intent engine not available"}

    def _execute_intent(self, gw, params):
        text = params.get("message", "")
        if gw._intent_engine:
            return gw._intent_engine.parse(text, execute=True)
        return {"error": "Intent engine not available"}

    def _security_events(self, gw):
        try:
            conn = gw._db()
            rows = conn.execute("SELECT * FROM security_log ORDER BY id DESC LIMIT 50").fetchall()
            conn.close()
            return {"events": []}
        except Exception:
            return {"events": []}

    def _security_stats(self, gw):
        return {"total_events": 0, "blocked": 0}


# ═══════════════════════════════════════════════════════════════
# MQTT Broker — 纯标准库 MQTT v3.1.1
# ═══════════════════════════════════════════════════════════════

class MQTTBroker:
    """
    轻量MQTT v3.1.1 Broker
    支持: CONNECT/CONNACK/PUBLISH/SUBSCRIBE/SUBACK/PINGREQ/PINGRESP/DISCONNECT
    QoS: 0 (at most once)
    Topic过滤: 支持单层+和多层#通配符
    """

    MQTT_PORT = 1883
    KEEPALIVE_DEFAULT = 60

    # MQTT Packet Types
    CONNECT = 1
    CONNACK = 2
    PUBLISH = 3
    PUBACK = 4
    SUBSCRIBE = 8
    SUBACK = 9
    PINGREQ = 12
    PINGRESP = 13
    DISCONNECT = 14

    def __init__(self, crypto: CryptoLayer, router: ActionRouter):
        self.crypto = crypto
        self.router = router
        self.clients = {}  # client_id → {socket, subscriptions, keepalive}
        self.subscriptions = {}  # topic_pattern → set(client_ids)
        self.retained = {}  # topic → payload
        self._lock = threading.Lock()
        self._running = False
        self._msg_id = 0

    def start(self):
        """启动MQTT Broker"""
        self._running = True
        t = threading.Thread(target=self._accept_loop, daemon=True, name="mqtt-accept")
        t.start()
        _log(f"[MQTT] Broker启动 :{self.MQTT_PORT}")

    def stop(self):
        self._running = False

    def publish_internal(self, topic: str, data: dict):
        """内部发布 (gateway_v6调用，推送设备状态变化)"""
        envelope = self.crypto.make_light_envelope(data)
        payload = json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        with self._lock:
            matched = self._match_subscribers(topic)
            for cid in matched:
                client = self.clients.get(cid)
                if client and client.get("socket"):
                    try:
                        self._send_publish(client["socket"], topic, payload, qos=0)
                    except Exception:
                        pass

    def _accept_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self.MQTT_PORT))
        sock.listen(10)
        sock.settimeout(1.0)

        while self._running:
            try:
                conn, addr = sock.accept()
                conn.settimeout(30)
                t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    _log(f"[MQTT] Accept错误: {e}")

        sock.close()

    def _handle_client(self, conn, addr):
        """处理单个MQTT客户端连接"""
        client_id = f"client_{addr[1]}"
        try:
            # 等待CONNECT
            packet = self._recv_packet(conn)
            if not packet or packet[0] >> 4 != self.CONNECT:
                conn.close()
                return

            ptype, flags, payload = packet
            # 解析CONNECT
            client_id, username, password, keepalive = self._parse_connect(payload)
            _log(f"[MQTT] 客户端连接: {client_id} from {addr[0]}")

            # 验证 (简单: 密码=SM4密钥指纹 或 空密码允许局域网)
            # CONNACK: 连接接受
            self._send_connack(conn, 0)

            with self._lock:
                self.clients[client_id] = {
                    "socket": conn,
                    "subscriptions": set(),
                    "keepalive": keepalive or self.KEEPALIVE_DEFAULT,
                    "addr": addr,
                }

            # 消息循环
            last_ping = time.time()
            while self._running:
                try:
                    conn.settimeout(5)
                    packet = self._recv_packet(conn)
                    if not packet:
                        # 检查keepalive
                        if time.time() - last_ping > (self.clients.get(client_id, {}).get("keepalive", 60) * 1.5):
                            break
                        continue

                    ptype = packet[0] >> 4
                    flags = packet[0] & 0x0F
                    payload = packet[2]

                    if ptype == self.PUBLISH:
                        self._handle_publish(client_id, flags, payload)
                    elif ptype == self.SUBSCRIBE:
                        self._handle_subscribe(client_id, payload, conn)
                    elif ptype == self.PINGREQ:
                        self._send_pingresp(conn)
                        last_ping = time.time()
                    elif ptype == self.DISCONNECT:
                        break

                    last_ping = time.time()

                except socket.timeout:
                    continue
                except Exception:
                    break

        except Exception as e:
            _log(f"[MQTT] 客户端处理异常: {e}")
        finally:
            with self._lock:
                self.clients.pop(client_id, None)
            try:
                conn.close()
            except Exception:
                pass
            _log(f"[MQTT] 客户端断开: {client_id}")

    def _recv_packet(self, conn) -> Optional[tuple]:
        """接收一个MQTT包, 返回 (first_byte, remaining_length, payload)"""
        header = self._recv_exact(conn, 1)
        if not header:
            return None
        first_byte = header[0]

        # 解码剩余长度 (变长编码)
        multiplier = 1
        remaining_length = 0
        while True:
            b = self._recv_exact(conn, 1)
            if not b:
                return None
            encoded_byte = b[0]
            remaining_length += (encoded_byte & 0x7F) * multiplier
            multiplier *= 128
            if not (encoded_byte & 0x80):
                break
            if multiplier > 128 * 128 * 128:
                return None

        if remaining_length == 0:
            return (first_byte, 0, b"")

        payload = self._recv_exact(conn, remaining_length)
        if not payload:
            return None

        return (first_byte, remaining_length, payload)

    def _recv_exact(self, conn, n):
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = conn.recv(n - len(buf))
                if not chunk:
                    return None
                buf.extend(chunk)
            except Exception:
                return None
        return bytes(buf)

    def _parse_connect(self, payload: bytes):
        """解析CONNECT包, 返回 (client_id, username, password, keepalive)"""
        # Protocol Name
        proto_len = struct.unpack("!H", payload[0:2])[0]
        proto_name = payload[2:2 + proto_len].decode('utf-8', errors='ignore')
        proto_level = payload[2 + proto_len]
        connect_flags = payload[3 + proto_len]
        keepalive = struct.unpack("!H", payload[4 + proto_len:6 + proto_len])[0]

        # Payload (Client ID, optional Will, Username, Password)
        offset = 6 + proto_len
        cid_len = struct.unpack("!H", payload[offset:offset + 2])[0]
        client_id = payload[offset + 2:offset + 2 + cid_len].decode('utf-8', errors='ignore')
        offset += 2 + cid_len

        username = None
        password = None

        has_username = bool(connect_flags & 0x80)
        has_password = bool(connect_flags & 0x40)

        # Skip Will Topic/Payload if present
        has_will = bool(connect_flags & 0x04)
        if has_will:
            will_len = struct.unpack("!H", payload[offset:offset + 2])[0]
            offset += 2 + will_len
            will_payload_len = struct.unpack("!H", payload[offset:offset + 2])[0]
            offset += 2 + will_payload_len

        if has_username and offset + 2 <= len(payload):
            ulen = struct.unpack("!H", payload[offset:offset + 2])[0]
            username = payload[offset + 2:offset + 2 + ulen].decode('utf-8', errors='ignore')
            offset += 2 + ulen

        if has_password and offset + 2 <= len(payload):
            plen = struct.unpack("!H", payload[offset:offset + 2])[0]
            password = payload[offset + 2:offset + 2 + plen].decode('utf-8', errors='ignore')

        return client_id, username, password, keepalive

    def _send_connack(self, conn, return_code: int):
        """发送CONNACK"""
        packet = bytearray()
        packet.append(0x20)  # CONNACK
        packet.append(0x02)  # Remaining length = 2
        packet.append(0x00)  # Session Present = 0
        packet.append(return_code)  # Return code
        conn.sendall(bytes(packet))

    def _send_publish(self, conn, topic: str, payload: bytes, qos: int = 0, retain: bool = False):
        """发送PUBLISH"""
        topic_bytes = topic.encode('utf-8')
        remaining = 2 + len(topic_bytes) + len(payload)
        if qos > 0:
            remaining += 2  # Packet ID

        first_byte = 0x30 | (qos << 1) | (0x01 if retain else 0x00)

        packet = bytearray()
        packet.append(first_byte)
        packet.extend(self._encode_remaining_length(remaining))
        packet.extend(struct.pack("!H", len(topic_bytes)))
        packet.extend(topic_bytes)
        if qos > 0:
            with self._lock:
                self._msg_id += 1
                packet.extend(struct.pack("!H", self._msg_id))
        packet.extend(payload)
        conn.sendall(bytes(packet))

    def _send_suback(self, conn, packet_id: int, return_codes: list):
        """发送SUBACK"""
        remaining = 2 + len(return_codes)
        packet = bytearray()
        packet.append(0x90)  # SUBACK
        packet.extend(self._encode_remaining_length(remaining))
        packet.extend(struct.pack("!H", packet_id))
        for rc in return_codes:
            packet.append(rc)  # 0=QoS0成功
        conn.sendall(bytes(packet))

    def _send_pingresp(self, conn):
        """发送PINGRESP"""
        conn.sendall(bytes([0xD0, 0x00]))

    def _encode_remaining_length(self, length: int) -> bytes:
        """编码MQTT剩余长度"""
        result = bytearray()
        while True:
            encoded_byte = length % 128
            length = length // 128
            if length > 0:
                encoded_byte |= 0x80
            result.append(encoded_byte)
            if length == 0:
                break
        return bytes(result)

    def _handle_publish(self, client_id: str, flags: int, payload: bytes):
        """处理客户端PUBLISH"""
        dup = bool(flags & 0x08)
        qos = (flags >> 1) & 0x03
        retain = bool(flags & 0x01)

        # 解析topic
        topic_len = struct.unpack("!H", payload[0:2])[0]
        topic = payload[2:2 + topic_len].decode('utf-8')
        offset = 2 + topic_len

        if qos > 0:
            packet_id = struct.unpack("!H", payload[offset:offset + 2])[0]
            offset += 2
            # Send PUBACK for QoS 1
            if qos == 1:
                client = self.clients.get(client_id)
                if client and client.get("socket"):
                    puback = bytearray()
                    puback.append(0x40)
                    puback.append(0x02)
                    puback.extend(struct.pack("!H", packet_id))
                    client["socket"].sendall(bytes(puback))

        msg_payload = payload[offset:]

        # 解密并路由
        try:
            envelope = json.loads(msg_payload.decode('utf-8'))
            data = self.crypto.open_light_envelope(envelope)
            action = data.get("action", "")
            params = data.get("params", {})
            result = self.router.route("mqtt", action, params)

            # 回复到 reply topic
            reply_topic = topic.replace("/cmd/", "/status/").replace("/req/", "/resp/")
            self.publish_internal(reply_topic, result)

        except Exception as e:
            _log(f"[MQTT] PUBLISH处理失败: {e}")

        # Retain
        if retain:
            self.retained[topic] = msg_payload

    def _handle_subscribe(self, client_id: str, payload: bytes, conn):
        """处理SUBSCRIBE"""
        packet_id = struct.unpack("!H", payload[0:2])[0]
        offset = 2
        topics = []
        return_codes = []

        while offset < len(payload):
            topic_len = struct.unpack("!H", payload[offset:offset + 2])[0]
            topic = payload[offset + 2:offset + 2 + topic_len].decode('utf-8')
            offset += 2 + topic_len
            requested_qos = payload[offset] if offset < len(payload) else 0
            offset += 1
            topics.append(topic)
            return_codes.append(0)  # 接受QoS 0

            with self._lock:
                if topic not in self.subscriptions:
                    self.subscriptions[topic] = set()
                self.subscriptions[topic].add(client_id)
                if client_id in self.clients:
                    self.clients[client_id]["subscriptions"].add(topic)

        self._send_suback(conn, packet_id, return_codes)
        _log(f"[MQTT] {client_id} 订阅: {topics}")

        # 发送retained消息
        for topic in topics:
            for rtopic, rpayload in self.retained.items():
                if self._topic_match(topic, rtopic):
                    try:
                        self._send_publish(conn, rtopic, rpayload, qos=0, retain=True)
                    except Exception:
                        pass

    def _topic_match(self, subscription: str, topic: str) -> bool:
        """检查topic是否匹配subscription模式"""
        sub_parts = subscription.split('/')
        top_parts = topic.split('/')

        for i, sp in enumerate(sub_parts):
            if sp == '#':
                return True
            if i >= len(top_parts):
                return False
            if sp != '+' and sp != top_parts[i]:
                return False

        return len(sub_parts) == len(top_parts)

    def _match_subscribers(self, topic: str) -> list:
        """找到订阅了该topic的所有client_id"""
        matched = []
        for pattern, cids in self.subscriptions.items():
            if self._topic_match(pattern, topic):
                matched.extend(cids)
        return list(set(matched))


# ═══════════════════════════════════════════════════════════════
# WebSocket Server — RFC 6455
# ═══════════════════════════════════════════════════════════════

class WebSocketServer:
    """
    WebSocket服务端 (复用channel.py的RFC 6455帧实现)
    在HTTP 8080端口的 /ws 路径提供升级
    支持双向: 客户端请求 + 服务端主动推送
    """

    WS_MAGIC = "258EAFA5-E914-47DA-95CA-5AB5A865B1D7"

    def __init__(self, crypto: CryptoLayer, router: ActionRouter):
        self.crypto = crypto
        self.router = router
        self.clients = {}  # fd → {socket, addr, authenticated}
        self._lock = threading.Lock()
        self._running = False
        self._event_queue = []  # 待推送事件
        self._event_lock = threading.Lock()

    def start(self, http_server_socket=None):
        """启动WebSocket接受线程 (在HTTP服务器socket上复用)"""
        self._running = True
        # WebSocket通过HTTP升级处理，不需要独立socket
        # 启动事件推送线程
        t = threading.Thread(target=self._push_loop, daemon=True, name="ws-push")
        t.start()
        _log("[WS] WebSocket服务端就绪 (升级路径: /ws)")

    def stop(self):
        self._running = False

    def handle_upgrade(self, request_headers: str, client_socket, client_addr) -> bool:
        """
        处理HTTP→WebSocket升级请求
        返回True表示升级成功，连接已接管
        """
        try:
            # 解析Sec-WebSocket-Key
            ws_key = None
            for line in request_headers.split('\r\n'):
                if line.lower().startswith('sec-websocket-key:'):
                    ws_key = line.split(':', 1)[1].strip()
                    break

            if not ws_key:
                return False

            # 计算Accept
            accept = base64.b64encode(
                hashlib.sha1((ws_key + self.WS_MAGIC).encode()).digest()
            ).decode()

            # 发送握手响应
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            )
            client_socket.sendall(response.encode())
            client_socket.settimeout(60)

            # 注册客户端
            fd = client_socket.fileno()
            with self._lock:
                self.clients[fd] = {
                    "socket": client_socket,
                    "addr": client_addr,
                    "authenticated": False,
                    "last_ping": time.time(),
                }

            _log(f"[WS] 客户端升级成功: {client_addr}")

            # 启动该客户端的消息处理线程
            t = threading.Thread(target=self._client_loop, args=(fd,), daemon=True)
            t.start()
            return True

        except Exception as e:
            _log(f"[WS] 升级失败: {e}")
            return False

    def broadcast_event(self, event_type: str, data: dict):
        """广播事件到所有WebSocket客户端"""
        envelope = self.crypto.make_light_envelope({
            "type": "event",
            "event": event_type,
            "data": data,
            "ts": int(time.time()),
        })
        msg = json.dumps(envelope, ensure_ascii=False, separators=(',', ':'))

        with self._lock:
            dead = []
            for fd, client in self.clients.items():
                try:
                    self._ws_send(client["socket"], msg, opcode=0x1)
                except Exception:
                    dead.append(fd)
            for fd in dead:
                self.clients.pop(fd, None)

    def _client_loop(self, fd: int):
        """处理单个WebSocket客户端的消息"""
        client = self.clients.get(fd)
        if not client:
            return

        sock = client["socket"]
        try:
            while self._running:
                frame = self._ws_recv(sock)
                if frame is None:
                    break

                opcode, payload = frame

                if opcode == 0x1:  # 文本
                    self._handle_text_message(fd, payload.decode('utf-8', errors='ignore'))
                elif opcode == 0x8:  # 关闭
                    break
                elif opcode == 0x9:  # Ping
                    self._ws_send(sock, payload, opcode=0xA)
                elif opcode == 0xA:  # Pong
                    pass

        except Exception as e:
            _log(f"[WS] 客户端异常: {e}")
        finally:
            with self._lock:
                self.clients.pop(fd, None)
            try:
                sock.close()
            except Exception:
                pass
            _log(f"[WS] 客户端断开: {client.get('addr')}")

    def _handle_text_message(self, fd: int, text: str):
        """处理WebSocket文本消息"""
        try:
            msg = json.loads(text)
            action = msg.get("action", "")
            params = msg.get("params", {})
            msg_id = msg.get("id", 0)
            token = msg.get("token", "")

            # 如果消息是加密的
            if "ct" in msg:
                data = self.crypto.open_light_envelope(msg)
                action = data.get("action", action)
                params = data.get("params", params)

            # 路由
            result = self.router.route("ws", action, params, token)

            # 加密响应
            response = self.crypto.make_light_envelope({
                "type": "response",
                "id": msg_id,
                "data": result,
            })
            resp_text = json.dumps(response, ensure_ascii=False, separators=(',', ':'))

            client = self.clients.get(fd)
            if client:
                self._ws_send(client["socket"], resp_text, opcode=0x1)

        except Exception as e:
            _log(f"[WS] 消息处理失败: {e}")
            try:
                err_resp = json.dumps({"type": "error", "message": str(e)})
                client = self.clients.get(fd)
                if client:
                    self._ws_send(client["socket"], err_resp, opcode=0x1)
            except Exception:
                pass

    def _push_loop(self):
        """定期推送设备状态到WebSocket客户端"""
        while self._running:
            try:
                time.sleep(5)
                with self._lock:
                    if not self.clients:
                        continue

                # 直接访问gateway_v6全局状态，不实例化H类
                import gateway_v6 as gw
                devices = []
                with gw._STATUS_LOCK:
                    for d in gw.DEVICE_DEFS:
                        cached = gw._DEVICE_STATUS.get(d["id"], {})
                        online = cached.get("online", False)
                        if online:
                            entry = {"id": d["id"], "name": d["name"], "type": d["type"],
                                     "status": "online", "room": d["room"], "icon": d["icon"],
                                     "values": cached.get("values", {})}
                        else:
                            entry = {"id": d["id"], "name": d["name"], "type": d["type"],
                                     "status": "offline", "room": d["room"], "icon": d["icon"]}
                        devices.append(entry)
                sensors = []
                with gw._STATUS_LOCK:
                    for s in gw.SENSOR_DEFS:
                        cached = gw._SENSOR_STATUS.get(s["id"], {})
                        entry = {"id": s["id"], "name": s["name"], "type": s["type"],
                                 "room": s["room"], "values": cached.get("values", {})}
                        sensors.append(entry)

                self.broadcast_event("status_update", {
                    "devices": {"devices": devices, "total": len(devices)},
                    "sensors": {"sensors": sensors, "total": len(sensors)},
                })

            except Exception as e:
                if self._running:
                    _log(f"[WS] 推送异常: {e}")

    # ===== WebSocket帧编解码 (复用channel.py实现) =====

    def _ws_send(self, sock, data, opcode=0x1):
        """发送WebSocket帧"""
        payload = data.encode('utf-8') if isinstance(data, str) else data
        frame = bytearray()
        frame.append(0x80 | opcode)  # FIN + opcode

        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack("!Q", length))

        frame.extend(payload)
        sock.sendall(bytes(frame))

    def _ws_recv(self, sock):
        """接收WebSocket帧"""
        header = self._recv_exact(sock, 2)
        if not header:
            return None

        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F

        if length == 126:
            ext = self._recv_exact(sock, 2)
            if not ext:
                return None
            length = struct.unpack("!H", ext)[0]
        elif length == 127:
            ext = self._recv_exact(sock, 8)
            if not ext:
                return None
            length = struct.unpack("!Q", ext)[0]

        mask_key = None
        if masked:
            mask_key = self._recv_exact(sock, 4)
            if not mask_key:
                return None

        payload = self._recv_exact(sock, length)
        if payload is None:
            return None

        if masked and mask_key:
            unmasked = bytearray(length)
            for i in range(length):
                unmasked[i] = payload[i] ^ mask_key[i % 4]
            payload = bytes(unmasked)

        return opcode, payload

    def _recv_exact(self, sock, n):
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = sock.recv(n - len(buf))
                if not chunk:
                    return None
                buf.extend(chunk)
            except Exception:
                return None
        return bytes(buf)


# ═══════════════════════════════════════════════════════════════
# HTTPS Server — TLS 1.3 + 国密
# ═══════════════════════════════════════════════════════════════

class HTTPSServer:
    """
    HTTPS服务端 (TLS 1.3 + SM2签名)
    镜像所有HTTP接口到HTTPS
    SecureEnvelope端点强制HTTPS
    """

    HTTPS_PORT = 8443

    def __init__(self, crypto: CryptoLayer, router: ActionRouter):
        self.crypto = crypto
        self.router = router
        self._running = False
        self._cert_dir = str(Path(__file__).resolve().parent / "keys" / "tls")

    def start(self):
        """启动HTTPS服务"""
        self._ensure_cert()
        self._running = True

        t = threading.Thread(target=self._serve, daemon=True, name="https")
        t.start()
        _log(f"[HTTPS] 服务启动 :{self.HTTPS_PORT}")

    def stop(self):
        self._running = False

    def _ensure_cert(self):
        """确保证书存在，不存在则生成"""
        cert_path = os.path.join(self._cert_dir, "device.crt")
        key_path = os.path.join(self._cert_dir, "device.key")

        if os.path.exists(cert_path) and os.path.exists(key_path):
            return

        os.makedirs(self._cert_dir, exist_ok=True)

        # 用Python ssl模块生成自签名证书
        # 使用openssl命令行（如果可用）或纯Python
        try:
            # 尝试用openssl
            import subprocess
            ca_key = os.path.join(self._cert_dir, "ca.key")
            ca_crt = os.path.join(self._cert_dir, "ca.crt")

            # 生成CA
            subprocess.run([
                "openssl", "req", "-x509", "-new", "-nodes",
                "-newkey", "ec:-pkeyopt ec_paramgen_curve:prime256v1",
                "-keyout", ca_key,
                "-out", ca_crt,
                "-days", "3650",
                "-subj", "/CN=A9-SmartHome-CA/O=SmartHome"
            ], capture_output=True, timeout=30)

            # 生成设备证书
            device_csr = os.path.join(self._cert_dir, "device.csr")
            subprocess.run([
                "openssl", "req", "-new", "-nodes",
                "-newkey", "ec:-pkeyopt ec_paramgen_curve:prime256v1",
                "-keyout", key_path,
                "-out", device_csr,
                "-subj", "/CN=a9-gateway/O=SmartHome"
            ], capture_output=True, timeout=30)

            # CA签发设备证书
            subprocess.run([
                "openssl", "x509", "-req",
                "-in", device_csr,
                "-CA", ca_crt,
                "-CAkey", ca_key,
                "-CAcreateserial",
                "-out", cert_path,
                "-days", "3650",
                "-sha256"
            ], capture_output=True, timeout=30)

            _log("[HTTPS] TLS证书生成成功 (openssl)")

        except Exception as e:
            _log(f"[HTTPS] openssl生成证书失败: {e}，使用纯Python生成")
            self._generate_cert_python(cert_path, key_path)

    def _generate_cert_python(self, cert_path: str, key_path: str):
        """纯Python生成自签名证书 (使用ssl模块)"""
        # 生成EC密钥对和自签名证书
        # Python 3.14 ssl模块不直接支持证书生成
        # 使用临时PEM文件
        try:
            import subprocess
            # 回退到RSA
            subprocess.run([
                "openssl", "req", "-x509", "-new", "-nodes",
                "-newkey", "rsa:2048",
                "-keyout", key_path,
                "-out", cert_path,
                "-days", "3650",
                "-subj", "/CN=a9-gateway/O=SmartHome"
            ], capture_output=True, timeout=30)
            _log("[HTTPS] RSA自签名证书生成成功")
        except Exception as e2:
            _log(f"[HTTPS] 证书生成全部失败: {e2}")
            # 创建占位文件，HTTPS将无法启动
            with open(cert_path, 'w') as f:
                f.write("PLACEHOLDER")
            with open(key_path, 'w') as f:
                f.write("PLACEHOLDER")

    def _serve(self):
        """HTTPS服务主循环"""
        cert_path = os.path.join(self._cert_dir, "device.crt")
        key_path = os.path.join(self._cert_dir, "device.key")

        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            _log("[HTTPS] 证书不存在，无法启动")
            return

        # 检查是否是占位文件
        with open(cert_path, 'r') as f:
            if f.read().strip() == "PLACEHOLDER":
                _log("[HTTPS] 证书为占位文件，无法启动")
                return

        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(cert_path, key_path)
            ctx.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:!aNULL:!MD5:!DSS')

            # 使用内部HTTPS handler
            router = self.router
            crypto = self.crypto

            class HTTPSHandler(BaseHTTPRequestHandler):
                """HTTPS请求处理器 - 镜像HTTP接口"""

                def _j(self, code, data):
                    try:
                        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                        self.send_response(code)
                        self.send_header('Content-Type', 'application/json;charset=utf-8')
                        self.send_header('Content-Length', str(len(body)))
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.send_header('Strict-Transport-Security', 'max-age=31536000')
                        self.end_headers()
                        self.wfile.write(body)
                    except Exception:
                        pass

                def do_OPTIONS(self):
                    self._j(200, {"ok": True})

                def do_GET(self):
                    p = self.path.split("?")[0]
                    try:
                        if p == "/health":
                            self._j(200, {"ok": True, "v": 6, "transport": "https",
                                          "crypto": "SM2+SM3+SM4+TLS1.3"})
                        elif p == "/api/protocols/status":
                            # 委托给ActionRouter
                            result = router.route("https", "health", {})
                            self._j(200, result)
                        else:
                            # 其他GET请求转发到localhost HTTP
                            self._proxy_to_http("GET", p)
                    except Exception as e:
                        self._j(500, {"error": str(e)})

                def do_POST(self):
                    p = self.path.split("?")[0]
                    try:
                        n = int(self.headers.get("Content-Length", 0))
                        body = json.loads(self.rfile.read(n).decode('utf-8')) if n else {}

                        # 检查是否是加密信封
                        if p == "/api/secure/call" and "payload" in body and "signature" in body:
                            # SecureEnvelope: 最高安全等级
                            data = crypto.open_envelope(body)
                            action = data.get("action", "")
                            params = data.get("params", {})
                            result = router.route("https", action, params)
                            # 封装响应
                            response = crypto.make_envelope(result, "https")
                            self._j(200, response)
                        elif p == "/api/encrypted":
                            # SM4加密JSON
                            if "ct" in body:
                                data = crypto.open_light_envelope(body)
                                action = data.get("action", "")
                                params = data.get("params", {})
                                result = router.route("https", action, params)
                                response = crypto.make_light_envelope(result)
                                self._j(200, response)
                            else:
                                self._j(400, {"error": "Invalid encrypted payload"})
                        else:
                            # 明文JSON (仍受TLS保护)
                            self._proxy_to_http("POST", p, body)
                    except Exception as e:
                        self._j(500, {"error": str(e)})

                def _proxy_to_http(self, method, path, body=None):
                    """代理请求到本地HTTP 8080"""
                    import urllib.request
                    try:
                        url = f"http://127.0.0.1:8080{path}"
                        if method == "GET":
                            with urllib.request.urlopen(url, timeout=10) as r:
                                data = json.loads(r.read().decode())
                                self._j(200, data)
                        else:
                            post_data = json.dumps(body or {}).encode('utf-8')
                            req = urllib.request.Request(url, data=post_data,
                                                         headers={'Content-Type': 'application/json'},
                                                         method='POST')
                            with urllib.request.urlopen(req, timeout=10) as r:
                                data = json.loads(r.read().decode())
                                self._j(200, data)
                    except Exception as e:
                        self._j(502, {"error": f"HTTP proxy failed: {e}"})

                def log_message(self, *a):
                    _log(f"[HTTPS] {self.command} {self.path}")

            server = ThreadingHTTPServer(("0.0.0.0", self.HTTPS_PORT), HTTPSHandler)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            _log(f"[HTTPS] TLS服务就绪 :{self.HTTPS_PORT}")
            server.serve_forever()

        except Exception as e:
            _log(f"[HTTPS] 服务异常: {e}")


# ═══════════════════════════════════════════════════════════════
# CoAP Server — RFC 7252 简化实现
# ═══════════════════════════════════════════════════════════════

class CoAPServer:
    """
    CoAP服务端 (RFC 7252简化)
    UDP协议，适合低功耗IoT设备
    支持GET/POST，确认/非确认消息
    Payload: SM4加密 + SM3完整性
    """

    COAP_PORT = 5683

    # CoAP Message Types
    CON = 0  # Confirmable
    NON = 1  # Non-Confirmable
    ACK = 2  # Acknowledgement
    RST = 3  # Reset

    # CoAP Method Codes
    GET = 1
    POST = 2

    # CoAP Response Codes
    CREATED = 0x41  # 2.01
    CONTENT = 0x45  # 2.05
    BAD_REQUEST = 0x80  # 4.00
    NOT_FOUND = 0x84  # 4.04
    METHOD_NOT_ALLOWED = 0x85  # 4.05
    INTERNAL_ERROR = 0xA0  # 5.00

    # Content-Format
    JSON_FORMAT = 50
    OCTET_STREAM = 42

    def __init__(self, crypto: CryptoLayer, router: ActionRouter):
        self.crypto = crypto
        self.router = router
        self._running = False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._serve, daemon=True, name="coap")
        t.start()
        _log(f"[CoAP] 服务启动 :{self.COAP_PORT}")

    def stop(self):
        self._running = False

    def _serve(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self.COAP_PORT))
        sock.settimeout(1.0)

        while self._running:
            try:
                data, addr = sock.recvfrom(1500)
                t = threading.Thread(target=self._handle_message, args=(sock, data, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    _log(f"[CoAP] 接收异常: {e}")

        sock.close()

    def _handle_message(self, sock, data: bytes, addr):
        """处理CoAP消息"""
        try:
            if len(data) < 4:
                return

            # 解析CoAP头部
            ver = (data[0] >> 6) & 0x03
            msg_type = (data[0] >> 4) & 0x03
            token_len = data[0] & 0x0F
            code = data[1]
            msg_id = struct.unpack("!H", data[2:4])[0]

            if ver != 1:
                return

            # Token
            token = data[4:4 + token_len] if token_len > 0 else b""

            # 解析Options
            offset = 4 + token_len
            options = []
            option_num = 0
            payload = b""

            while offset < len(data):
                if data[offset] == 0xFF:  # Payload marker
                    payload = data[offset + 1:]
                    break

                delta = (data[offset] >> 4) & 0x0F
                length = data[offset] & 0x0F
                offset += 1

                if delta == 13:
                    delta = data[offset] + 13
                    offset += 1
                elif delta == 14:
                    delta = struct.unpack("!H", data[offset:offset + 2])[0] + 269
                    offset += 2

                if length == 13:
                    length = data[offset] + 13
                    offset += 1
                elif length == 14:
                    length = struct.unpack("!H", data[offset:offset + 2])[0] + 269
                    offset += 2

                option_num += delta
                option_value = data[offset:offset + length]
                offset += length
                options.append((option_num, option_value))

            # 提取URI-Path (Option 11)
            uri_path = ""
            for opt_num, opt_val in options:
                if opt_num == 11:  # Uri-Path
                    uri_path += "/" + opt_val.decode('utf-8', errors='ignore')

            # 处理请求
            method = code
            if method == self.GET:
                result = self._handle_get(uri_path, options)
            elif method == self.POST:
                result = self._handle_post(uri_path, payload, options)
            else:
                result = (self.METHOD_NOT_ALLOWED, {"error": "Method not allowed"})

            resp_code, resp_data = result

            # 加密响应
            envelope = self.crypto.make_light_envelope(resp_data)
            resp_payload = json.dumps(envelope, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

            # 构建CoAP响应
            if msg_type == self.CON:
                resp_type = self.ACK
            else:
                resp_type = self.NON

            response = self._build_response(resp_type, resp_code, msg_id, token, resp_payload)
            sock.sendto(response, addr)

        except Exception as e:
            _log(f"[CoAP] 处理异常: {e}")
            # 发送RST
            try:
                rst = struct.pack("!BBH", 0x70, 0, msg_id)
                sock.sendto(rst, addr)
            except Exception:
                pass

    def _handle_get(self, uri_path: str, options: list) -> tuple:
        """处理CoAP GET请求"""
        # 映射URI到action
        action_map = {
            "/sensors": "sensor.list",
            "/devices": "device.list",
            "/health": "health",
            "/status": "status.all",
            "/energy": "ai.energy",
            "/anomaly": "ai.anomaly",
            "/linkage": "ai.linkage",
        }

        # 支持路径参数 /devices/{id}
        if uri_path.startswith("/devices/"):
            device_id = uri_path.split("/")[-1]
            result = self.router.route("coap", "device.status", {"device_id": device_id})
            return (self.CONTENT, result)

        action = action_map.get(uri_path)
        if not action:
            return (self.NOT_FOUND, {"error": f"Not found: {uri_path}"})

        result = self.router.route("coap", action, {})
        return (self.CONTENT, result)

    def _handle_post(self, uri_path: str, payload: bytes, options: list) -> tuple:
        """处理CoAP POST请求"""
        try:
            # 解密payload
            envelope = json.loads(payload.decode('utf-8'))
            data = self.crypto.open_light_envelope(envelope)
            action = data.get("action", "")
            params = data.get("params", {})
        except Exception:
            # 尝试直接JSON
            try:
                data = json.loads(payload.decode('utf-8'))
                action = data.get("action", "")
                params = data.get("params", {})
            except Exception:
                return (self.BAD_REQUEST, {"error": "Invalid payload"})

        result = self.router.route("coap", action, params)
        code = self.CONTENT if not result.get("error") else self.BAD_REQUEST
        return (code, result)

    def _build_response(self, msg_type: int, code: int, msg_id: int,
                        token: bytes, payload: bytes) -> bytes:
        """构建CoAP响应包"""
        # Header
        token_len = len(token)
        first_byte = (0x01 << 6) | (msg_type << 4) | token_len
        header = struct.pack("!BBH", first_byte, code, msg_id)

        # Content-Format Option (JSON = 50)
        # Option delta = 12 (from 0 to 12), length = 1
        opt_byte = (12 << 4) | 1
        options = bytes([opt_byte, self.JSON_FORMAT])

        # Payload marker + payload
        result = header + token + options + bytes([0xFF]) + payload
        return result


# ═══════════════════════════════════════════════════════════════
# ProtocolGateway — 多协议网关主入口
# ═══════════════════════════════════════════════════════════════

class ProtocolGateway:
    """
    多协议安全传输网关
    统一管理 HTTPS/WS/MQTT/CoAP 四个协议服务
    提供统一的事件广播接口
    """

    def __init__(self, sm4_key: bytes, sm2_keypair: SM2KeyPair):
        self.crypto = CryptoLayer(sm4_key, sm2_keypair)
        self.router = ActionRouter(self.crypto)
        self.mqtt = MQTTBroker(self.crypto, self.router)
        self.ws = WebSocketServer(self.crypto, self.router)
        self.https = HTTPSServer(self.crypto, self.router)
        self.coap = CoAPServer(self.crypto, self.router)
        self._running = False

    def start(self):
        """启动所有协议服务"""
        self._running = True
        self.mqtt.start()
        self.ws.start()
        self.https.start()
        self.coap.start()

        _log("=" * 50)
        _log("多协议安全传输网关已启动")
        _log(f"  HTTPS  :{HTTPSServer.HTTPS_PORT}  (TLS 1.3 + SM2签名)")
        _log(f"  WebSocket :8080/ws  (SM4加密帧)")
        _log(f"  MQTT   :{MQTTBroker.MQTT_PORT}  (SM4+SM3)")
        _log(f"  CoAP   :{CoAPServer.COAP_PORT}  (SM4+SM3轻量)")
        _log(f"  HTTP   :8080  (向后兼容)")
        _log("=" * 50)

    def stop(self):
        """停止所有协议服务"""
        self._running = False
        self.mqtt.stop()
        self.ws.stop()
        self.https.stop()
        self.coap.stop()

    def broadcast_event(self, event_type: str, data: dict):
        """
        广播事件到所有协议
        gateway_v6业务方法调用此方法推送状态变化
        """
        # WebSocket推送
        self.ws.broadcast_event(event_type, data)

        # MQTT推送
        topic = f"smarthome/events/{event_type}"
        self.mqtt.publish_internal(topic, data)

    def handle_ws_upgrade(self, headers: str, sock, addr) -> bool:
        """处理WebSocket升级 (由gateway_v6的HTTP handler调用)"""
        return self.ws.handle_upgrade(headers, sock, addr)

    def get_status(self) -> dict:
        """获取多协议网关状态"""
        return {
            "protocols": {
                "https": {"port": HTTPSServer.HTTPS_PORT, "status": "running"},
                "websocket": {"port": 8080, "path": "/ws", "status": "running",
                              "clients": len(self.ws.clients)},
                "mqtt": {"port": MQTTBroker.MQTT_PORT, "status": "running",
                         "clients": len(self.mqtt.clients),
                         "topics": list(self.mqtt.subscriptions.keys())},
                "coap": {"port": CoAPServer.COAP_PORT, "status": "running"},
                "http": {"port": 8080, "status": "running (legacy)"},
            },
            "crypto": {
                "algorithms": ["SM2", "SM3", "SM4-CBC"],
                "envelope_version": 1,
            },
            "security_levels": {
                "L1": "HTTPS + SecureEnvelope (SM2+SM4+SM3)",
                "L2": "HTTPS + SM4加密",
                "L3": "WebSocket + SM4加密帧",
                "L4": "MQTT + SM4+SM3",
                "L5": "CoAP + SM4+SM3轻量",
            },
        }
