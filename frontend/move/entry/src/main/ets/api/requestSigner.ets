import { cryptoFramework } from '@kit.CryptoArchitectureKit';
import { util } from '@kit.ArkTS';

export class RequestSigner {
  private static bytes(value: string): Uint8Array {
    return new util.TextEncoder().encodeInto(value);
  }

  private static blob(value: string): cryptoFramework.DataBlob {
    const result: cryptoFramework.DataBlob = { data: RequestSigner.bytes(value) };
    return result;
  }

  private static hex(data: Uint8Array): string {
    let output = '';
    for (let index = 0; index < data.length; index++) {
      const value = data[index].toString(16);
      output += value.length === 1 ? `0${value}` : value;
    }
    return output;
  }

  private static async digest(algorithm: string, value: string): Promise<string> {
    const md = cryptoFramework.createMd(algorithm);
    await md.update(RequestSigner.blob(value));
    return RequestSigner.hex((await md.digest()).data);
  }

  private static async hmac(algorithm: string, key: string, value: string): Promise<string> {
    const keyGenerator = cryptoFramework.createSymKeyGenerator('HMAC');
    const symKey = await keyGenerator.convertKey(RequestSigner.blob(key));
    const spec: cryptoFramework.HmacSpec = { algName: 'HMAC', mdName: algorithm };
    const mac = cryptoFramework.createMac(spec);
    await mac.init(symKey);
    await mac.update(RequestSigner.blob(value));
    return RequestSigner.hex((await mac.doFinal()).data);
  }

  private static async signature(accessToken: string, method: string, path: string,
    timestamp: string, nonce: string, bodyText: string, algorithm: string): Promise<string> {
    const secret = (await RequestSigner.digest(algorithm, `${accessToken}:app-sign`)).slice(0, 32);
    const base = `${method.toUpperCase()}\n${path}\n${timestamp}\n${nonce}\n${bodyText}`;
    return RequestSigner.hmac(algorithm, secret, base);
  }

  static async headers(accessToken: string, method: string, path: string,
    bodyText: string): Promise<Record<string, string>> {
    const timestamp = `${Date.now()}`;
    const nonce = RequestSigner.hex(cryptoFramework.createRandom().generateRandomSync(8).data);
    let signature = '';
    try {
      signature = await RequestSigner.signature(accessToken, method, path, timestamp, nonce, bodyText, 'SM3');
    } catch (_) {
      signature = await RequestSigner.signature(accessToken, method, path, timestamp, nonce, bodyText, 'SHA256');
    }
    const headers: Record<string, string> = {};
    headers['X-App-Timestamp'] = timestamp;
    headers['X-App-Nonce'] = nonce;
    headers['X-App-Signature'] = signature;
    return headers;
  }
}
