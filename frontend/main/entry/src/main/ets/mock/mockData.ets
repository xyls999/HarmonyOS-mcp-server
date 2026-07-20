/**
 * Mock 静态数据 · 本地预览用
 * 图标全部使用 HarmonyOS SymbolGlyph 系统图标库（sys.symbol.xxx）
 */
import {
  Device, DeviceType, DeviceStatus,
  Sensor, SensorType, SensorGroup,
  Camera, AlertMessage,
  UserProfile, ServerStatus,
  Scene, Weather
} from '../api/types';

const now = Date.now();

// 生成 24 点历史趋势（正弦波动）
function genHistory(base: number, range: number): number[] {
  const arr: number[] = [];
  for (let i = 0; i < 24; i++) {
    const v: number = base + Math.sin(i / 3) * range + (Math.random() - 0.5) * range * 0.3;
    arr.push(parseFloat(v.toFixed(1)));
  }
  return arr;
}

export class MockData {
  // ============ 设备：风扇 / 门禁 / 空调 / 灯光 ============
  static readonly devices: Device[] = [
    {
      id: 'fan_02', name: '换气扇', type: DeviceType.FAN, status: DeviceStatus.ONLINE,
      room: '卫生间', icon: $r('sys.symbol.fan_fill_1'), primaryValue: 0, isOn: false
    },
    {
      id: 'ac_01', name: '客厅空调', type: DeviceType.AC, status: DeviceStatus.ACTIVE,
      room: '客厅', icon: $r('sys.symbol.air_fill'), primaryValue: 24, isOn: true, mode: '制冷'
    },
    {
      id: 'door_01', name: '客厅大门', type: DeviceType.DOOR, status: DeviceStatus.ONLINE,
      room: '客厅', icon: $r('sys.symbol.doors_and_windows_closed'), primaryValue: 0, isOn: false
    },
    {
      id: 'light_01', name: '客厅主灯', type: DeviceType.LIGHT, status: DeviceStatus.ONLINE,
      room: '客厅', icon: $r('sys.symbol.lightbulb'), primaryValue: 80, isOn: true
    },
    {
      id: 'light_02', name: '厨房灯', type: DeviceType.LIGHT, status: DeviceStatus.ONLINE,
      room: '厨房', icon: $r('sys.symbol.lightbulb'), primaryValue: 40, isOn: false
    },
    {
      id: 'light_03', name: '卧室灯', type: DeviceType.LIGHT, status: DeviceStatus.ONLINE,
      room: '卧室', icon: $r('sys.symbol.lightbulb'), primaryValue: 0, isOn: false
    },
    {
      id: 'light_04', name: '卫生间灯', type: DeviceType.LIGHT, status: DeviceStatus.ONLINE,
      room: '卫生间', icon: $r('sys.symbol.lightbulb'), primaryValue: 0, isOn: false
    },
    {
      id: 'curtain_01', name: '智能窗帘', type: DeviceType.CURTAIN, status: DeviceStatus.ONLINE,
      room: '卧室', icon: $r('sys.symbol.lock_open_fill'), primaryValue: 0, isOn: false
    }
  ];

  // ============ 传感器 8+ 类 ============
  static readonly sensors: Sensor[] = [
    // —— 环境监测 ——
    {
      id: 'temp_01', name: '客厅温度', type: SensorType.TEMPERATURE, group: SensorGroup.ENVIRONMENT,
      room: '客厅', icon: $r('sys.symbol.thermometer'),
      current: { value: 24.6, unit: '°C', timestamp: now },
      history: genHistory(24, 3),
      thresholdMin: 10, thresholdMax: 35, protocol: 'wifi', isAlert: false
    },
    {
      id: 'humid_01', name: '客厅湿度', type: SensorType.HUMIDITY, group: SensorGroup.ENVIRONMENT,
      room: '客厅', icon: $r('sys.symbol.drop'),
      current: { value: 52, unit: '%RH', timestamp: now },
      history: genHistory(52, 10),
      thresholdMin: 30, thresholdMax: 70, protocol: 'wifi', isAlert: false
    },
    {
      id: 'air_01', name: 'PM2.5', type: SensorType.AIR_QUALITY, group: SensorGroup.ENVIRONMENT,
      room: '客厅', icon: $r('sys.symbol.wind'),
      current: { value: 18, unit: 'μg/m³', timestamp: now },
      history: genHistory(18, 8),
      thresholdMin: 0, thresholdMax: 75, protocol: 'wifi', isAlert: false
    },
    {
      id: 'air_02', name: 'CO₂ 浓度', type: SensorType.AIR_QUALITY, group: SensorGroup.ENVIRONMENT,
      room: '客厅', icon: $r('sys.symbol.air'),
      current: { value: 612, unit: 'ppm', timestamp: now },
      history: genHistory(612, 120),
      thresholdMin: 350, thresholdMax: 1000, protocol: 'wifi', isAlert: false
    },
    {
      id: 'light_s_01', name: '客厅光照度', type: SensorType.ILLUMINANCE, group: SensorGroup.ENVIRONMENT,
      room: '客厅', icon: $r('sys.symbol.sun_max'),
      current: { value: 842, unit: 'lux', timestamp: now },
      history: genHistory(842, 400),
      thresholdMin: 0, thresholdMax: 2000, protocol: 'starflash', isAlert: false
    },
    // —— 安防 ——
    {
      id: 'pir_01', name: '客厅人体感应', type: SensorType.PIR, group: SensorGroup.SECURITY,
      room: '客厅', icon: $r('sys.symbol.figure_arms_open'),
      current: { value: 1, unit: '触发', timestamp: now },
      history: [0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 0],
      thresholdMin: 0, thresholdMax: 1, protocol: 'starflash', isAlert: true
    },
    {
      id: 'door_s_01', name: '入户门状态', type: SensorType.DOOR_WINDOW, group: SensorGroup.SECURITY,
      room: '玄关', icon: $r('sys.symbol.doors_and_windows_closed'),
      current: { value: 0, unit: '关闭', timestamp: now },
      history: [0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
      thresholdMin: 0, thresholdMax: 0, protocol: 'starflash', isAlert: false
    },
    {
      id: 'smoke_01', name: '厨房烟雾', type: SensorType.SMOKE, group: SensorGroup.SECURITY,
      room: '厨房', icon: $r('sys.symbol.flame_fill'),
      current: { value: 0, unit: '正常', timestamp: now },
      history: genHistory(0, 0.2),
      thresholdMin: 0, thresholdMax: 1, protocol: 'wifi', isAlert: false
    },
    {
      id: 'water_01', name: '卫生间水浸', type: SensorType.WATER_LEAK, group: SensorGroup.SECURITY,
      room: '卫生间', icon: $r('sys.symbol.drop_fill'),
      current: { value: 0, unit: '正常', timestamp: now },
      history: genHistory(0, 0.1),
      thresholdMin: 0, thresholdMax: 0, protocol: 'starflash', isAlert: false
    },
    // —— 能耗 ——
    {
      id: 'power_01', name: '实时功率', type: SensorType.POWER, group: SensorGroup.ENERGY,
      room: '全屋', icon: $r('sys.symbol.bolt_fill'),
      current: { value: 1.86, unit: 'kW', timestamp: now },
      history: genHistory(1.86, 0.8),
      thresholdMin: 0, thresholdMax: 10, protocol: 'wifi', isAlert: false
    },
    {
      id: 'power_02', name: '今日电量', type: SensorType.POWER, group: SensorGroup.ENERGY,
      room: '全屋', icon: $r('sys.symbol.battery_fill'),
      current: { value: 14.3, unit: 'kWh', timestamp: now },
      history: genHistory(14.3, 4),
      thresholdMin: 0, thresholdMax: 100, protocol: 'wifi', isAlert: false
    },
    // —— 其他 ——
    {
      id: 'weight_01', name: '智能体脂秤', type: SensorType.WEIGHT, group: SensorGroup.OTHER,
      room: '卫生间', icon: $r('sys.symbol.person_fill'),
      current: { value: 68.5, unit: 'kg', timestamp: now },
      history: genHistory(68.5, 1.2),
      protocol: 'starflash', isAlert: false
    },
    {
      id: 'posture_01', name: '坐姿监测', type: SensorType.POSTURE, group: SensorGroup.OTHER,
      room: '书房', icon: $r('sys.symbol.figure_walk'),
      current: { value: 85, unit: '分', timestamp: now },
      history: genHistory(85, 10),
      thresholdMin: 60, protocol: 'starflash', isAlert: false
    }
  ];

  // ============ 摄像头 ============
  static readonly cameras: Camera[] = [
    { id: 'cam_01', name: '客厅摄像头', room: '客厅', status: DeviceStatus.ONLINE, isRecording: true, resolution: '2K', previewColor: '#1A3A5C' },
    { id: 'cam_02', name: '入户门铃', room: '玄关', status: DeviceStatus.ONLINE, isRecording: true, resolution: '1080P', previewColor: '#1E5AA8' },
    { id: 'cam_03', name: '车库监控', room: '车库', status: DeviceStatus.ONLINE, isRecording: false, resolution: '1080P', previewColor: '#2563EB' },
    { id: 'cam_04', name: '后院摄像头', room: '后院', status: DeviceStatus.OFFLINE, isRecording: false, resolution: '2K', previewColor: '#60A5FA' }
  ];

  // ============ 警报消息 ============
  static readonly alerts: AlertMessage[] = [
    { id: 'a1', source: '客厅人体感应', content: '检测到陌生人体活动，已自动开启布防', level: 'danger', timestamp: now - 5 * 60 * 1000, isRead: false },
    { id: 'a2', source: '入户门铃', content: '有人按响了门铃', level: 'info', timestamp: now - 32 * 60 * 1000, isRead: false },
    { id: 'a3', source: '后院摄像头', content: '设备离线超过 1 小时', level: 'warning', timestamp: now - 2 * 60 * 60 * 1000, isRead: false },
    { id: 'a4', source: 'CO₂ 浓度', content: '浓度达到 1200ppm，建议通风', level: 'warning', timestamp: now - 5 * 60 * 60 * 1000, isRead: true },
    { id: 'a5', source: '车库门', content: '车库门已开启', level: 'info', timestamp: now - 8 * 60 * 60 * 1000, isRead: true }
  ];

  // ============ 场景 ============
  static readonly scenes: Scene[] = [
    {
      id: 's1', name: '回家', icon: $r('sys.symbol.house_fill'), color: '#0A84FF', isActive: true,
      actions: [
        { deviceId: 'ac_01', isOn: true, primaryValue: 24 },
        { deviceId: 'light_01', isOn: true, primaryValue: 80 }
      ]
    },
    {
      id: 's2', name: '离家', icon: $r('sys.symbol.figure_walk'), color: '#3B82F6', isActive: false,
      actions: [
        { deviceId: 'fan_02', isOn: false },
        { deviceId: 'ac_01', isOn: false },
        { deviceId: 'light_01', isOn: false },
        { deviceId: 'light_02', isOn: false },
        { deviceId: 'door_01', isOn: false }
      ]
    },
    {
      id: 's3', name: '睡眠', icon: $r('sys.symbol.moon_fill'), color: '#5E6CE6', isActive: false,
      actions: [
        { deviceId: 'light_01', isOn: false },
        { deviceId: 'light_02', isOn: false },
        { deviceId: 'ac_01', isOn: true, primaryValue: 26 }
      ]
    },
    {
      id: 's4', name: '观影', icon: $r('sys.symbol.film'), color: '#60A5FA', isActive: false,
      actions: [
        { deviceId: 'light_01', isOn: true, primaryValue: 20 },
        { deviceId: 'light_02', isOn: false },
        { deviceId: 'ac_01', isOn: true, primaryValue: 24 }
      ]
    },
    {
      id: 's5', name: '用餐', icon: $r('sys.symbol.fork_knife'), color: '#0EA5E9', isActive: false,
      actions: [
        { deviceId: 'light_01', isOn: true, primaryValue: 60 }
      ]
    }
  ];

  // ============ 天气 ============
  static readonly weather: Weather = {
    city: '上海', temp: 23, condition: '多云', humidity: 58, icon: $r('sys.symbol.cloud_fill')
  };

  // ============ 用户（昵称/homeName 由引导页写入，此处为默认值）============
  static readonly user: UserProfile = {
    id: 'u001', nickname: '用户',
    homeName: '我的家', memberCount: 3, deviceCount: 8
  };

  // ============ 服务端状态 ============
  static readonly server: ServerStatus = {
    host: '192.168.1.100', port: 8080, isOnline: true,
    protocol: 'wifi', latency: 12, cpuUsage: 34, memUsage: 56, storageUsage: 41
  };

  // ============ 大模型欢迎语 ============
  static readonly chatWelcome: string = '你好，我是你的智能家居助手。可以问我「把客厅温度调到 22 度」「家里现在安全吗」之类的问题。';
}
