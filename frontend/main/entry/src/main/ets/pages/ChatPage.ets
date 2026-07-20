/**
 * ChatFlow 对话页 · 优化版
 * 修复: isResponding 在 try/finally 中重置，防止卡死
 * 增强: 消息出现动画、打字光标呼吸效果、优化排版
 */
import { ChatBubble } from '../components/ChatBubble';
import { ChatApi } from '../api/chatApi';
import { ChatMessage, ChatRole } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN = 0x0001;
const TAG = 'SmartHomeChatPage';

@Component
export struct ChatPage {
  @State messages: ChatMessage[] = [];
  @State inputText: string = '';
  @State isResponding: boolean = false;
  @State isListening: boolean = false;
  private scroller: Scroller = new Scroller();
  private msgId: number = 1;

  aboutToAppear(): void {
    this.messages = [{
      id: 'msg_0',
      role: ChatRole.ASSISTANT,
      content: ChatApi.getWelcome(),
      timestamp: Date.now()
    }];
  }

  scrollToBottom(): void {
    setTimeout((): void => { this.scroller.scrollEdge(Edge.Bottom); }, 50);
  }

  async send(): Promise<void> {
    const text = this.inputText.trim();
    if (!text || this.isResponding) return;

    hilog.info(DOMAIN, TAG, `send: "${text}"`);

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
    this.scrollToBottom();

    // 关键修复: try/finally 确保 isResponding 必定重置
    try {
      await ChatApi.sendStream(
        this.messages.slice(0, -1),
        (partial: string) => {
          // 逐字更新: 整个数组重新赋值触发 @State
          this.messages = this.messages.map((m: ChatMessage): ChatMessage =>
            m.id === assistantId ? {
              id: assistantId, role: ChatRole.ASSISTANT, content: partial,
              timestamp: m.timestamp, isStreaming: true
            } : m
          );
        },
        (finalMsg: ChatMessage) => {
          // 最终更新: 用全新 id 让 ForEach 识别为新元素
          const newId = `msg_${this.msgId++}`;
          hilog.info(DOMAIN, TAG, `onDone: newId=${newId}, content="${finalMsg.content.substring(0, 30)}"`);
          this.messages = this.messages.map((m: ChatMessage): ChatMessage =>
            m.id === assistantId ? {
              id: newId, role: ChatRole.ASSISTANT, content: finalMsg.content,
              timestamp: finalMsg.timestamp, isStreaming: false, chartData: finalMsg.chartData
            } : m
          );
          ChatApi.speak(finalMsg.content);
          this.scrollToBottom();
          hilog.info(DOMAIN, TAG, `onDone fired, messages=${this.messages.length}`);
        }
      );
    } catch (e) {
      hilog.error(DOMAIN, TAG, `send error: ${(e as Error).message}`);
      // 错误降级: 替换 placeholder 为错误提示
      this.messages = this.messages.map((m: ChatMessage): ChatMessage =>
        m.id === assistantId ? {
          id: assistantId, role: ChatRole.ASSISTANT,
          content: '抱歉，处理消息时出了点问题，请重试。',
          timestamp: Date.now(), isStreaming: false
        } : m
      );
    } finally {
      // 必定执行: 重置状态
      this.isResponding = false;
      hilog.info(DOMAIN, TAG, `send finished, isResponding reset to false`);
    }
  }

  async startVoice(): Promise<void> {
    if (this.isListening) return;
    this.isListening = true;
    const text = await ChatApi.voiceToText('');
    this.isListening = false;
    this.inputText = text;
    this.send();
  }

  build() {
    Column() {
      // 顶部标题栏
      Row({ space: AppSpace.SM }) {
        Column() {
          SymbolGlyph($r('sys.symbol.Celia'))
            .fontSize(24)
            .fontColor([AppColors.PRIMARY])
        }
        .width(40).height(40)
        .borderRadius(20)
        .backgroundColor(AppColors.PRIMARY_BG)
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)

        Column({ space: 2 }) {
          Text('明日家居')
            .fontSize(AppFont.SIZE_TITLE)
            .fontColor(AppColors.TEXT_PRIMARY)
            .fontWeight(FontWeight.Bold)
          if (this.isResponding) {
            Row({ space: 6 }) {
              Circle({ width: 6, height: 6 })
                .fill(AppColors.PRIMARY)
                .opacity(0.9)
              Text('正在回复...')
                .fontSize(AppFont.SIZE_CAPTION)
                .fontColor(AppColors.PRIMARY)
            }
          }
        }
        .alignItems(HorizontalAlign.Start)
        .layoutWeight(1)
      }
      .width('100%')
      .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: 44, bottom: AppSpace.MD })
      .backgroundColor(AppColors.BG_CARD)

      // 消息流
      Scroll(this.scroller) {
        Column({ space: AppSpace.MD }) {
          ForEach(this.messages, (m: ChatMessage) => {
            ChatBubble({ message: m })
          }, (m: ChatMessage) => m.id)
          Column().height(AppSpace.LG)
        }
        .width('100%')
        .padding({ top: AppSpace.SM, bottom: 80 })
      }
      .layoutWeight(1)
      .width('100%')
      .backgroundColor(AppColors.BG_PAGE)
      .scrollBar(BarState.Off)
      .edgeEffect(EdgeEffect.Spring)
      .align(Alignment.TopStart)

      // 底部输入栏
      Row({ space: AppSpace.SM }) {
        // 语音按钮
        Column() {
          SymbolGlyph(this.isListening ? $r('sys.symbol.mic_badge_recordingtape') : $r('sys.symbol.mic_fill'))
            .fontSize(20)
            .fontColor([this.isListening ? AppColors.DANGER : AppColors.TEXT_SECONDARY])
        }
        .width(40).height(40)
        .borderRadius(20)
        .backgroundColor(this.isListening ? '#EAF2FF' : AppColors.BG_INPUT)
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .onClick(() => this.startVoice())

        // 输入框
        TextInput({ text: this.inputText, placeholder: this.isListening ? '正在聆听...' : '输入消息或点击语音' })
          .layoutWeight(1)
          .height(40)
          .fontSize(AppFont.SIZE_BODY)
          .fontColor(AppColors.TEXT_PRIMARY)
          .placeholderColor(AppColors.TEXT_TERTIARY)
          .placeholderFont({ size: AppFont.SIZE_BODY })
          .borderRadius(20)
          .backgroundColor(AppColors.BG_INPUT)
          .padding({ left: AppSpace.BASE, right: AppSpace.BASE })
          .onChange((v: string) => { this.inputText = v; })
          .onSubmit(() => this.send())

        // 发送按钮
        Column() {
          SymbolGlyph($r('sys.symbol.paperplane_fill'))
            .fontSize(16)
            .fontColor([AppColors.TEXT_INVERSE])
        }
        .width(40).height(40)
        .borderRadius(20)
        .backgroundColor(this.inputText.trim() ? AppColors.PRIMARY : '#D5D7DB')
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .opacity(this.inputText.trim() ? 1 : 0.5)
        .onClick(() => this.send())
      }
      .width('100%')
      .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: AppSpace.SM, bottom: AppSpace.SM })
      .backgroundColor(AppColors.BG_CARD)
      .border({ width: { top: 0.5 }, color: AppColors.HAIRLINE })
    }
    .width('100%')
    .height('100%')
    .backgroundColor(AppColors.BG_PAGE)
  }
}
