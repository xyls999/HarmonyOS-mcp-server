import { ApiActionResult, Scene } from './types';
import { Http, HttpResult } from './http';

type Json = Record<string, Object>;

interface SceneListResponse { scenes: Scene[]; }
interface EmptyRequest {}

export class SceneApi {
  static async getScenes(): Promise<Scene[]> {
    const raw = await Http.get('/api/app/scenes');
    if (!raw) return [];
    try {
      const response = JSON.parse(raw) as SceneListResponse;
      return response.scenes;
    } catch (_) { return []; }
  }

  static async activate(id: string): Promise<ApiActionResult> {
    const body: EmptyRequest = {};
    const result: HttpResult = await Http.postResult(`/api/app/scenes/${encodeURIComponent(id)}/activate`, body);
    let success = result.status >= 200 && result.status < 300;
    let message = success ? '场景已执行' : result.error || '场景执行失败';
    let offline = result.offline;
    if (result.body) {
      try {
        const value = JSON.parse(result.body) as Json;
        if (typeof value.success === 'boolean') success = value.success;
        if (typeof value.error === 'string') message = value.error;
        else if (typeof value.message === 'string') message = value.message;
        offline = offline || value.offline === true;
      } catch (_) {}
    }
    if (offline) message = '设备离线';
    return { success, message, offline };
  }
}
