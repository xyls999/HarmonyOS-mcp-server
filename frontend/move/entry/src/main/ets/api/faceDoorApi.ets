import { http } from '@kit.NetworkKit';
import { util } from '@kit.ArkTS';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

type Json = Record<string, Object>;

const FACE_DOOR_BASE: string = 'https://192.168.1.138:5001';
const FACE_DOOR_CA: string = '-----BEGIN CERTIFICATE-----\n' +
  'MIIC/jCCAeagAwIBAgIUf/lfFA7k2gG30K9OEvhGqnQhfncwDQYJKoZIhvcNAQEL\n' +
  'BQAwJjERMA8GA1UEAwwIRmFjZURvb3IxETAPBgNVBAoMCEZhY2VEb29yMB4XDTI2\n' +
  'MDcxOTA0NDQxN1oXDTI3MDcxOTA0NDQxN1owJjERMA8GA1UEAwwIRmFjZURvb3Ix\n' +
  'ETAPBgNVBAoMCEZhY2VEb29yMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKC\n' +
  'AQEAoRGqTnTTm2NiK1+MBRfawi1EyK/f5AxR8BE22ptvrUewZC6lI4UQZ3ztFc+f\n' +
  'zRHEJgl4BD2QcxSwl8hNhdGYcl7p4cOrhFu+xfGWHWr+NdoiLWij9665s2kzNC2j\n' +
  '74KURzwpGapHC4JXi7SxEA30WKidfqgk1xM0cgg+UD+v+NwbYK6z79TuYtxRvCxe\n' +
  '7Y02whvx1bApDl3+dMjgB1/TBiTnFNa2/TT+VFAGzNPR3UmwfVFUb28KM/rl7i89\n' +
  'um+KW40ctzYqT7lUly6mIt4jCLuCe9VLl1/jq01PaoqwuW/SV0cAg+55V8RTxP0F\n' +
  '1mfXgCBQHe7FC5WoevvesBqRDwIDAQABoyQwIjAgBgNVHREEGTAXgglsb2NhbGhv\n' +
  'c3SHBH8AAAGHBMCoAYowDQYJKoZIhvcNAQELBQADggEBAF1a6VVG+xbJaEQbTZwl\n' +
  'C2OhDRXbkfw8AJNJKQxloZFd/wJCF1GBBqhCQ/x4vBv4O0TLKN8eKsxO8xMuh7dj\n' +
  'roqHwocpthypljGMWAB/e+ql0hkGaaPjjcPOjmTKXFYKy/5h0aRjBUrTzqAp9keV\n' +
  'M5+bu+LtzCH1Og0RjT+WyDqjSPrkO/jfpTwbWLP17+nX8Ovn8qcpY19zl1PTKDCR\n' +
  '690uvRgLJAs4ZbXszFKvANTeNKnpSu9Fi3tw8sbePbXA/UwfrRN+Ba6/9CqSIbGv\n' +
  'nNmnqQcNLWm7d4p4J76VzuwVAiIwBF4B0GNH2YNFaQVry+WAhpRcDIHnMopRyUUq\n' +
  'pPY=\n-----END CERTIFICATE-----';

interface FaceRegisterRequest {
  name: string;
  image: string;
}

interface FaceDeleteRequest {
  name: string;
}

interface RequestHeaders {
  'Content-Type': string;
}

export interface FaceDoorResult {
  success: boolean;
  stage: string;
  recognized: boolean;
  name: string;
  distance: number;
  threshold: number;
  doorState: string;
  error: string;
}

export interface FaceListResult {
  success: boolean;
  faces: string[];
  error: string;
}

export interface FaceDoorStatusResult {
  success: boolean;
  state: string;
  address: string;
  error: string;
}

export interface FaceHealthResult {
  success: boolean;
  facesLoaded: number;
  doorDevice: string;
  error: string;
}

interface RawResult {
  status: number;
  body: string;
  error: string;
}

interface MultipartData {
  body: ArrayBuffer;
  contentType: string;
}

interface DoorPayload {
  state?: Object;
  ip?: Object;
  port?: Object;
}

export class FaceDoorApi {
  private static readonly TIMEOUT: number = 10000;

  private static stringValue(value: Object | undefined): string {
    return typeof value === 'string' ? value : '';
  }

  private static numberValue(value: Object | undefined): number {
    return typeof value === 'number' ? value : 0;
  }

  private static boolValue(value: Object | undefined): boolean {
    return value === true;
  }

  private static parse(body: string): Json {
    try { return JSON.parse(body) as Json; } catch (_) { return {}; }
  }

  private static errorMessage(value: Json, fallback: string): string {
    const error = FaceDoorApi.stringValue(value.error);
    return error || fallback;
  }

  private static async request(path: string, method: http.RequestMethod, data?: string | ArrayBuffer,
    contentType: string = 'application/json'): Promise<RawResult> {
    const headers: RequestHeaders = { 'Content-Type': contentType };
    const options: http.HttpRequestOptions = {
      method,
      connectTimeout: FaceDoorApi.TIMEOUT,
      readTimeout: FaceDoorApi.TIMEOUT,
      header: headers,
      caData: FACE_DOOR_CA
    };
    if (data !== undefined) options.extraData = data;
    const client = http.createHttp();
    try {
      const response = await client.request(FACE_DOOR_BASE + path, options);
      const body = typeof response.result === 'string' ? response.result : JSON.stringify(response.result);
      const status = Number(response.responseCode);
      hilog.info(0x0000, 'FaceDoorApi', '%{public}s status=%{public}d', path, status);
      if (status >= 200 && status < 300) return { status, body, error: '' };
      const value = FaceDoorApi.parse(body);
      return { status, body, error: FaceDoorApi.errorMessage(value, `请求失败 (${status})`) };
    } catch (error) {
      const err = error as BusinessError;
      const timeout = err.message.toLowerCase().includes('timeout') || err.message.includes('超时');
      hilog.warn(0x0000, 'FaceDoorApi', '%{public}s failed: %{public}s', path, err.message);
      return { status: 0, body: '', error: timeout ? '门禁响应超时' : '无法连接人脸门禁服务' };
    } finally {
      client.destroy();
    }
  }

  private static multipart(imageData: ArrayBuffer): MultipartData {
    const boundary = `HarmonyFaceDoor${Date.now()}`;
    const prefix = `--${boundary}\r\nContent-Disposition: form-data; name="image"; filename="face.jpg"\r\n` +
      'Content-Type: image/jpeg\r\n\r\n';
    const suffix = `\r\n--${boundary}--\r\n`;
    const encoder = new util.TextEncoder();
    const head = encoder.encodeInto(prefix);
    const tail = encoder.encodeInto(suffix);
    const imageBytes = new Uint8Array(imageData);
    const merged = new Uint8Array(head.length + imageBytes.length + tail.length);
    merged.set(head, 0);
    merged.set(imageBytes, head.length);
    merged.set(tail, head.length + imageBytes.length);
    const body = merged.buffer as ArrayBuffer;
    const result: MultipartData = { body, contentType: `multipart/form-data; boundary=${boundary}` };
    return result;
  }

  private static faceResult(raw: RawResult): FaceDoorResult {
    if (!raw.body) {
      return { success: false, stage: '', recognized: false, name: '', distance: 0,
        threshold: 0, doorState: '', error: raw.error };
    }
    const value = FaceDoorApi.parse(raw.body);
    return {
      success: FaceDoorApi.boolValue(value.success),
      stage: FaceDoorApi.stringValue(value.stage),
      recognized: FaceDoorApi.boolValue(value.recognized),
      name: FaceDoorApi.stringValue(value.name),
      distance: FaceDoorApi.numberValue(value.distance),
      threshold: FaceDoorApi.numberValue(value.threshold),
      doorState: FaceDoorApi.stringValue(value.door_state),
      error: FaceDoorApi.errorMessage(value, raw.error || '门禁未返回有效结果')
    };
  }

  static async openDoor(imageData: ArrayBuffer): Promise<FaceDoorResult> {
    const part = FaceDoorApi.multipart(imageData);
    return FaceDoorApi.faceResult(await FaceDoorApi.request('/api/door/open', http.RequestMethod.POST,
      part.body, part.contentType));
  }

  static async recognize(imageData: ArrayBuffer): Promise<FaceDoorResult> {
    const part = FaceDoorApi.multipart(imageData);
    return FaceDoorApi.faceResult(await FaceDoorApi.request('/api/recognize', http.RequestMethod.POST,
      part.body, part.contentType));
  }

  static async register(name: string, imageData: ArrayBuffer): Promise<FaceDoorResult> {
    const base64 = new util.Base64Helper().encodeToStringSync(new Uint8Array(imageData));
    const body: FaceRegisterRequest = { name, image: `data:image/jpeg;base64,${base64}` };
    const raw = await FaceDoorApi.request('/api/faces/register', http.RequestMethod.POST, JSON.stringify(body));
    return FaceDoorApi.faceResult(raw);
  }

  static async deleteFace(name: string): Promise<FaceDoorResult> {
    const body: FaceDeleteRequest = { name };
    return FaceDoorApi.faceResult(await FaceDoorApi.request('/api/faces/delete', http.RequestMethod.POST,
      JSON.stringify(body)));
  }

  static async reload(): Promise<FaceHealthResult> {
    const raw = await FaceDoorApi.request('/api/faces/reload', http.RequestMethod.POST, '{}');
    const value = FaceDoorApi.parse(raw.body);
    return { success: FaceDoorApi.boolValue(value.success),
      facesLoaded: FaceDoorApi.numberValue(value.faces_loaded), doorDevice: '',
      error: FaceDoorApi.errorMessage(value, raw.error) };
  }

  static async listFaces(): Promise<FaceListResult> {
    const raw = await FaceDoorApi.request('/api/faces', http.RequestMethod.GET);
    const value = FaceDoorApi.parse(raw.body);
    const faces: string[] = [];
    if (Array.isArray(value.faces)) {
      (value.faces as Object[]).forEach((item: Object): void => {
        if (typeof item === 'string') faces.push(item);
      });
    }
    return { success: raw.status === 200, faces, error: raw.error };
  }

  static async doorStatus(): Promise<FaceDoorStatusResult> {
    const raw = await FaceDoorApi.request('/api/door/status', http.RequestMethod.GET);
    const value = FaceDoorApi.parse(raw.body);
    const door: DoorPayload = typeof value.door === 'object' && value.door !== null ?
      value.door as DoorPayload : {};
    const ip = FaceDoorApi.stringValue(door.ip);
    const port = FaceDoorApi.numberValue(door.port);
    return { success: FaceDoorApi.boolValue(value.success), state: FaceDoorApi.stringValue(door.state),
      address: ip && port ? `${ip}:${port}` : '', error: FaceDoorApi.errorMessage(value, raw.error) };
  }

  static async health(): Promise<FaceHealthResult> {
    const raw = await FaceDoorApi.request('/api/health', http.RequestMethod.GET);
    const value = FaceDoorApi.parse(raw.body);
    return { success: FaceDoorApi.stringValue(value.status) === 'ok',
      facesLoaded: FaceDoorApi.numberValue(value.faces_in_db),
      doorDevice: FaceDoorApi.stringValue(value.door_device),
      error: FaceDoorApi.errorMessage(value, raw.error) };
  }
}
