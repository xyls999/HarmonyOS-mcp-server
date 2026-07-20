/**
 * 场景激活 API
 * 遍历场景的 actions，批量调用 DeviceApi 控制设备
 *
 * 接口契约:
 *   POST /api/scenes/{id}/activate → { success, affectedCount }
 */
import { Scene, SceneAction, DeviceType } from './types';
import { DeviceApi } from './deviceApi';
import { MockData } from '../mock/mockData';

export class SceneApi {
  /**
   * 激活场景：遍历 actions 调 DeviceApi.toggle/control
   * @returns Toast 提示文案
   */
  static async activate(sceneId: string): Promise<string> {
    // TODO[后端对接]: POST /api/scenes/{id}/activate
    const scene = MockData.scenes.find((s: Scene) => s.id === sceneId);
    if (!scene) return '场景不存在';

    // 更新所有场景的 isActive 状态
    MockData.scenes.forEach((s: Scene) => {
      s.isActive = s.id === sceneId;
    });

    // 执行设备动作
    let count = 0;
    for (let i = 0; i < scene.actions.length; i++) {
      const action: SceneAction = scene.actions[i];
      await DeviceApi.toggle(action.deviceId, action.isOn);
      if (action.primaryValue !== undefined) {
        const dev = MockData.devices.find(d => d.id === action.deviceId);
        if (dev) {
          const act = dev.type === DeviceType.FAN ? 'set_speed'
            : dev.type === DeviceType.AC ? 'set_temp' : 'set_brightness';
          await DeviceApi.control(action.deviceId, act, { value: action.primaryValue });
        }
      }
      count++;
    }

    return `已切换到「${scene.name}」模式，控制 ${count} 台设备`;
  }

  /** 获取全部场景 */
  static async getScenes(): Promise<Scene[]> {
    return MockData.scenes;
  }

  /** 获取当前激活场景 */
  static getCurrentScene(): Scene | null {
    const found = MockData.scenes.find((s: Scene) => s.isActive);
    return found ?? null;
  }
}
