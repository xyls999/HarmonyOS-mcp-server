/**
 * 监控 API · 对接设备端网关
 * 策略: v6.1 真实数据优先；请求失败不再返回 mock 状态。
 */
import { Camera, AlertMessage } from './types';
import { MockData } from '../mock/mockData';
import { Http } from './http';
import { normalizeAlert, normalizeCamera } from './adapter';

interface CameraListEnvelope {
  cameras?: Record<string, Object>[];
  total?: number;
}

interface AlertListEnvelope {
  alerts?: Record<string, Object>[];
  total?: number;
}

export class MonitorApi {
  /** 获取全部摄像头 */
  static async getCameras(): Promise<Camera[]> {
    const remote = await Http.get('/api/cameras');
    if (remote) {
      try {
        const parsed = JSON.parse(remote) as Object;
        const data = Array.isArray(parsed) ? parsed as Record<string, Object>[] :
          (parsed as CameraListEnvelope).cameras || [];
        return data.map((item: Record<string, Object>) => normalizeCamera(item));
      } catch (e) {
      }
    }
    return [];
  }

  /** 获取视频流地址（占位） */
  static async getStreamUrl(id: string): Promise<string> {
    return '';
  }

  /** 开关录像 */
  static async toggleRecord(id: string, on: boolean): Promise<boolean> {
    const cam = MockData.cameras.find(c => c.id === id);
    if (cam) cam.isRecording = on;
    return true;
  }

  /** 获取警报消息流 */
  static async getAlerts(): Promise<AlertMessage[]> {
    const remote = await Http.get('/api/alerts');
    if (remote) {
      try {
        const parsed = JSON.parse(remote) as Object;
        const data = Array.isArray(parsed) ? parsed as Record<string, Object>[] :
          (parsed as AlertListEnvelope).alerts || [];
        return data.map((item: Record<string, Object>) => normalizeAlert(item));
      } catch (e) {
      }
    }
    return [];
  }

  /** 标记已读 */
  static async markRead(id: string): Promise<boolean> {
    const a = MockData.alerts.find(x => x.id === id);
    if (a) a.isRead = true;
    return true;
  }
}
