import { Device, DeviceStatus, DeviceType, Sensor, SensorGroup, SensorReading, SensorType } from './types';

type Json = Record<string, Object>;

function text(value: Object | undefined, fallback: string): string {
  return typeof value === 'string' ? value : fallback;
}

function json(value: Object | undefined): Json | null {
  return typeof value === 'object' && value !== null ? value as Json : null;
}

function numeric(value: Object | undefined): number | null {
  return typeof value === 'number' ? value : null;
}

export function deviceIcon(type: DeviceType): Resource {
  if (type === DeviceType.FAN || type === DeviceType.EXHAUST) return $r('sys.symbol.fan_fill_1');
  if (type === DeviceType.AC) return $r('sys.symbol.air_fill');
  if (type === DeviceType.DOOR) return $r('sys.symbol.lock');
  if (type === DeviceType.ALARM) return $r('sys.symbol.bell_fill');
  if (type === DeviceType.CURTAIN) return $r('sys.symbol.lock_open_fill');
  return $r('sys.symbol.lightbulb');
}

export function normalizeDevice(raw: Json): Device {
  const type = text(raw.type, DeviceType.LIGHT) as DeviceType;
  const values = json(raw.values);
  const statusText = text(raw.status, raw.online === true ? DeviceStatus.ONLINE : DeviceStatus.OFFLINE);
  const online = statusText !== DeviceStatus.OFFLINE && raw.online !== false;
  let primaryValue = numeric(raw.primaryValue);
  if (primaryValue === null && values) {
    primaryValue = numeric(values.brightness);
    if (primaryValue === null) primaryValue = numeric(values.temperature);
    if (primaryValue === null) primaryValue = numeric(values.position);
    if (primaryValue === null) primaryValue = numeric(values.speed);
  }
  const nestedOn = values ? values.is_on === true : false;
  const isOn = raw.isOn === true || nestedOn;
  return {
    id: text(raw.id, ''), name: text(raw.name, '未知设备'), type,
    status: online ? DeviceStatus.ONLINE : DeviceStatus.OFFLINE,
    room: text(raw.room, '未知区域'), icon: deviceIcon(type),
    primaryValue,
    isOn: online && isOn,
    mode: typeof raw.mode === 'string' ? raw.mode : values && typeof values.mode === 'string' ? values.mode : undefined,
    online,
    primaryUnit: text(raw.primaryUnit, text(raw.unit, '')),
    updatedAt: text(raw.updatedAt, text(raw.updated_at, ''))
  };
}

export function normalizeSensor(raw: Json): Sensor {
  const type = text(raw.type, SensorType.ALARM) as SensorType;
  const current = json(raw.current);
  const values = json(raw.values);
  const online = raw.online !== false && text(raw.status, DeviceStatus.ONLINE) !== DeviceStatus.OFFLINE;
  let value = current ? numeric(current.value) : numeric(raw.primaryValue);
  if (value === null && values) {
    value = numeric(values[type]);
    if (value === null) value = numeric(values.value);
  }
  const reading: SensorReading = {
    value,
    unit: current ? text(current.unit, text(raw.unit, '')) : text(raw.unit, text(raw.primaryUnit, '')),
    timestamp: current && typeof current.timestamp === 'number' ? current.timestamp : Date.now()
  };
  return {
    id: text(raw.id, ''), name: text(raw.name, '未知传感器'), type,
    group: type === SensorType.TEMPERATURE || type === SensorType.HUMIDITY ? SensorGroup.ENVIRONMENT : SensorGroup.SECURITY,
    room: text(raw.room, '未知区域'), icon: type === SensorType.TEMPERATURE ? $r('sys.symbol.thermometer') : type === SensorType.HUMIDITY ? $r('sys.symbol.drop') : $r('sys.symbol.flame_fill'),
    current: online ? reading : null,
    history: [], thresholdMin: typeof raw.thresholdMin === 'number' ? raw.thresholdMin : undefined,
    thresholdMax: typeof raw.thresholdMax === 'number' ? raw.thresholdMax : undefined,
    protocol: 'wifi', isAlert: raw.isAlert === true, online
  };
}
