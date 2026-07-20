/**
 * 数据管理：日志 / 设备 / 环境三选一分页。
 * 全部数据来自现有后端接口，缺失字段明确显示“未上报”。
 */
import { AlertMessage, Device, DeviceStatus, Sensor, SensorType } from '../api/types';
import { DeviceApi } from '../api/deviceApi';
import {
  AiConversationFeed,
  AiConversationLog,
  DailyLogRecord,
  EdgeAuthStatus,
  LogChart,
  LogChartResponse,
  LogGaugeData,
  LogApi,
  OperationFeed,
  OperationLogRecord,
  SecurityLogStats,
  TodayLogSnapshot
} from '../api/logApi';
import { AiMcpApi, AiMcpTool } from '../api/aiMcpApi';
import { SensorApi } from '../api/sensorApi';
import { BackendAreaStat, BackendFeatureStats, BackendStatItem, SystemStatsApi } from '../api/systemStatsApi';
import { TacticalMotion, TacticalSpace, TacticalTheme } from '../theme/TacticalTheme';

@Component
export struct HistoryPage {
  @Prop isDark: boolean = true;
  onAnalyzeChart: (title: string, context: string) => void = (_: string, __: string): void => {};
  @State activeSection: number = 0;
  @State devices: Device[] = [];
  @State alerts: AlertMessage[] = [];
  @State sensors: Sensor[] = [];
  @State tempHistory: number[] = [];
  @State humidHistory: number[] = [];
  @State historyLabels: string[] = [];
  @State stats: BackendFeatureStats = {
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
  @State securityStats: SecurityLogStats = {
    available: false, today: 0, total: 0, critical: 0, high: 0, medium: 0, low: 0
  };
  @State authStatus: EdgeAuthStatus = {
    available: false, enableAuth: false, doorPasswordRequired: false, sharedKeySet: false,
    authAlgorithm: '', doorPasswordAlgorithm: ''
  };
  @State logsAvailable: boolean = false;
  @State logsComplete: boolean = false;
  @State devicesAvailable: boolean = false;
  @State sensorsAvailable: boolean = false;
  @State historyAvailable: boolean = false;
  @State isLoading: boolean = true;
  @State pressedSection: number = -1;
  @State dailyLogs: DailyLogRecord[] = [];
  @State todayLog: TodayLogSnapshot = { available: false, today: null, realtime: null };
  @State operationFeed: OperationFeed = { available: false, total: 0, limit: 100, operations: [] };
  @State dailyExpanded: boolean = false;
  @State todayExpanded: boolean = false;
  @State detailedLogsExpanded: boolean = false;
  @State dangerLogsExpanded: boolean = false;
  @State normalLogsExpanded: boolean = false;
  @State aiLogsExpanded: boolean = false;
  @State operationsExpanded: boolean = false;
  @State operationResultFilter: number = 0;
  @State operationSourceFilter: number = 0;
  @State expandedOperationKey: string = '';
  @State aiConversationFeed: AiConversationFeed = {
    available: false, source: '/api/chat/history', total: 0, logs: []
  };
  @State dailyChartResponse: LogChartResponse = {
    available: false, chartType: '', keyword: '七日统计', kimiUsed: false, days: 7, charts: [], raw: ''
  };
  @State todayChartResponse: LogChartResponse = {
    available: false, chartType: '', keyword: '今日实时', kimiUsed: false, days: 7, charts: [], raw: ''
  };
  @State mcpTools: AiMcpTool[] = [];
  private logRefreshTimer: number = -1;
  private refreshingLogs: boolean = false;

  aboutToAppear(): void {
    this.loadData();
    this.logRefreshTimer = setInterval(() => { this.refreshLogData(); }, 10000);
  }

  aboutToDisappear(): void {
    if (this.logRefreshTimer !== -1) clearInterval(this.logRefreshTimer);
    this.logRefreshTimer = -1;
  }

  async loadData(): Promise<void> {
    this.isLoading = true;
    const deviceRequest = DeviceApi.getDeviceSnapshot();
    const logRequest = LogApi.getSnapshot();
    const sensorRequest = SensorApi.getSensorSnapshot();
    const historyRequest = SensorApi.getTempHumidHistory();
    const statsRequest = SystemStatsApi.getFeatureStats();
    const dailyRequest = LogApi.getDaily(7);
    const todayRequest = LogApi.getToday();
    const operationRequest = LogApi.getOperationFeed(100);
    const aiConversationRequest = LogApi.getAiConversationFeed(20);
    const dailyChartRequest = LogApi.getChart('七日统计', 7);
    const todayChartRequest = LogApi.getChart('今日实时', 7);
    const toolRequest = AiMcpApi.listTools();

    const deviceSnapshot = await deviceRequest;
    this.devices = deviceSnapshot.devices;
    this.devicesAvailable = deviceSnapshot.available;

    const logSnapshot = await logRequest;
    this.alerts = logSnapshot.alerts;
    this.securityStats = logSnapshot.securityStats;
    this.authStatus = logSnapshot.authStatus;
    this.logsAvailable = logSnapshot.available;
    this.logsComplete = logSnapshot.complete;

    const sensorSnapshot = await sensorRequest;
    this.sensors = sensorSnapshot.sensors;
    this.sensorsAvailable = sensorSnapshot.available;

    const history = await historyRequest;
    this.tempHistory = history.temp;
    this.humidHistory = history.humid;
    this.historyLabels = history.labels;
    this.historyAvailable = history.available;

    this.stats = await statsRequest;
    this.dailyLogs = await dailyRequest;
    this.todayLog = await todayRequest;
    this.reconcileDailyWithToday();
    this.operationFeed = await operationRequest;
    this.aiConversationFeed = await aiConversationRequest;
    this.dailyChartResponse = await dailyChartRequest;
    this.todayChartResponse = await todayChartRequest;
    this.mcpTools = await toolRequest;
    this.isLoading = false;
  }

  private async refreshLogData(): Promise<void> {
    if (this.refreshingLogs) return;
    this.refreshingLogs = true;
    try {
      const snapshotRequest = LogApi.getSnapshot();
      const dailyRequest = LogApi.getDaily(7);
      const todayRequest = LogApi.getToday();
      const operationRequest = LogApi.getOperationFeed(100);
      const aiConversationRequest = LogApi.getAiConversationFeed(20);
      const dailyChartRequest = LogApi.getChart('七日统计', 7);
      const todayChartRequest = LogApi.getChart('今日实时', 7);
      const snapshot = await snapshotRequest;
      this.alerts = snapshot.alerts;
      this.securityStats = snapshot.securityStats;
      this.authStatus = snapshot.authStatus;
      this.logsAvailable = snapshot.available;
      this.logsComplete = snapshot.complete;
      this.dailyLogs = await dailyRequest;
      this.todayLog = await todayRequest;
      this.reconcileDailyWithToday();
      this.operationFeed = await operationRequest;
      this.aiConversationFeed = await aiConversationRequest;
      this.dailyChartResponse = await dailyChartRequest;
      this.todayChartResponse = await todayChartRequest;
    } finally {
      this.refreshingLogs = false;
    }
  }

  private selectSection(index: number): void {
    if (this.activeSection === index) return;
    this.activeSection = index;
  }

  private dangerAlerts(): AlertMessage[] {
    return this.alerts.filter((alert: AlertMessage) => alert.level === 'danger' || alert.level === 'warning');
  }

  private normalAlerts(): AlertMessage[] {
    return this.alerts.filter((alert: AlertMessage) => alert.level === 'info');
  }

  private levelCount(level: string): number {
    return this.alerts.filter((alert: AlertMessage) => alert.level === level).length;
  }

  private totalLogCount(): number {
    return this.operationFeed.total + this.aiConversationFeed.total + this.securityStats.total;
  }

  private importantLogCount(): number {
    return this.securityStats.critical + this.securityStats.high + this.securityStats.medium;
  }

  private onlineDevices(): Device[] {
    return this.devices.filter((device: Device) => device.status !== DeviceStatus.OFFLINE);
  }

  private deviceRate(): number {
    if (this.stats.available && this.stats.deviceTotal > 0) return this.stats.deviceOnlineRate;
    if (!this.devicesAvailable || this.devices.length === 0) return -1;
    return this.onlineDevices().length / this.devices.length * 100;
  }

  private deviceSummary(): string {
    if (this.stats.available) return `${this.stats.deviceOnline} 在线 / ${this.stats.deviceOffline} 离线`;
    if (this.devicesAvailable) return `${this.onlineDevices().length} 在线 / ${this.devices.length - this.onlineDevices().length} 离线`;
    return '暂时无法读取设备';
  }

  private sensorOf(type: SensorType): Sensor | undefined {
    return this.sensors.find((sensor: Sensor) => sensor.type === type && sensor.current.unit !== '离线');
  }

  private maxNumber(values: number[]): number {
    let max = 0;
    for (const value of values) if (value > max) max = value;
    return max;
  }

  private minNumber(values: number[]): number {
    if (values.length === 0) return 0;
    let min = values[0];
    for (const value of values) if (value < min) min = value;
    return min;
  }

  private barHeight(value: number, values: number[]): number {
    const min = this.minNumber(values);
    const max = this.maxNumber(values);
    if (max <= min) return 72;
    return 24 + (value - min) / (max - min) * 72;
  }

  private chartValues(values: number[]): number[] {
    if (values.length <= 18) return values;
    return values.slice(values.length - 18);
  }

  private uptimeMax(): number {
    let max = 0;
    for (const device of this.devices) {
      if (device.uptimeSeconds !== undefined && device.uptimeSeconds > max) max = device.uptimeSeconds;
    }
    return max;
  }

  private uptimeProgress(device: Device): number {
    const max = this.uptimeMax();
    if (device.uptimeSeconds === undefined || max <= 0) return -1;
    return Math.max(0, Math.min(100, device.uptimeSeconds / max * 100));
  }

  private durationText(seconds: number | undefined): string {
    if (seconds === undefined || seconds < 0) return '未上报';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor(seconds % 86400 / 3600);
    const minutes = Math.floor(seconds % 3600 / 60);
    if (days > 0) return `${days}天 ${hours}小时`;
    if (hours > 0) return `${hours}小时 ${minutes}分钟`;
    return `${minutes}分钟`;
  }

  private timeText(value: string | undefined): string {
    if (!value) return '未上报';
    const ts = Date.parse(value.replace(' ', 'T'));
    if (ts !== ts) return value;
    const date = new Date(ts);
    const month = `${date.getMonth() + 1}`.padStart(2, '0');
    const day = `${date.getDate()}`.padStart(2, '0');
    const hour = `${date.getHours()}`.padStart(2, '0');
    const minute = `${date.getMinutes()}`.padStart(2, '0');
    return `${month}-${day} ${hour}:${minute}`;
  }

  private alertTime(timestamp: number): string {
    if (timestamp <= 0) return '--:--';
    const date = new Date(timestamp);
    const hour = `${date.getHours()}`.padStart(2, '0');
    const minute = `${date.getMinutes()}`.padStart(2, '0');
    return `${hour}:${minute}`;
  }

  private currentText(type: SensorType, fallbackUnit: string): string {
    if (type === SensorType.TEMPERATURE && this.stats.temperatureOnline && this.stats.temperatureValue !== null) {
      return `${this.stats.temperatureValue}${this.stats.temperatureUnit || fallbackUnit}`;
    }
    if (type === SensorType.HUMIDITY && this.stats.humidityOnline && this.stats.humidityValue !== null) {
      return `${this.stats.humidityValue}${this.stats.humidityUnit || fallbackUnit}`;
    }
    const sensor = this.sensorOf(type);
    if (!sensor) return '--';
    if (sensor.current.unit === '离线') return '暂不可用';
    return `${sensor.current.value}${sensor.current.unit || fallbackUnit}`;
  }

  private visibleEnvironmentStats(): BackendStatItem[] {
    const hidden: string[] = ['temperature', 'humidity', 'smoke', 'thermal', 'heat',
      'kitchen_smoke', 'kitchen_heat', 'kitchen_temperature', 'kitchen_alarm'];
    return this.stats.items.slice(2).filter((item: BackendStatItem) => hidden.indexOf(item.key) < 0);
  }

  private dailyMax(): number {
    let max = 1;
    for (const record of this.dailyLogs) {
      max = Math.max(max, record.total_requests, record.total_chat, record.total_device_ops,
        record.total_security_events);
    }
    return max;
  }

  private dailyBarHeight(value: number): number {
    return Math.max(4, Math.min(82, value / this.dailyMax() * 82));
  }

  private dailyBackendChart(): LogChart | null {
    for (const chart of this.dailyChartResponse.charts) if (chart.id === 'daily_bar') return chart;
    return this.dailyChartResponse.charts.length > 0 ? this.dailyChartResponse.charts[0] : null;
  }

  private dailyCategories(): string[] {
    const chart = this.dailyBackendChart();
    return chart ? chart.categories : [];
  }

  private dailySeries(name: string): number[] {
    const chart = this.dailyBackendChart();
    if (!chart) return [];
    for (const series of chart.series) if (series.name === name) return series.data;
    return [];
  }

  private chartNumber(values: number[], index: number): number {
    return index >= 0 && index < values.length ? values[index] : 0;
  }

  private backendChartMax(): number {
    let max = 1;
    const request = this.dailySeries('请求数');
    const chat = this.dailySeries('对话数');
    const operation = this.dailySeries('设备操作');
    for (const value of request) max = Math.max(max, value);
    for (const value of chat) max = Math.max(max, value);
    for (const value of operation) max = Math.max(max, value);
    return max;
  }

  private backendBarHeight(value: number): number {
    return Math.max(4, Math.min(82, value / this.backendChartMax() * 82));
  }

  private todayGaugeData(): LogGaugeData {
    for (const chart of this.todayChartResponse.charts) {
      if (chart.id === 'today_gauge' && chart.gauge) return chart.gauge;
    }
    return {
      date: '', totalRequests: 0, totalChat: 0, totalDeviceOps: 0, totalSecurityEvents: 0,
      onlineDevices: 0, totalDevices: 0, onlineSensors: 0, totalSensors: 0
    };
  }

  private reconcileDailyWithToday(): void {
    if (!this.todayLog.available || !this.todayLog.today) return;
    const today = this.todayLog.today;
    const records: DailyLogRecord[] = [];
    let replaced = false;
    for (const record of this.dailyLogs) {
      if (record.log_date === today.log_date) {
        records.push(today);
        replaced = true;
      } else {
        records.push(record);
      }
    }
    if (!replaced) records.push(today);
    this.dailyLogs = records.length > 7 ? records.slice(records.length - 7) : records;
  }

  private dailyChartContext(): string {
    if (this.dailyChartResponse.available && this.dailyChartResponse.raw.length > 0) {
      return `数据来源：GET /api/log/chart?type=七日统计&days=7\n` +
        `ECharts配置：${this.dailyChartResponse.raw}\n前端校验摘要：${this.dailyAnalysisSummary()}`;
    }
    const lines: string[] = [
      '图表名称：最近7日日志汇总',
      '图表类型：按日期分组的多序列柱状图',
      '序列：请求总数、对话条数、设备操作、安全事件',
      `前端校验摘要：${this.dailyAnalysisSummary()}`
    ];
    for (const record of this.dailyLogs) {
      lines.push(`${record.log_date} | 请求=${record.total_requests} | 对话=${record.total_chat} | ` +
        `设备操作=${record.total_device_ops} | 安全事件=${record.total_security_events} | ` +
        `设备在线峰值=${record.devices_online_peak} | 活跃传感器=${record.sensors_active}`);
    }
    return lines.join('\n');
  }

  private dailyAnalysisSummary(): string {
    if (this.dailyChartResponse.available && this.dailyCategories().length > 0) {
      const labels = this.dailyCategories();
      const requests = this.dailySeries('请求数');
      const chats = this.dailySeries('对话数');
      const operations = this.dailySeries('设备操作');
      const latestIndex = labels.length - 1;
      const latestRequests = this.chartNumber(requests, latestIndex);
      const latestChats = this.chartNumber(chats, latestIndex);
      const latestOperations = this.chartNumber(operations, latestIndex);
      const change = latestRequests - this.chartNumber(requests, 0);
      const trend = labels.length <= 1 ? '当前只有一天数据，暂不能判断跨日趋势' :
        change > 0 ? `请求较首日增加${change}` : change < 0 ? `请求较首日减少${Math.abs(change)}` : '请求量与首日持平';
      return `最新日期${labels[latestIndex]}共有${latestRequests}次请求、${latestChats}条对话和` +
        `${latestOperations}次设备操作；${trend}`;
    }
    if (this.dailyLogs.length === 0) return '暂无每日汇总，无法判断趋势';
    const latest = this.dailyLogs[this.dailyLogs.length - 1];
    const requestTotal = Math.max(1, latest.total_requests);
    const chatRate = Math.round(latest.total_chat / requestTotal * 100);
    let trend = '目前只有一天汇总，暂不能判断跨日趋势';
    if (this.dailyLogs.length > 1) {
      const first = this.dailyLogs[0];
      const change = latest.total_requests - first.total_requests;
      trend = change > 0 ? `请求较首日增加${change}` : change < 0 ? `请求较首日减少${Math.abs(change)}` : '请求量与首日持平';
    }
    return `最新日期${latest.log_date}共有${latest.total_requests}次请求、${latest.total_chat}条对话、` +
      `${latest.total_device_ops}次设备操作和${latest.total_security_events}次安全事件；` +
      `对话约占请求${chatRate}%；${trend}。安全事件需要结合操作失败记录继续排查`;
  }

  private todayChartContext(): string {
    if (this.todayChartResponse.available && this.todayChartResponse.raw.length > 0) {
      return `数据来源：GET /api/log/chart?type=今日实时&days=7\n` +
        `ECharts配置：${this.todayChartResponse.raw}\n前端校验摘要：${this.todayAnalysisSummary()}`;
    }
    if (!this.todayLog.available || !this.todayLog.today) return '今日日志接口暂无数据';
    const today = this.todayLog.today;
    const realtime = this.todayLog.realtime;
    let context = `图表名称：今日日志与实时状态\n前端校验摘要：${this.todayAnalysisSummary()}\n` +
      `日期=${today.log_date}\n请求=${today.total_requests}\n` +
      `对话=${today.total_chat}\n设备操作=${today.total_device_ops}\n安全事件=${today.total_security_events}\n` +
      `设备在线峰值=${today.devices_online_peak}\n活跃传感器=${today.sensors_active}`;
    if (realtime) {
      context += `\n当前在线设备=${realtime.online_devices}/${realtime.total_devices}` +
        `\n当前在线传感器=${realtime.online_sensors}/${realtime.total_sensors}` +
        `\nWebSocket客户端=${realtime.ws_clients}\nMQTT客户端=${realtime.mqtt_clients}`;
    }
    return context;
  }

  private todayAnalysisSummary(): string {
    if (this.todayChartResponse.available && this.todayGaugeData().date.length > 0) {
      const gauge = this.todayGaugeData();
      return `今日${gauge.date}累计${gauge.totalRequests}次请求、${gauge.totalChat}条对话、` +
        `${gauge.totalDeviceOps}次设备操作和${gauge.totalSecurityEvents}次安全事件；` +
        `当前设备在线${gauge.onlineDevices}/${gauge.totalDevices}，` +
        `传感器在线${gauge.onlineSensors}/${gauge.totalSensors}`;
    }
    if (!this.todayLog.available || !this.todayLog.today) return '今日日志暂无数据';
    const today = this.todayLog.today;
    let online = '实时连接状态未上报';
    if (this.todayLog.realtime) {
      online = `当前设备在线${this.todayLog.realtime.online_devices}/${this.todayLog.realtime.total_devices}，` +
        `传感器在线${this.todayLog.realtime.online_sensors}/${this.todayLog.realtime.total_sensors}`;
    }
    return `今日累计${today.total_requests}次请求、${today.total_chat}条对话、` +
      `${today.total_device_ops}次设备操作和${today.total_security_events}次安全事件；${online}。` +
      `若设备或传感器在线数为0，应优先检查供电与局域网连接`;
  }

  private filteredOperations(): OperationLogRecord[] {
    const result: OperationLogRecord[] = [];
    for (const operation of this.operationFeed.operations) {
      const success = operation.result === 'ok' || operation.result === 'success';
      if (this.operationResultFilter === 1 && !success) continue;
      if (this.operationResultFilter === 2 && success) continue;
      if (this.operationSourceFilter === 1 && operation.source !== 'api') continue;
      if (this.operationSourceFilter === 2 && operation.source !== 'scene') continue;
      if (this.operationSourceFilter === 3 && operation.source !== 'local') continue;
      result.push(operation);
      if (result.length >= 50) break;
    }
    return result;
  }

  private operationTimeText(operation: OperationLogRecord): string {
    if (operation.timestampMs <= 0) return operation.timestamp || '--';
    const date = new Date(operation.timestampMs);
    const month = `${date.getMonth() + 1}`.padStart(2, '0');
    const day = `${date.getDate()}`.padStart(2, '0');
    const hour = `${date.getHours()}`.padStart(2, '0');
    const minute = `${date.getMinutes()}`.padStart(2, '0');
    const second = `${date.getSeconds()}`.padStart(2, '0');
    return `${month}-${day} ${hour}:${minute}:${second}`;
  }

  private actionLabel(action: string): string {
    if (action === 'toggle') return '开关';
    if (action === 'set_brightness') return '亮度';
    if (action === 'set_temp' || action === 'set_temperature') return '温度';
    if (action === 'set_mode') return '模式';
    if (action === 'set_fan' || action === 'set_speed') return '风速';
    if (action === 'set_swing') return '摆风';
    if (action === 'set_position') return '位置';
    if (action === 'stop') return '停止';
    if (action === 'scene_toggle') return '场景联动';
    return action;
  }

  private deviceCapabilityText(deviceId: string): string {
    const labels: string[] = [];
    for (const tool of this.mcpTools) {
      if (tool.deviceId !== deviceId) continue;
      const label = this.actionLabel(tool.action);
      if (labels.indexOf(label) < 0) labels.push(label);
    }
    return labels.length > 0 ? `AI可调用：${labels.join(' · ')}` : '后端未声明可调用动作';
  }

  private activeInterfaceState(): number {
    if (this.activeSection === 0) {
      if (this.logsComplete) return 2;
      return this.logsAvailable ? 1 : 0;
    }
    if (this.activeSection === 1) {
      if (this.devicesAvailable && this.stats.available) return 2;
      return this.devicesAvailable || this.stats.available ? 1 : 0;
    }
    const available = (this.sensorsAvailable ? 1 : 0) + (this.historyAvailable ? 1 : 0) + (this.stats.available ? 1 : 0);
    if (available === 3) return 2;
    return available > 0 ? 1 : 0;
  }

  private interfaceLabel(): string {
    const state = this.activeInterfaceState();
    if (state === 2) return '● 在线';
    if (state === 1) return '◐ 部分在线';
    return '○ 离线';
  }

  private panel(): string { return TacticalTheme.panel(this.isDark); }
  private raised(): string { return TacticalTheme.panelRaised(this.isDark); }
  private text(): string { return TacticalTheme.text(this.isDark); }
  private secondary(): string { return TacticalTheme.textSecondary(this.isDark); }
  private muted(): string { return TacticalTheme.textMuted(this.isDark); }
  private frameTone(): string { return TacticalTheme.border(this.isDark); }
  private accent(): string { return TacticalTheme.accent(this.isDark); }
  private danger(): string { return TacticalTheme.danger(this.isDark); }

  @Builder
  sectionSelector(index: number, label: string, icon: Resource) {
    Stack({ alignContent: Alignment.BottomStart }) {
      Row({ space: 8 }) {
        SymbolGlyph(icon)
          .fontSize(18)
          .fontColor([this.activeSection === index ? TacticalTheme.inverse(this.isDark) : this.accent()])
        Text(label)
          .fontSize(14)
          .fontFamily('HarmonyOS Sans SC')
          .fontWeight(FontWeight.Bold)
          .fontColor(this.activeSection === index ? TacticalTheme.inverse(this.isDark) : this.text())
      }
      .width('100%')
      .padding({ left: 12, bottom: 13 })
      .alignItems(VerticalAlign.Center)

      Column()
        .width(this.activeSection === index ? '100%' : 22)
        .height(4)
        .backgroundColor(this.activeSection === index ? TacticalTheme.inverse(this.isDark) : this.accent())
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    }
    .layoutWeight(1)
    .height(56)
    .backgroundColor(this.activeSection === index ? this.accent() : this.panel())
    .border({ width: 1, color: this.activeSection === index ? this.accent() : this.frameTone() })
    .opacity(this.pressedSection === index ? 0.7 : 1)
    .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    .onTouch((event: TouchEvent) => {
      if (event.type === TouchType.Down) this.pressedSection = index;
      else if (event.type === TouchType.Up || event.type === TouchType.Cancel) this.pressedSection = -1;
    })
    .onClick(() => this.selectSection(index))
  }

  @Builder
  metricTile(value: string, label: string, danger: boolean = false) {
    Column({ space: 4 }) {
      Column().width(24).height(2).backgroundColor(danger ? this.danger() : this.accent())
      Text(value)
        .fontSize(26)
        .fontWeight(FontWeight.Bold)
        .fontColor(danger ? this.danger() : this.text())
        .maxLines(1)
      Text(label)
        .fontSize(14)
        .fontColor(this.muted())
    }
    .layoutWeight(1)
    .height(88)
    .padding(10)
    .backgroundColor(this.raised())
    .border({ width: { bottom: 2 }, color: danger ? this.danger() : this.accent() })
    .alignItems(HorizontalAlign.Start)
    .justifyContent(FlexAlign.Center)
  }

  @Builder
  severityBar(label: string, count: number, color: string) {
    Column({ space: 5 }) {
      Row() {
        Text(label).fontSize(14).fontColor(this.secondary())
        Blank()
        Text(`${count}`).fontSize(14).fontWeight(FontWeight.Bold).fontColor(color)
      }
      .width('100%')
      Progress({ value: this.alerts.length > 0 ? count / this.alerts.length * 100 : 0,
        total: 100, type: ProgressType.Linear })
        .width('100%')
        .height(7)
        .color(color)
        .backgroundColor(TacticalTheme.panelMuted(this.isDark))
        .style({ strokeWidth: 7 })
    }
    .width('100%')
  }

  @Builder
  alertRow(alert: AlertMessage, important: boolean) {
    Row({ space: 10 }) {
      Column()
        .width(4)
        .height(48)
        .backgroundColor(important ? this.danger() : this.accent())
      Column({ space: 4 }) {
        Row({ space: 8 }) {
          Text(alert.source)
            .fontSize(14)
            .fontWeight(FontWeight.Bold)
            .fontColor(this.text())
            .maxLines(1)
          if (!alert.isRead) {
            Text('新')
              .fontSize(14)
              .fontWeight(FontWeight.Bold)
              .fontColor(important ? this.danger() : this.accent())
          }
        }
        Text(alert.content)
          .fontSize(14)
          .fontColor(this.secondary())
          .maxLines(2)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
      Text(this.alertTime(alert.timestamp))
        .fontSize(14)
        .fontColor(this.muted())
    }
    .width('100%')
    .constraintSize({ minHeight: 64 })
    .padding({ top: 8, bottom: 8, right: 10 })
    .backgroundColor(important ? TacticalTheme.dangerSoft(this.isDark) : this.raised())
    .border({ width: { left: important ? 3 : 1 }, color: important ? this.danger() : this.frameTone() })
    .alignItems(VerticalAlign.Center)
  }

  @Builder
  emptyState(text: string) {
    Column({ space: 8 }) {
      Text('暂无数据')
        .fontSize(18)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.muted())
      Text(text)
        .fontSize(14)
        .fontColor(this.secondary())
    }
    .width('100%')
    .height(112)
    .backgroundColor(this.panel())
    .border({ width: 1, color: this.frameTone(), style: BorderStyle.Dashed })
    .justifyContent(FlexAlign.Center)
    .alignItems(HorizontalAlign.Center)
  }

  @Builder
  disclosureHeader(title: string, subtitle: string, expanded: boolean, onClick: () => void) {
    Row({ space: 12 }) {
      Column().width(3).height(34).backgroundColor(this.accent())
      Column({ space: 3 }) {
        Text(title).fontSize(15).fontWeight(FontWeight.Bold).fontColor(this.text())
        Text(subtitle).fontSize(14).fontColor(this.muted()).maxLines(1)
      }.layoutWeight(1).alignItems(HorizontalAlign.Start)
      SymbolGlyph($r('sys.symbol.chevron_right'))
        .fontSize(17)
        .fontColor([this.accent()])
        .rotate({ angle: expanded ? 90 : 0 })
    }
    .width('100%')
    .height(58)
    .padding({ left: 12, right: 12 })
    .backgroundColor(this.panel())
    .border({ width: 1, color: this.frameTone() })
    .alignItems(VerticalAlign.Center)
    .onClick(onClick)
  }

  @Builder
  chartLegend(label: string, color: string) {
    Row({ space: 5 }) {
      Column().width(8).height(8).backgroundColor(color)
      Text(label).fontSize(14).fontColor(this.muted())
    }
  }

  @Builder
  analyzeButton(title: string, context: string) {
    Row({ space: 8 }) {
      SymbolGlyph($r('sys.symbol.paperplane_fill')).fontSize(16).fontColor([TacticalTheme.inverse(this.isDark)])
      Text('发送到明日家居分析').fontSize(14).fontWeight(FontWeight.Bold)
        .fontColor(TacticalTheme.inverse(this.isDark))
    }
    .height(44)
    .padding({ left: 14, right: 14 })
    .backgroundColor(this.accent())
    .alignItems(VerticalAlign.Center)
    .justifyContent(FlexAlign.Center)
    .onClick(() => this.onAnalyzeChart(title, context))
  }

  @Builder
  chartChoiceButton(title: string, mode: number, icon: Resource) {
    Row({ space: 8 }) {
      SymbolGlyph(icon).fontSize(17)
        .fontColor([(mode === 0 ? this.dailyExpanded : this.todayExpanded) ?
          TacticalTheme.inverse(this.isDark) : this.accent()])
      Text(title).fontSize(14).fontWeight(FontWeight.Bold)
        .fontColor((mode === 0 ? this.dailyExpanded : this.todayExpanded) ?
          TacticalTheme.inverse(this.isDark) : this.text())
      Blank()
      if (mode === 0 ? this.dailyExpanded : this.todayExpanded) {
        SymbolGlyph($r('sys.symbol.checkmark')).fontSize(14)
          .fontColor([TacticalTheme.inverse(this.isDark)])
      }
    }
    .layoutWeight(1)
    .height(48)
    .padding({ left: 12, right: 12 })
    .backgroundColor((mode === 0 ? this.dailyExpanded : this.todayExpanded) ? this.accent() : this.raised())
    .border({ width: 1, color: (mode === 0 ? this.dailyExpanded : this.todayExpanded) ?
      this.accent() : this.frameTone() })
    .alignItems(VerticalAlign.Center)
    .onClick(() => {
      if (mode === 0) {
        this.dailyExpanded = !this.dailyExpanded;
        if (this.dailyExpanded) this.todayExpanded = false;
      } else {
        this.todayExpanded = !this.todayExpanded;
        if (this.todayExpanded) this.dailyExpanded = false;
      }
    })
  }

  @Builder
  logChartChoices() {
    Column({ space: 8 }) {
      Row() {
        Text('日志图表').fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
        Blank()
        Text('每10秒读取真实统计').fontSize(14).fontColor(this.muted())
      }.width('100%')
      Row({ space: 8 }) {
        this.chartChoiceButton('七日统计', 0, $r('sys.symbol.bolt_fill'))
        this.chartChoiceButton('今日实时', 1, $r('sys.symbol.clock_fill'))
      }.width('100%')
    }.width('100%').alignItems(HorizontalAlign.Start)
  }

  @Builder
  dailyLogSection() {
    Column({ space: 10 }) {
      if (this.dailyExpanded) {
        if (this.dailyChartResponse.available && this.dailyCategories().length > 0) {
          Column({ space: 12 }) {
            Row({ space: 10 }) {
              this.chartLegend('请求', this.accent())
              this.chartLegend('对话', this.secondary())
              this.chartLegend('设备', this.muted())
            }.width('100%')
            Row({ space: 6 }) {
              ForEach(this.dailyCategories(), (label: string, index: number) => {
                Column({ space: 6 }) {
                  Row({ space: 2 }) {
                    Column().layoutWeight(1)
                      .height(this.backendBarHeight(this.chartNumber(this.dailySeries('请求数'), index)))
                      .backgroundColor(this.accent())
                    Column().layoutWeight(1)
                      .height(this.backendBarHeight(this.chartNumber(this.dailySeries('对话数'), index)))
                      .backgroundColor(this.secondary())
                    Column().layoutWeight(1)
                      .height(this.backendBarHeight(this.chartNumber(this.dailySeries('设备操作'), index)))
                      .backgroundColor(this.muted())
                  }.width('100%').height(86).alignItems(VerticalAlign.Bottom)
                  Text(label).fontSize(14).fontColor(this.muted()).maxLines(1)
                  Text(`请${this.chartNumber(this.dailySeries('请求数'), index)} · ` +
                    `对${this.chartNumber(this.dailySeries('对话数'), index)}`)
                    .fontSize(14).fontColor(this.secondary()).maxLines(1)
                }.layoutWeight(1).alignItems(HorizontalAlign.Center)
              }, (label: string) => label)
            }.width('100%').height(124).alignItems(VerticalAlign.Bottom)
            this.analyzeButton('最近七日日志趋势', this.dailyChartContext())
          }
          .width('100%').padding(14).backgroundColor(this.raised())
          .border({ width: { left: 1, right: 1, bottom: 1 }, color: this.frameTone() })
        } else {
          this.emptyState('后端图表接口暂无七日统计')
        }
      }
    }.width('100%')
  }

  @Builder
  todayMetricRow(label: string, value: number, max: number, color: string) {
    Column({ space: 5 }) {
      Row() {
        Text(label).fontSize(14).fontColor(this.secondary())
        Blank()
        Text(`${value}`).fontSize(14).fontWeight(FontWeight.Bold).fontColor(color)
      }.width('100%')
      Progress({ value: max > 0 ? value / max * 100 : 0, total: 100, type: ProgressType.Linear })
        .width('100%').height(6).color(color).backgroundColor(TacticalTheme.panelMuted(this.isDark))
        .style({ strokeWidth: 6 })
    }.width('100%')
  }

  @Builder
  realtimeTile(value: string, label: string) {
    Column({ space: 3 }) {
      Text(value).fontSize(18).fontWeight(FontWeight.Bold).fontColor(this.text())
      Text(label).fontSize(14).fontColor(this.muted())
    }.layoutWeight(1).height(58).justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Start)
      .padding({ left: 10 }).backgroundColor(this.panel())
  }

  @Builder
  todayLogSection() {
    Column({ space: 10 }) {
      if (this.todayExpanded) {
        if (this.todayChartResponse.available && this.todayGaugeData().date.length > 0) {
          Column({ space: 10 }) {
            Text(this.todayGaugeData().date).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.accent())
              .width('100%')
            this.todayMetricRow('接口请求（含轮询）', this.todayGaugeData().totalRequests,
              Math.max(1, this.todayGaugeData().totalRequests), this.accent())
            this.todayMetricRow('对话（双向）', this.todayGaugeData().totalChat,
              Math.max(1, this.todayGaugeData().totalRequests), this.secondary())
            this.todayMetricRow('设备操作', this.todayGaugeData().totalDeviceOps,
              Math.max(1, this.todayGaugeData().totalRequests), this.muted())
            this.todayMetricRow('安全事件', this.todayGaugeData().totalSecurityEvents,
              Math.max(1, this.todayGaugeData().totalRequests), this.danger())
            Row({ space: 6 }) {
              this.realtimeTile(`${this.todayGaugeData().onlineDevices}/${this.todayGaugeData().totalDevices}`, '在线设备')
              this.realtimeTile(`${this.todayGaugeData().onlineSensors}/${this.todayGaugeData().totalSensors}`, '在线传感器')
            }.width('100%')
            this.analyzeButton('今日日志与实时状态', this.todayChartContext())
          }.width('100%').padding(14).backgroundColor(this.raised())
            .border({ width: { left: 1, right: 1, bottom: 1 }, color: this.frameTone() })
        } else {
          this.emptyState('后端图表接口暂无今日实时数据')
        }
      }
    }.width('100%')
  }

  @Builder
  filterChip(label: string, value: number, sourceFilter: boolean) {
    Stack({ alignContent: Alignment.Center }) {
      Row({ space: 4 }) {
        if ((sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value) {
          SymbolGlyph($r('sys.symbol.checkmark')).fontSize(14)
            .fontColor([TacticalTheme.inverse(this.isDark)])
        }
        Text(label).fontSize(14)
          .fontWeight((sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value ?
            FontWeight.Bold : FontWeight.Regular)
          .fontColor((sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value ?
            TacticalTheme.inverse(this.isDark) : this.secondary())
      }.justifyContent(FlexAlign.Center)
      Column()
        .width((sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value ? '100%' : 0)
        .height(3)
        .backgroundColor(TacticalTheme.inverse(this.isDark))
        .position({ x: 0, y: 31 })
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    }
    .height(38)
    .layoutWeight(1)
    .backgroundColor((sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value ?
      this.accent() : this.raised())
    .border({
      width: (sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value ? 2 : 1,
      color: (sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value ?
        this.accent() : this.frameTone()
    })
    .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    .accessibilityText(`${label}${(sourceFilter ? this.operationSourceFilter : this.operationResultFilter) === value ? '，已选择' : ''}`)
    .onClick(() => {
      if (sourceFilter) this.operationSourceFilter = value;
      else this.operationResultFilter = value;
    })
  }

  @Builder
  aiConversationRow(log: AiConversationLog) {
    Row({ space: 10 }) {
      Column().width(3).height(38)
        .backgroundColor(log.role === 'user' ? this.secondary() : this.accent())
      Column({ space: 4 }) {
        Text(log.role === 'user' ? '用户' : '明日家居')
          .fontSize(14).fontWeight(FontWeight.Bold)
          .fontColor(log.role === 'user' ? this.secondary() : this.accent())
        Text(log.content).fontSize(14).lineHeight(17).fontColor(this.text()).width('100%')
          .copyOption(CopyOptions.LocalDevice)
      }.layoutWeight(1).alignItems(HorizontalAlign.Start)
    }
    .width('100%').padding(10).backgroundColor(this.raised())
    .border({ width: { bottom: 1 }, color: this.frameTone() })
    .alignItems(VerticalAlign.Top)
  }

  @Builder
  operationRow(operation: OperationLogRecord) {
    Column({ space: 8 }) {
      Row({ space: 8 }) {
        Column().width(3).height(34).backgroundColor(
          operation.result === 'ok' || operation.result === 'success' ? this.accent() : this.danger())
        Column({ space: 3 }) {
          Text(`${operation.deviceId} · ${this.actionLabel(operation.action)}`)
            .fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.text()).maxLines(1)
          Text(`${operation.source} · ${this.operationTimeText(operation)}`)
            .fontSize(14).fontColor(this.muted()).maxLines(1)
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
        Text(operation.result === 'ok' || operation.result === 'success' ? '成功' : '失败')
          .fontSize(14).fontWeight(FontWeight.Bold)
          .fontColor(operation.result === 'ok' || operation.result === 'success' ? this.accent() : this.danger())
        SymbolGlyph($r('sys.symbol.chevron_right')).fontSize(14).fontColor([this.muted()])
          .rotate({ angle: this.expandedOperationKey === operation.key ? 90 : 0 })
      }.width('100%').alignItems(VerticalAlign.Center)
      if (this.expandedOperationKey === operation.key) {
        Column({ space: 5 }) {
          Text(`动作：${operation.action}`).fontSize(14).fontColor(this.secondary())
          Text(`参数：${operation.params}`).fontSize(14).fontColor(this.secondary()).copyOption(CopyOptions.LocalDevice)
          Text(`来源：${operation.source}${operation.sceneId ? ` · 场景 ${operation.sceneId}` : ''}`)
            .fontSize(14).fontColor(this.secondary())
          Text(`时间：${operation.timestamp || this.operationTimeText(operation)}`).fontSize(14).fontColor(this.secondary())
        }.width('100%').padding({ left: 11, top: 6 }).alignItems(HorizontalAlign.Start)
      }
    }
    .width('100%').padding(10).backgroundColor(this.raised())
    .border({ width: { bottom: 1 }, color: this.frameTone() })
    .onClick(() => {
      this.expandedOperationKey = this.expandedOperationKey === operation.key ? '' : operation.key;
    })
  }

  @Builder
  operationsSection() {
    Column({ space: 10 }) {
      this.disclosureHeader('操作日志详情', `每10秒更新 · 数据库共 ${this.operationFeed.total} 条`,
        this.operationsExpanded, () => { this.operationsExpanded = !this.operationsExpanded; })
      if (this.operationsExpanded) {
        Column({ space: 10 }) {
          Row({ space: 5 }) {
            this.filterChip('全部', 0, false)
            this.filterChip('成功', 1, false)
            this.filterChip('失败', 2, false)
          }.width('100%')
          Row({ space: 5 }) {
            this.filterChip('全部来源', 0, true)
            this.filterChip('接口', 1, true)
            this.filterChip('场景', 2, true)
            this.filterChip('本地', 3, true)
          }.width('100%')
          Text(`当前：${this.operationResultFilter === 0 ? '全部结果' :
            this.operationResultFilter === 1 ? '成功' : '失败'} / ${this.operationSourceFilter === 0 ? '全部来源' :
            this.operationSourceFilter === 1 ? '接口' : this.operationSourceFilter === 2 ? '场景' : '本地'} · ` +
            `显示 ${this.filteredOperations().length} 条`)
            .fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.accent()).width('100%')
          if (this.filteredOperations().length > 0) {
            ForEach(this.filteredOperations(), (operation: OperationLogRecord) => {
              this.operationRow(operation)
            }, (operation: OperationLogRecord) => operation.key)
          } else {
            this.emptyState(this.operationFeed.available ? '当前筛选条件没有记录' : '操作日志接口不可达')
          }
        }.width('100%').padding(10).backgroundColor(this.panel())
          .border({ width: { left: 1, right: 1, bottom: 1 }, color: this.frameTone() })
      }
    }.width('100%')
  }

  @Builder
  collectedLogsSection() {
    Column({ space: 10 }) {
      this.disclosureHeader('详细日志收集',
        `默认收起 · 对话 ${this.aiConversationFeed.total} · 操作 ${this.operationFeed.total} · 安全 ${this.securityStats.total}`,
        this.detailedLogsExpanded, () => { this.detailedLogsExpanded = !this.detailedLogsExpanded; })
      if (this.detailedLogsExpanded) {
        Column({ space: 10 }) {
          this.disclosureHeader('AI 对话日志',
            this.aiConversationFeed.available ?
              `数据库共 ${this.aiConversationFeed.total} 条 · 显示最新 ${this.aiConversationFeed.logs.length} 条 · 每10秒更新` :
              '后端对话日志接口不可达',
            this.aiLogsExpanded, () => { this.aiLogsExpanded = !this.aiLogsExpanded; })
          if (this.aiLogsExpanded) {
            Column({ space: 0 }) {
              if (this.aiConversationFeed.logs.length > 0) {
                ForEach(this.aiConversationFeed.logs, (log: AiConversationLog) => {
                  this.aiConversationRow(log)
                }, (log: AiConversationLog) => log.key)
              } else {
                this.emptyState(this.aiConversationFeed.available ? '后端没有返回最近对话' : 'AI 对话日志接口不可达')
              }
            }.width('100%')
          }

          this.operationsSection()

          this.disclosureHeader('重点危险信息', `${this.dangerAlerts().length} 条 · 最多显示最新20条`,
            this.dangerLogsExpanded, () => { this.dangerLogsExpanded = !this.dangerLogsExpanded; })
          if (this.dangerLogsExpanded) {
            Column({ space: 8 }) {
              if (this.dangerAlerts().length > 0) {
                ForEach(this.dangerAlerts().slice(0, 20), (alert: AlertMessage) => {
                  this.alertRow(alert, true)
                }, (alert: AlertMessage) => alert.id)
              } else {
                this.emptyState(this.logsAvailable ? '暂无危险或警告日志' : '日志与安全事件接口不可达')
              }
            }.width('100%')
          }

          this.disclosureHeader('普通信息', `${this.normalAlerts().length} 条 · 最多显示最新20条`,
            this.normalLogsExpanded, () => { this.normalLogsExpanded = !this.normalLogsExpanded; })
          if (this.normalLogsExpanded) {
            Column({ space: 8 }) {
              if (this.normalAlerts().length > 0) {
                ForEach(this.normalAlerts().slice(0, 20), (alert: AlertMessage) => {
                  this.alertRow(alert, false)
                }, (alert: AlertMessage) => alert.id)
              } else {
                this.emptyState(this.logsAvailable ? '暂无普通日志' : '日志接口不可达')
              }
            }.width('100%')
          }
        }.width('100%')
      }
    }.width('100%')
  }

  @Builder
  logsPage() {
    Column({ space: 14 }) {
      Row({ space: 8 }) {
        this.metricTile(`${this.totalLogCount()}`, '数据库日志')
        this.metricTile(`${this.importantLogCount()}`, '安全重点', true)
        this.metricTile(`${this.alerts.length}`, '当前显示')
      }
      .width('100%')

      this.logChartChoices()
      this.dailyLogSection()
      this.todayLogSection()

      Column({ space: 10 }) {
        this.severityBar('危险', this.levelCount('danger'), this.danger())
        this.severityBar('警告', this.levelCount('warning'), this.accent())
        this.severityBar('普通', this.levelCount('info'), this.muted())
      }
      .width('100%')
      .padding(14)
      .backgroundColor(this.panel())
      .border({ width: { bottom: 1 }, color: this.frameTone() })

      this.collectedLogsSection()
    }
    .width('100%')
  }

  @Builder
  deviceRow(device: Device) {
    Column({ space: 9 }) {
      Row({ space: 10 }) {
        Stack() {
          Column().width(36).height(36).backgroundColor(TacticalTheme.panelMuted(this.isDark))
          SymbolGlyph(device.icon).fontSize(20).fontColor([device.status === DeviceStatus.OFFLINE ? this.muted() : this.accent()])
        }
        .width(36).height(36)
        Column({ space: 3 }) {
          Text(device.name).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.text()).maxLines(1)
          Text(device.room).fontSize(14).fontColor(this.muted()).maxLines(1)
          Text(this.deviceCapabilityText(device.id)).fontSize(14).fontColor(this.accent()).maxLines(2)
        }
        .layoutWeight(1)
        .alignItems(HorizontalAlign.Start)
        Row({ space: 5 }) {
          Circle({ width: 7, height: 7 }).fill(device.status === DeviceStatus.OFFLINE ? TacticalTheme.offline(this.isDark) : this.accent())
          Text(device.status === DeviceStatus.OFFLINE ? '离线' : '在线')
            .fontSize(14)
            .fontWeight(FontWeight.Bold)
            .fontColor(device.status === DeviceStatus.OFFLINE ? this.muted() : this.accent())
        }
      }
      .width('100%')
      Row() {
        Column({ space: 2 }) {
          Text('累计在线').fontSize(14).fontColor(this.muted())
          Text(this.durationText(device.uptimeSeconds)).fontSize(14).fontColor(this.secondary())
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
        Column({ space: 2 }) {
          Text('最近在线').fontSize(14).fontColor(this.muted())
          Text(this.timeText(device.lastSeen || device.onlineSince)).fontSize(14).fontColor(this.secondary())
        }.layoutWeight(1).alignItems(HorizontalAlign.End)
      }
      .width('100%')
      if (this.uptimeProgress(device) >= 0) {
        Progress({ value: this.uptimeProgress(device),
          total: 100, type: ProgressType.Linear })
          .width('100%').height(5).color(this.accent()).backgroundColor(TacticalTheme.panelMuted(this.isDark)).style({ strokeWidth: 5 })
      }
    }
    .width('100%')
    .padding(12)
    .backgroundColor(this.raised())
    .border({ width: { left: 3 }, color: device.status === DeviceStatus.OFFLINE ? this.frameTone() : this.accent() })
  }

  @Builder
  areaRow(area: BackendAreaStat) {
    Row({ space: 10 }) {
      Column().width(3).height(38).backgroundColor(area.online ? this.accent() : TacticalTheme.offline(this.isDark))
      Column({ space: 3 }) {
        Text(area.name).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.text())
        Text(area.ip || '地址未上报').fontSize(14).fontColor(this.muted())
      }.layoutWeight(1).alignItems(HorizontalAlign.Start)
      Column({ space: 3 }) {
        Text(area.online ? '在线' : '离线').fontSize(14).fontWeight(FontWeight.Bold).fontColor(area.online ? this.accent() : this.muted())
        Text(this.timeText(area.lastSeen)).fontSize(14).fontColor(this.secondary())
      }.alignItems(HorizontalAlign.End)
    }
    .width('100%').height(58).padding({ left: 10, right: 10 })
    .backgroundColor(this.panel()).border({ width: { bottom: 1 }, color: this.frameTone() }).alignItems(VerticalAlign.Center)
  }

  @Builder
  devicesPage() {
    Column({ space: 14 }) {
      Row({ space: 12 }) {
        Stack() {
          Progress({ value: 100, total: 100, type: ProgressType.Ring })
            .width(92).height(92).color(TacticalTheme.panelMuted(this.isDark)).style({ strokeWidth: 7 })
          Progress({ value: Math.max(0, this.deviceRate()), total: 100, type: ProgressType.Ring })
            .width(92).height(92).color(this.accent()).style({ strokeWidth: 7 })
          Column({ space: 0 }) {
            Text(this.deviceRate() >= 0 ? `${Math.round(this.deviceRate())}` : '--')
              .fontSize(24).fontWeight(FontWeight.Bold).fontColor(this.text())
            Text('%').fontSize(14).fontColor(this.muted())
          }
        }.width(92).height(92)
        Column({ space: 7 }) {
          Text('设备在线状态').fontSize(18).fontWeight(FontWeight.Bold).fontColor(this.text())
          Text(this.deviceSummary())
            .fontSize(14).fontColor(this.secondary())
          Text('在线时长与最近在线仅展示后端上报值').fontSize(14).fontColor(this.muted())
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
      }
      .width('100%').padding(14).backgroundColor(this.panel()).border({ width: { bottom: 1 }, color: this.frameTone() }).alignItems(VerticalAlign.Center)

      if (this.stats.areas.length > 0) {
        Column({ space: 7 }) {
          Text('区域链路').fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
          ForEach(this.stats.areas, (area: BackendAreaStat) => { this.areaRow(area) }, (area: BackendAreaStat) => area.key)
        }.width('100%').alignItems(HorizontalAlign.Start)
      }

      Column({ space: 8 }) {
        Text('设备明细').fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
        if (this.devices.length > 0) {
          ForEach(this.devices, (device: Device) => { this.deviceRow(device) }, (device: Device) => device.id)
        } else {
          this.emptyState(this.devicesAvailable ? '设备列表为空' : '暂时无法读取设备')
        }
      }.width('100%').alignItems(HorizontalAlign.Start)
    }
    .width('100%')
  }

  @Builder
  historyChart(title: string, current: string, values: number[], color: string) {
    Column({ space: 10 }) {
      Row() {
        Column({ space: 2 }) {
          Text(title).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.secondary())
          Text(values.length > 0 ? `${values.length} 个真实采样点` : '暂无历史采样').fontSize(14).fontColor(this.muted())
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
        Text(current).fontSize(26).fontWeight(FontWeight.Bold).fontColor(color)
      }.width('100%').alignItems(VerticalAlign.Center)

      if (values.length > 0) {
        Row({ space: 3 }) {
          ForEach(this.chartValues(values), (value: number, index: number) => {
            Column() {
              Column().width('100%')
                .height(this.barHeight(value, this.chartValues(values)))
                .backgroundColor(color)
                .opacity(0.38 + index / Math.max(1, this.chartValues(values).length - 1) * 0.62)
            }.layoutWeight(1).height(104).justifyContent(FlexAlign.End)
          }, (_: number, index: number) => `${index}`)
        }.width('100%').height(104).alignItems(VerticalAlign.Bottom)
        Row() {
          Text(this.historyLabels.length > 0 ? this.historyLabels[0] : '早').fontSize(14).fontColor(this.muted())
          Blank()
          Text(this.historyLabels.length > 0 ? this.historyLabels[this.historyLabels.length - 1] : '现在').fontSize(14).fontColor(this.muted())
        }.width('100%')
      } else {
        this.emptyState(`${title}暂无真实历史数据`)
      }
    }
    .width('100%').padding(14).backgroundColor(this.raised()).border({ width: { bottom: 1 }, color: this.frameTone() })
  }

  @Builder
  telemetryRow(stat: BackendStatItem) {
    Column({ space: 7 }) {
      Row() {
        Column({ space: 2 }) {
          Text(stat.label).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.text())
          Text(stat.detail).fontSize(14).fontColor(this.muted()).maxLines(1)
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
        Text(stat.value).fontSize(14).fontWeight(FontWeight.Bold).fontColor(stat.online ? this.accent() : this.muted())
      }.width('100%')
      if (stat.progress >= 0) {
        Progress({ value: stat.progress, total: 100, type: ProgressType.Linear })
          .width('100%').height(5).color(stat.online ? this.accent() : this.muted())
          .backgroundColor(TacticalTheme.panelMuted(this.isDark)).style({ strokeWidth: 5 })
      }
    }
    .width('100%').padding(10).backgroundColor(this.panel()).border({ width: { bottom: 1 }, color: this.frameTone() })
  }

  @Builder
  environmentPage() {
    Column({ space: 14 }) {
      Row({ space: 8 }) {
        this.metricTile(this.currentText(SensorType.TEMPERATURE, '°C'), '当前温度')
        this.metricTile(this.currentText(SensorType.HUMIDITY, '%RH'), '当前湿度')
      }.width('100%')

      Column({ space: 14 }) {
        this.historyChart('温度趋势', this.currentText(SensorType.TEMPERATURE, '°C'), this.tempHistory, this.accent())
        this.historyChart('湿度趋势', this.currentText(SensorType.HUMIDITY, '%RH'), this.humidHistory,
          TacticalTheme.humidity(this.isDark))
      }
      .width('100%')

      Column({ space: 8 }) {
        Text('室内状态矩阵').fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
        if (this.visibleEnvironmentStats().length > 0) {
          ForEach(this.visibleEnvironmentStats(), (stat: BackendStatItem) => {
            this.telemetryRow(stat)
          }, (stat: BackendStatItem) => stat.key)
        } else {
          this.emptyState(this.stats.available ? '后端没有返回室内状态统计' : '环境统计接口不可达，未生成默认数据')
        }
      }.width('100%').alignItems(HorizontalAlign.Start)
    }
    .width('100%')
  }

  @Builder
  loadingState() {
    Row({ space: 12 }) {
      SymbolGlyph($r('sys.symbol.clock_fill'))
        .fontSize(20)
        .fontColor([this.accent()])
      Column({ space: 4 }) {
        Text('正在读取数据')
          .fontSize(15)
          .fontWeight(FontWeight.Bold)
          .fontColor(this.text())
        Text('日志、设备和环境信息将按后端返回结果展示')
          .fontSize(14)
          .fontColor(this.muted())
      }
      .alignItems(HorizontalAlign.Start)
    }
    .width('100%')
    .height(88)
    .padding({ left: 16, right: 16 })
    .backgroundColor(this.panel())
    .border({ width: { left: 3, bottom: 1 }, color: this.frameTone() })
    .alignItems(VerticalAlign.Center)
  }

  build() {
    Column({ space: 14 }) {
      Row() {
        Column({ space: 3 }) {
          Text('数据管理').fontSize(26).fontFamily('HarmonyOS Sans SC')
            .fontWeight(FontWeight.Bolder).fontColor(this.text())
          Text('日志、设备与环境').fontSize(14).fontColor(this.muted())
        }.alignItems(HorizontalAlign.Start)
        Blank()
        Text(this.interfaceLabel()).fontSize(14).fontWeight(FontWeight.Bold)
          .fontColor(this.activeInterfaceState() > 0 ? this.accent() : this.muted())
      }
      .width('100%')
      .height(66)
      .alignItems(VerticalAlign.Center)

      Row({ space: 6 }) {
        this.sectionSelector(0, '日志', $r('sys.symbol.clock_fill'))
        this.sectionSelector(1, '设备', $r('sys.symbol.house_fill'))
        this.sectionSelector(2, '环境', $r('sys.symbol.thermometer'))
      }.width('100%')

      if (this.isLoading) {
        this.loadingState()
      } else {
        Column() {
          if (this.activeSection === 0) {
            this.logsPage()
          } else if (this.activeSection === 1) {
            this.devicesPage()
          } else {
            this.environmentPage()
          }
        }
        .width('100%')
      }
    }
    .width('100%')
    .padding({ left: TacticalSpace.PAGE, right: TacticalSpace.PAGE, top: 8, bottom: 104 })
  }
}
