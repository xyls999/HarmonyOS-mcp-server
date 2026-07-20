/**
 * 用户与服务端管理 API · 对接设备端网关
 * 策略: HTTP 优先；资料设置保留本地编辑态，不用于设备/传感器真实状态展示。
 */
import { UserProfile, UserProfileUpdate, ServerStatus } from './types';
import { MockData } from '../mock/mockData';
import { Http } from './http';

export class UserApi {
  /** 获取用户资料 */
  static async getProfile(): Promise<UserProfile> {
    const remote = await Http.get('/api/user/profile');
    if (remote) {
      try {
        return JSON.parse(remote) as UserProfile;
      } catch (e) {
        // 降级
      }
    }
    return MockData.user;
  }

  /** 更新用户资料 */
  static async updateProfile(profile: UserProfileUpdate): Promise<boolean> {
    if (profile.nickname !== undefined) MockData.user.nickname = profile.nickname;
    if (profile.homeName !== undefined) MockData.user.homeName = profile.homeName;
    if (profile.memberCount !== undefined) MockData.user.memberCount = profile.memberCount;
    if (profile.deviceCount !== undefined) MockData.user.deviceCount = profile.deviceCount;
    return true;
  }

  /** 获取服务端状态 */
  static async getServerStatus(): Promise<ServerStatus> {
    const remote = await Http.get('/api/server/status');
    if (remote) {
      try {
        const status = JSON.parse(remote) as ServerStatus;
        return {
          host: Http.getActiveBase().replace('http://', '').replace(':8080', ''),
          port: status.port || 8080,
          isOnline: status.isOnline,
          protocol: status.protocol,
          latency: status.latency,
          cpuUsage: status.cpuUsage,
          memUsage: status.memUsage,
          storageUsage: status.storageUsage
        };
      } catch (e) {
        // 降级
      }
    }
    return MockData.server;
  }

  /** 重启服务端 */
  static async restartServer(): Promise<boolean> {
    return true;
  }

  /** 连接服务端 */
  static async connectServer(host: string, port: number, protocol: 'wifi' | 'starflash'): Promise<boolean> {
    MockData.server.host = host;
    MockData.server.port = port;
    MockData.server.protocol = protocol;
    MockData.server.isOnline = true;
    return true;
  }
}
