/**
 * ChatFlow 对话页 · 经典鸿蒙浅色
 */
import { ChatBubble } from '../components/ChatBubble';
import { ChatApi } from '../api/chatApi';
import { ChatMessage, ChatRole, ChartData } from '../api/types';
import { SpeechApi, SpeechCallbacks } from '../api/speechApi';
import { TtsApi } from '../api/ttsApi';
import { DeviceApi } from '../api/deviceApi';
import { AppContext } from '../api/appContext';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct ChatPage {
  @State messages: ChatMessage[] = [];
  @State inputText: string = '';
  @State isResponding: boolean = false;
  @State isListening: boolean = false;
  @State voiceHint: string = '';
  @State showThinking: boolean = false;
  @State thinkingAngle: number = 0;
  @State thinkingProgress: number = 4;
  @State thinkingTick: number = 0;
  @State thinkingFinishing: boolean = false;
  @State pressedKey: string = '';
  @State feedbackVisible: boolean = false;
  @State feedbackMessageId: string = '';
  @State feedbackScore: number = 0;
  @State feedbackNote: string = '';
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;
  private scroller: Scroller = new Scroller();
  private msgId: number = 1;
  private speechApi: SpeechApi = new SpeechApi();
  private ttsApi: TtsApi = new TtsApi();
  private thinkingStartedAt: number = 0;
  private thinkingTimer: number = -1;
  private thinkingProgressTimer: number = -1;
  private thinkingRunId: number = 0;

  aboutToAppear(): void {
    this.messages = [{
      id: 'msg_0',
      role: ChatRole.ASSISTANT,
      content: ChatApi.getWelcome(),
      timestamp: Date.now()
    }];
    this.restoreHistory();
  }

  private async restoreHistory(): Promise<void> {
    const history = await ChatApi.getHistory();
    if (history.length > 0 && this.messages.length === 1 && this.messages[0].id === 'msg_0') {
      this.messages = history;
      this.scrollToBottom();
    }
  }

  aboutToDisappear(): void {
    this.speechApi.cancel();
    this.ttsApi.shutdown();
    if (this.thinkingTimer >= 0) clearTimeout(this.thinkingTimer);
    if (this.thinkingProgressTimer >= 0) clearTimeout(this.thinkingProgressTimer);
    this.thinkingRunId++;
    this.showThinking = false;
  }

  private touchKey(key: string, event: TouchEvent): void {
    this.pressedKey = event.type === TouchType.Down ? key : '';
  }

  private startThinking(): void {
    if (this.thinkingProgressTimer >= 0) clearTimeout(this.thinkingProgressTimer);
    this.showThinking = true;
    this.thinkingAngle = 0;
    this.thinkingProgress = 4;
    this.thinkingTick = 0;
    this.thinkingFinishing = false;
    this.thinkingStartedAt = Date.now();
    const runId: number = ++this.thinkingRunId;
    this.advanceThinking(runId);
    setTimeout((): void => {
      this.getUIContext().animateTo({ duration: 2200, curve: Curve.Linear, iterations: -1 }, (): void => {
        this.thinkingAngle = 360;
      });
    }, 24);
  }

  private advanceThinking(runId: number): void {
    if (runId !== this.thinkingRunId || !this.showThinking || this.thinkingFinishing) return;
    this.thinkingTick += 1;
    this.thinkingProgress = Math.min(92, 4 + this.thinkingTick * 4);
    this.thinkingProgressTimer = setTimeout((): void => this.advanceThinking(runId), 140);
  }

  private finishThinking(after: () => void): void {
    const remaining: number = Math.max(0, 1800 - (Date.now() - this.thinkingStartedAt));
    const complete = (): void => {
      if (!this.showThinking) return;
      if (this.thinkingProgressTimer >= 0) clearTimeout(this.thinkingProgressTimer);
      this.thinkingRunId++;
      this.thinkingFinishing = true;
      this.thinkingProgress = 100;
      this.thinkingTimer = setTimeout((): void => {
        this.showThinking = false;
        this.thinkingFinishing = false;
        this.thinkingTimer = -1;
        after();
      }, 320);
    };
    if (remaining === 0) complete();
    else this.thinkingTimer = setTimeout(complete, remaining);
  }

  scrollToBottom(): void {
    setTimeout((): void => { this.scroller.scrollEdge(Edge.Bottom); }, 50);
  }

  private async speakResponse(text: string): Promise<void> {
    await this.ttsApi.speak(text);
  }

  async send(): Promise<void> {
    const text = this.inputText.trim();
    if (!text || this.isResponding || this.isListening) return;

    const userMsg: ChatMessage = {
      id: `msg_${this.msgId++}`,
      role: ChatRole.USER,
      content: text,
      timestamp: Date.now()
    };
    this.messages = this.messages.concat([userMsg]);
    this.inputText = '';
    this.scrollToBottom();

    const assistantId = `msg_${this.msgId++}`;
    this.isResponding = true;
    const placeholder: ChatMessage = {
      id: assistantId,
      role: ChatRole.ASSISTANT,
      content: '',
      timestamp: Date.now(),
      isStreaming: true
    };
    this.messages = this.messages.concat([placeholder]);
    this.startThinking();
    this.scrollToBottom();

    await ChatApi.sendStream(
      this.messages.slice(0, -1),
      (partial: string) => {
        this.messages = this.messages.map((m: ChatMessage): ChatMessage =>
          m.id === assistantId ? {
            id: m.id, role: m.role, content: partial, timestamp: m.timestamp, isStreaming: true
          } : m
        );
        this.scrollToBottom();
      },
      (finalMsg: ChatMessage) => {
        if (finalMsg.actions && finalMsg.actions.length > 0) DeviceApi.syncAssistantActions(finalMsg.actions);
        this.messages = this.messages.map((m: ChatMessage): ChatMessage =>
          m.id === assistantId ? {
            id: assistantId, role: finalMsg.role, content: finalMsg.content,
            timestamp: finalMsg.timestamp, isStreaming: false,
            chartData: finalMsg.chartData,
            ttsAudio: finalMsg.ttsAudio,
            imageUrl: finalMsg.imageUrl,
            isError: finalMsg.isError,
            sceneName: finalMsg.sceneName,
            actions: finalMsg.actions,
            feedbackScore: finalMsg.feedbackScore
          } : m
        );
        this.finishThinking((): void => {
          this.isResponding = false;
          this.scrollToBottom();
          if (finalMsg.content && !finalMsg.isError) this.speakResponse(finalMsg.content);
        });
      }
    );
  }

  async toggleVoice(): Promise<void> {
    if (this.isResponding) return;
    if (this.isListening) {
      this.voiceHint = '正在完成识别...';
      await this.speechApi.stop();
      return;
    }

    const context = AppContext.abilityContext;
    if (!context) {
      this.voiceHint = '无法访问当前页面的麦克风';
      return;
    }

    this.inputText = '';
    this.isListening = true;
    this.voiceHint = '正在打开麦克风...';
    const callbacks: SpeechCallbacks = {
      onResult: (text: string, isFinal: boolean): void => {
        this.inputText = text;
        this.voiceHint = isFinal ? '已识别，再次点击麦克风结束' : '正在识别...';
      },
      onComplete: (): void => {
        this.isListening = false;
        this.handleSpeechComplete();
      },
      onError: (message: string): void => {
        this.isListening = false;
        this.voiceHint = message;
      }
    };

    const started = await this.speechApi.start(context, callbacks);
    if (started) {
      this.voiceHint = '正在听，请再次点击麦克风结束';
    } else {
      this.isListening = false;
    }
  }

  handleSpeechComplete(): void {
    const text = this.inputText.trim();
    if (!text) {
      this.voiceHint = '未识别到语音，请靠近麦克风重试';
      return;
    }
    this.voiceHint = '语音已转为文字';
  }

  private thinkingLabel(): string {
    if (this.thinkingFinishing) return '已完成';
    if (this.thinkingProgress < 35) return '正在读取';
    if (this.thinkingProgress < 70) return '正在整理';
    return '即将完成';
  }

  private thinkingStep(): number {
    return Math.min(3, Math.floor(this.thinkingProgress / 25));
  }

  private openFeedback(message: ChatMessage): void {
    this.feedbackMessageId = message.id;
    this.feedbackScore = message.feedbackScore || 0;
    this.feedbackNote = '';
    this.feedbackVisible = true;
  }

  private submitFeedback(): void {
    if (!this.feedbackMessageId || this.feedbackScore < 1) return;
    this.messages = this.messages.map((message: ChatMessage): ChatMessage =>
      message.id === this.feedbackMessageId ? {
        id: message.id,
        role: message.role,
        content: message.content,
        timestamp: message.timestamp,
        isStreaming: message.isStreaming,
        chartData: message.chartData,
        ttsAudio: message.ttsAudio,
        imageUrl: message.imageUrl,
        isError: message.isError,
        sceneName: message.sceneName,
        actions: message.actions,
        feedbackScore: this.feedbackScore
      } : message
    );
    this.feedbackVisible = false;
  }

  @Builder
  feedbackDialog() {
    Column({ space: AppSpace.MD }) {
      Row() {
        Text('本次评价').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
          .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
        SymbolGlyph($r('sys.symbol.xmark')).fontSize(18)
          .fontColor([AppColors.textSecondary(this.isDarkTheme)]).width(36).height(36)
          .onClick((): void => { this.feedbackVisible = false; })
      }.width('100%')
      Row({ space: AppSpace.XS }) {
        ForEach([1, 2, 3, 4, 5], (score: number) => {
          Button(`${score}`)
            .layoutWeight(1).height(38).fontSize(AppFont.SIZE_FOOTNOTE).fontWeight(FontWeight.Bold)
            .borderRadius(AppSpace.XS)
            .fontColor(this.feedbackScore === score ? AppColors.onPrimary(this.isDarkTheme) : AppColors.textPrimary(this.isDarkTheme))
            .backgroundColor(this.feedbackScore === score ? AppColors.primary(this.isDarkTheme) : AppColors.group(this.isDarkTheme))
            .border({ width: 1, color: this.feedbackScore === score ? AppColors.primary(this.isDarkTheme) : AppColors.hairline(this.isDarkTheme) })
            .onClick((): void => { this.feedbackScore = score; })
        }, (score: number) => `${score}`)
      }.width('100%')
      TextInput({ text: this.feedbackNote, placeholder: '补充说明' })
        .width('100%').height(42).fontSize(AppFont.SIZE_BODY)
        .fontColor(AppColors.textPrimary(this.isDarkTheme)).placeholderColor(AppColors.textTertiary(this.isDarkTheme))
        .backgroundColor(AppColors.input(this.isDarkTheme))
        .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
        .borderRadius(AppSpace.XS).padding({ left: AppSpace.MD, right: AppSpace.MD })
        .onChange((value: string): void => { this.feedbackNote = value; })
      Button('记录评价')
        .width('100%').height(42).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
        .fontColor(this.feedbackScore > 0 ? AppColors.onPrimary(this.isDarkTheme) : AppColors.textTertiary(this.isDarkTheme))
        .backgroundColor(this.feedbackScore > 0 ? AppColors.primary(this.isDarkTheme) : AppColors.group(this.isDarkTheme))
        .borderRadius(AppSpace.XS).enabled(this.feedbackScore > 0)
        .onClick((): void => { this.submitFeedback(); })
    }.width('88%').padding(AppSpace.LG).backgroundColor(AppColors.card(this.isDarkTheme))
      .border({ width: 1, color: AppColors.primary(this.isDarkTheme) }).borderRadius(AppSpace.XS)
  }

  @Builder thinkingIndicator() {
    Row() {
      Blank()
      Row({ space: 10 }) {
        Stack({ alignContent: Alignment.Center }) {
          Progress({ value: this.thinkingProgress, total: 100, type: ProgressType.Ring })
            .width(44).height(44).color(AppColors.primary(this.isDarkTheme))
            .style({ strokeWidth: 2 })
            .animation({ duration: this.thinkingFinishing ? 320 : 280, curve: Curve.EaseOut })
            .rotate({ angle: this.thinkingAngle * 0.48 })
          Column().width(34).height(34)
            .border({ width: 1, color: AppColors.lineStrong(this.isDarkTheme) })
            .rotate({ angle: this.thinkingFinishing ? 45 : 45 + this.thinkingAngle })
            .scale({ x: this.thinkingFinishing ? 0.82 : 1, y: this.thinkingFinishing ? 0.82 : 1 })
            .opacity(this.thinkingFinishing ? 0.42 : 0.9)
            .animation({ duration: this.thinkingFinishing ? 360 : 220, curve: Curve.EaseOut })
          Column().width(22).height(22)
            .border({ width: 1, color: AppColors.primary(this.isDarkTheme) })
            .backgroundColor(AppColors.group(this.isDarkTheme))
            .rotate({ angle: this.thinkingFinishing ? 45 : 45 - this.thinkingAngle * 1.35 })
            .scale({ x: this.thinkingFinishing ? 0.68 : 1, y: this.thinkingFinishing ? 0.68 : 1 })
            .animation({ duration: this.thinkingFinishing ? 360 : 220, curve: Curve.EaseOut })
          if (this.thinkingFinishing) {
            SymbolGlyph($r('sys.symbol.checkmark')).fontSize(15)
              .fontColor([AppColors.primary(this.isDarkTheme)])
          } else {
            Column().width(6).height(6)
              .backgroundColor(AppColors.primary(this.isDarkTheme))
              .scale({ x: this.thinkingTick % 2 === 0 ? 0.66 : 1, y: this.thinkingTick % 2 === 0 ? 0.66 : 1 })
              .animation({ duration: 220, curve: Curve.EaseInOut })
          }
        }.width(46).height(46)

        Column({ space: 6 }) {
          Text(this.thinkingLabel())
            .fontSize(11).fontWeight(FontWeight.Medium)
            .fontColor(AppColors.textSecondary(this.isDarkTheme))
          Row({ space: 4 }) {
            ForEach([0, 1, 2, 3], (index: number) => {
              Column().width(20).height(3)
                .backgroundColor(index <= this.thinkingStep()
                  ? AppColors.primary(this.isDarkTheme)
                  : AppColors.hairline(this.isDarkTheme))
                .opacity(index === this.thinkingStep() && !this.thinkingFinishing ? 0.62 : 1)
                .animation({ duration: 280, curve: Curve.EaseOut })
            }, (index: number) => `${index}`)
          }.height(4)
        }.width(86).alignItems(HorizontalAlign.Start)
      }
      .padding({ left: 11, right: 12, top: 9, bottom: 9 })
      .backgroundColor(AppColors.card(this.isDarkTheme))
      .border({ width: { right: 2, top: 1, left: 1, bottom: 1 }, color: AppColors.primary(this.isDarkTheme) })
      .borderRadius(AppSpace.XS)
    }
    .width('100%')
    .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING })
  }

  build() {
    Stack() {
      Column() {
        Column() {
          Text('助手').fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.textPrimary(this.isDarkTheme))
        }
        .width('100%')
        .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: AppSpace.PAGE_TOP, bottom: AppSpace.MD })

        Scroll(this.scroller) {
          Column({ space: AppSpace.MD }) {
            ForEach(this.messages, (message: ChatMessage) => {
              if (!message.isStreaming) {
                ChatBubble({
                  message,
                  onSpeak: (text: string): void => { this.speakResponse(text); },
                  onRate: (rated: ChatMessage): void => { this.openFeedback(rated); }
                })
              }
            }, (message: ChatMessage) => `${message.id}_${message.isStreaming ? 1 : 0}`)
            if (this.showThinking) this.thinkingIndicator()
            Column().height(AppSpace.LG)
          }.width('100%').padding({ top: AppSpace.SM, bottom: AppSpace.MD })
        }
        .layoutWeight(1).width('100%').scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring).align(Alignment.TopStart)

        Column() {
          Row({ space: AppSpace.SM }) {
            Column() {
              SymbolGlyph(this.isListening ? $r('sys.symbol.mic_badge_recordingtape') : $r('sys.symbol.mic_fill'))
                .fontSize(20).fontColor([this.isListening ? AppColors.TEXT_INVERSE : AppColors.textSecondary(this.isDarkTheme)])
            }
            .width(46).height(46).borderRadius(AppSpace.XS).backgroundColor(this.isListening ? AppColors.DANGER : AppColors.group(this.isDarkTheme))
            .border({ width: 1, color: this.isListening ? AppColors.DANGER : AppColors.hairline(this.isDarkTheme) })
            .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
            .opacity(this.pressedKey === 'voice' ? 0.68 : 1)
            .scale({ x: this.pressedKey === 'voice' ? 0.94 : 1, y: this.pressedKey === 'voice' ? 0.94 : 1 })
            .animation({ duration: 140, curve: Curve.EaseOut })
            .onTouch((event: TouchEvent): void => { this.touchKey('voice', event); })
            .onClick((): void => { this.toggleVoice(); })

            TextInput({
              text: this.inputText,
              placeholder: this.isListening ? '正在聆听' : (this.voiceHint && !this.inputText ? this.voiceHint : '输入消息')
            })
              .layoutWeight(1).height(46).fontSize(AppFont.SIZE_BODY)
              .fontColor(AppColors.textPrimary(this.isDarkTheme)).placeholderColor(AppColors.textTertiary(this.isDarkTheme))
              .placeholderFont({ size: AppFont.SIZE_FOOTNOTE }).borderRadius(AppSpace.XS)
              .backgroundColor(AppColors.input(this.isDarkTheme)).border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
              .padding({ left: AppSpace.MD, right: AppSpace.MD })
              .onChange((value: string): void => { this.inputText = value; })
              .onSubmit((): void => { this.send(); })

            Column() {
              SymbolGlyph($r('sys.symbol.paperplane_fill')).fontSize(17)
                .fontColor([this.inputText.trim() && !this.isListening && !this.isResponding ? AppColors.onPrimary(this.isDarkTheme) : AppColors.textTertiary(this.isDarkTheme)])
            }
            .width(46).height(46)
            .borderRadius(AppSpace.XS)
            .backgroundColor(this.inputText.trim() && !this.isListening && !this.isResponding ? AppColors.primary(this.isDarkTheme) : AppColors.group(this.isDarkTheme))
            .border({ width: 1, color: this.inputText.trim() ? AppColors.primary(this.isDarkTheme) : AppColors.hairline(this.isDarkTheme) })
            .justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
            .opacity(this.pressedKey === 'send' ? 0.68 : 1)
            .scale({ x: this.pressedKey === 'send' ? 0.94 : 1, y: this.pressedKey === 'send' ? 0.94 : 1 })
            .animation({ duration: 140, curve: Curve.EaseOut })
            .onTouch((event: TouchEvent): void => { this.touchKey('send', event); })
            .onClick((): void => { this.send(); })
          }.width('100%')
        }
        .width('100%')
        .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: AppSpace.SM, bottom: AppSpace.SM })
        .backgroundColor(AppColors.card(this.isDarkTheme))
        .border({ width: { top: 1 }, color: AppColors.divider(this.isDarkTheme) })
      }.width('100%').height('100%').backgroundColor(AppColors.page(this.isDarkTheme))
      if (this.feedbackVisible) {
        Column() { this.feedbackDialog() }
          .width('100%').height('100%').justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
          .backgroundColor('#99000000')
      }
    }.width('100%').height('100%')
  }
}
