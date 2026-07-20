import { Http, HttpResult } from './http';
import { hilog } from '@kit.PerformanceAnalysisKit';

type Json = Record<string, Object>;

interface LoginRequest { nickname: string; password: string; }
interface LogoutRequest { refresh_token: string; }

export interface AuthActionResult {
  success: boolean;
  message: string;
}

interface ProfileUpdateRequest {
  nickname: string;
}

export interface AppUserAccount {
  id: string;
  nickname: string;
  role: string;
  allowed: boolean;
  allowedDevices: string[];
  createdAt: string;
  updatedAt: string;
}

export interface UserLoginRecord {
  id: string;
  loginAt: string;
  ip: string;
  userAgent: string;
  success: boolean;
}

export class AuthApi {
  private static currentUser: AppUserAccount | null = null;

  private static result(success: boolean, message: string): AuthActionResult {
    return { success, message };
  }

  private static message(response: HttpResult, fallback: string): string {
    if (response.offline) return '设备网关离线';
    if (!response.body) return response.error || fallback;
    try {
      const value = JSON.parse(response.body) as Json;
      if (typeof value.message === 'string') return value.message;
      if (typeof value.error === 'string') return value.error;
    } catch (_) {}
    return response.error || fallback;
  }

  private static allowedDevices(value: Object | undefined): string[] {
    if (!Array.isArray(value)) return [];
    return value.filter((item: Object): boolean => typeof item === 'string') as string[];
  }

  private static normalizeUser(raw: Json): AppUserAccount {
    return {
      id: typeof raw.id === 'string' ? raw.id : '',
      nickname: typeof raw.nickname === 'string' ? raw.nickname : '未命名用户',
      role: typeof raw.role === 'string' ? raw.role : 'guest',
      allowed: raw.allowed === true || raw.allowed === 1,
      allowedDevices: AuthApi.allowedDevices(raw.allowed_devices),
      createdAt: typeof raw.created_at === 'string' ? raw.created_at : '',
      updatedAt: typeof raw.updated_at === 'string' ? raw.updated_at : ''
    };
  }

  static getCurrentUser(): AppUserAccount | null { return AuthApi.currentUser; }

  static async restoreUser(): Promise<AppUserAccount | null> {
    await Http.initialize();
    if (!Http.hasSession()) return null;
    const response = await Http.getResult('/api/app/auth/me');
    if (response.status !== 200) return null;
    try {
      const value = JSON.parse(response.body) as Json;
      if (typeof value.user !== 'object') return null;
      AuthApi.currentUser = AuthApi.normalizeUser(value.user as Json);
      AppStorage.setOrCreate<boolean>('isAuthenticated', AuthApi.currentUser.allowed);
      return AuthApi.currentUser;
    } catch (_) { return null; }
  }

  static async authenticateUser(nickname: string, password: string): Promise<AuthActionResult> {
    Http.clearSession(false);
    const body: LoginRequest = { nickname, password };
    const response = await Http.postResult('/api/app/auth/login', body, false);
    hilog.info(0x0000, 'SmartHomeAuth', 'login status=%{public}d', response.status);
    if (response.status === 401) return AuthApi.result(false, '账号或密码错误');
    if (response.status === 429) return AuthApi.result(false, '登录操作过于频繁，请稍后再试');
    if (response.status !== 200) return AuthApi.result(false, AuthApi.message(response, '暂时无法登录，请稍后重试'));
    try {
      const value = JSON.parse(response.body) as Json;
      if (value.success !== true || typeof value.user !== 'object' ||
        typeof value.access_token !== 'string' || typeof value.refresh_token !== 'string') {
        return AuthApi.result(false, '服务器返回了无效的登录信息');
      }
      AuthApi.currentUser = AuthApi.normalizeUser(value.user as Json);
      if (!AuthApi.currentUser.allowed) {
        AuthApi.currentUser = null;
        return AuthApi.result(false, '该应用账号已被停用');
      }
      const expiresIn = typeof value.expires_in === 'number' ? value.expires_in : 7200;
      await Http.setSession(value.access_token, value.refresh_token, expiresIn);
      AppStorage.setOrCreate<string>('authUserId', AuthApi.currentUser.id);
      AppStorage.setOrCreate<boolean>('isAuthenticated', true);
      return AuthApi.result(true, '登录成功');
    } catch (_) { return AuthApi.result(false, '服务器返回了无法识别的用户信息'); }
  }

  static async getLoginRecords(): Promise<UserLoginRecord[]> {
    if (!AuthApi.currentUser) await AuthApi.restoreUser();
    if (!AuthApi.currentUser) return [];
    const loginTime = Http.getLoginTime();
    if (loginTime <= 0) return [];
    return [{
      id: `${loginTime}`,
      loginAt: new Date(loginTime).toLocaleString(),
      ip: '远程服务',
      userAgent: 'HarmonyOS 应用',
      success: true
    }];
  }

  static async updateProfile(nickname: string): Promise<AuthActionResult> {
    const body: ProfileUpdateRequest = { nickname };
    const response = await Http.postResult('/api/app/user/profile', body);
    if (response.status !== 200) return AuthApi.result(false, AuthApi.message(response, '资料更新失败'));
    await AuthApi.restoreUser();
    return AuthApi.result(true, '资料已更新');
  }

  static async changePassword(_currentPassword: string, _newPassword: string): Promise<AuthActionResult> {
    return AuthApi.result(false, '当前服务端未开放修改密码接口');
  }

  static async deleteAccount(): Promise<AuthActionResult> {
    return AuthApi.result(false, '当前服务端未开放删除账号接口');
  }

  static async logout(): Promise<void> {
    const refreshToken = Http.getRefreshToken();
    if (Http.hasSession()) {
      const body: LogoutRequest = { refresh_token: refreshToken };
      await Http.postResult('/api/app/auth/logout', body, false);
    }
    AuthApi.currentUser = null;
    Http.clearSession();
    AppStorage.setOrCreate<string>('authUserId', '');
  }
}
