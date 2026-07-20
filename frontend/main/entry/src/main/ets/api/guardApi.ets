import { Http } from './http';

export interface GuardConfig {
  enabled: boolean;
  activeAiEnabled: boolean;
  cooldownSeconds: number;
  feedbackAutomation?: FeedbackAutomationConfig;
  planConfirmation?: PlanConfirmationConfig;
}

export interface FeedbackAutomationConfig { enabled: boolean; minSamples: number; minAverageScore: number; }
export interface PlanConfirmationConfig { enabled: boolean; }

export interface GuardIncident {
  id: number;
  signature: string;
  ruleKey: string;
  room: string;
  guardLevel: number;
  mode: string;
  status: string;
  needsFeedback: boolean;
  feedbackReceived: boolean;
  createdAt: string;
}

export interface GuardStatus {
  available: boolean;
  enabled: boolean;
  activeAiEnabled: boolean;
  feedbackAutomationEnabled: boolean;
  planConfirmationEnabled: boolean;
  mode: string;
  guardLevel: number;
  pendingFeedback: number;
  recentIncidents: GuardIncident[];
}

export interface GuardNotificationStatus {
  enabled: boolean;
  configured: boolean;
  mode: string;
}

export interface ProtocolItem {
  name: string;
  status: string;
  port: number;
}

interface GuardStatusResponse {
  success?: boolean;
  enabled?: boolean;
  activeAiEnabled?: boolean;
  feedbackAutomationEnabled?: boolean;
  planConfirmationEnabled?: boolean;
  mode?: string;
  guardLevel?: number;
  pendingFeedback?: number;
  recentIncidents?: GuardIncident[];
  config?: GuardNestedConfig;
}

interface GuardNestedConfig { enabled?: boolean; activeAiEnabled?: boolean; feedbackAutomation?: FeedbackAutomationConfig; }

export interface GuardConfigResponse {
  success?: boolean;
  config?: GuardConfig;
  notification?: GuardNotificationStatus;
}

interface GuardIncidentResponse {
  success?: boolean;
  incidents?: GuardIncident[];
}

interface ProtocolRawItem {
  status?: string;
  port?: number;
}

interface ProtocolResponse {
  protocols?: Record<string, ProtocolRawItem>;
}

interface MutationResponse {
  success?: boolean;
}

interface RadarResponse {
  success?: boolean;
  radar_presence?: Record<string, boolean>;
}

interface RadarBody {
  enabled: boolean;
}

interface ConfigUpdateBody {
  config: GuardEnabledConfig;
}

interface GuardEnabledConfig {
  enabled: boolean;
  activeAiEnabled: boolean;
  feedbackAutomation: FeedbackAutomationConfig;
  planConfirmationEnabled: boolean;
}

export interface TelemetryMetadata {
  deviceId?: string;
  incidentId?: number;
  score?: number;
}

interface FeedbackBody {
  incidentId: number;
  score: number;
  betterAction: string;
  notes: string;
}

interface TelemetryBody {
  eventType: string;
  page: string;
  action: string;
  result: string;
  metadata: TelemetryMetadata;
}

export class GuardApi {
  private static booleanField(payload: string, key: string, fallback: boolean): boolean {
    const marker = `"${key}"`;
    const start = payload.indexOf(marker);
    if (start < 0) return fallback;
    const window = payload.substring(start, Math.min(payload.length, start + marker.length + 18));
    if (window.indexOf('true') >= 0) return true;
    if (window.indexOf('false') >= 0) return false;
    return fallback;
  }

  static async getStatus(): Promise<GuardStatus> {
    const text = await Http.get('/api/ai/guard/status');
    if (text) {
      try {
        const data = JSON.parse(text) as GuardStatusResponse;
        const nestedConfig = data.config;
        return {
          available: data.success === true,
          enabled: GuardApi.booleanField(text, 'enabled', data.enabled === true || nestedConfig?.enabled === true),
          activeAiEnabled: GuardApi.booleanField(text, 'activeAiEnabled', data.activeAiEnabled === true || nestedConfig?.activeAiEnabled === true),
          feedbackAutomationEnabled: GuardApi.booleanField(text, 'feedbackAutomationEnabled', data.feedbackAutomationEnabled === true || nestedConfig?.feedbackAutomation?.enabled === true),
          planConfirmationEnabled: false,
          mode: data.mode || 'passive',
          guardLevel: data.guardLevel || 0,
          pendingFeedback: data.pendingFeedback || 0,
          recentIncidents: data.recentIncidents || []
        };
      } catch (e) {
      }
    }
    return {
      available: false, enabled: true, activeAiEnabled: true, feedbackAutomationEnabled: true, planConfirmationEnabled: false, mode: 'offline',
      guardLevel: 0, pendingFeedback: 0, recentIncidents: []
    };
  }

  static async getConfig(): Promise<GuardConfigResponse> {
    const text = await Http.get('/api/ai/guard/config');
    if (text) {
      try {
        return JSON.parse(text) as GuardConfigResponse;
      } catch (e) {
      }
    }
    return { success: false };
  }

  static async getPendingIncidents(): Promise<GuardIncident[]> {
    const text = await Http.get('/api/ai/guard/incidents?limit=50&pending=true');
    if (text) {
      try {
        const data = JSON.parse(text) as GuardIncidentResponse;
        return data.incidents || [];
      } catch (e) {
      }
    }
    return [];
  }

  static async updateConfig(enabled: boolean, activeAiEnabled: boolean,
    feedbackAutomationEnabled: boolean): Promise<boolean> {
    const feedbackAutomation: FeedbackAutomationConfig = {
      enabled: feedbackAutomationEnabled, minSamples: 3, minAverageScore: 8
    };
    const config: GuardEnabledConfig = {
      enabled: enabled, activeAiEnabled: activeAiEnabled, feedbackAutomation: feedbackAutomation
      , planConfirmationEnabled: false
    };
    const body: ConfigUpdateBody = { config: config };
    const text = await Http.post('/api/ai/guard/config', body);
    if (!text) return false;
    try {
      return (JSON.parse(text) as MutationResponse).success === true;
    } catch (e) {
      return false;
    }
  }

  static async submitFeedback(incidentId: number, score: number, betterAction: string,
    notes: string = ''): Promise<boolean> {
    const body: FeedbackBody = {
      incidentId: incidentId,
      score: Math.max(0, Math.min(10, Math.round(score))),
      betterAction: betterAction.trim(),
      notes: notes.trim()
    };
    const text = await Http.post('/api/ai/guard/feedback', body);
    if (!text) return false;
    try {
      return (JSON.parse(text) as MutationResponse).success === true;
    } catch (e) {
      return false;
    }
  }

  static async recordTelemetry(eventType: string, page: string, action: string, result: string,
    metadata: TelemetryMetadata = {}): Promise<void> {
    const body: TelemetryBody = {
      eventType: eventType,
      page: page,
      action: action,
      result: result,
      metadata: metadata
    };
    await Http.post('/api/app/telemetry', body);
  }

  static async getProtocols(): Promise<ProtocolItem[]> {
    const text = await Http.get('/api/protocols/status');
    if (!text) return [];
    try {
      const data = JSON.parse(text) as ProtocolResponse;
      const source = data.protocols || {};
      const result: ProtocolItem[] = [];
      const names = Object.keys(source);
      for (let i = 0; i < names.length; i++) {
        const item = source[names[i]];
        result.push({ name: names[i].toUpperCase(), status: item.status || 'unknown', port: item.port || 0 });
      }
      return result;
    } catch (e) {
      return [];
    }
  }

  static async getRadarEnabled(): Promise<boolean | null> {
    const text = await Http.get('/api/ai/radar/config');
    if (!text) return null;
    try {
      const data = JSON.parse(text) as RadarResponse;
      return data.radar_presence?.enabled === true;
    } catch (e) {
      return null;
    }
  }

  static async setRadarEnabled(enabled: boolean): Promise<boolean> {
    const body: RadarBody = { enabled: enabled };
    const text = await Http.post('/api/ai/radar/config', body);
    if (!text) return false;
    try {
      return (JSON.parse(text) as MutationResponse).success === true;
    } catch (e) {
      return false;
    }
  }
}
