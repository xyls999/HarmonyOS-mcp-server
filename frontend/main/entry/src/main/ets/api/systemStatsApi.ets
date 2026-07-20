/**
 * A9 v6.1 真实状态统计。
 * 单次请求 /api/stats；离线 null 原样保留为“暂无”，不生成默认数据。
 */
import { Http } from './http';

interface DeviceOnlineRateResponse {
  total?: number;
  online?: number;
  offline?: number;
  rate?: number;
}

interface AreaStateResponse {
  name?: string;
  ip?: string;
  online?: boolean;
  last_seen?: string | null;
}

interface AreaConnectivityResponse {
  living_room?: AreaStateResponse;
  kitchen?: AreaStateResponse;
  bathroom?: AreaStateResponse;
  bedroom?: AreaStateResponse;
}

interface EnvironmentStateResponse {
  value?: number | null;
  unit?: string;
  online?: boolean;
  is_alert?: boolean;
  threshold?: number;
}

interface KitchenSmokeResponse {
  smoke_level?: number | null;
  smoke_alarm?: boolean | null;
  online?: boolean;
}

interface KitchenThermalResponse {
  thermal_mv?: number | null;
  temp_alarm?: boolean | null;
  online?: boolean;
}

interface KitchenAlarmResponse {
  alarm?: number | null;
  online?: boolean;
}

interface BathroomFanResponse {
  motor_running?: boolean | null;
  motor_speed?: number | null;
  motor_direction?: number | null;
  direction_label?: string | null;
  online?: boolean;
}

interface BedroomCurtainResponse {
  position?: number | null;
  moving?: boolean | null;
  homed?: boolean | null;
  online?: boolean;
}

interface LightStateResponse {
  brightness?: number | null;
  is_on?: boolean | null;
  online?: boolean;
}

interface AllLightsResponse {
  light_01?: LightStateResponse;
  light_02?: LightStateResponse;
  light_03?: LightStateResponse;
  light_04?: LightStateResponse;
}

interface AlarmLinkageResponse {
  last_kitchen_alarm?: number | null;
  buzzer_triggered?: boolean | null;
  udp_listening?: boolean;
  events_24h?: number;
}

interface StatsResponse {
  timestamp?: string;
  poll_interval_kitchen?: number;
  poll_interval_other?: number;
  device_online_rate?: DeviceOnlineRateResponse;
  area_connectivity?: AreaConnectivityResponse;
  living_temperature?: EnvironmentStateResponse;
  living_humidity?: EnvironmentStateResponse;
  kitchen_smoke?: KitchenSmokeResponse;
  kitchen_thermal?: KitchenThermalResponse;
  kitchen_alarm?: KitchenAlarmResponse;
  bathroom_fan?: BathroomFanResponse;
  bedroom_curtain?: BedroomCurtainResponse;
  all_lights?: AllLightsResponse;
  alarm_linkage?: AlarmLinkageResponse;
}

export interface BackendStatItem {
  key: string;
  label: string;
  value: string;
  detail: string;
  online: boolean;
  progress: number;
}

export interface BackendAreaStat {
  key: string;
  name: string;
  ip: string;
  online: boolean;
  lastSeen: string;
}

export interface BackendFeatureStats {
  available: boolean;
  timestamp: string;
  deviceTotal: number;
  deviceOnline: number;
  deviceOffline: number;
  deviceOnlineRate: number;
  temperatureValue: number | null;
  temperatureUnit: string;
  temperatureOnline: boolean;
  humidityValue: number | null;
  humidityUnit: string;
  humidityOnline: boolean;
  items: BackendStatItem[];
  areas: BackendAreaStat[];
}

function numberText(value: number | null | undefined, suffix: string = ''): string {
  return typeof value === 'number' ? `${value}${suffix}` : '暂无';
}

function boolText(value: boolean | null | undefined, trueText: string, falseText: string): string {
  if (typeof value !== 'boolean') return '暂无';
  return value ? trueText : falseText;
}

function item(key: string, label: string, value: string, detail: string, online: boolean,
  progress: number): BackendStatItem {
  return { key: key, label: label, value: value, detail: detail, online: online, progress: progress };
}

function percent(value: number | null | undefined, total: number | null | undefined): number {
  if (typeof value !== 'number' || typeof total !== 'number' || total <= 0) return -1;
  return Math.max(0, Math.min(100, value / total * 100));
}

function areaSummary(areas: AreaConnectivityResponse | undefined): string {
  if (!areas) return '暂无';
  const values: (AreaStateResponse | undefined)[] = [areas.living_room, areas.kitchen, areas.bathroom, areas.bedroom];
  let total = 0;
  let online = 0;
  for (const area of values) {
    if (area) {
      total++;
      if (area.online === true) online++;
    }
  }
  return total > 0 ? `${online}/${total} 在线` : '暂无';
}

function areaProgress(areas: AreaConnectivityResponse | undefined): number {
  if (!areas) return -1;
  const values: (AreaStateResponse | undefined)[] = [areas.living_room, areas.kitchen, areas.bathroom, areas.bedroom];
  let total = 0;
  let online = 0;
  for (const area of values) {
    if (area) {
      total++;
      if (area.online === true) online++;
    }
  }
  return percent(online, total);
}

function lightsSummary(lights: AllLightsResponse | undefined): string {
  if (!lights) return '暂无';
  const values: (LightStateResponse | undefined)[] = [lights.light_01, lights.light_02, lights.light_03, lights.light_04];
  let connected = 0;
  let on = 0;
  for (const light of values) {
    if (light && light.online === true) {
      connected++;
      if (light.is_on === true) on++;
    }
  }
  return connected > 0 ? `${on}/${connected} 盏开启` : '暂无';
}

function lightsProgress(lights: AllLightsResponse | undefined): number {
  if (!lights) return -1;
  const values: (LightStateResponse | undefined)[] = [lights.light_01, lights.light_02, lights.light_03, lights.light_04];
  let connected = 0;
  let on = 0;
  for (const light of values) {
    if (light && light.online === true) {
      connected++;
      if (light.is_on === true) on++;
    }
  }
  return percent(on, connected);
}

function appendArea(result: BackendAreaStat[], key: string, area: AreaStateResponse | undefined): void {
  if (!area) return;
  result.push({
    key: key,
    name: area.name || key,
    ip: area.ip || '',
    online: area.online === true,
    lastSeen: area.last_seen || ''
  });
}

function areaDetails(areas: AreaConnectivityResponse | undefined): BackendAreaStat[] {
  const result: BackendAreaStat[] = [];
  if (!areas) return result;
  appendArea(result, 'living_room', areas.living_room);
  appendArea(result, 'kitchen', areas.kitchen);
  appendArea(result, 'bathroom', areas.bathroom);
  appendArea(result, 'bedroom', areas.bedroom);
  return result;
}

export class SystemStatsApi {
  static async getFeatureStats(): Promise<BackendFeatureStats> {
    const empty: BackendFeatureStats = {
      available: false,
      timestamp: '',
      deviceTotal: 0,
      deviceOnline: 0,
      deviceOffline: 0,
      deviceOnlineRate: 0,
      temperatureValue: null,
      temperatureUnit: '°C',
      temperatureOnline: false,
      humidityValue: null,
      humidityUnit: '%RH',
      humidityOnline: false,
      items: [],
      areas: []
    };
    const text = await Http.get('/api/stats');
    if (!text) return empty;

    try {
      const raw = JSON.parse(text) as StatsResponse;
      const devices = raw.device_online_rate;
      if (!devices || typeof devices.total !== 'number' || typeof devices.online !== 'number' ||
        typeof devices.offline !== 'number' || typeof devices.rate !== 'number') return empty;
      const temp = raw.living_temperature;
      const humid = raw.living_humidity;
      const smoke = raw.kitchen_smoke;
      const thermal = raw.kitchen_thermal;
      const alarm = raw.kitchen_alarm;
      const fan = raw.bathroom_fan;
      const curtain = raw.bedroom_curtain;
      const linkage = raw.alarm_linkage;
      const statsItems: BackendStatItem[] = [];

      statsItems.push(item('device', '设备在线率', numberText(devices?.rate, '%'),
        `${numberText(devices?.online)} 在线 · ${numberText(devices?.offline)} 离线`, true, devices?.rate ?? -1));
      statsItems.push(item('areas', '区域连通', areaSummary(raw.area_connectivity), '客厅 · 厨房 · 卫生间 · 卧室', true,
        areaProgress(raw.area_connectivity)));
      statsItems.push(item('temperature', '客厅温度', numberText(temp?.value, temp?.unit || '°C'),
        boolText(temp?.is_alert, '超过阈值', '状态正常'), temp?.online === true, percent(temp?.value, temp?.threshold)));
      statsItems.push(item('humidity', '客厅湿度', numberText(humid?.value, humid?.unit || '%RH'),
        boolText(humid?.is_alert, '超过阈值', '状态正常'), humid?.online === true, percent(humid?.value, humid?.threshold)));
      statsItems.push(item('smoke', '厨房烟雾', numberText(smoke?.smoke_level),
        boolText(smoke?.smoke_alarm, '烟雾报警', '状态正常'), smoke?.online === true,
        typeof smoke?.smoke_alarm === 'boolean' ? (smoke?.smoke_alarm ? 100 : 0) : -1));
      statsItems.push(item('thermal', '厨房热敏', numberText(thermal?.thermal_mv, 'mV'),
        boolText(thermal?.temp_alarm, '过热报警', '状态正常'), thermal?.online === true, percent(thermal?.thermal_mv, 3300)));
      statsItems.push(item('kitchen_alarm', '厨房综合报警', numberText(alarm?.alarm),
        alarm?.alarm === 1 ? '报警中' : alarm?.alarm === 0 ? '状态正常' : '暂无', alarm?.online === true,
        typeof alarm?.alarm === 'number' ? (alarm?.alarm || 0) * 100 : -1));
      statsItems.push(item('fan', '卫生间风扇', boolText(fan?.motor_running, '运行中', '已停止'),
        fan?.motor_speed === null || fan?.motor_speed === undefined ? '暂无' : `${fan?.direction_label || '方向未知'} · ${fan.motor_speed}%`,
        fan?.online === true, typeof fan?.motor_speed === 'number' ? (fan?.motor_speed || 0) : -1));
      statsItems.push(item('curtain', '卧室窗帘', numberText(curtain?.position, '%'),
        boolText(curtain?.moving, '移动中', '已停止'), curtain?.online === true,
        typeof curtain?.position === 'number' ? (curtain?.position || 0) : -1));
      statsItems.push(item('lights', '所有灯光', lightsSummary(raw.all_lights), '已连接灯具开启比例',
        lightsSummary(raw.all_lights) !== '暂无', lightsProgress(raw.all_lights)));
      statsItems.push(item('linkage', '报警联动', numberText(linkage?.events_24h, ' 次/24h'),
        `蜂鸣器 ${boolText(linkage?.buzzer_triggered, '已触发', '未触发')}`, typeof linkage?.buzzer_triggered === 'boolean',
        typeof linkage?.buzzer_triggered === 'boolean' ? (linkage?.buzzer_triggered ? 100 : 0) : -1));
      statsItems.push(item('polling', '轮询配置', `${numberText(raw.poll_interval_kitchen, 's')} / ${numberText(raw.poll_interval_other, 's')}`,
        '厨房 / 其他区域', typeof raw.poll_interval_kitchen === 'number' && typeof raw.poll_interval_other === 'number', -1));

      return {
        available: true,
        timestamp: raw.timestamp || '',
        deviceTotal: typeof devices?.total === 'number' ? devices.total : 0,
        deviceOnline: typeof devices?.online === 'number' ? devices.online : 0,
        deviceOffline: typeof devices?.offline === 'number' ? devices.offline : 0,
        deviceOnlineRate: typeof devices?.rate === 'number' ? devices.rate : 0,
        temperatureValue: temp?.online === true && typeof temp.value === 'number' ? temp.value : null,
        temperatureUnit: temp?.unit || '°C',
        temperatureOnline: temp?.online === true,
        humidityValue: humid?.online === true && typeof humid.value === 'number' ? humid.value : null,
        humidityUnit: humid?.unit || '%RH',
        humidityOnline: humid?.online === true,
        items: statsItems,
        areas: areaDetails(raw.area_connectivity)
      };
    } catch (e) {
      return empty;
    }
  }
}
