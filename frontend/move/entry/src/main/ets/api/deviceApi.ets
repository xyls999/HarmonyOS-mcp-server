import { ApiActionResult, ChatAction, ControlParams, Device, DeviceStatus, DeviceType } from './types';
import { normalizeDevice } from './adapter';
import { Http, HttpResult } from './http';
import { hilog } from '@kit.PerformanceAnalysisKit';

type Json = Record<string, Object>;

interface DeviceListResponse { devices: Json[]; total: number; }
interface DeviceResponse { device: Json; }
interface ControlRequest {
  action: string;
  value?: number;
  mode?: string;
  direction?: number;
  speed?: number;
  position?: number;
  brightness?: number;
  temperature?: number;
  fan_speed?: string;
}
interface ToggleRequest { isOn: boolean; doorPassword?: string; }
interface DoorRequest { action: string; doorPassword?: string; }
interface DeviceStateOverride {
  isOn?: boolean;
  primaryValue?: number;
  mode?: string;
}

export interface DeviceLoadResult {
  devices: Device[];
  error: string;
  offline: boolean;
}

function offlineDevice(id: string, name: string, type: DeviceType, room: string): Device {
  return {
    id, name, type, room,
    status: DeviceStatus.OFFLINE,
    icon: type === DeviceType.FAN || type === DeviceType.EXHAUST ? $r('sys.symbol.fan_fill_1')
      : type === DeviceType.AC ? $r('sys.symbol.air_fill')
        : type === DeviceType.DOOR ? $r('sys.symbol.lock')
          : type === DeviceType.ALARM ? $r('sys.symbol.bell_fill')
            : type === DeviceType.CURTAIN ? $r('sys.symbol.lock_open_fill')
              : $r('sys.symbol.lightbulb'),
    primaryValue: null,
    isOn: false,
    online: false
  };
}

const DEVICE_INVENTORY: Device[] = [
  offlineDevice('light_01', '客厅主灯', DeviceType.LIGHT, '客厅'),
  offlineDevice('ac_01', '客厅空调', DeviceType.AC, '客厅'),
  offlineDevice('door_01', '客厅大门', DeviceType.DOOR, '客厅'),
  offlineDevice('alarm_01', '蜂鸣警报', DeviceType.ALARM, '客厅'),
  offlineDevice('light_02', '厨房灯', DeviceType.LIGHT, '厨房'),
  offlineDevice('light_04', '卫生间灯', DeviceType.LIGHT, '卫生间'),
  offlineDevice('fan_02', '换气扇', DeviceType.FAN, '卫生间'),
  offlineDevice('light_03', '卧室灯', DeviceType.LIGHT, '卧室'),
  offlineDevice('curtain_01', '智能窗帘', DeviceType.CURTAIN, '卧室')
];

function visibleDevice(device: Device): boolean {
  return device.id !== 'light_05';
}

export class DeviceApi {
  private static stateOverrides: Map<string, DeviceStateOverride> = new Map<string, DeviceStateOverride>();

  private static rememberState(id: string, isOn?: boolean, primaryValue?: number, mode?: string): void {
    const state: DeviceStateOverride = {};
    const previous = DeviceApi.stateOverrides.get(id);
    if (previous?.isOn !== undefined) state.isOn = previous.isOn;
    if (previous?.primaryValue !== undefined) state.primaryValue = previous.primaryValue;
    if (previous?.mode !== undefined) state.mode = previous.mode;
    if (isOn !== undefined) state.isOn = isOn;
    if (primaryValue !== undefined) state.primaryValue = primaryValue;
    if (mode !== undefined) state.mode = mode;
    DeviceApi.stateOverrides.set(id, state);
  }

  private static applyOverride(device: Device): Device {
    const state = DeviceApi.stateOverrides.get(device.id);
    if (!state) return device;
    const isOnConfirmed = state.isOn === undefined || state.isOn === device.isOn;
    const valueConfirmed = state.primaryValue === undefined || state.primaryValue === device.primaryValue;
    const modeConfirmed = state.mode === undefined || state.mode === device.mode;
    if (isOnConfirmed && valueConfirmed && modeConfirmed) {
      DeviceApi.stateOverrides.delete(device.id);
      return device;
    }
    return {
      id: device.id,
      name: device.name,
      type: device.type,
      status: device.status,
      room: device.room,
      icon: device.icon,
      primaryValue: state.primaryValue === undefined ? device.primaryValue : state.primaryValue,
      isOn: state.isOn === undefined ? device.isOn : state.isOn,
      mode: state.mode === undefined ? device.mode : state.mode,
      online: device.online,
      primaryUnit: device.primaryUnit,
      updatedAt: device.updatedAt
    };
  }

  private static rememberControlState(id: string, action: string, body: ControlRequest): void {
    if (action === 'stop') DeviceApi.rememberState(id, false, undefined, 'stop');
    else if (action === 'forward' || action === 'reverse') {
      DeviceApi.rememberState(id, true, body.speed, action);
    } else if (action === 'set_position') DeviceApi.rememberState(id, undefined, body.position);
    else if (action === 'set_temperature') DeviceApi.rememberState(id, undefined, body.temperature);
    else if (action === 'set_brightness' && body.brightness !== undefined) {
      DeviceApi.rememberState(id, body.brightness > 0, body.brightness);
    }
  }

  static syncAssistantActions(actions: ChatAction[]): void {
    actions.forEach((item: ChatAction): void => {
      if (!item.success || !item.deviceId) return;
      if (item.action === '关闭') DeviceApi.rememberState(item.deviceId, false);
      else if (item.action === '打开') DeviceApi.rememberState(item.deviceId, true);
      else if (item.action === '调整位置') DeviceApi.rememberState(item.deviceId, undefined, item.value);
      else if (item.action === '调整温度') DeviceApi.rememberState(item.deviceId, undefined, item.value);
      else if (item.action === '调整亮度') {
        DeviceApi.rememberState(item.deviceId, item.value !== undefined ? item.value > 0 : undefined, item.value);
      }
    });
  }

  private static actionResult(result: HttpResult): ApiActionResult {
    let success = result.status >= 200 && result.status < 300;
    let message = success ? '操作成功' : result.error || '操作失败';
    let offline = result.offline;
    if (result.body) {
      try {
        const value = JSON.parse(result.body) as Json;
        if (typeof value.success === 'boolean') success = value.success;
        if (typeof value.message === 'string') message = value.message;
        else if (typeof value.error === 'string') message = value.error;
        offline = offline || value.offline === true;
      } catch (_) {}
    }
    if (offline) message = '设备离线';
    return { success, message, offline };
  }

  static getInventory(): Device[] { return DEVICE_INVENTORY; }

  static async getDevicesResult(): Promise<DeviceLoadResult> {
    const result = await Http.getResult('/api/app/devices');
    if (result.status < 200 || result.status >= 300) {
      return { devices: [], error: result.error || '设备数据加载失败', offline: result.offline };
    }
    try {
      const parsed = JSON.parse(result.body) as Object;
      let source: Json[] = [];
      if (Array.isArray(parsed)) source = parsed as Json[];
      else {
        const response = parsed as DeviceListResponse;
        if (Array.isArray(response.devices)) source = response.devices;
      }
      const devices = source
        .map((item: Json): Device => DeviceApi.applyOverride(normalizeDevice(item)))
        .filter(visibleDevice);
      const onlineCount = devices.filter((device: Device): boolean => device.online).length;
      hilog.info(0x0000, 'SmartHomeDevice', 'parsed=%{public}d online=%{public}d', devices.length, onlineCount);
      return {
        devices,
        error: '',
        offline: false
      };
    } catch (_) {
      return { devices: [], error: '设备数据格式无法识别', offline: false };
    }
  }

  static async getDevices(): Promise<Device[]> {
    return (await DeviceApi.getDevicesResult()).devices;
  }

  static async getDevice(id: string): Promise<Device | undefined> {
    if (id === 'light_05') return undefined;
    const raw = await Http.get(`/api/app/devices/${encodeURIComponent(id)}`);
    if (!raw) return undefined;
    try {
      const response = JSON.parse(raw) as DeviceResponse;
      return DeviceApi.applyOverride(normalizeDevice(response.device));
    } catch (_) { return undefined; }
  }

  static async controlResult(id: string, action: string, params: ControlParams): Promise<ApiActionResult> {
    const normalizedAction = action === 'set_temp' ? 'set_temperature' : action === 'position' ? 'set_position' : action;
    const body: ControlRequest = { action: normalizedAction };
    if (params.value !== undefined) {
      if (normalizedAction === 'position' || normalizedAction === 'set_position') body.position = params.value;
      else if (normalizedAction === 'set_brightness') body.brightness = params.value;
      else if (normalizedAction === 'set_temperature') body.temperature = params.value;
      else if (normalizedAction === 'forward' || normalizedAction === 'reverse' || normalizedAction === 'set_speed') body.speed = params.value;
      else body.value = params.value;
    }
    if (params.mode !== undefined) body.mode = params.mode;
    if (params.direction !== undefined) body.direction = params.direction;
    if (params.speed !== undefined) body.speed = params.speed;
    if (params.fanSpeed !== undefined) body.fan_speed = params.fanSpeed;
    const result = DeviceApi.actionResult(
      await Http.postResult(`/api/app/devices/${encodeURIComponent(id)}/control`, body));
    if (result.success) DeviceApi.rememberControlState(id, normalizedAction, body);
    return result;
  }

  static async control(id: string, action: string, params: ControlParams): Promise<boolean> {
    return (await DeviceApi.controlResult(id, action, params)).success;
  }

  static async toggleResult(id: string, isOn: boolean, doorPassword?: string): Promise<ApiActionResult> {
    if (id === 'door_01' && isOn && !doorPassword) {
      return { success: false, message: '请输入门禁密码', offline: false };
    }
    const body: ToggleRequest = { isOn };
    if (doorPassword) body.doorPassword = doorPassword;
    const result = DeviceApi.actionResult(
      await Http.postResult(`/api/app/devices/${encodeURIComponent(id)}/toggle`, body));
    if (result.success) DeviceApi.rememberState(id, isOn);
    return result;
  }

  static async toggle(id: string, isOn: boolean, doorPassword?: string): Promise<boolean> {
    return (await DeviceApi.toggleResult(id, isOn, doorPassword)).success;
  }

  static async doorResult(action: 'open' | 'close' | 'query', doorPassword?: string): Promise<ApiActionResult> {
    if (action === 'open' && !doorPassword) return { success: false, message: '请输入门禁密码', offline: false };
    const body: DoorRequest = { action };
    if (doorPassword) body.doorPassword = doorPassword;
    const result = DeviceApi.actionResult(await Http.postResult('/api/app/door/control', body));
    if (result.success && action !== 'query') DeviceApi.rememberState('door_01', action === 'open');
    return result;
  }

  static async door(action: 'open' | 'close' | 'query', doorPassword?: string): Promise<boolean> {
    return (await DeviceApi.doorResult(action, doorPassword)).success;
  }
}
