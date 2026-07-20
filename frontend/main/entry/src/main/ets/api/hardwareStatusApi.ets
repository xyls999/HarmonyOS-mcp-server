/**
 * v6.1 硬件区域状态 API
 * /api/hardware/status 来自后端缓存，不阻塞实时轮询；离线区域由后端标记 offline。
 */
import { Http } from './http';

type AnyRecord = Record<string, Object>;

export interface HardwareAreaStatus {
  key: string;
  name: string;
  isOnline: boolean;
  latency: number;
}

export interface HardwareStatusSummary {
  total: number;
  online: number;
  offline: number;
  areas: HardwareAreaStatus[];
}

function textOf(value: Object | undefined, fallback: string): string {
  if (typeof value === 'string' && value.trim().length > 0) {
    return value.trim();
  }
  return fallback;
}

function numberOf(value: Object | undefined, fallback: number): number {
  if (typeof value === 'number' && value === value) {
    return value;
  }
  return fallback;
}

function boolOf(value: Object | undefined, fallback: boolean): boolean {
  if (typeof value === 'boolean') {
    return value;
  }
  return fallback;
}

function areaOnline(raw: AnyRecord): boolean {
  const status = textOf(raw.status, '').toLowerCase();
  if (status === 'offline' || status === 'down' || status === 'false') return false;
  if (status === 'online' || status === 'active' || status === 'ok') return true;
  if (typeof raw.isOnline === 'boolean') return raw.isOnline as boolean;
  if (typeof raw.online === 'boolean') return raw.online as boolean;
  if (typeof raw.reachable === 'boolean') return raw.reachable as boolean;
  return boolOf(raw.connected, false);
}

function normalizeArea(key: string, value: Object): HardwareAreaStatus {
  const raw = value as AnyRecord;
  const area: HardwareAreaStatus = {
    key,
    name: textOf(raw.name, textOf(raw.label, key)),
    isOnline: areaOnline(raw),
    latency: numberOf(raw.latency, numberOf(raw.latencyMs, 0))
  };
  return area;
}

export class HardwareStatusApi {
  static async getStatus(): Promise<HardwareStatusSummary> {
    const fallback: HardwareStatusSummary = {
      total: 0,
      online: 0,
      offline: 0,
      areas: []
    };

    const text = await Http.get('/api/hardware/status');
    if (!text) return fallback;

    try {
      const raw = JSON.parse(text) as AnyRecord;
      const source = raw.areas || raw.regions || raw.status || raw;
      const areas: HardwareAreaStatus[] = [];

      if (Array.isArray(source)) {
        const list = source as Object[];
        for (let i = 0; i < list.length; i++) {
          const item = list[i] as AnyRecord;
          areas.push(normalizeArea(textOf(item.id, textOf(item.key, `area_${i}`)), list[i]));
        }
      } else {
        const map = source as AnyRecord;
        const keys = Object.keys(map);
        for (let i = 0; i < keys.length; i++) {
          const key = keys[i];
          if (key === 'total' || key === 'online' || key === 'offline' || key === 'online_count' || key === 'offline_count' || key === 'timestamp' || key === 'message' || key === 'voiceSequence') continue;
          const value = map[key];
          if (value === undefined) continue;
          areas.push(normalizeArea(key, value));
        }
      }

      let online = 0;
      for (const area of areas) {
        if (area.isOnline) online++;
      }
      const onlineCount = numberOf(raw.online_count, online);
      const offlineCount = numberOf(raw.offline_count, Math.max(0, areas.length - online));
      const totalCount = areas.length > 0 ? areas.length : onlineCount + offlineCount;

      const summary: HardwareStatusSummary = {
        total: totalCount,
        online: onlineCount,
        offline: offlineCount,
        areas
      };
      return summary;
    } catch (e) {
      return fallback;
    }
  }
}
