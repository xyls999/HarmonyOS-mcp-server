/** A9 v6.1 网关公开状态与安全能力。 */
import { Http } from './http';

interface HealthResponse {
  ok?: boolean;
  v?: number | string;
  hardware?: boolean;
  crypto?: string;
  intent_engine?: boolean;
}

interface PublicKeyResponse {
  device_id?: string;
  sm2_public_key?: string;
  sm4_key_fingerprint?: string;
  supported_algorithms?: string[];
  envelope_version?: number;
}

export interface GatewayHealth {
  available: boolean;
  ok: boolean;
  version: string;
  hardware: boolean;
  crypto: string;
  intentEngine: boolean;
}

export interface GatewayPublicKey {
  available: boolean;
  deviceId: string;
  sm2PublicKey: string;
  sm4KeyFingerprint: string;
  supportedAlgorithms: string[];
  envelopeVersion: number;
}

export interface ProtocolCatalog {
  available: boolean;
  protocols: string[];
  encryptedProtocols: string[];
  adapterCount: number;
}

export class GatewayApi {
  static async getHealth(): Promise<GatewayHealth> {
    const empty: GatewayHealth = {
      available: false, ok: false, version: '', hardware: false, crypto: '', intentEngine: false
    };
    const text = await Http.get('/health');
    if (!text) return empty;
    try {
      const data = JSON.parse(text) as HealthResponse;
      return {
        available: true,
        ok: data.ok === true,
        version: data.v === undefined ? '' : `${data.v}`,
        hardware: data.hardware === true,
        crypto: data.crypto || '',
        intentEngine: data.intent_engine === true
      };
    } catch (e) {
      return empty;
    }
  }

  static async getPublicKey(): Promise<GatewayPublicKey> {
    const empty: GatewayPublicKey = {
      available: false, deviceId: '', sm2PublicKey: '', sm4KeyFingerprint: '',
      supportedAlgorithms: [], envelopeVersion: 0
    };
    const text = await Http.get('/api/auth/public-key');
    if (!text) return empty;
    try {
      const data = JSON.parse(text) as PublicKeyResponse;
      if (!data.device_id || !data.sm2_public_key) return empty;
      return {
        available: true,
        deviceId: data.device_id,
        sm2PublicKey: data.sm2_public_key,
        sm4KeyFingerprint: data.sm4_key_fingerprint || '',
        supportedAlgorithms: data.supported_algorithms || [],
        envelopeVersion: data.envelope_version || 0
      };
    } catch (e) {
      return empty;
    }
  }

  static async getProtocolStatus(): Promise<Object | null> {
    return GatewayApi.getObject('/api/protocols/status');
  }

  /** 协议与适配器目录：用于设置页现场演示，不返回地址和密钥。 */
  static async getProtocolCatalog(): Promise<ProtocolCatalog> {
    const empty: ProtocolCatalog = { available: false, protocols: [], encryptedProtocols: [], adapterCount: 0 };
    const text = await Http.get('/api/protocols/catalog');
    if (!text) return empty;
    try {
      const data = JSON.parse(text) as Record<string, Object>;
      const protocolMap = data.protocols as Record<string, Object> | undefined;
      const names: string[] = ['http', 'https', 'websocket', 'mqtt', 'coap'];
      const protocols: string[] = [];
      const encrypted: string[] = [];
      for (let i = 0; i < names.length; i++) {
        const profile = protocolMap ? protocolMap[names[i]] as Record<string, Object> | undefined : undefined;
        if (profile) {
          protocols.push(names[i]);
          if (profile.encrypted === true) encrypted.push(names[i]);
        }
      }
      const adapters = data.adapters as Array<Object> | undefined;
      return {
        available: protocols.length > 0,
        protocols: protocols,
        encryptedProtocols: encrypted,
        adapterCount: adapters ? adapters.length : 0
      };
    } catch (e) {
      return empty;
    }
  }

  static async getSystemCheck(): Promise<Object | null> {
    return GatewayApi.getObject('/api/check');
  }

  private static async getObject(path: string): Promise<Object | null> {
    const text = await Http.get(path);
    if (!text) return null;
    try {
      return JSON.parse(text) as Object;
    } catch (e) {
      return null;
    }
  }
}
