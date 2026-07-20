/**
 * 设备控制 API · 对接设备端网关
 * 策略: v6.1 真实硬件优先。离线设备由后端标记 offline，控制失败不伪造成功状态。
 */
import { Device, DeviceType, DeviceStatus, ControlParams } from './types';
import { Http } from './http';
import { normalizeDevice } from './adapter';

interface DeviceMutationResult {
  success?: boolean;
  data?: Object;
}

interface DeviceControlResponse {
  success?: boolean;
  device?: Device;
  result?: DeviceMutationResult;
  error?: string;
}

interface DeviceListResponse {
  devices?: Record<string, Object>[];
  total?: number;
}

interface ControlRequestBody {
  action: string;
  params: ControlParams;
}

interface ToggleRequestBody {
  isOn: boolean;
  doorPassword?: string;
}

interface AddDeviceRequestBody {
  id: string;
  name: string;
  type: DeviceType;
  room: string;
  icon: string;
  primaryValue: number;
}

interface CustomDiscoveryRequestBody {
  name?: string;
  room?: string;
  deviceType?: string;
  register?: boolean;
  manufacturer?: string;
  devBoard?: string;
}

interface CustomRegisterRequestBody {
  device_id: string;
}

interface ProtocolCommandResult {
  success: boolean;
  detail: string;
}

interface BearPiCommandBody {
  command: string;
}

export interface DeviceSnapshot {
  available: boolean;
  devices: Device[];
}

export class DeviceApi {
  /** 获取全部设备列表 */
  static async getDevices(): Promise<Device[]> {
    return (await DeviceApi.getDeviceSnapshot()).devices;
  }

  /** 获取设备列表及接口可用状态，空数组不再和请求失败混为一谈。 */
  static async getDeviceSnapshot(): Promise<DeviceSnapshot> {
    const remote = await Http.get('/api/devices');
    if (remote) {
      try {
        const parsed = JSON.parse(remote) as Object;
        const data = Array.isArray(parsed) ? parsed as Record<string, Object>[] :
          (parsed as DeviceListResponse).devices || [];
        return {
          available: true,
          devices: data.map((item: Record<string, Object>) => normalizeDevice(item))
        };
      } catch (e) {
      }
    }
    return { available: false, devices: [] };
  }

  /** 获取单个设备详情 */
  static async getDevice(id: string): Promise<Device | undefined> {
    const all = await DeviceApi.getDevices();
    return all.find(d => d.id === id);
  }

  /** 控制设备 */
  static async control(id: string, action: string, params: ControlParams): Promise<boolean> {
    const body: ControlRequestBody = { action, params };
    const respText = await Http.post(`/api/devices/${id}/control`, body);
    if (respText) {
      try {
        const resp = JSON.parse(respText) as DeviceControlResponse;
        if (resp.success === true || resp.result?.success === true) return true;
      } catch (e) {
      }
    }
    return false;
  }

  /** 开关设备 */
  static async toggle(id: string, isOn: boolean, doorPassword: string = ''): Promise<boolean> {
    const body: ToggleRequestBody = doorPassword.length > 0 ? { isOn: isOn, doorPassword: doorPassword } : { isOn: isOn };
    const respText = await Http.post(`/api/devices/${id}/toggle`, body);
    if (respText) {
      try {
        const resp = JSON.parse(respText) as DeviceControlResponse;
        if (resp.success === true || resp.result?.success === true) return true;
      } catch (e) {
      }
    }
    return false;
  }

  /** 门禁开锁 */
  static async unlockDoor(id: string, pin: string): Promise<boolean> {
    if (!pin) return false;
    return DeviceApi.toggle(id, true, pin);
  }

  static async setBrightness(id: string, value: number): Promise<boolean> {
    const brightness = Math.max(0, Math.min(100, Math.round(value)));
    const params: ControlParams = { value: brightness, brightness: brightness };
    return DeviceApi.control(id, 'set_brightness', params);
  }

  static async setFanSpeed(id: string, value: number): Promise<boolean> {
    const speed = Math.max(0, Math.min(100, Math.round(value)));
    const params: ControlParams = { value: speed, speed: speed };
    return DeviceApi.control(id, 'set_speed', params);
  }

  static async setFanDirection(id: string, direction: string, speed: number): Promise<boolean> {
    const safeSpeed = Math.max(0, Math.min(100, Math.round(speed)));
    const params: ControlParams = { direction: direction, value: safeSpeed, speed: safeSpeed };
    return DeviceApi.control(id, 'set_direction', params);
  }

  static async setAcTemperature(id: string, value: number): Promise<boolean> {
    const temperature = Math.max(16, Math.min(30, Math.round(value)));
    const params: ControlParams = { value: temperature, temperature: temperature };
    return DeviceApi.control(id, 'set_temp', params);
  }

  static async setAcMode(id: string, mode: string): Promise<boolean> {
    const params: ControlParams = { mode: mode };
    return DeviceApi.control(id, 'set_mode', params);
  }

  static async setAcFan(id: string, mode: string): Promise<boolean> {
    const params: ControlParams = { mode: mode, fan_speed: mode };
    return DeviceApi.control(id, 'set_fan', params);
  }

  static async setAcSwing(id: string, enabled: boolean): Promise<boolean> {
    const mode = enabled ? 'on' : 'off';
    const params: ControlParams = { mode: mode, swing: mode };
    return DeviceApi.control(id, 'set_swing', params);
  }

  static async applyAcProfile(id: string, profile: string): Promise<boolean> {
    const params: ControlParams = { profile: profile };
    return DeviceApi.control(id, 'preset', params);
  }

  static async setCurtainPosition(id: string, value: number): Promise<boolean> {
    const position = Math.max(0, Math.min(100, Math.round(value)));
    const params: ControlParams = { value: position, position: position };
    return DeviceApi.control(id, 'set_position', params);
  }

  static async stopCurtain(id: string): Promise<boolean> {
    const params: ControlParams = {};
    return DeviceApi.control(id, 'stop', params);
  }

  /** 添加设备 */
  static async addDevice(device: Device): Promise<boolean> {
    const body: AddDeviceRequestBody = {
      id: device.id, name: device.name, type: device.type,
      room: device.room, icon: 'lightbulb', primaryValue: device.primaryValue
    };
    const respText = await Http.post('/api/devices', body);
    if (respText) {
      try {
        const resp = JSON.parse(respText) as DeviceControlResponse;
        if (resp.success === true || resp.result?.success === true) return true;
      } catch (e) {
      }
    }
    return false;
  }

  /** 按类型扫描局域网设备，网关返回真实能力后注册到统一设备模型。 */
  static async scanCustomDevice(deviceType: string, name: string = '', room: string = '自定义设备', register: boolean = false,
    manufacturer: string = '自研', devBoard: string = 'ESP32'): Promise<Device | undefined> {
    const body: CustomDiscoveryRequestBody = {
      name: name, room: room, deviceType: deviceType, register: register,
      manufacturer: manufacturer, devBoard: devBoard
    };
    const respText = await Http.post('/api/custom/scan', body);
    if (!respText) return undefined;
    try {
      const resp = JSON.parse(respText) as Record<string, Object>;
      if (resp.success !== true || !resp.device) return undefined;
      return normalizeDevice(resp.device as Record<string, Object>);
    } catch (e) {
      return undefined;
    }
  }

  /** 用户在协议匹配成功后确认接入扫描结果。 */
  static async registerScannedDevice(deviceId: string): Promise<boolean> {
    const body: CustomRegisterRequestBody = { device_id: deviceId };
    const respText = await Http.post('/api/custom/register', body);
    if (!respText) return false;
    try {
      const resp = JSON.parse(respText) as DeviceControlResponse;
      return resp.success === true;
    } catch (e) {
      return false;
    }
  }

  /** 兼容旧版调用方。 */
  static async discoverCustomLed(name: string = '', room: string = '自定义设备'): Promise<Device | undefined> {
    return DeviceApi.scanCustomDevice('light', name, room);
  }

  /** BearPi 亮度 / 人感 / 雷达命令 */
  static async sendBearPiCommand(command: string): Promise<ProtocolCommandResult> {
    const body: BearPiCommandBody = { command };
    const respText = await Http.post('/api/bearpi/command', body);
    if (respText) {
      try {
        const resp = JSON.parse(respText) as ProtocolCommandResult;
        return resp;
      } catch (e) {
        // fallback
      }
    }
    return { success: false, detail: 'BearPi command failed' };
  }

  /** 移除设备 */
  static async removeDevice(id: string): Promise<boolean> {
    return false;
  }

  /** 生成新设备 ID */
  static genId(type: string): string {
    return type + '_' + Date.now();
  }
}
