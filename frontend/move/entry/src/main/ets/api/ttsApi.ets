import { textToSpeech } from '@kit.CoreSpeechKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

export class TtsApi {
  private engine: textToSpeech.TextToSpeechEngine | null = null;
  private createTask: Promise<boolean> | null = null;

  private async createEngineForMode(online: number): Promise<textToSpeech.TextToSpeechEngine | null> {
    try {
      const params: textToSpeech.CreateEngineParams = {
        language: 'zh-CN',
        person: 0,
        online
      };
      return await textToSpeech.createEngine(params);
    } catch (error) {
      const err = error as BusinessError;
      hilog.warn(0x0000, 'SmartHomeTts', 'mode=%{public}d failed=%{public}d %{public}s',
        online, err.code ?? -1, err.message);
      return null;
    }
  }

  private async createEngine(): Promise<boolean> {
    try {
      const engine = await this.createEngineForMode(1) || await this.createEngineForMode(0);
      if (!engine) return false;
      const listener: textToSpeech.SpeakListener = {
        onStart: (_requestId: string, _response: textToSpeech.StartResponse): void => {
          hilog.info(0x0000, 'SmartHomeTts', 'speech started');
        },
        onComplete: (_requestId: string, _response: textToSpeech.CompleteResponse): void => {
          hilog.info(0x0000, 'SmartHomeTts', 'speech completed');
        },
        onStop: (_requestId: string, _response: textToSpeech.StopResponse): void => {
          hilog.info(0x0000, 'SmartHomeTts', 'speech stopped');
        },
        onError: (_requestId: string, errorCode: number, errorMessage: string): void => {
          hilog.error(0x0000, 'SmartHomeTts', 'speech error=%{public}d %{public}s', errorCode, errorMessage);
        }
      };
      engine.setListener(listener);
      this.engine = engine;
      return true;
    } catch (error) {
      const err = error as BusinessError;
      hilog.error(0x0000, 'SmartHomeTts', 'create failed=%{public}d %{public}s', err.code ?? -1, err.message);
      return false;
    }
  }

  private async ensureEngine(): Promise<boolean> {
    if (this.engine) return true;
    if (!this.createTask) this.createTask = this.createEngine();
    const ready = await this.createTask;
    this.createTask = null;
    return ready;
  }

  async speak(text: string): Promise<boolean> {
    const content = text.trim();
    if (!content || !await this.ensureEngine() || !this.engine) return false;
    try {
      if (this.engine.isBusy()) this.engine.stop();
      const params: textToSpeech.SpeakParams = { requestId: `tts_${Date.now()}` };
      this.engine.speak(content, params);
      return true;
    } catch (error) {
      const err = error as BusinessError;
      hilog.error(0x0000, 'SmartHomeTts', 'speak failed=%{public}d %{public}s', err.code ?? -1, err.message);
      return false;
    }
  }

  stop(): void {
    try {
      if (this.engine?.isBusy()) this.engine.stop();
    } catch (_) {}
  }

  shutdown(): void {
    const engine = this.engine;
    this.engine = null;
    this.createTask = null;
    if (!engine) return;
    try { engine.shutdown(); } catch (_) {}
  }
}
