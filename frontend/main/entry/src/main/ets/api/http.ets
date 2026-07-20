/**
 * A9 v6.1 HTTP 客户端。
 * 内网兼容模式可直接请求；配置 API Key 后自动获取、刷新并携带 Bearer Token。
 */
import { http } from '@kit.NetworkKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN = 0x0001;
const TAG = 'SmartHomeHttp';

interface HttpResponseData {
  code: number;
  text: string;
}

interface AuthTokenRequest {
  api_key: string;
}

interface AuthTokenResponse {
  token?: string;
  expires_in?: number;
  permissions?: string[];
  error?: string;
  code?: number;
}

interface EmptyRequestBody {
}

export class Http {
  static readonly BASE: string = 'http://192.168.1.73:8080';
  private static readonly BASE_CANDIDATES: string[] = [
    'http://192.168.1.73:8080',
    'http://192.168.1.94:8080',
    'http://192.168.1.81:8080',
    'http://127.0.0.1:8080'
  ];
  private static readonly CONNECT_TIMEOUT: number = 4500;
  private static readonly READ_TIMEOUT: number = 90000;
  private static activeBase: string = Http.BASE;
  private static apiKey: string = '';
  private static token: string = '';
  private static tokenExpiresAt: number = 0;
  private static tokenRequest: Promise<string | null> | null = null;

  static getActiveBase(): string {
    return Http.activeBase;
  }

  /** 由设置层注入 API Key；空值表示使用后端的内网兼容模式。 */
  static configureApiKey(apiKey: string): void {
    const next = apiKey.trim();
    if (next === Http.apiKey) return;
    Http.apiKey = next;
    Http.clearToken();
  }

  static hasToken(): boolean {
    return Http.token.length > 0 && Date.now() < Http.tokenExpiresAt;
  }

  static async get(path: string): Promise<string | null> {
    return Http.request(path, null);
  }

  static async post(path: string, body: object): Promise<string | null> {
    return Http.request(path, body);
  }

  private static async request(path: string, body: object | null): Promise<string | null> {
    const bases = Http.orderedBases();
    let token = await Http.ensureToken();
    for (let i = 0; i < bases.length; i++) {
      const base = bases[i];
      let response = await Http.requestOnce(base, path, body, token || '');
      if (response && (response.code === 401 || response.code === 403) && Http.apiKey.length > 0) {
        Http.clearToken();
        token = await Http.ensureToken();
        if (token) response = await Http.requestOnce(base, path, body, token);
      }
      if (response && response.code >= 200 && response.code < 300) {
        Http.activeBase = base;
        return response.text;
      }
      if (response) hilog.warn(DOMAIN, TAG, `${body === null ? 'GET' : 'POST'} ${base}${path} code=${response.code}`);
    }
    return null;
  }

  private static async ensureToken(): Promise<string | null> {
    if (Http.apiKey.length === 0) return null;
    if (Http.token.length > 0 && Date.now() < Http.tokenExpiresAt) return Http.token;
    if (Http.tokenRequest) return Http.tokenRequest;
    Http.tokenRequest = Http.acquireToken();
    const result = await Http.tokenRequest;
    Http.tokenRequest = null;
    return result;
  }

  private static async acquireToken(): Promise<string | null> {
    const bases = Http.orderedBases();
    const previousToken = Http.token;
    if (previousToken.length > 0) {
      const emptyBody: EmptyRequestBody = {};
      for (let i = 0; i < bases.length; i++) {
        const refreshed = await Http.requestOnce(bases[i], '/api/auth/refresh', emptyBody, previousToken);
        const token = Http.acceptToken(refreshed);
        if (token) {
          Http.activeBase = bases[i];
          return token;
        }
      }
    }

    const body: AuthTokenRequest = { api_key: Http.apiKey };
    for (let i = 0; i < bases.length; i++) {
      const response = await Http.requestOnce(bases[i], '/api/auth/token', body, '');
      const token = Http.acceptToken(response);
      if (token) {
        Http.activeBase = bases[i];
        return token;
      }
    }
    return null;
  }

  private static acceptToken(response: HttpResponseData | null): string | null {
    if (!response || response.code < 200 || response.code >= 300) return null;
    try {
      const data = JSON.parse(response.text) as AuthTokenResponse;
      if (!data.token || data.token.trim().length === 0) return null;
      const lifetime = typeof data.expires_in === 'number' && data.expires_in > 0 ? data.expires_in : 86400;
      Http.token = data.token.trim();
      Http.tokenExpiresAt = Date.now() + Math.max(60, lifetime - 60) * 1000;
      return Http.token;
    } catch (e) {
      return null;
    }
  }

  private static clearToken(): void {
    Http.token = '';
    Http.tokenExpiresAt = 0;
    Http.tokenRequest = null;
  }

  private static async requestOnce(base: string, path: string, body: object | null,
    token: string): Promise<HttpResponseData | null> {
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token.length > 0) headers['Authorization'] = `Bearer ${token}`;
      const httpInst = http.createHttp();
      const options: http.HttpRequestOptions = {
        method: body === null ? http.RequestMethod.GET : http.RequestMethod.POST,
        connectTimeout: Http.CONNECT_TIMEOUT,
        readTimeout: Http.READ_TIMEOUT,
        header: headers
      };
      if (body !== null) options.extraData = JSON.stringify(body);
      const resp = await httpInst.request(base + path, options);
      httpInst.destroy();
      const raw = resp.result;
      const text = typeof raw === 'string' ? raw : JSON.stringify(raw);
      return { code: resp.responseCode, text: text };
    } catch (e) {
      const err = e as BusinessError;
      hilog.warn(DOMAIN, TAG, `${body === null ? 'GET' : 'POST'} ${base}${path} err: ${err.message}`);
      return null;
    }
  }

  private static orderedBases(): string[] {
    const result: string[] = [Http.activeBase];
    for (let i = 0; i < Http.BASE_CANDIDATES.length; i++) {
      if (result.indexOf(Http.BASE_CANDIDATES[i]) < 0) result.push(Http.BASE_CANDIDATES[i]);
    }
    return result;
  }
}
