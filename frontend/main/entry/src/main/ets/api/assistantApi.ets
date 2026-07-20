import { Http } from './http';

export interface AssistantFeedback {
  score: number;
  choice: string;
  note: string;
  created_at?: string;
}

export interface AssistantOperation {
  device_id?: string;
  action?: string;
  result?: string;
  created_at?: string;
  params?: Record<string, Object>;
}

export interface AssistantFeedItem {
  id: number;
  kind: string;
  title: string;
  summary: string;
  severity: string;
  evidence: Record<string, Object>;
  operations: AssistantOperation[];
  chart: Record<string, Object>;
  createdAt?: string;
  createdTs?: number;
  feedback?: AssistantFeedback;
  feedbackEnabled?: boolean;
  requiresAcknowledgement?: boolean;
  acknowledged?: boolean;
}

export interface ExternalFeedItem {
  category: string;
  title: string;
  summary: string;
  source_url: string;
  source_name?: string;
  image_url?: string;
  published_at?: string;
  fetched_at?: number;
  stale?: boolean;
}

export interface ExternalConfig {
  enabled: boolean;
  latitude: string;
  longitude: string;
  locationName: string;
  trafficUrl: string;
  marketSymbol: string;
  updatedAt?: number;
}

interface FeedResponse { success?: boolean; items?: AssistantFeedItem[]; reports?: AssistantFeedItem[]; }
interface ExternalResponse { success?: boolean; items?: ExternalFeedItem[]; }
interface ExternalConfigResponse extends ExternalConfig { success?: boolean; }
interface ExternalConfigUpdateBody { enabled: boolean; }
interface FeedbackResponse { success?: boolean; reportId?: number; }
interface AssistantFeedbackBody { eventId: number; score: number; choice: string; note: string; }
interface AssistantAcknowledgeBody { eventId: number; }
interface StatusCheckResponse { success?: boolean; reports?: AssistantFeedItem[]; message?: string; }
interface StatusCheckRequest { trigger: string; }

export class AssistantApi {
  static async getFeed(since: number = 0, limit: number = 30): Promise<AssistantFeedItem[]> {
    const text = await Http.get(`/api/ai/assistant/feed?since=${since}&limit=${limit}`);
    if (!text) return [];
    try {
      const data = JSON.parse(text) as FeedResponse;
      return data.items || data.reports || [];
    } catch (e) {
      return [];
    }
  }

  /** 手动运行一次与十分钟汇报相同的实时状态检测。 */
  static async runStatusCheck(): Promise<AssistantFeedItem[]> {
    const body: StatusCheckRequest = { trigger: 'manual' };
    const text = await Http.post('/api/ai/status/check', body);
    if (!text) return [];
    try {
      const data = JSON.parse(text) as StatusCheckResponse;
      return data.success === true ? (data.reports || []) : [];
    } catch (e) {
      return [];
    }
  }

  static async getExternalFeed(): Promise<ExternalFeedItem[]> {
    const text = await Http.get('/api/ai/external/feed');
    if (!text) return [];
    try { return (JSON.parse(text) as ExternalResponse).items || []; } catch (e) { return []; }
  }

  static async getExternalConfig(): Promise<ExternalConfig | null> {
    const text = await Http.get('/api/ai/external/config');
    if (!text) return null;
    try {
      const data = JSON.parse(text) as ExternalConfigResponse;
      return data.success === false ? null : data;
    } catch (e) {
      return null;
    }
  }

  static async setExternalEnabled(enabled: boolean): Promise<boolean> {
    const body: ExternalConfigUpdateBody = { enabled: enabled };
    const text = await Http.post('/api/ai/external/config', body);
    if (!text) return false;
    try { return (JSON.parse(text) as ExternalConfigResponse).success === true; } catch (e) { return false; }
  }

  static async submitFeedback(eventId: number, score: number, choice: string = '', note: string = ''): Promise<boolean> {
    const body: AssistantFeedbackBody = {
      eventId: eventId,
      score: Math.max(1, Math.min(10, Math.round(score))),
      choice: choice,
      note: note
    };
    const text = await Http.post('/api/ai/assistant/feedback', body);
    if (!text) return false;
    try {
      return (JSON.parse(text) as FeedbackResponse).success === true;
    } catch (e) {
      return false;
    }
  }

  static async acknowledgeAlert(eventId: number): Promise<boolean> {
    const body: AssistantAcknowledgeBody = { eventId: eventId };
    const text = await Http.post('/api/ai/assistant/acknowledge', body);
    if (!text) return false;
    try {
      return (JSON.parse(text) as FeedbackResponse).success === true;
    } catch (e) {
      return false;
    }
  }
}
