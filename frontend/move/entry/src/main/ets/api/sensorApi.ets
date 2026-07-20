import { Sensor } from './types';
import { normalizeSensor } from './adapter';
import { Http } from './http';

type Json = Record<string, Object>;

interface SensorListResponse { sensors: Json[]; total: number; }
interface SensorHistoryPoint { time: string; value: number; }
interface SensorHistoryBucket { history: SensorHistoryPoint[]; }
interface SensorHistoryResponse { sensors: Record<string, Object>; }

export interface SensorLoadResult {
  sensors: Sensor[];
  error: string;
  offline: boolean;
}

export class SensorApi {
  static async getSensorsResult(): Promise<SensorLoadResult> {
    const result = await Http.getResult('/api/app/sensors');
    if (result.status < 200 || result.status >= 300) {
      return { sensors: [], error: result.error || '传感器数据加载失败', offline: result.offline };
    }
    try {
      const parsed = JSON.parse(result.body) as Object;
      let source: Json[] = [];
      if (Array.isArray(parsed)) source = parsed as Json[];
      else {
        const response = parsed as SensorListResponse;
        if (Array.isArray(response.sensors)) source = response.sensors;
      }
      return {
        sensors: source.map((item: Json): Sensor => normalizeSensor(item)),
        error: '',
        offline: false
      };
    } catch (_) {
      return { sensors: [], error: '传感器数据格式无法识别', offline: false };
    }
  }

  static async getSensors(): Promise<Sensor[]> {
    return (await SensorApi.getSensorsResult()).sensors;
  }

  static async getSensor(id: string): Promise<Sensor | undefined> {
    return (await SensorApi.getSensors()).find((item: Sensor): boolean => item.id === id);
  }

  static async getHistory(id: string): Promise<number[]> {
    const raw = await Http.get(`/api/app/sensors/history?sensorId=${encodeURIComponent(id)}&hours=24`);
    if (!raw) return [];
    try {
      const response = JSON.parse(raw) as SensorHistoryResponse;
      const bucket = response.sensors[id] as SensorHistoryBucket | undefined;
      if (!bucket || !Array.isArray(bucket.history)) return [];
      return bucket.history.map((point: SensorHistoryPoint): number => point.value);
    } catch (_) { return []; }
  }
}
