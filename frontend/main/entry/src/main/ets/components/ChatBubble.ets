/**
 * 对话气泡 · 优化版
 * 用户气泡: 右对齐，鸿蒙蓝底白字
 * 助手气泡: 左对齐，白底深字 + 头像 + 细边框
 * 优化: 更精致的圆角、间距、头像、打字光标
 */
import { ChatMessage, ChatRole } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';
import { ChatChartPanel } from './ChatChartPanel';

@Component
export struct ChatBubble {
  @Prop message: ChatMessage;

  build() {
    Row() {
      if (this.message.role === ChatRole.USER) {
        Blank()
      }

      // 助手头像
      if (this.message.role === ChatRole.ASSISTANT) {
        Column() {
          SymbolGlyph($r('sys.symbol.Celia'))
            .fontSize(16)
            .fontColor([AppColors.PRIMARY])
        }
        .width(30).height(30)
        .borderRadius(15)
        .backgroundColor(AppColors.PRIMARY_BG)
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .margin({ top: 2 })
      }

      // 气泡内容
      if (this.message.role === ChatRole.ASSISTANT) {
        Column({ space: 8 }) {
          Text(this.message.content + (this.message.isStreaming ? '▍' : ''))
            .fontSize(AppFont.SIZE_BODY).lineHeight(22).fontColor(AppColors.TEXT_PRIMARY).width('100%')
          if (this.message.chartData && this.message.chartData.charts && this.message.chartData.charts.length > 0) {
            ChatChartPanel({ chartData: this.message.chartData, isDark: false })
          }
        }
        .padding({ left: AppSpace.BASE, right: AppSpace.BASE, top: AppSpace.SM + 2, bottom: AppSpace.SM + 2 })
        .borderRadius({ topLeft: 4, topRight: AppSpace.RADIUS_BASE,
          bottomLeft: AppSpace.RADIUS_BASE, bottomRight: AppSpace.RADIUS_BASE })
        .backgroundColor(AppColors.BG_CARD).border({ width: 0.5, color: AppColors.HAIRLINE })
        .constraintSize({ maxWidth: '82%' })
      } else {
        Text(this.message.content + (this.message.isStreaming ? '▍' : ''))
          .fontSize(AppFont.SIZE_BODY).lineHeight(22).fontColor(AppColors.TEXT_INVERSE)
          .padding({ left: AppSpace.BASE, right: AppSpace.BASE, top: AppSpace.SM + 2, bottom: AppSpace.SM + 2 })
          .borderRadius({ topLeft: AppSpace.RADIUS_BASE, topRight: 4,
            bottomLeft: AppSpace.RADIUS_BASE, bottomRight: AppSpace.RADIUS_BASE })
          .backgroundColor(AppColors.PRIMARY).constraintSize({ maxWidth: '72%' })
          .shadow({ radius: 8, color: '#0D007DFF', offsetX: 0, offsetY: 2 })
      }

      if (this.message.role === ChatRole.ASSISTANT) {
        Blank()
      }
    }
    .width('100%')
    .padding({
      left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING
    })
    .alignItems(VerticalAlign.Top)
  }
}
