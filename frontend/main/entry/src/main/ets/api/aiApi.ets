/** A9 v6.1 AI 意图、推荐、能耗、联动与上下文接口。 */
import { Http } from './http';

interface MessageRequest {
  message: string;
}

interface RecommendationRequest {
  id: string;
}

interface DeviceIdRequest {
  device_id: string;
}

interface EmptyRequest {
}

export interface AiIntentResult {
  available: boolean;
  reply: string;
  source: string;
  executed: boolean;
  intent: Object | null;
  result: Object | null;
}

export class AiApi {
  static async parseIntent(message: string): Promise<AiIntentResult> {
    return AiApi.sendMessage('/api/ai/intent', message);
  }

  static async executeIntent(message: string): Promise<AiIntentResult> {
    return AiApi.sendMessage('/api/ai/execute', message);
  }

  static async analyzeEmotion(message: string): Promise<Object | null> {
    const body: MessageRequest = { message: message };
    return AiApi.postObject('/api/ai/emotion', body);
  }

  static async getCapabilities(): Promise<Object | null> { return AiApi.getObject('/api/ai/capabilities'); }
  static async getAnomalies(): Promise<Object | null> { return AiApi.getObject('/api/ai/anomaly'); }
  static async getRecommendations(): Promise<Object | null> { return AiApi.getObject('/api/ai/recommendations'); }
  static async getHabitStats(): Promise<Object | null> { return AiApi.getObject('/api/ai/habit/stats'); }
  static async getEnergy(): Promise<Object | null> { return AiApi.getObject('/api/ai/energy'); }
  static async getEnergyWaste(): Promise<Object | null> { return AiApi.getObject('/api/ai/energy/waste'); }
  static async getEnergyReport(): Promise<Object | null> { return AiApi.getObject('/api/ai/energy/report'); }
  static async getLinkageRules(): Promise<Object | null> { return AiApi.getObject('/api/ai/linkage/rules'); }
  static async getLinkageLog(): Promise<Object | null> { return AiApi.getObject('/api/ai/linkage/log'); }
  static async getContext(): Promise<Object | null> { return AiApi.getObject('/api/ai/context'); }
  static async getContextStats(): Promise<Object | null> { return AiApi.getObject('/api/ai/context/stats'); }
  static async getDeviceTemplates(): Promise<Object | null> { return AiApi.getObject('/api/ai/devices'); }

  static async acceptRecommendation(id: string): Promise<Object | null> {
    const body: RecommendationRequest = { id: id };
    return AiApi.postObject('/api/ai/recommendation/accept', body);
  }

  static async dismissRecommendation(id: string): Promise<Object | null> {
    const body: RecommendationRequest = { id: id };
    return AiApi.postObject('/api/ai/recommendation/dismiss', body);
  }

  static async clearContext(): Promise<Object | null> {
    const body: EmptyRequest = {};
    return AiApi.postObject('/api/ai/context/clear', body);
  }

  static async registerDevice(template: object): Promise<Object | null> {
    return AiApi.postObject('/api/ai/device/register', template);
  }

  static async unregisterDevice(deviceId: string): Promise<Object | null> {
    const body: DeviceIdRequest = { device_id: deviceId };
    return AiApi.postObject('/api/ai/device/unregister', body);
  }

  private static async sendMessage(path: string, message: string): Promise<AiIntentResult> {
    const empty: AiIntentResult = {
      available: false, reply: '', source: '', executed: false, intent: null, result: null
    };
    const body: MessageRequest = { message: message.trim() };
    if (!body.message) return empty;
    const data = await AiApi.postObject(path, body);
    if (!data) return empty;
    const raw = data as Record<string, Object>;
    return {
      available: true,
      reply: typeof raw.reply === 'string' ? raw.reply : '',
      source: typeof raw.source === 'string' ? raw.source : '',
      executed: raw.executed === true,
      intent: raw.intent || null,
      result: raw.result || null
    };
  }

  private static async getObject(path: string): Promise<Object | null> {
    const text = await Http.get(path);
    return AiApi.parseObject(text);
  }

  private static async postObject(path: string, body: object): Promise<Object | null> {
    const text = await Http.post(path, body);
    return AiApi.parseObject(text);
  }

  private static parseObject(text: string | null): Object | null {
    if (!text) return null;
    try {
      return JSON.parse(text) as Object;
    } catch (e) {
      return null;
    }
  }
}
