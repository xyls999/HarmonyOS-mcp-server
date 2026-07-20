import { Http } from './http';
import {
  AlarmLinkage, AlertMessage, AreaStatus, BathroomFan, BedroomCurtain, CheckResult, DeviceOnlineRate,
  KitchenAlarm, KitchenSmoke, KitchenThermal, LightStat, MetricValue, OperationRecord, RagStats, SecurityEvent, Stats
} from './types';

type Json = Record<string, Object>;

interface VoiceRequest { text: string; }
interface TtsRequest { text: string; }

function objectValue(value: Object | undefined): Json | null {
  return typeof value === 'object' && value !== null ? value as Json : null;
}

function numberValue(value: Object | undefined, fallback: number): number {
  return typeof value === 'number' ? value : fallback;
}

function nullableNumber(value: Object | undefined): number | null {
  return typeof value === 'number' ? value : null;
}

function stringValue(value: Object | undefined, fallback: string = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function listValue(value: Object, field: string): Json[] {
  if (Array.isArray(value)) return value as Json[];
  const response = objectValue(value);
  if (!response || !Array.isArray(response[field])) return [];
  return response[field] as Json[];
}

function timestampValue(value: Object | undefined): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') return Date.parse(value.replace(' ', 'T')) || Date.now();
  return Date.now();
}

function metric(raw: Json | null, threshold: number): MetricValue {
  return {
    value: raw ? nullableNumber(raw.value) : null,
    unit: raw ? stringValue(raw.unit) : '',
    online: raw?.online === true,
    is_alert: raw?.is_alert === true,
    threshold
  };
}

export class V5Api {
  private static async getJson<T>(path: string): Promise<T | null> {
    const raw = await Http.get(path);
    if (!raw) return null;
    try { return JSON.parse(raw) as T; } catch (_) { return null; }
  }

  static async getStats(): Promise<Stats | null> {
    const value = await V5Api.getJson<Json>('/api/app/stats');
    if (!value) return null;

    const rateRaw = objectValue(value.device_online_rate);
    const total = rateRaw ? numberValue(rateRaw.total, 0) : 0;
    const online = rateRaw ? numberValue(rateRaw.online, 0) : 0;
    const rate: DeviceOnlineRate = {
      total,
      online,
      offline: rateRaw ? numberValue(rateRaw.offline, Math.max(0, total - online)) : 0,
      rate: rateRaw ? numberValue(rateRaw.rate, total > 0 ? Math.round(online / total * 100) : 0) : 0
    };

    const areaConnectivity: Record<string, AreaStatus> = {};
    const areaRaw = objectValue(value.area_connectivity);
    if (areaRaw) {
      Object.keys(areaRaw).forEach((id: string): void => {
        const item = objectValue(areaRaw[id]);
        if (!item) return;
        const area: AreaStatus = {
          id,
          name: stringValue(item.name, id),
          ip: stringValue(item.ip),
          port: numberValue(item.port, 0),
          online: item.online === true,
          lastSeen: typeof item.lastSeen === 'string' ? item.lastSeen : null
        };
        areaConnectivity[id] = area;
      });
    }

    const smokeRaw = objectValue(value.kitchen_smoke);
    const kitchenSmoke: KitchenSmoke = {
      smoke_level: smokeRaw ? nullableNumber(smokeRaw.smoke_level) : null,
      smoke_alarm: smokeRaw && typeof smokeRaw.smoke_alarm === 'boolean' ? smokeRaw.smoke_alarm : null,
      online: smokeRaw?.online === true,
      description: smokeRaw && typeof smokeRaw.description === 'string' ? smokeRaw.description : null
    };
    const thermalRaw = objectValue(value.kitchen_thermal);
    const kitchenThermal: KitchenThermal = {
      thermal_mv: thermalRaw ? nullableNumber(thermalRaw.thermal_mv) : null,
      temp_alarm: thermalRaw && typeof thermalRaw.temp_alarm === 'boolean' ? thermalRaw.temp_alarm : null,
      online: thermalRaw?.online === true,
      threshold_mv: thermalRaw ? numberValue(thermalRaw.threshold_mv, 1400) : 1400,
      description: thermalRaw && typeof thermalRaw.description === 'string' ? thermalRaw.description : null
    };
    const alarmRaw = objectValue(value.kitchen_alarm);
    const kitchenAlarm: KitchenAlarm = {
      alarm: alarmRaw ? nullableNumber(alarmRaw.alarm) : null,
      online: alarmRaw?.online === true,
      description: alarmRaw && typeof alarmRaw.description === 'string' ? alarmRaw.description : null
    };
    const fanRaw = objectValue(value.bathroom_fan);
    const bathroomFan: BathroomFan = {
      motor_running: fanRaw && typeof fanRaw.motor_running === 'boolean' ? fanRaw.motor_running : null,
      motor_speed: fanRaw ? nullableNumber(fanRaw.motor_speed) : null,
      motor_direction: fanRaw ? nullableNumber(fanRaw.motor_direction) : null,
      online: fanRaw?.online === true,
      direction_label: fanRaw && typeof fanRaw.direction_label === 'string' ? fanRaw.direction_label : null
    };
    const curtainRaw = objectValue(value.bedroom_curtain);
    const bedroomCurtain: BedroomCurtain = {
      position: curtainRaw ? nullableNumber(curtainRaw.position) : null,
      moving: curtainRaw && typeof curtainRaw.moving === 'boolean' ? curtainRaw.moving : null,
      homed: curtainRaw && typeof curtainRaw.homed === 'boolean' ? curtainRaw.homed : null,
      close_limit: curtainRaw ? nullableNumber(curtainRaw.close_limit) : null,
      open_limit: curtainRaw ? nullableNumber(curtainRaw.open_limit) : null,
      online: curtainRaw?.online === true
    };
    const linkageRaw = objectValue(value.alarm_linkage);
    const linkage: AlarmLinkage = {
      last_kitchen_alarm: linkageRaw ? numberValue(linkageRaw.last_kitchen_alarm, 0) : 0,
      buzzer_triggered: linkageRaw && typeof linkageRaw.buzzer_triggered === 'boolean' ? linkageRaw.buzzer_triggered : null,
      udp_listening: linkageRaw?.udp_listening === true,
      events_24h: linkageRaw ? numberValue(linkageRaw.events_24h, 0) : 0,
      rule: linkageRaw ? stringValue(linkageRaw.rule) : ''
    };
    const lights = objectValue(value.all_lights) as Record<string, LightStat> | null;

    return {
      timestamp: stringValue(value.timestamp),
      poll_interval_kitchen: numberValue(value.poll_interval_kitchen, 0),
      poll_interval_other: numberValue(value.poll_interval_other, 0),
      device_online_rate: rate,
      area_connectivity: areaConnectivity,
      living_temperature: metric(objectValue(value.living_temperature), 28),
      living_humidity: metric(objectValue(value.living_humidity), 70),
      kitchen_smoke: kitchenSmoke,
      kitchen_thermal: kitchenThermal,
      kitchen_alarm: kitchenAlarm,
      bathroom_fan: bathroomFan,
      bedroom_curtain: bedroomCurtain,
      all_lights: lights || {},
      alarm_linkage: linkage
    };
  }

  static async getCheck(): Promise<CheckResult | null> {
    const value = await V5Api.getJson<Json>('/api/app/check');
    if (!value) return null;
    const areas: AreaStatus[] = [];
    if (Array.isArray(value.areas)) {
      (value.areas as Json[]).forEach((item: Json): void => {
        areas.push({
          id: stringValue(item.id),
          name: stringValue(item.name, '未知区域'),
          ip: stringValue(item.ip),
          port: numberValue(item.port, 0),
          online: item.online === true
        });
      });
    }
    return {
      timestamp: stringValue(value.timestamp),
      onlineCount: numberValue(value.online_count, 0),
      offlineCount: numberValue(value.offline_count, 0),
      areas,
      message: stringValue(value.message, '设备检查完成')
    };
  }

  static async getAlerts(): Promise<AlertMessage[]> {
    const value = await V5Api.getJson<Object>('/api/app/alerts');
    if (!value) return [];
    return listValue(value, 'alerts').map((item: Json, index: number): AlertMessage => {
      let level: 'info' | 'warning' | 'danger' = 'info';
      if (item.level === 'danger') level = 'danger';
      else if (item.level === 'warning') level = 'warning';
      return {
        id: stringValue(item.id, `${index}`),
        source: stringValue(item.source, '远程服务'),
        content: stringValue(item.content, stringValue(item.message, '告警事件')),
        level,
        timestamp: timestampValue(item.timestamp || item.created_at),
        isRead: item.isRead === true || item.is_read === true
      };
    });
  }

  static async getOperations(): Promise<OperationRecord[]> {
    const value = await V5Api.getJson<Object>('/api/app/operations');
    if (!value) return [];
    return listValue(value, 'operations').map((item: Json, index: number): OperationRecord => {
      const deviceId = stringValue(item.device_id, stringValue(item.deviceId, '未知设备'));
      const timestampText = stringValue(item.timestamp);
      const result = stringValue(item.result);
      const source = stringValue(item.source);
      const sceneId = stringValue(item.scene_id);
      return {
        id: `${deviceId}_${timestampText}_${index}`,
        deviceName: deviceId,
        action: stringValue(item.action, 'unknown'),
        success: result === 'ok' || item.success === true,
        timestamp: timestampText ? Date.parse(timestampText.replace(' ', 'T')) : Date.now(),
        message: sceneId ? `${result} · ${source} · ${sceneId}` : source ? `${result} · ${source}` : result
      };
    });
  }

  static async getSecurityEvents(): Promise<SecurityEvent[]> {
    const value = await V5Api.getJson<Object>('/api/app/security/events');
    if (!value) return [];
    return listValue(value, 'events').map((item: Json, index: number): SecurityEvent => {
      let level: 'info' | 'warning' | 'danger' = 'info';
      const rawLevel = stringValue(item.level, stringValue(item.severity)).toLowerCase();
      if (rawLevel === 'danger' || rawLevel === 'critical' || rawLevel === 'high') level = 'danger';
      else if (rawLevel === 'warning' || rawLevel === 'medium') level = 'warning';
      return {
        id: typeof item.id === 'number' ? `${item.id}` : stringValue(item.id, `security_${index}`),
        source: stringValue(item.source, stringValue(item.device_id, '安全系统')),
        room: stringValue(item.room, '全屋'),
        content: stringValue(item.content, stringValue(item.message,
          stringValue(item.reason, stringValue(item.event, '安全事件')))),
        level,
        timestamp: timestampValue(item.timestamp || item.created_at)
      };
    });
  }

  static async getRagStats(): Promise<RagStats | null> {
    const value = await V5Api.getJson<Json>('/api/app/rag/stats');
    if (!value || typeof value.error === 'string') return { exactCommands: 0, documents: 0, available: false };
    return {
      exactCommands: numberValue(value.exact_commands, 0),
      documents: numberValue(value.documents, numberValue(value.total, 0)),
      available: value.available !== false
    };
  }

  static async voiceInput(text: string): Promise<string | null> {
    const body: VoiceRequest = { text };
    const raw = await Http.post('/api/app/voice/input', body);
    if (!raw) return null;
    try {
      const value = JSON.parse(raw) as Json;
      return stringValue(value.reply, stringValue(value.content)) || null;
    } catch (_) { return null; }
  }

  static async speak(text: string): Promise<boolean> {
    const body: TtsRequest = { text };
    const raw = await Http.post('/api/app/tts/speak', body);
    if (!raw) return false;
    try {
      const value = JSON.parse(raw) as Json;
      return value.ok === true || value.success === true;
    } catch (_) { return false; }
  }
}
