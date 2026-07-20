/**
 * 环形数据指示器 · 经典鸿蒙浅色
 */
import { AppColors } from '../theme/Colors';
import { AppFont } from '../theme/Typography';

@Component
export struct StatRing {
  @Prop value: number;
  @Prop max: number;
  @Prop unit: string = '';
  @Prop ringColor: string = AppColors.PRIMARY;
  @Prop ringSize: number = 76;
  @Prop decimals: number = 0;

  private get percent(): number {
    return Math.max(0, Math.min(1, this.value / this.max));
  }

  build() {
    Stack() {
      Progress({ value: 100, total: 100, type: ProgressType.Ring })
        .width(this.ringSize)
        .height(this.ringSize)
        .color(AppColors.BG_INPUT)
        .style({ strokeWidth: 5 })

      Progress({ value: this.percent * 100, total: 100, type: ProgressType.Ring })
        .width(this.ringSize)
        .height(this.ringSize)
        .color(this.ringColor)
        .style({ strokeWidth: 5 })

      Column() {
        Text(`${this.value.toFixed(this.decimals)}`)
          .fontSize(AppFont.SIZE_TITLE_LG)
          .fontColor(AppColors.TEXT_PRIMARY)
          .fontWeight(FontWeight.Bold)
        if (this.unit) {
          Text(this.unit)
            .fontSize(AppFont.SIZE_CAPTION)
            .fontColor(AppColors.TEXT_TERTIARY)
        }
      }
      .justifyContent(FlexAlign.Center)
      .alignItems(HorizontalAlign.Center)
    }
    .width(this.ringSize)
    .height(this.ringSize)
  }
}
