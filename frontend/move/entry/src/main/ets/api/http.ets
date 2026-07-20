import { http } from '@kit.NetworkKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { preferences } from '@kit.ArkData';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { AppContext } from './appContext';
import { RequestSigner } from './requestSigner';

type Json = Record<string, Object>;

interface RefreshRequest { refresh_token: string; }

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface HttpResult {
  status: number;
  body: string;
  error: string;
  offline: boolean;
}

export class Http {
  static readonly BASE: string = 'http://yuanzhe.tech';
  static readonly CHAT_TIMEOUT: number = 120000;
  private static readonly TIMEOUT: number = 20000;
  private static readonly HEALTH_TIMEOUT: number = 5000;
  private static readonly REFRESH_AHEAD_MS: number = 5 * 60 * 1000;
  private static readonly STORE_NAME: string = 'smart_home_auth';
  private static accessToken: string = '';
  private static refreshToken: string = '';
  private static expiresAt: number = 0;
  private static loginTime: number = 0;
  private static initialized: boolean = false;
  private static offlineMode: boolean = false;
  private static lastError: string = '';
  private static lastOffline: boolean = false;
  private static refreshTask: Promise<boolean> | null = null;

  static hasSession(): boolean { return Http.accessToken.length > 0 || Http.refreshToken.length > 0; }
  static isOfflineMode(): boolean { return Http.offlineMode; }
  static getLastError(): string { return Http.lastError; }
  static wasLastOffline(): boolean { return Http.lastOffline; }
  static getLoginTime(): number { return Http.loginTime; }
  static getRefreshToken(): string { return Http.refreshToken; }

  static setOfflineMode(offline: boolean): void {
    Http.offlineMode = offline;
    AppStorage.setOrCreate<boolean>('isOfflineMode', offline);
  }

  static async initialize(): Promise<void> {
    if (Http.initialized) return;
    const context = AppContext.abilityContext;
    if (!context) return;
    Http.initialized = true;
    try {
      const store = await preferences.getPreferences(context, Http.STORE_NAME);
      Http.accessToken = await store.get('access_token', '') as string;
      Http.refreshToken = await store.get('refresh_token', '') as string;
      Http.expiresAt = await store.get('expires_at', 0) as number;
      Http.loginTime = await store.get('login_time', 0) as number;
      AppStorage.setOrCreate<boolean>('isAuthenticated', Http.hasSession());
    } catch (error) {
      const err = error as BusinessError;
      hilog.warn(0x0000, 'SmartHomeHttp', 'restore session failed: %{public}s', err.message);
    }
  }

  private static async persistSession(): Promise<void> {
    const context = AppContext.abilityContext;
    if (!context) return;
    try {
      const store = await preferences.getPreferences(context, Http.STORE_NAME);
      await store.put('access_token', Http.accessToken);
      await store.put('refresh_token', Http.refreshToken);
      await store.put('expires_at', Http.expiresAt);
      await store.put('login_time', Http.loginTime);
      await store.flush();
    } catch (error) {
      const err = error as BusinessError;
      hilog.warn(0x0000, 'SmartHomeHttp', 'persist session failed: %{public}s', err.message);
    }
  }

  static async setSession(accessToken: string, refreshToken: string, expiresIn: number): Promise<void> {
    Http.accessToken = accessToken;
    Http.refreshToken = refreshToken;
    const now = Date.now();
    if (Http.loginTime <= 0) Http.loginTime = now;
    Http.expiresAt = now + Math.max(60, expiresIn) * 1000;
    AppStorage.setOrCreate<boolean>('isAuthenticated', true);
    await Http.persistSession();
  }

  static clearSession(updateLoginState: boolean = true): void {
    Http.accessToken = '';
    Http.refreshToken = '';
    Http.expiresAt = 0;
    Http.loginTime = 0;
    if (updateLoginState) AppStorage.setOrCreate<boolean>('isAuthenticated', false);
    Http.persistSession();
  }

  private static isPublicAuthPath(path: string): boolean {
    return path === '/api/app/auth/login' || path === '/api/app/auth/refresh';
  }

  private static parseError(body: string, status: number): HttpResult {
    let error = status === 400 ? '请求参数不正确'
      : status === 401 ? '登录状态无效'
        : status === 403 ? '当前账号没有操作权限'
          : status === 404 ? '请求的设备或功能不存在'
            : status === 426 ? '服务端要求使用 HTTPS，请升级应用连接配置'
              : status === 504 ? 'A9 网关无响应' : `请求失败 (${status})`;
    let offline = status === 504;
    if (body) {
      try {
        const value = JSON.parse(body) as Json;
        if (typeof value.error === 'string') error = value.error;
        else if (typeof value.message === 'string') error = value.message;
        offline = offline || value.offline === true;
      } catch (_) {}
    }
    return { status, body, error, offline };
  }

  private static async rawRequest(path: string, method: http.RequestMethod, body?: object,
    includeAuth: boolean = true, timeout: number = Http.TIMEOUT): Promise<HttpResult> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (includeAuth && Http.accessToken) headers.Authorization = `Bearer ${Http.accessToken}`;
    const bodyText = body === undefined ? '' : JSON.stringify(body);
    if (includeAuth && Http.accessToken) {
      try {
        const signed = await RequestSigner.headers(Http.accessToken, `${method}`, path, bodyText);
        headers['X-App-Timestamp'] = signed['X-App-Timestamp'];
        headers['X-App-Nonce'] = signed['X-App-Nonce'];
        headers['X-App-Signature'] = signed['X-App-Signature'];
      } catch (error) {
        const err = error as BusinessError;
        hilog.error(0x0000, 'SmartHomeHttp', 'request sign failed: %{public}s', err.message);
        return { status: 0, body: '', error: '无法生成安全请求签名', offline: false };
      }
    }
    const options: http.HttpRequestOptions = {
      method,
      connectTimeout: timeout,
      readTimeout: timeout,
      header: headers
    };
    if (body !== undefined) options.extraData = bodyText;

    const httpInst = http.createHttp();
    try {
      const response = await httpInst.request(Http.BASE + path, options);
      const responseBody = typeof response.result === 'string' ? response.result : JSON.stringify(response.result);
      const status = Number(response.responseCode);
      const result: HttpResult = status >= 200 && status < 300 ?
        { status, body: responseBody, error: '', offline: false } : Http.parseError(responseBody, status);
      Http.lastError = result.error;
      Http.lastOffline = result.offline;
      hilog.info(0x0000, 'SmartHomeHttp', '%{public}s %{public}d', path, status);
      return result;
    } catch (error) {
      const err = error as BusinessError;
      const timeoutError = err.message.toLowerCase().includes('timeout') || err.message.includes('超时');
      Http.lastError = timeoutError ? '请求超时，请稍后重试' : '无法连接远程服务';
      Http.lastOffline = false;
      hilog.warn(0x0000, 'SmartHomeHttp', '%{public}s failed: %{public}s', path, err.message);
      return { status: 0, body: '', error: Http.lastError, offline: false };
    } finally {
      httpInst.destroy();
    }
  }

  private static tokenExpiring(): boolean {
    return Http.accessToken.length > 0 && Date.now() >= Http.expiresAt - Http.REFRESH_AHEAD_MS;
  }

  private static async refreshAccessToken(): Promise<boolean> {
    if (!Http.refreshToken) return false;
    const body: RefreshRequest = { refresh_token: Http.refreshToken };
    const result = await Http.rawRequest('/api/app/auth/refresh', http.RequestMethod.POST, body, false);
    if (result.status !== 200) {
      Http.clearSession();
      return false;
    }
    try {
      const value = JSON.parse(result.body) as Json;
      if (typeof value.access_token !== 'string' || typeof value.refresh_token !== 'string') {
        Http.clearSession();
        return false;
      }
      const tokens: TokenResponse = {
        access_token: value.access_token,
        refresh_token: value.refresh_token,
        expires_in: typeof value.expires_in === 'number' ? value.expires_in : 7200
      };
      await Http.setSession(tokens.access_token, tokens.refresh_token, tokens.expires_in);
      return true;
    } catch (_) {
      Http.clearSession();
      return false;
    }
  }

  private static async ensureFreshToken(): Promise<boolean> {
    if (!Http.tokenExpiring()) return Http.accessToken.length > 0;
    if (!Http.refreshTask) Http.refreshTask = Http.refreshAccessToken();
    const refreshed = await Http.refreshTask;
    Http.refreshTask = null;
    return refreshed;
  }

  private static async request(path: string, method: http.RequestMethod, body?: object,
    retry401: boolean = true, timeout: number = Http.TIMEOUT): Promise<HttpResult> {
    await Http.initialize();
    const protectedPath = !Http.isPublicAuthPath(path);
    if (protectedPath && Http.hasSession()) await Http.ensureFreshToken();
    let result = await Http.rawRequest(path, method, body, protectedPath, timeout);
    if (result.status === 401 && protectedPath && retry401 && Http.refreshToken) {
      const refreshed = await Http.refreshAccessToken();
      if (refreshed) result = await Http.rawRequest(path, method, body, true, timeout);
    }
    if (result.status === 401 && protectedPath) Http.clearSession();
    return result;
  }

  private static success(result: HttpResult): string | null {
    return result.status >= 200 && result.status < 300 ? result.body : null;
  }

  static getResult(path: string, retry401: boolean = true, timeout: number = Http.TIMEOUT): Promise<HttpResult> {
    return Http.request(path, http.RequestMethod.GET, undefined, retry401, timeout);
  }

  static postResult(path: string, body: object, retry401: boolean = true,
    timeout: number = Http.TIMEOUT): Promise<HttpResult> {
    return Http.request(path, http.RequestMethod.POST, body, retry401, timeout);
  }

  static async checkService(): Promise<boolean> {
    await Http.initialize();
    const result = await Http.rawRequest('/api/app/auth/me', http.RequestMethod.GET, undefined, false, Http.HEALTH_TIMEOUT);
    const available = result.status === 200 || result.status === 401 || result.status === 403;
    Http.setOfflineMode(!available);
    return available;
  }

  static async get(path: string): Promise<string | null> {
    return Http.success(await Http.getResult(path));
  }

  static async post(path: string, body: object): Promise<string | null> {
    return Http.success(await Http.postResult(path, body));
  }

  static async put(path: string, body: object): Promise<string | null> {
    return Http.success(await Http.request(path, http.RequestMethod.PUT, body));
  }

  static async delete(path: string): Promise<string | null> {
    const body: Record<string, string> = {};
    return Http.success(await Http.request(path, http.RequestMethod.DELETE, body));
  }

  static async getBinary(path: string, retry401: boolean = true): Promise<ArrayBuffer | null> {
    await Http.initialize();
    if (Http.hasSession()) await Http.ensureFreshToken();
    const headers: Record<string, string> = {};
    if (Http.accessToken) headers.Authorization = `Bearer ${Http.accessToken}`;
    const options: http.HttpRequestOptions = {
      method: http.RequestMethod.GET,
      connectTimeout: Http.TIMEOUT,
      readTimeout: Http.TIMEOUT,
      header: headers,
      expectDataType: http.HttpDataType.ARRAY_BUFFER
    };
    const httpInst = http.createHttp();
    try {
      const response = await httpInst.request(Http.BASE + path, options);
      if (response.responseCode === 401 && retry401 && Http.refreshToken) {
        httpInst.destroy();
        if (await Http.refreshAccessToken()) return Http.getBinary(path, false);
        return null;
      }
      if (response.responseCode < 200 || response.responseCode >= 300 ||
        response.resultType !== http.HttpDataType.ARRAY_BUFFER) return null;
      return response.result as ArrayBuffer;
    } catch (error) {
      const err = error as BusinessError;
      Http.lastError = err.message || '音频下载失败';
      return null;
    } finally {
      httpInst.destroy();
    }
  }
}
