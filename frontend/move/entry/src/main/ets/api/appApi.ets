import { Http } from './http';

type Json = Record<string, Object>;

interface MessageRequest { message: string; }
interface IdRequest { id: string; }
interface TextRequest { text: string; }
interface VoiceTextRequest { text: string; }
interface DoorRequest { action: string; doorPassword?: string; }
interface PasswordRequest { password: string; }
interface RagRequest { query: string; n_results: number; }
interface TtsRequest { text: string; voice?: string; }
interface KeyRevokeRequest { id: string; }
interface DeviceIdRequest { deviceId: string; }

export class AppApi {
  private static async getJson<T>(path: string): Promise<T | null> {
    const raw = await Http.get(path);
    if (!raw) return null;
    try { return JSON.parse(raw) as T; } catch (_) { return null; }
  }

  private static async postJson<T>(path: string, body: object): Promise<T | null> {
    const raw = await Http.post(path, body);
    if (!raw) return null;
    try { return JSON.parse(raw) as T; } catch (_) { return null; }
  }

  static devices(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/devices'); }
  static device(id: string): Promise<Json | null> {
    return AppApi.getJson<Json>(`/api/app/devices/${encodeURIComponent(id)}`);
  }
  static sensors(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/sensors'); }
  static sensorHistory(sensorId: string, hours: number = 24): Promise<Json | null> {
    return AppApi.getJson<Json>(`/api/app/sensors/history?sensorId=${encodeURIComponent(sensorId)}&hours=${hours}`);
  }
  static scenes(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/scenes'); }
  static activateScene(id: string): Promise<Json | null> {
    const body: Record<string, string> = {};
    return AppApi.postJson<Json>(`/api/app/scenes/${encodeURIComponent(id)}/activate`, body);
  }

  static aiIntent(message: string): Promise<Json | null> {
    const body: MessageRequest = { message };
    return AppApi.postJson<Json>('/api/app/ai/intent', body);
  }
  static aiExecute(message: string): Promise<Json | null> {
    const body: MessageRequest = { message };
    return AppApi.postJson<Json>('/api/app/ai/execute', body);
  }
  static aiCapabilities(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/capabilities'); }
  static aiAnomaly(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/anomaly'); }
  static aiRecommendations(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/recommendations'); }
  static aiAcceptRecommendation(id: string): Promise<Json | null> {
    const body: IdRequest = { id };
    return AppApi.postJson<Json>('/api/app/ai/recommendation/accept', body);
  }
  static aiDismissRecommendation(id: string): Promise<Json | null> {
    const body: IdRequest = { id };
    return AppApi.postJson<Json>('/api/app/ai/recommendation/dismiss', body);
  }
  static aiHabitStats(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/habit/stats'); }
  static aiEnergy(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/energy'); }
  static aiEnergyWaste(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/energy/waste'); }
  static aiEnergyReport(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/energy/report'); }
  static aiLinkageRules(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/linkage/rules'); }
  static aiLinkageLog(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/linkage/log'); }
  static aiEmotion(message: string): Promise<Json | null> {
    const body: MessageRequest = { message };
    return AppApi.postJson<Json>('/api/app/ai/emotion', body);
  }
  static aiContext(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/context'); }
  static aiContextClear(): Promise<Json | null> {
    const body: Record<string, string> = {};
    return AppApi.postJson<Json>('/api/app/ai/context/clear', body);
  }
  static aiDevices(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/ai/devices'); }
  static aiRegisterDevice(device: Json): Promise<Json | null> {
    return AppApi.postJson<Json>('/api/app/ai/device/register', device);
  }
  static aiUnregisterDevice(deviceId: string): Promise<Json | null> {
    const body: DeviceIdRequest = { deviceId };
    return AppApi.postJson<Json>('/api/app/ai/device/unregister', body);
  }

  static chat(message: string): Promise<Json | null> {
    const body: MessageRequest = { message };
    return AppApi.postJson<Json>('/api/app/chat/send', body);
  }
  static voiceInput(text: string): Promise<Json | null> {
    const body: VoiceTextRequest = { text };
    return AppApi.postJson<Json>('/api/app/voice/input', body);
  }
  static securityEvents(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/security/events'); }
  static securityStats(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/security/stats'); }
  static authStatus(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/security/auth-status'); }
  static doorControl(action: string, doorPassword?: string): Promise<Json | null> {
    const body: DoorRequest = { action };
    if (doorPassword) body.doorPassword = doorPassword;
    return AppApi.postJson<Json>('/api/app/door/control', body);
  }
  static verifyDoorPassword(password: string): Promise<Json | null> {
    const body: PasswordRequest = { password };
    return AppApi.postJson<Json>('/api/app/security/door-password-verify', body);
  }
  static check(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/check'); }
  static hardwareStatus(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/hardware/status'); }
  static serverStatus(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/server/status'); }

  static ttsConfig(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/tts/config'); }
  static ttsList(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/tts/list'); }
  static ttsTextMap(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/tts/text_map'); }
  static ttsCache(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/tts/cache'); }
  static ttsSpeak(text: string, voice?: string): Promise<Json | null> {
    const body: TtsRequest = { text };
    if (voice) body.voice = voice;
    return AppApi.postJson<Json>('/api/app/tts/speak', body);
  }
  static ttsTest(text: string): Promise<Json | null> {
    const body: TextRequest = { text };
    return AppApi.postJson<Json>('/api/app/tts/test', body);
  }
  static ttsAudioPath(file: string): string {
    return `/api/app/tts/audio/${encodeURIComponent(file)}`;
  }
  static ttsAudio(file: string): Promise<ArrayBuffer | null> {
    return Http.getBinary(AppApi.ttsAudioPath(file));
  }

  static profile(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/user/profile'); }
  static updateProfile(profile: Json): Promise<Json | null> {
    return AppApi.postJson<Json>('/api/app/user/profile', profile);
  }
  static cameras(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/cameras'); }
  static alerts(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/alerts'); }
  static operations(): Promise<Json[] | null> { return AppApi.getJson<Json[]>('/api/app/operations'); }
  static stats(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/stats'); }
  static ragStats(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/rag/stats'); }
  static ragSearch(query: string, results: number = 5): Promise<Json | null> {
    const body: RagRequest = { query, n_results: results };
    return AppApi.postJson<Json>('/api/app/rag/search', body);
  }
  static protocolsStatus(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/protocols/status'); }

  static remoteKeys(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/remote/keys'); }
  static remoteCreateKey(body: Json): Promise<Json | null> {
    return AppApi.postJson<Json>('/api/app/remote/keys/create', body);
  }
  static remoteRevokeKey(id: string): Promise<Json | null> {
    const body: KeyRevokeRequest = { id };
    return AppApi.postJson<Json>('/api/app/remote/keys/revoke', body);
  }
  static remoteAccessLog(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/remote/access-log'); }
  static remoteCryptoStatus(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/remote/crypto/status'); }
  static remoteCryptoSelfTest(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/remote/crypto/self-test'); }
  static remoteRotateSm4(): Promise<Json | null> {
    const body: Record<string, string> = {};
    return AppApi.postJson<Json>('/api/app/remote/crypto/rotate-sm4', body);
  }
  static remoteRegisterPubkey(body: Json): Promise<Json | null> {
    return AppApi.postJson<Json>('/api/app/remote/crypto/register-pubkey', body);
  }
  static securityTest(): Promise<Json | null> { return AppApi.getJson<Json>('/api/app/security/test'); }
}
