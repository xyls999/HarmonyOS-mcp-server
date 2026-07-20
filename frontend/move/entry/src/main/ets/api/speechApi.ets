import { abilityAccessCtrl, common, Permissions } from '@kit.AbilityKit';
import { speechRecognizer } from '@kit.CoreSpeechKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const MICROPHONE_PERMISSION: Permissions = 'ohos.permission.MICROPHONE';

export interface SpeechCallbacks {
  onResult: (text: string, isFinal: boolean) => void;
  onComplete: () => void;
  onError: (message: string) => void;
}

export class SpeechApi {
  private engine: speechRecognizer.SpeechRecognitionEngine | null = null;
  private callbacks: SpeechCallbacks | null = null;
  private sessionId: string = '';
  private isRecording: boolean = false;

  async start(context: common.Context, callbacks: SpeechCallbacks): Promise<boolean> {
    if (this.isRecording) return true;

    this.callbacks = callbacks;
    if (!await this.requestMicrophonePermission(context)) {
      this.callbacks = null;
      callbacks.onError('未获得麦克风权限，请在系统设置中允许访问麦克风');
      return false;
    }

    try {
      hilog.info(0x0000, 'SmartHomeSpeech', 'microphone permission granted, creating engine');
      const engineExtraParams: Record<string, Object> = {
        'locate': 'CN',
        'recognizerMode': 'short'
      };
      const engineParams: speechRecognizer.CreateEngineParams = {
        language: 'zh-CN',
        online: 1,
        extraParams: engineExtraParams
      };
      this.engine = await speechRecognizer.createEngine(engineParams);
      hilog.info(0x0000, 'SmartHomeSpeech', 'speech engine created');
      this.sessionId = `speech_${Date.now()}`;

      const listener: speechRecognizer.RecognitionListener = {
        onStart: (_sessionId: string, _eventMessage: string): void => {
          hilog.info(0x0000, 'SmartHomeSpeech', 'recognition session started');
        },
        onEvent: (_sessionId: string, eventCode: number, _eventMessage: string): void => {
          hilog.info(0x0000, 'SmartHomeSpeech', 'recognition event=%{public}d', eventCode);
        },
        onResult: (_sessionId: string, result: speechRecognizer.SpeechRecognitionResult): void => {
          const currentCallbacks = this.callbacks;
          if (currentCallbacks && result.result) {
            hilog.info(0x0000, 'SmartHomeSpeech', 'recognition result length=%{public}d final=%{public}s',
              result.result.length, result.isFinal ? 'true' : 'false');
            currentCallbacks.onResult(result.result, result.isFinal);
          }
        },
        onComplete: (_sessionId: string, _eventMessage: string): void => {
          this.completeRecognition();
        },
        onError: (_sessionId: string, errorCode: number, errorMessage: string): void => {
          hilog.error(0x0000, 'SmartHomeSpeech', 'recognition error code=%{public}d message=%{public}s', errorCode,
            errorMessage);
          this.failRecognition(`语音识别失败（${errorCode}）：${errorMessage}`);
        }
      };
      this.engine.setListener(listener);

      const startExtraParams: Record<string, Object> = {
        'recognitionMode': 0,
        'vadBegin': 10000,
        'vadEnd': 1200,
        'maxAudioDuration': 60000
      };
      const startParams: speechRecognizer.StartParams = {
        sessionId: this.sessionId,
        audioInfo: {
          audioType: 'pcm',
          sampleRate: 16000,
          soundChannel: 1,
          sampleBit: 16
        },
        extraParams: startExtraParams
      };
      this.isRecording = true;
      this.engine.startListening(startParams);
      hilog.info(0x0000, 'SmartHomeSpeech', 'system microphone recognition requested');
      return true;
    } catch (error) {
      const speechError = error as BusinessError;
      hilog.error(0x0000, 'SmartHomeSpeech', 'start failed code=%{public}d message=%{public}s',
        speechError.code ?? -1, speechError.message ?? 'unknown');
      this.isRecording = false;
      this.shutdownEngine();
      this.callbacks = null;
      callbacks.onError(`无法启动语音识别（${speechError.code ?? '未知错误'}）`);
      return false;
    }
  }

  async stop(): Promise<void> {
    if (!this.isRecording) return;

    this.isRecording = false;

    try {
      if (this.engine && this.sessionId) {
        this.engine.finish(this.sessionId);
      }
    } catch (_) {
      this.failRecognition('结束语音识别失败，请重试');
    }
  }

  async cancel(): Promise<void> {
    this.isRecording = false;

    try {
      if (this.engine && this.sessionId) {
        this.engine.cancel(this.sessionId);
      }
    } catch (_) {}
    this.shutdownEngine();
    this.callbacks = null;
  }

  private async requestMicrophonePermission(context: common.Context): Promise<boolean> {
    try {
      const permissions: Array<Permissions> = [MICROPHONE_PERMISSION];
      const result = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(context, permissions);
      const granted = result.authResults.length > 0 && result.authResults[0] === 0;
      hilog.info(0x0000, 'SmartHomeSpeech', 'microphone permission=%{public}s', granted ? 'granted' : 'denied');
      return granted;
    } catch (error) {
      const permissionError = error as BusinessError;
      hilog.error(0x0000, 'SmartHomeSpeech', 'permission request failed code=%{public}d message=%{public}s',
        permissionError.code ?? -1, permissionError.message ?? 'unknown');
      return false;
    }
  }

  private completeRecognition(): void {
    const currentCallbacks = this.callbacks;
    this.callbacks = null;
    this.isRecording = false;
    this.shutdownEngine();
    if (currentCallbacks) currentCallbacks.onComplete();
  }

  private failRecognition(message: string): void {
    const currentCallbacks = this.callbacks;
    this.callbacks = null;
    this.isRecording = false;
    this.shutdownEngine();
    if (currentCallbacks) currentCallbacks.onError(message);
  }

  private shutdownEngine(): void {
    const currentEngine = this.engine;
    this.engine = null;
    this.sessionId = '';
    if (!currentEngine) return;
    try { currentEngine.shutdown(); } catch (_) {}
  }
}
