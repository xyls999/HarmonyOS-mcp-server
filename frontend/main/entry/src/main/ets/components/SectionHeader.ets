/**
 * 章节标题 · 经典鸿蒙浅色
 */
import { AppColors } from '../theme/Colors';
import { AppFont } from '../theme/Typography';

@Component
export struct SectionHeader {
  @Prop title: string;
  @Prop subtitle: string = '';
  actionText: string = '';
  onAction?: () => void;

  build() {
    Row() {
      Column({ space: 2 }) {
        Text(this.title)
          .fontSize(AppFont.SIZE_TITLE)
          .fontColor(AppColors.TEXT_PRIMARY)
          .fontWeight(FontWeight.Bold)
        if (this.subtitle) {
          Text(this.subtitle)
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.TEXT_TERTIARY)
            .lineHeight(20)
        }
      }
      .alignItems(HorizontalAlign.Start)
      .layoutWeight(1)

      if (this.actionText) {
        Text(this.actionText)
          .fontSize(AppFont.SIZE_FOOTNOTE)
          .fontColor(AppColors.PRIMARY)
          .onClick(() => { if (this.onAction) this.onAction(); })
      }
    }
    .width('100%')
    .alignItems(VerticalAlign.Center)
  }
}
