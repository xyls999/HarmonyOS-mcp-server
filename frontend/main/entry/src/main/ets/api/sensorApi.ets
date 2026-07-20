/**
 * 传感器数据 API · 对接设备端网关
 * 策略: v6.1 真实硬件优先。离线传感器 current=null，前端显示离线且不补模拟值。
 */
import { Sensor, SensorGroup, SensorReading } from './types';
import { Http } from './http';
import { normalizeSensor } from './adapter';

/** 传感器历史数据点 */
interface SensorHistoryPoint {
  value?: number | null;
  time?: string;
  timestamp?: string;
}

/** 温湿度历史响应 */
export interface TempHumidHistory {
  available: boolean;
  temp: number[];
  humid: number[];
  labels: string[];
}

interface SensorHistoryGroups {
  temp_01?: SensorHistoryPoint[];
  humid_01?: SensorHistoryPoint[];
}

interface SensorHistoryEnvelope {
  sensors?: SensorHistoryGroups;
  total?: number;
  error?: string;
  temp?: SensorHistoryPoint[];
  humid?: SensorHistoryPoint[];
}

interface SensorListEnvelope {
  sensors?: Record<string, Object>[];
  total?: number;
}

export interface SensorSnapshot {
  available: boolean;
  sensors: Sensor[];
}

function historyValues(points: SensorHistoryPoint[]): number[] {
  const values: number[] = [];
  for (const point of points) {
    if (typeof point.value === 'number') values.push(point.value);
  }
  return values;
}

function historyLabels(points: SensorHistoryPoint[]): string[] {
  const labels: string[] = [];
  for (const point of points) labels.push(point.timestamp || point.time || '');
  return labels;
}

function chronological(points: SensorHistoryPoint[]): SensorHistoryPoint[] {
  const result: SensorHistoryPoint[] = [];
  for (let index = points.length - 1; index >= 0; index--) result.push(points[index]);
  return result;
}

export class SensorApi {
  /** 获取全部传感器 */
  static async getSensors(): Promise<Sensor[]> {
    return (await SensorApi.getSensorSnapshot()).sensors;
  }

  static async getSensorSnapshot(): Promise<SensorSnapshot> {
    const remote = await Http.get('/api/sensors');
    if (remote) {
      try {
        const parsed = JSON.parse(remote) as Object;
        const data = Array.isArray(parsed) ? parsed as Record<string, Object>[] :
          (parsed as SensorListEnvelope).sensors || [];
        return {
          available: true,
          sensors: data.map((item: Record<string, Object>) => normalizeSensor(item))
        };
      } catch (e) {
      }
    }
    return { available: false, sensors: [] };
  }

  /** 按分组获取 */
  static async getByGroup(group: SensorGroup): Promise<Sensor[]> {
    const all = await SensorApi.getSensors();
    return all.filter(s => s.group === group);
  }

  /** 获取单个传感器详情 */
  static async getSensor(id: string): Promise<Sensor | undefined> {
    const all = await SensorApi.getSensors();
    return all.find(s => s.id === id);
  }

  /** 获取历史趋势 (真实数据) */
  static async getHistory(id: string, hours: number = 24): Promise<number[]> {
    const history = await SensorApi.getTempHumidHistory();
    if (id === 'temp_01') return history.temp;
    if (id === 'humid_01') return history.humid;
    return [];
  }

  /** 获取温湿度历史 (完整结构,含时间标签) */
  static async getTempHumidHistory(): Promise<TempHumidHistory> {
    const remote = await Http.get('/api/sensors/history');
    if (remote) {
      try {
        const data = JSON.parse(remote) as SensorHistoryEnvelope;
        const rawTemp = data.sensors?.temp_01 || data.temp || [];
        const rawHumid = data.sensors?.humid_01 || data.humid || [];
        const hasV5Envelope = data.sensors !== undefined && typeof data.total === 'number';
        const hasLegacyHistory = data.temp !== undefined || data.humid !== undefined;
        if (data.error !== undefined || (!hasV5Envelope && !hasLegacyHistory)) return {
          available: false,
          temp: [],
          humid: [],
          labels: []
        };
        const temp = data.sensors ? chronological(rawTemp) : rawTemp;
        const humid = data.sensors ? chronological(rawHumid) : rawHumid;
        return {
          available: true,
          temp: historyValues(temp),
          humid: historyValues(humid),
          labels: historyLabels(temp.length > 0 ? temp : humid)
        };
      } catch (e) {
      }
    }
    const fallback: TempHumidHistory = {
      available: false,
      temp: [],
      humid: [],
      labels: []
    };
    return fallback;
  }

  /** 订阅实时数据：轮询 v6.1 真实状态，不再生成模拟波动 */
  static subscribeRealtime(onReading: (id: string, reading: SensorReading) => void): () => void {
    const timer = setInterval(() => {
      SensorApi.getSensors().then((sensors: Sensor[]) => {
        sensors.forEach((s: Sensor) => {
          if (s.current && s.current.unit !== '离线') {
            onReading(s.id, s.current);
          }
        });
      }).catch(() => {
      });
    }, 3000);
    return () => clearInterval(timer);
  }

  /** 获取告警中的传感器 */
  static async getAlerts(): Promise<Sensor[]> {
    const all = await SensorApi.getSensors();
    return all.filter(s => s.isAlert);
  }
}
