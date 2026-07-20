import { ChatMessage, ChatRole } from '../api/types';
import { ChatChartPanel } from './ChatChartPanel';
import { TacticalTheme } from '../theme/TacticalTheme';

@Component
export struct HarmonChatBubble {
  @Prop message: ChatMessage;
  @Prop isDark: boolean = true;
  onSpeak?: (text: string) => void;
  @State appeared: boolean = false;

  aboutToAppear(): void { setTimeout((): void => { this.appeared = true; }, 20); }

  build() {
    Row() {
      if (this.message.role === ChatRole.USER) Blank();
      if (this.message.role === ChatRole.ASSISTANT) {
        this.assistantBubble()
        Blank()
      } else {
        this.userBubble()
      }
    }
    .width('100%').padding({ left: 14, right: 14 })
    .opacity(this.appeared ? 1 : 0).translate({ y: this.appeared ? 0 : 8 })
    .scale({ x: this.appeared ? 1 : 0.985, y: this.appeared ? 1 : 0.985 })
    .animation({ duration: 320, curve: Curve.EaseOut })
  }

  @Builder
  assistantBubble() {
    Column({ space: 8 }) {
      Row({ space: 8 }) {
        Column().width(28).height(2).backgroundColor(TacticalTheme.accent(this.isDark))
        Column().width(6).height(6).border({ width: 1, color: TacticalTheme.accent(this.isDark) }).rotate({ angle: 45 })
      }.width('100%').alignItems(VerticalAlign.Center)
      if (this.message.content) {
        Text(this.message.content + (this.message.isStreaming ? '▍' : ''))
          .fontSize(15).lineHeight(23).fontColor(TacticalTheme.text(this.isDark)).width('100%')
      }
      if (this.message.chartData && this.message.chartData.charts && this.message.chartData.charts.length > 0) {
        ChatChartPanel({ chartData: this.message.chartData, isDark: this.isDark })
      }
      Row() {
        Column().layoutWeight(1).height(1).backgroundColor(TacticalTheme.grid(this.isDark))
        Column().width(7).height(7).border({ width: 1, color: TacticalTheme.accent(this.isDark) }).rotate({ angle: 45 })
        if (this.message.content) {
          SymbolGlyph($r('sys.symbol.speaker_wave_2_fill')).fontSize(17)
            .fontColor([TacticalTheme.accent(this.isDark)]).width(34).height(30)
            .accessibilityText('朗读回复').onClick(() => { if (this.onSpeak) this.onSpeak(this.message.content); })
        }
      }.width('100%').alignItems(VerticalAlign.Bottom)
    }.width('84%').padding({ left: 14, right: 12, top: 11, bottom: 9 })
      .backgroundColor(TacticalTheme.panelRaised(this.isDark))
      .border({ width: { left: 3, top: 1, right: 1, bottom: 1 }, color: TacticalTheme.accent(this.isDark) })
      .borderRadius(3)
  }

  @Builder
  userBubble() {
    Column({ space: 8 }) {
      Text(this.message.content + (this.message.isStreaming ? '▍' : ''))
        .fontSize(15).lineHeight(23).fontColor(TacticalTheme.inverse(this.isDark)).width('100%')
      Row() {
        Column().layoutWeight(1).height(1).backgroundColor(TacticalTheme.inverse(this.isDark))
        Column().width(7).height(7).backgroundColor(TacticalTheme.inverse(this.isDark)).rotate({ angle: 45 })
      }.width('100%').alignItems(VerticalAlign.Bottom).opacity(0.56)
    }.width('76%').padding({ left: 14, right: 12, top: 11, bottom: 9 })
      .backgroundColor(TacticalTheme.accent(this.isDark))
      .border({ width: { left: 1, top: 1, right: 3, bottom: 1 }, color: TacticalTheme.accent(this.isDark) })
      .borderRadius(3)
  }
}
