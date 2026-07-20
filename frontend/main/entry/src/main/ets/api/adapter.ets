import { AlertMessage, Camera, Device, DeviceStatus, DeviceType, Sensor, SensorGroup, SensorType } from './types';

type AnyRecord = Record<string, Object>;

function textOf(value: Object | undefined, fallback: string): string {
  if (typeof value === 'string') {
    const text = value.trim();
    const lower = text.toLowerCase();
    if (text.length === 0 || lower === 'undefined' || lower === 'undifeid' || lower === 'null' || lower === 'nan') {
      return fallback;
    }
    return text;
  }
  return fallback;
}

function visibleTextOf(value: Object | undefined, fallback: string): string {
  const text = textOf(value, fallback);
  if (/[A-Za-z]/.test(text)) {
    return fallback;
  }
  return text;
}

function numberOf(value: Object | undefined, fallback: number): number {
  if (typeof value === 'number') {
    if (value !== value) {
      return fallback;
    }
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

function optionalNumberOf(...values: (Object | undefined)[]): number | undefined {
  for (const value of values) {
    if (typeof value === 'number' && value === value) return value;
  }
  return undefined;
}

function optionalTextOf(...values: (Object | undefined)[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim().length > 0) return value.trim();
  }
  return undefined;
}

function alertLevelOf(value: Object | undefined): 'info' | 'warning' | 'danger' {
  if (typeof value === 'string') {
    const level = value.toLowerCase();
    if (level === 'critical' || level === 'danger' || level === 'high') return 'danger';
    if (level === 'warning' || level === 'medium') return 'warning';
    if (level === 'info' || level === 'low') return 'info';
  }
  return 'info';
}

export function iconFromName(name: string, fallback: Resource = $r('sys.symbol.house')): Resource {
  switch (name) {
    case 'fan_fill_1':
    case 'fan':
      return $r('sys.symbol.fan_fill_1');
    case 'air_fill':
    case 'air':
      return $r('sys.symbol.air_fill');
    case 'door_service':
    case 'door':
    case 'lock':
      return $r('sys.symbol.doors_and_windows_closed');
    case 'lock_open_fill':
    case 'curtain':
      return $r('sys.symbol.doors_and_windows_closed');
    case 'bell_fill':
    case 'alarm':
      return $r('sys.symbol.bell_fill');
    case 'lightbulb':
    case 'light':
      return $r('sys.symbol.lightbulb');
    case 'camera_fill':
    case 'camera':
      return $r('sys.symbol.camera_fill');
    case 'thermometer':
      return $r('sys.symbol.thermometer');
    case 'drop':
    case 'drop_fill':
      return $r('sys.symbol.drop');
    case 'wind':
      return $r('sys.symbol.wind');
    case 'sun_max':
      return $r('sys.symbol.sun_max');
    case 'figure_arms_open':
      return $r('sys.symbol.figure_arms_open');
    case 'doors_and_windows_closed':
      return $r('sys.symbol.doors_and_windows_closed');
    case 'flame_fill':
      return $r('sys.symbol.flame_fill');
    case 'bolt_fill':
      return $r('sys.symbol.bolt_fill');
    case 'battery_fill':
      return $r('sys.symbol.battery_fill');
    case 'person_fill':
      return $r('sys.symbol.person_fill');
    case 'figure_walk':
      return $r('sys.symbol.figure_walk');
    default:
      return fallback;
  }
}

export function normalizeDevice(raw: AnyRecord): Device {
  const type = textOf(raw.type, DeviceType.LIGHT) as DeviceType;
  const iconName = textOf(raw.icon, type);
  const values = raw.values as AnyRecord | undefined;
  const primaryValue = values ? optionalNumberOf(raw.primaryValue, raw.primary_value, values.brightness,
    values.temperature, values.speed, values.position) : optionalNumberOf(raw.primaryValue, raw.primary_value);
  const isOn = values ? boolOf(raw.isOn, boolOf(raw.is_on, boolOf(values.is_on, false))) :
    boolOf(raw.isOn, boolOf(raw.is_on, false));
  return {
    id: textOf(raw.id, `device_${Date.now()}`),
    name: visibleTextOf(raw.name, '智能设备'),
    type,
    status: textOf(raw.status, DeviceStatus.OFFLINE) as DeviceStatus,
    room: visibleTextOf(raw.room, '全屋'),
    icon: iconFromName(iconName),
    primaryValue: primaryValue === undefined ? 0 : primaryValue,
    isOn: isOn,
    mode: typeof raw.mode === 'string' ? visibleTextOf(raw.mode, '自动') : undefined,
    battery: typeof raw.battery === 'number' ? raw.battery : undefined,
    uptimeSeconds: optionalNumberOf(raw.uptimeSeconds, raw.uptime_seconds, raw.onlineTime, raw.online_time),
    lastSeen: optionalTextOf(raw.lastSeen, raw.last_seen, raw.lastOnline, raw.last_online),
    onlineSince: optionalTextOf(raw.onlineSince, raw.online_since)
  };
}

export function normalizeSensor(raw: AnyRecord): Sensor {
  const current = raw.current as AnyRecord | undefined;
  const values = raw.values as AnyRecord | undefined;
  const type = textOf(raw.type, SensorType.TEMPERATURE) as SensorType;
  const historyRaw = raw.history as Array<number> | undefined;
  let valuesReading: number | undefined = undefined;
  if (values) {
    if (type === SensorType.TEMPERATURE) valuesReading = optionalNumberOf(values.temperature, values.value);
    else if (type === SensorType.HUMIDITY) valuesReading = optionalNumberOf(values.humidity, values.value);
    else valuesReading = optionalNumberOf(values.value);
  }
  const hasReading = current !== undefined && current !== null || valuesReading !== undefined || typeof raw.value === 'number';
  const isOffline = !hasReading || textOf(raw.status, '') === DeviceStatus.OFFLINE ||
    (typeof raw.online === 'boolean' && raw.online === false);
  const currentValue = current ? numberOf(current.value, numberOf(raw.value, valuesReading === undefined ? 0 : valuesReading)) :
    numberOf(raw.value, valuesReading === undefined ? 0 : valuesReading);
  return {
    id: textOf(raw.id, `sensor_${Date.now()}`),
    name: visibleTextOf(raw.name, '传感器'),
    type,
    group: textOf(raw.group, SensorGroup.OTHER) as SensorGroup,
    room: visibleTextOf(raw.room, '全屋'),
    icon: iconFromName(textOf(raw.icon, type)),
    current: {
      value: currentValue,
      unit: isOffline ? '离线' : current ? textOf(current.unit, textOf(raw.unit, '')) : textOf(raw.unit, ''),
      timestamp: current ? numberOf(current.timestamp, Date.now()) : Date.now()
    },
    history: historyRaw ?? [],
    thresholdMin: typeof raw.thresholdMin === 'number' ? raw.thresholdMin : undefined,
    thresholdMax: typeof raw.thresholdMax === 'number' ? raw.thresholdMax : undefined,
    protocol: textOf(raw.protocol, 'wifi') as 'wifi' | 'starflash',
    isAlert: boolOf(raw.isAlert, false)
  };
}

export function normalizeCamera(raw: AnyRecord): Camera {
  return {
    id: textOf(raw.id, `camera_${Date.now()}`),
    name: visibleTextOf(raw.name, '摄像头'),
    room: visibleTextOf(raw.room, '全屋'),
    status: textOf(raw.status, DeviceStatus.OFFLINE) as DeviceStatus,
    isRecording: boolOf(raw.isRecording, false),
    resolution: textOf(raw.resolution, '1080P'),
    previewColor: textOf(raw.previewColor, '#1D7F68')
  };
}

export function normalizeAlert(raw: AnyRecord): AlertMessage {
  return {
    id: textOf(raw.id, `alert_${Date.now()}`),
    source: visibleTextOf(raw.source, '系统告警'),
    content: visibleTextOf(raw.content, '暂无详细说明'),
    level: alertLevelOf(raw.level),
    timestamp: numberOf(raw.timestamp, Date.now()),
    isRead: boolOf(raw.isRead, false)
  };
}
