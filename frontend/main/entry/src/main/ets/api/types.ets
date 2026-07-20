/**
 * 数据模型定义 · 智能家居 App 前端数据契约
 * agent3 审核: 所有页面只依赖这些类型，不直接依赖后端结构
 */

// ============ 图标约定 ============
// 图标使用 HarmonyOS 原生 SymbolGlyph 系统图标库（sys.symbol.xxx）
// icon 字段类型为 Resource，由 $r('sys.symbol.xxx') 返回
// 渲染时用 SymbolGlyph(icon).fontColor([color]) 组件

// ============ 设备 ============
export enum DeviceType {
  FAN = 'fan',
  AC = 'ac',
  DOOR = 'door',
  LIGHT = 'light',
  CAMERA = 'camera',
  ALARM = 'alarm',
  CURTAIN = 'curtain',
  CUSTOM = 'custom'
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
  /** SymbolGlyph 系统图标资源，如 $r('sys.symbol.fan_fill_1') */
  icon: Resource;
  /** 风扇: 0-3 档位 / 空调: 温度 / 门禁: 0关1开 / 灯光: 0-100亮度 */
  primaryValue: number;
  /** 开关状态 */
  isOn: boolean;
  /** 二级参数：空调模式等 */
  mode?: string;
  /** 电量百分比（电池设备） */
  battery?: number;
  /** 后端累计在线时长，单位秒；未上报时为空 */
  uptimeSeconds?: number;
  /** 最近一次在线时间；保留后端时间字符串 */
  lastSeen?: string;
  /** 本次上线开始时间；保留后端时间字符串 */
  onlineSince?: string;
}

// ============ 设备控制参数 ============
export interface ControlParams {
  value?: number;
  mode?: string;
  temperature?: number;
  brightness?: number;
  speed?: number;
  direction?: string;
  position?: number;
  fan_speed?: string;
  swing?: string;
  profile?: string;
  color?: string;
}

// ============ 传感器 ============
export enum SensorType {
  TEMPERATURE = 'temperature',   // 温度
  HUMIDITY = 'humidity',          // 湿度
  AIR_QUALITY = 'air_quality',    // 空气 PM2.5/CO2
  ILLUMINANCE = 'illuminance',    // 光照度
  PIR = 'pir',                    // 人体存在
  DOOR_WINDOW = 'door_window',    // 门窗
  SMOKE = 'smoke',                // 烟雾
  WATER_LEAK = 'water_leak',      // 水浸
  POWER = 'power',                // 电量能耗
  WEIGHT = 'weight',              // 体重
  POSTURE = 'posture'             // 姿态
}

export enum SensorGroup {
  ENVIRONMENT = '环境监测',
  SECURITY = '安防',
  ENERGY = '能耗',
  OTHER = '其他'
}

export interface SensorReading {
  value: number;
  unit: string;
  timestamp: number;
}

export interface Sensor {
  id: string;
  name: string;
  type: SensorType;
  group: SensorGroup;
  room: string;
  /** SymbolGlyph 系统图标资源 */
  icon: Resource;
  current: SensorReading;
  /** 历史趋势 24h（用于详情页曲线） */
  history: number[];
  /** 告警阈值 */
  thresholdMin?: number;
  thresholdMax?: number;
  /** 通信协议 */
  protocol: 'wifi' | 'starflash';
  /** 是否告警 */
  isAlert: boolean;
}

// ============ 摄像头/监控 ============
export interface Camera {
  id: string;
  name: string;
  room: string;
  status: DeviceStatus;
  /** 是否正在录像 */
  isRecording: boolean;
  /** 分辨率 */
  resolution: string;
  /** 预览图（占位用纯色） */
  previewColor: string;
}

export interface AlertMessage {
  id: string;
  source: string;        // 来源设备/传感器
  content: string;
  level: 'info' | 'warning' | 'danger';
  timestamp: number;
  isRead: boolean;
}

// ============ 大模型对话 ============
export enum ChatRole {
  USER = 'user',
  ASSISTANT = 'assistant'
}

export interface ChartAxis {
  type?: string;
  data?: string[];
}

export interface ChartDatum {
  name?: string;
  value?: number | number[];
}

export interface ChartRadarIndicator {
  name?: string;
  max?: number;
}

export interface ChartRadar {
  indicator?: ChartRadarIndicator[];
}

export interface ChartSeries {
  name?: string;
  type?: string;
  smooth?: boolean;
  areaStyle?: Object;
  radius?: string[];
  data?: Array<number | string | ChartDatum>;
}

export interface ChartGaugeData {
  date?: string;
  total_requests?: number;
  total_chat?: number;
  total_device_ops?: number;
  total_security_events?: number;
  online_devices?: number;
  total_devices?: number;
  online_sensors?: number;
  total_sensors?: number;
}

export interface ChartConfig {
  id?: string;
  title?: string;
  type?: string;
  xAxis?: ChartAxis;
  radar?: ChartRadar;
  series?: ChartSeries[];
  data?: ChartGaugeData;
}

export interface ChartData {
  chart_type?: string;
  keyword?: string;
  kimi_used?: boolean;
  days?: number;
  charts?: ChartConfig[];
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  timestamp: number;
  /** 是否正在流式输出 */
  isStreaming?: boolean;
  /** 仅发送给 AI 的结构化上下文，不在对话气泡中显示。 */
  context?: string;
  /** 后端随回复返回的 ECharts 兼容图表。 */
  chartData?: ChartData;
  /** 待确认计划的一次性令牌，仅用于同一会话的执行或取消。 */
  planNonce?: string;
  planDigest?: string;
}

// ============ 用户与服务端 ============
export interface UserProfile {
  id: string;
  nickname: string;
  homeName: string;
  memberCount: number;
  deviceCount: number;
}

/** 用户资料可更新字段（全部可选） */
export interface UserProfileUpdate {
  nickname?: string;
  homeName?: string;
  memberCount?: number;
  deviceCount?: number;
}

export interface ServerStatus {
  host: string;
  port: number;
  isOnline: boolean;
  protocol: 'wifi' | 'starflash';
  latency: number;       // ms
  cpuUsage: number;      // %
  memUsage: number;      // %
  storageUsage: number;  // %
}

// ============ 路由参数（router.pushUrl 的 params）============
export interface RouterDeviceParam {
  deviceId: string;
}
export interface RouterSensorParam {
  sensorId: string;
}
export interface RouterCameraParam {
  cameraId: string;
}

// ============ 场景 ============
/** 场景动作：对某设备执行某操作 */
export interface SceneAction {
  deviceId: string;
  isOn: boolean;
  primaryValue?: number;
}

export interface Scene {
  id: string;
  name: string;
  /** SymbolGlyph 系统图标资源 */
  icon: Resource;
  color: string;
  isActive: boolean;
  /** 该场景触发的设备动作列表 */
  actions: SceneAction[];
}

// ============ 天气 ============
export interface Weather {
  city: string;
  temp: number;
  condition: string;
  humidity: number;
  /** SymbolGlyph 系统图标资源 */
  icon: Resource;
}
