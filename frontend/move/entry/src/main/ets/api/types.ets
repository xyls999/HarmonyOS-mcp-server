/** A9 智慧家居后端 v5 前端数据契约。离线数据必须保持 null。 */
export enum DeviceType {
  FAN = 'fan',
  AC = 'ac',
  DOOR = 'door',
  LIGHT = 'light',
  ALARM = 'alarm',
  CURTAIN = 'curtain',
  EXHAUST = 'exhaust'
}

export enum DeviceStatus {
  ONLINE = 'online',
  OFFLINE = 'offline',
  ACTIVE = 'active'
}

export interface Device {
  id: string;
  name: string;
  type: DeviceType;
  status: DeviceStatus;
  room: string;
  icon: Resource;
  primaryValue: number | null;
  isOn: boolean;
  mode?: string;
  online: boolean;
  primaryUnit?: string;
  updatedAt?: string;
}

export interface ControlParams {
  value?: number;
  mode?: string;
  direction?: number;
  speed?: number;
  fanSpeed?: string;
}

export enum SensorType {
  TEMPERATURE = 'temperature',
  HUMIDITY = 'humidity',
  SMOKE = 'smoke',
  HEAT = 'heat',
  ALARM = 'alarm',
  AIR_QUALITY = 'air_quality'
}

export enum SensorGroup {
  ENVIRONMENT = '环境监测',
  SECURITY = '安全报警'
}

export interface SensorReading {
  value: number | null;
  unit: string;
  timestamp: number;
}

export interface Sensor {
  id: string;
  name: string;
  type: SensorType;
  group: SensorGroup;
  room: string;
  icon: Resource;
  current: SensorReading | null;
  history: number[];
  thresholdMin?: number;
  thresholdMax?: number;
  protocol: 'wifi';
  isAlert: boolean;
  online: boolean;
}

export interface AlertMessage {
  id: string;
  source: string;
  content: string;
  level: 'info' | 'warning' | 'danger';
  timestamp: number;
  isRead: boolean;
}

export interface AreaStatus {
  id?: string;
  name: string;
  ip: string;
  port: number;
  deviceType?: string;
  online: boolean;
  lastSeen?: string | null;
  devices?: Device[];
  sensors?: Sensor[];
}

export interface CheckResult {
  timestamp: string;
  onlineCount: number;
  offlineCount: number;
  areas: AreaStatus[];
  message: string;
}

export interface OperationRecord {
  id: string;
  deviceName: string;
  action: string;
  success: boolean;
  timestamp: number;
  message: string;
}

export interface SecurityEvent {
  id: string;
  source: string;
  room: string;
  content: string;
  level: 'info' | 'warning' | 'danger';
  timestamp: number;
}

export interface Scene {
  id: string;
  name: string;
  deviceCount: number;
  allowed: boolean;
}

export interface ApiActionResult {
  success: boolean;
  message: string;
  offline: boolean;
}

export interface DeviceOnlineRate { total: number; online: number; offline: number; rate: number; }
export interface MetricValue { value: number | null; unit: string; online: boolean; is_alert: boolean; threshold: number; }
export interface KitchenSmoke { smoke_level: number | null; smoke_alarm: boolean | null; online: boolean; description: string | null; }
export interface KitchenThermal { thermal_mv: number | null; temp_alarm: boolean | null; online: boolean; threshold_mv: number; description: string | null; }
export interface KitchenAlarm { alarm: number | null; online: boolean; description: string | null; }
export interface BathroomFan { motor_running: boolean | null; motor_speed: number | null; motor_direction: number | null; online: boolean; direction_label: string | null; }
export interface BedroomCurtain { position: number | null; moving: boolean | null; homed: boolean | null; close_limit: number | null; open_limit: number | null; online: boolean; }
export interface LightStat { name: string; room: string; brightness: number | null; is_on: boolean | null; online: boolean; }
export interface AlarmLinkage { last_kitchen_alarm: number; buzzer_triggered: boolean | null; udp_listening: boolean; events_24h: number; rule: string; }

export interface Stats {
  timestamp: string;
  poll_interval_kitchen: number;
  poll_interval_other: number;
  device_online_rate: DeviceOnlineRate;
  area_connectivity: Record<string, AreaStatus>;
  living_temperature: MetricValue;
  living_humidity: MetricValue;
  kitchen_smoke: KitchenSmoke;
  kitchen_thermal: KitchenThermal;
  kitchen_alarm: KitchenAlarm;
  bathroom_fan: BathroomFan;
  bedroom_curtain: BedroomCurtain;
  all_lights: Record<string, LightStat>;
  alarm_linkage: AlarmLinkage;
}

export enum ChatRole { USER = 'user', ASSISTANT = 'assistant' }

// 图表数据类型（ECharts兼容）
export interface ChartSeries {
  name?: string;
  type: string;
  smooth?: boolean;
  areaStyle?: Record<string, Object>;
  data: (number | string)[];
  radius?: string[];
}

export interface ChartAxis {
  type: string;
  data: string[];
}

export interface RadarIndicator {
  name: string;
  max: number;
}

export interface ChartRadar {
  indicator: RadarIndicator[];
}

export interface ChartConfig {
  id: string;
  title: string;
  type: string; // bar | line | pie | gauge | radar
  xAxis?: ChartAxis;
  series: ChartSeries[];
  data?: Record<string, Object>; // gauge类型
  radar?: ChartRadar; // radar类型
}

export interface ChartData {
  chart_type: string;
  keyword: string;
  kimi_used: boolean;
  days: number;
  charts: ChartConfig[];
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  chartData?: ChartData;
  ttsAudio?: string;
  imageUrl?: string;
  isError?: boolean;
  sceneName?: string;
  actions?: ChatAction[];
  feedbackScore?: number;
}
export interface ChatAction {
  deviceId: string;
  deviceName: string;
  action: string;
  success: boolean;
  value?: number;
}
export interface RagStats { exactCommands: number; documents: number; available: boolean; }
export interface RouterDeviceParam { deviceId: string; }
export interface RouterSensorParam { sensorId: string; }
