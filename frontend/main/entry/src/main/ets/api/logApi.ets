/** 将数据库操作、安全事件和鉴权状态规范成日志统计页数据。 */
import { Http } from './http';
import { AlertMessage } from './types';
import { normalizeAlert } from './adapter';

interface OperationResponse {
  id?: string;
  device_id?: string;
  action?: string;
  params?: string;
  result?: string;
  source?: string;
  scene_id?: string | null;
  timestamp?: string | number;
}

interface OperationListResponse {
  operations?: OperationResponse[];
  total?: number;
  limit?: number;
}

interface DailyLogResponse {
  daily?: DailyLogRecord[];
}

interface TodayLogResponse {
  today?: DailyLogRecord;
  realtime?: RealtimeLogState;
}

interface AiContextResponse {
  context?: string;
}

interface ChatHistoryMessage {
  id?: number | string;
  role?: string;
  content?: string;
}

interface ChatHistoryResponse {
  messages?: ChatHistoryMessage[];
  total?: number;
  limit?: number;
}

interface RawChartAxis {
  type?: string;
  data?: string[];
}

interface RawChartSeries {
  name?: string;
  type?: string;
  data?: number[];
}

interface RawGaugeData {
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

interface RawLogChart {
  id?: string;
  title?: string;
  type?: string;
  xAxis?: RawChartAxis;
  series?: RawChartSeries[];
  data?: RawGaugeData;
}

interface RawLogChartResponse {
  chart_type?: string;
  keyword?: string;
  kimi_used?: boolean;
  days?: number;
  charts?: RawLogChart[];
}

interface AlertListResponse {
  alerts?: Record<string, Object>[];
  total?: number;
}

interface SecurityEventResponse {
  id?: number | string;
  ruleId?: string;
  rule_id?: string;
  severity?: string;
  category?: string;
  inputText?: string;
  input_text?: string;
  matchedText?: string;
  matched_text?: string;
  reason?: string;
  source?: string;
  blocked?: boolean;
  timestamp?: string | number;
}

interface SecurityEventsResponse {
  total?: number;
  events?: SecurityEventResponse[];
}

interface SeverityCountResponse {
  Critical?: number;
  High?: number;
  Medium?: number;
  Low?: number;
}

interface SecurityStatsResponse {
  today?: number;
  total?: number;
  bySeverity?: SeverityCountResponse;
  by_severity?: SeverityCountResponse;
  total_rules?: number;
  critical_rules?: number;
  high_rules?: number;
  medium_rules?: number;
}

interface AuthStatusResponse {
  enableAuth?: boolean;
  enable_auth?: boolean;
  doorPasswordRequired?: boolean;
  door_password_required?: boolean;
  sharedKeySet?: boolean;
  shared_key_set?: boolean;
  authAlgorithm?: string;
  auth_algorithm?: string;
  doorPasswordAlgorithm?: string;
  door_password_algorithm?: string;
}

export interface SecurityLogStats {
  available: boolean;
  today: number;
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface EdgeAuthStatus {
  available: boolean;
  enableAuth: boolean;
  doorPasswordRequired: boolean;
  sharedKeySet: boolean;
  authAlgorithm: string;
  doorPasswordAlgorithm: string;
}

export interface LogSnapshot {
  available: boolean;
  complete: boolean;
  alerts: AlertMessage[];
  securityStats: SecurityLogStats;
  authStatus: EdgeAuthStatus;
}

export interface DailyLogRecord {
  id?: number;
  log_date: string;
  total_requests: number;
  total_chat: number;
  total_device_ops: number;
  total_security_events: number;
  devices_online_peak: number;
  sensors_active: number;
  summary_json?: Object | string | null;
  created_at?: string;
}

export interface RealtimeLogState {
  online_devices: number;
  total_devices: number;
  online_sensors: number;
  total_sensors: number;
  ws_clients: number;
  mqtt_clients: number;
}

export interface TodayLogSnapshot {
  available: boolean;
  today: DailyLogRecord | null;
  realtime: RealtimeLogState | null;
}

export interface OperationLogRecord {
  key: string;
  deviceId: string;
  action: string;
  params: string;
  result: string;
  source: string;
  sceneId: string;
  timestamp: string;
  timestampMs: number;
}

export interface OperationFeed {
  available: boolean;
  total: number;
  limit: number;
  operations: OperationLogRecord[];
}

export interface AiConversationLog {
  key: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface AiConversationFeed {
  available: boolean;
  source: string;
  total: number;
  logs: AiConversationLog[];
}

export interface LogChartSeries {
  name: string;
  type: string;
  data: number[];
}

export interface LogGaugeData {
  date: string;
  totalRequests: number;
  totalChat: number;
  totalDeviceOps: number;
  totalSecurityEvents: number;
  onlineDevices: number;
  totalDevices: number;
  onlineSensors: number;
  totalSensors: number;
}

export interface LogChart {
  id: string;
  title: string;
  type: string;
  categories: string[];
  series: LogChartSeries[];
  gauge: LogGaugeData | null;
}

export interface LogChartResponse {
  available: boolean;
  chartType: string;
  keyword: string;
  kimiUsed: boolean;
  days: number;
  charts: LogChart[];
  raw: string;
}

function emptyGauge(): LogGaugeData {
  return {
    date: '', totalRequests: 0, totalChat: 0, totalDeviceOps: 0, totalSecurityEvents: 0,
    onlineDevices: 0, totalDevices: 0, onlineSensors: 0, totalSensors: 0
  };
}

function normalizeGauge(raw: RawGaugeData | undefined): LogGaugeData | null {
  if (!raw || typeof raw.date !== 'string') return null;
  const gauge = emptyGauge();
  gauge.date = raw.date;
  gauge.totalRequests = raw.total_requests || 0;
  gauge.totalChat = raw.total_chat || 0;
  gauge.totalDeviceOps = raw.total_device_ops || 0;
  gauge.totalSecurityEvents = raw.total_security_events || 0;
  gauge.onlineDevices = raw.online_devices || 0;
  gauge.totalDevices = raw.total_devices || 0;
  gauge.onlineSensors = raw.online_sensors || 0;
  gauge.totalSensors = raw.total_sensors || 0;
  return gauge;
}

function normalizeChart(raw: RawLogChart): LogChart {
  const series: LogChartSeries[] = [];
  for (const item of raw.series || []) {
    series.push({ name: item.name || '', type: item.type || '', data: item.data || [] });
  }
  return {
    id: raw.id || '', title: raw.title || '', type: raw.type || '',
    categories: raw.xAxis?.data || [], series: series, gauge: normalizeGauge(raw.data)
  };
}

function parseAiContext(context: string): AiConversationLog[] {
  const result: AiConversationLog[] = [];
  const lines = context.split('\n');
  let started = false;
  let role: 'user' | 'assistant' = 'user';
  let content = '';
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === '最近对话:') {
      started = true;
      continue;
    }
    if (!started) continue;
    if (line.startsWith('用户:')) {
      if (content.length > 0) result.push({ key: `ai_${result.length}`, role: role, content: content });
      role = 'user';
      content = line.substring(3).trim();
    } else if (line.startsWith('助手:')) {
      if (content.length > 0) result.push({ key: `ai_${result.length}`, role: role, content: content });
      role = 'assistant';
      content = line.substring(3).trim();
    } else if (line.length > 0 && content.length > 0) {
      content += `\n${line}`;
    }
  }
  if (content.length > 0) result.push({ key: `ai_${result.length}`, role: role, content: content });
  return result;
}

function operationTime(value: string | number | undefined): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const normalized = value.replace(' ', 'T');
    const hasTimezone = normalized.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(normalized);
    const parsed = Date.parse(hasTimezone ? normalized : normalized + 'Z');
    if (parsed === parsed) return parsed;
  }
  return 0;
}

function operationMessage(raw: OperationResponse, index: number): AlertMessage {
  const timestamp = operationTime(raw.timestamp);
  const result = raw.result || 'unknown';
  const action = raw.action || 'operation';
  const device = raw.device_id || raw.source || '系统';
  return {
    id: raw.id || `operation_${device}_${timestamp}_${index}`,
    source: device,
    content: `${action} / ${result}`,
    level: result === 'ok' || result === 'success' ? 'info' : 'warning',
    timestamp: timestamp,
    isRead: true
  };
}

function normalizeOperation(raw: OperationResponse, index: number): OperationLogRecord {
  const timestampMs = operationTime(raw.timestamp);
  const timestamp = typeof raw.timestamp === 'string' ? raw.timestamp : '';
  const deviceId = raw.device_id || 'system';
  const action = raw.action || 'operation';
  return {
    key: raw.id || `${deviceId}_${action}_${timestampMs}_${index}`,
    deviceId: deviceId,
    action: action,
    params: raw.params || '{}',
    result: raw.result || 'unknown',
    source: raw.source || 'unknown',
    sceneId: raw.scene_id || '',
    timestamp: timestamp,
    timestampMs: timestampMs
  };
}

function emptyDailyRecord(): DailyLogRecord {
  return {
    log_date: '', total_requests: 0, total_chat: 0, total_device_ops: 0,
    total_security_events: 0, devices_online_peak: 0, sensors_active: 0
  };
}

function validDailyRecord(record: DailyLogRecord | undefined): boolean {
  return record !== undefined && typeof record.log_date === 'string' &&
    typeof record.total_requests === 'number' && typeof record.total_chat === 'number' &&
    typeof record.total_device_ops === 'number' && typeof record.total_security_events === 'number';
}

function securityLevel(value: string | undefined): 'info' | 'warning' | 'danger' {
  const level = (value || '').toLowerCase();
  if (level === 'critical' || level === 'high') return 'danger';
  if (level === 'medium') return 'warning';
  return 'info';
}

function securityMessage(raw: SecurityEventResponse, index: number): AlertMessage {
  const timestamp = operationTime(raw.timestamp);
  const rule = raw.ruleId || raw.rule_id || raw.category || 'security';
  const matchedText = raw.matchedText || raw.matched_text || '';
  const detail = matchedText ? `${raw.reason || '安全事件'} / 命中 ${matchedText}` : raw.reason || '安全事件';
  return {
    id: `security_${raw.id === undefined ? index : raw.id}`,
    source: raw.source || raw.category || '安全护栏',
    content: `[${rule}] ${detail}`,
    level: securityLevel(raw.severity),
    timestamp: timestamp,
    isRead: raw.blocked !== true
  };
}

function isToday(timestamp: number): boolean {
  if (timestamp <= 0) return false;
  const date = new Date(timestamp);
  const now = new Date();
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
}

function statsFromEvents(events: SecurityEventResponse[]): SecurityLogStats {
  let today = 0;
  let critical = 0;
  let high = 0;
  let medium = 0;
  let low = 0;
  for (const event of events) {
    if (isToday(operationTime(event.timestamp))) today++;
    const severity = (event.severity || '').toLowerCase();
    if (severity === 'critical') critical++;
    else if (severity === 'high') high++;
    else if (severity === 'medium') medium++;
    else low++;
  }
  return {
    available: true,
    today: today,
    total: events.length,
    critical: critical,
    high: high,
    medium: medium,
    low: low
  };
}

function emptySecurityStats(): SecurityLogStats {
  return { available: false, today: 0, total: 0, critical: 0, high: 0, medium: 0, low: 0 };
}

function emptyAuthStatus(): EdgeAuthStatus {
  return {
    available: false,
    enableAuth: false,
    doorPasswordRequired: false,
    sharedKeySet: false,
    authAlgorithm: '',
    doorPasswordAlgorithm: ''
  };
}

export class LogApi {
  static async getChart(type: string, days: number = 7): Promise<LogChartResponse> {
    const safeDays = Math.max(1, Math.min(30, Math.floor(days)));
    const empty: LogChartResponse = {
      available: false, chartType: '', keyword: type, kimiUsed: false, days: safeDays, charts: [], raw: ''
    };
    const text = await Http.get(`/api/log/chart?type=${encodeURIComponent(type)}&days=${safeDays}`);
    if (!text) return empty;
    try {
      const data = JSON.parse(text) as RawLogChartResponse;
      const charts: LogChart[] = [];
      for (const raw of data.charts || []) charts.push(normalizeChart(raw));
      return {
        available: charts.length > 0,
        chartType: data.chart_type || '',
        keyword: data.keyword || type,
        kimiUsed: data.kimi_used || false,
        days: data.days || safeDays,
        charts: charts,
        raw: text
      };
    } catch (e) {
      return empty;
    }
  }

  static async getAiConversationFeed(limit: number = 20): Promise<AiConversationFeed> {
    const safeLimit = Math.max(2, Math.min(50, Math.floor(limit)));
    const source = '/api/chat/history';
    const empty: AiConversationFeed = { available: false, source: source, total: 0, logs: [] };
    const text = await Http.get(`/api/chat/history?limit=${safeLimit}`);
    if (!text) return empty;
    try {
      const data = JSON.parse(text) as ChatHistoryResponse;
      const logs: AiConversationLog[] = [];
      for (const message of data.messages || []) {
        if ((message.role !== 'user' && message.role !== 'assistant') || typeof message.content !== 'string') continue;
        logs.push({
          key: `chat_${message.id === undefined ? logs.length : message.id}`,
          role: message.role as 'user' | 'assistant',
          content: message.content
        });
      }
      return {
        available: true,
        source: source,
        total: typeof data.total === 'number' ? data.total : logs.length,
        logs: logs
      };
    } catch (e) {
      return empty;
    }
  }

  static async getDaily(days: number = 7): Promise<DailyLogRecord[]> {
    const safeDays = Math.max(1, Math.min(30, Math.floor(days)));
    const text = await Http.get(`/api/log/daily?days=${safeDays}`);
    if (!text) return [];
    try {
      const data = JSON.parse(text) as DailyLogResponse;
      const records = data.daily || [];
      return records.filter((record: DailyLogRecord) => validDailyRecord(record));
    } catch (e) {
      return [];
    }
  }

  static async getToday(): Promise<TodayLogSnapshot> {
    const empty: TodayLogSnapshot = { available: false, today: null, realtime: null };
    const text = await Http.get('/api/log/today');
    if (!text) return empty;
    try {
      const data = JSON.parse(text) as TodayLogResponse;
      if (!validDailyRecord(data.today)) return empty;
      return { available: true, today: data.today || emptyDailyRecord(), realtime: data.realtime || null };
    } catch (e) {
      return empty;
    }
  }

  static async getOperationFeed(limit: number = 100): Promise<OperationFeed> {
    const safeLimit = Math.max(10, Math.min(200, Math.floor(limit)));
    const empty: OperationFeed = { available: false, total: 0, limit: safeLimit, operations: [] };
    const text = await Http.get(`/api/operations?days=0&limit=${safeLimit}`);
    if (!text) return empty;
    try {
      const parsed = JSON.parse(text) as Object;
      const envelope = Array.isArray(parsed) ? null : parsed as OperationListResponse;
      const records = Array.isArray(parsed) ? parsed as OperationResponse[] : envelope?.operations || [];
      const normalized: OperationLogRecord[] = [];
      const count = Math.min(records.length, safeLimit);
      for (let index = 0; index < count; index++) normalized.push(normalizeOperation(records[index], index));
      return {
        available: true,
        total: envelope && typeof envelope.total === 'number' ? envelope.total : records.length,
        limit: envelope && typeof envelope.limit === 'number' ? envelope.limit : safeLimit,
        operations: normalized
      };
    } catch (e) {
      return empty;
    }
  }

  static async getOperations(): Promise<AlertMessage[]> {
    const feed = await LogApi.getOperationFeed(100);
    return feed.operations.map((record: OperationLogRecord, index: number): AlertMessage => ({
      id: record.key,
      source: record.deviceId,
      content: `${record.action} / ${record.result}`,
      level: record.result === 'ok' || record.result === 'success' ? 'info' : 'warning',
      timestamp: record.timestampMs,
      isRead: true
    }));
  }

  static async getSnapshot(): Promise<LogSnapshot> {
    const alertRequest = Http.get('/api/alerts');
    const operationRequest = Http.get('/api/operations?days=7');
    const eventRequest = Http.get('/api/security/events?limit=50');
    const statsRequest = Http.get('/api/security/stats');
    const authRequest = Http.get('/api/security/auth-status');

    const alertText = await alertRequest;
    const operationText = await operationRequest;
    const eventText = await eventRequest;
    const statsText = await statsRequest;
    const authText = await authRequest;
    const alerts: AlertMessage[] = [];
    let securityEvents: SecurityEventResponse[] = [];
    let securityEventsAvailable = false;
    let successCount = 0;

    if (alertText) {
      try {
        const parsed = JSON.parse(alertText) as Object;
        const data = Array.isArray(parsed) ? parsed as Record<string, Object>[] :
          (parsed as AlertListResponse).alerts || [];
        for (const raw of data) alerts.push(normalizeAlert(raw));
        successCount++;
      } catch (e) {
      }
    }
    if (operationText) {
      try {
        const parsed = JSON.parse(operationText) as Object;
        const data = Array.isArray(parsed) ? parsed as OperationResponse[] :
          (parsed as OperationListResponse).operations || [];
        const count = Math.min(data.length, 40);
        for (let index = 0; index < count; index++) alerts.push(operationMessage(data[index], index));
        successCount++;
      } catch (e) {
      }
    }
    if (eventText) {
      try {
        const parsed = JSON.parse(eventText) as Object;
        securityEvents = Array.isArray(parsed) ? parsed as SecurityEventResponse[] :
          (parsed as SecurityEventsResponse).events || [];
        for (let index = 0; index < securityEvents.length; index++) {
          alerts.push(securityMessage(securityEvents[index], index));
        }
        securityEventsAvailable = true;
        successCount++;
      } catch (e) {
      }
    }

    let securityStats = securityEventsAvailable ? statsFromEvents(securityEvents) : emptySecurityStats();
    if (statsText) {
      try {
        const data = JSON.parse(statsText) as SecurityStatsResponse;
        const levels = data.bySeverity || data.by_severity;
        if (typeof data.today === 'number' && typeof data.total === 'number' && levels !== undefined) {
          securityStats = {
            available: true,
            today: data.today,
            total: data.total,
            critical: levels.Critical || 0,
            high: levels.High || 0,
            medium: levels.Medium || 0,
            low: levels.Low || 0
          };
        }
        if (typeof data.total_rules === 'number' || typeof data.total === 'number') successCount++;
      } catch (e) {
      }
    }

    let authStatus = emptyAuthStatus();
    if (authText) {
      try {
        const data = JSON.parse(authText) as AuthStatusResponse;
        const enableAuth = typeof data.enableAuth === 'boolean' ? data.enableAuth : data.enable_auth;
        const doorPasswordRequired = typeof data.doorPasswordRequired === 'boolean' ?
          data.doorPasswordRequired : data.door_password_required;
        const sharedKeySet = typeof data.sharedKeySet === 'boolean' ? data.sharedKeySet : data.shared_key_set;
        if (typeof enableAuth === 'boolean' && typeof doorPasswordRequired === 'boolean' &&
          typeof sharedKeySet === 'boolean') {
          authStatus = {
            available: true,
            enableAuth: enableAuth,
            doorPasswordRequired: doorPasswordRequired,
            sharedKeySet: sharedKeySet,
            authAlgorithm: data.authAlgorithm || data.auth_algorithm || '',
            doorPasswordAlgorithm: data.doorPasswordAlgorithm || data.door_password_algorithm || ''
          };
          successCount++;
        }
      } catch (e) {
      }
    }

    alerts.sort((a: AlertMessage, b: AlertMessage) => b.timestamp - a.timestamp);
    return {
      available: successCount > 0,
      complete: successCount === 5,
      alerts: alerts,
      securityStats: securityStats,
      authStatus: authStatus
    };
  }
}
