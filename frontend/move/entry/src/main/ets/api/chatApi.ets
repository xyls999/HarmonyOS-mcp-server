import { ChatAction, ChatMessage, ChatRole, ChartData } from './types';
import { Http, HttpResult } from './http';

let id = 100;

interface ChatRequest {
  message: string;
}

interface VoiceSequenceItem {
  text?: string;
  audioUrl?: string;
}

interface ChatImagePayload {
  url?: string;
  data?: string;
  base64?: string;
  mimeType?: string;
  mime_type?: string;
}

interface ChatReplyPayload {
  text?: string;
  content?: string;
  message?: string;
  image?: string | ChatImagePayload;
  imageUrl?: string;
  image_url?: string;
  url?: string;
}

interface ChatResponse {
  reply?: string | ChatReplyPayload;
  content?: string;
  message?: string;
  image?: string | ChatImagePayload;
  imageUrl?: string;
  image_url?: string;
  chartData?: ChartData;
  tts_audio?: string;
  voiceSequence?: VoiceSequenceItem[];
  intent?: ChatIntentPayload;
  execution?: ChatExecutionPayload;
}

interface ChatIntentPayload {
  scene_name?: string;
}

interface ChatExecutionItem {
  deviceId?: string;
  action?: string;
  success?: boolean;
  params?: ChatExecutionParams;
}

interface ChatExecutionParams {
  value?: number;
  position?: number;
  temperature?: number;
  brightness?: number;
}

interface ChatExecutionPayload {
  results?: ChatExecutionItem[];
}

interface ChatContextResponse {
  context?: string;
}

interface ParsedReply {
  text: string;
  imageUrl: string;
}

export class ChatApi {
  private static deviceName(id: string): string {
    if (id === 'light_01') return '客厅主灯';
    if (id === 'light_02') return '厨房灯';
    if (id === 'light_03') return '卧室灯';
    if (id === 'light_04') return '卫生间灯';
    if (id === 'ac_01') return '客厅空调';
    if (id === 'fan_02') return '换气扇';
    if (id === 'curtain_01') return '智能窗帘';
    if (id === 'door_01') return '客厅大门';
    return id || '设备';
  }

  private static actionText(action: string): string {
    if (action === 'on') return '打开';
    if (action === 'off') return '关闭';
    if (action === 'set_position') return '调整位置';
    if (action === 'set_temperature') return '调整温度';
    if (action === 'set_brightness') return '调整亮度';
    return action || '执行操作';
  }

  private static executionActions(value: ChatExecutionPayload | undefined): ChatAction[] {
    if (!value || !Array.isArray(value.results)) return [];
    return value.results.map((item: ChatExecutionItem): ChatAction => {
      const deviceId = item.deviceId || '';
      return {
        deviceId,
        deviceName: ChatApi.deviceName(deviceId),
        action: ChatApi.actionText(item.action || ''),
        success: item.success === true,
        value: item.params?.position ?? item.params?.temperature ?? item.params?.brightness ?? item.params?.value
      };
    });
  }

  static async getHistory(): Promise<ChatMessage[]> {
    const raw = await Http.get('/api/app/ai/context');
    if (!raw) return [];
    try {
      const response = JSON.parse(raw) as ChatContextResponse;
      const context = response.context || '';
      const marker = context.indexOf('最近对话:');
      if (marker < 0) return [];
      const lines = context.substring(marker + '最近对话:'.length).split('\n');
      const messages: ChatMessage[] = [];
      let skipAssistant = false;
      for (let index = 0; index < lines.length; index++) {
        const line = lines[index].trim();
        if (line.startsWith('用户:')) {
          const content = line.substring('用户:'.length).trim();
          if (content && content.replace(/[?？]/g, '').trim().length === 0) {
            skipAssistant = true;
            continue;
          }
          skipAssistant = false;
          messages.push({
            id: `history_user_${index}`,
            role: ChatRole.USER,
            content,
            timestamp: Date.now() - (lines.length - index) * 1000
          });
        } else if (line.startsWith('助手:')) {
          if (skipAssistant) {
            skipAssistant = false;
            continue;
          }
          messages.push({
            id: `history_assistant_${index}`,
            role: ChatRole.ASSISTANT,
            content: line.substring('助手:'.length).trim(),
            timestamp: Date.now() - (lines.length - index) * 1000
          });
        } else if (line && messages.length > 0) {
          messages[messages.length - 1].content += `\n${line}`;
        }
      }
      return messages.slice(Math.max(0, messages.length - 12));
    } catch (_) {
      return [];
    }
  }

  private static displayText(value: string): string {
    return value.replace(/\*\*/g, '').replace(/^###?\s+/gm, '');
  }

  private static responseText(result: HttpResult): string {
    if (result.offline || result.status === 504) return 'A9 网关无响应，请稍后重试';
    if (result.status === 401) return '登录已过期，请重新登录';
    if (result.status === 403) return '当前账号没有执行该操作的权限';
    if (result.status === 426) return '服务端已要求 HTTPS，请升级连接配置';
    return result.error || '暂时无法连接服务';
  }

  private static validChartData(value: ChartData | undefined): ChartData | undefined {
    if (!value || !Array.isArray(value.charts) || value.charts.length === 0) return undefined;
    return value;
  }

  private static normalizeAudioPath(path: string): string {
    if (!path) return '';
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    if (path.startsWith('/api/tts/audio/')) return `${Http.BASE}/api/app${path.substring(4)}`;
    return `${Http.BASE}${path.startsWith('/') ? '' : '/'}${path}`;
  }

  private static normalizeImagePath(path: string, mimeType: string = 'image/png'): string {
    const source = path.trim();
    if (!source) return '';
    if (source.startsWith('http://') || source.startsWith('https://') || source.startsWith('data:image/')) {
      return source;
    }
    if (source.startsWith('/')) return `${Http.BASE}${source}`;
    if (source.startsWith('iVBOR') || source.startsWith('/9j/') || source.startsWith('R0lGOD') ||
      source.startsWith('UklGR')) {
      return `data:${mimeType};base64,${source}`;
    }
    return `${Http.BASE}/${source}`;
  }

  private static imageSource(value: string | ChatImagePayload | undefined): string {
    if (typeof value === 'string') return ChatApi.normalizeImagePath(value);
    if (!value) return '';
    const mimeType = value.mimeType || value.mime_type || 'image/png';
    const source = value.url || value.data || value.base64 || '';
    return ChatApi.normalizeImagePath(source, mimeType);
  }

  private static parseReply(value: ChatResponse): ParsedReply {
    let text = '';
    let imageUrl = ChatApi.imageSource(value.image) ||
      ChatApi.normalizeImagePath(value.imageUrl || value.image_url || '');

    if (typeof value.reply === 'string') {
      text = value.reply;
    } else if (value.reply) {
      const reply = value.reply;
      text = reply.text || reply.content || reply.message || '';
      imageUrl = ChatApi.imageSource(reply.image) ||
        ChatApi.normalizeImagePath(reply.imageUrl || reply.image_url || reply.url || '') || imageUrl;
    }

    text = text || value.content || value.message || '';
    if (!text && value.voiceSequence && value.voiceSequence.length > 0) {
      text = value.voiceSequence[0].text || '';
    }
    if (!text && !imageUrl) text = '服务端未返回内容';

    const parsed: ParsedReply = { text, imageUrl };
    return parsed;
  }

  static async sendStream(messages: ChatMessage[], onToken: (text: string) => void,
    onDone: (message: ChatMessage) => void): Promise<void> {
    const latest = messages.length > 0 ? messages[messages.length - 1].content.trim() : '';
    const body: ChatRequest = { message: latest };
    const result = await Http.postResult('/api/app/chat/send', body, true, Http.CHAT_TIMEOUT);
    let reply = ChatApi.responseText(result);
    let chartData: ChartData | undefined;
    let ttsAudio = '';
    let imageUrl = '';
    let sceneName = '';
    let actions: ChatAction[] = [];
    const isError = result.status < 200 || result.status >= 300;

    if (result.status >= 200 && result.status < 300) {
      try {
        const value = JSON.parse(result.body) as ChatResponse;
        const parsed = ChatApi.parseReply(value);
        reply = ChatApi.displayText(parsed.text);
        imageUrl = parsed.imageUrl;
        chartData = ChatApi.validChartData(value.chartData);
        sceneName = value.intent?.scene_name || '';
        actions = ChatApi.executionActions(value.execution);
        if (value.tts_audio) ttsAudio = ChatApi.normalizeAudioPath(value.tts_audio);
        else if (value.voiceSequence && value.voiceSequence.length > 0) {
          ttsAudio = ChatApi.normalizeAudioPath(value.voiceSequence[0].audioUrl || '');
        }
      } catch (_) {
        reply = '服务端返回数据无法解析';
      }
    }

    let index = 0;
    await new Promise<void>((resolve) => {
      const timer = setInterval(() => {
        index += reply.length > 180 ? 3 : 1;
        onToken(reply.slice(0, index));
        if (index >= reply.length) {
          clearInterval(timer);
          const message: ChatMessage = {
            id: `msg_${id++}`,
            role: ChatRole.ASSISTANT,
            content: reply,
            timestamp: Date.now(),
            chartData,
            ttsAudio,
            imageUrl,
            isError,
            sceneName,
            actions
          };
          onDone(message);
          resolve();
        }
      }, 24);
    });
  }

  static getWelcome(): string { return '你好，需要做什么？'; }
}
