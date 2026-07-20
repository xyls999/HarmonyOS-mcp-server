import { AppColors } from '../theme/Colors';
import { AppFont } from '../theme/Typography';

@Component
export struct SectionLabel {
  @Prop index: string = '';
  @Prop title: string = '';
  @Prop detail: string = '';
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;
  build() {
    Row({ space: 9 }) {
      if (this.index) {
        Text(this.index).fontSize(9).fontWeight(FontWeight.Bold).fontColor(AppColors.primary(this.isDarkTheme))
      }
      Column().width(16).height(3).backgroundColor(AppColors.primary(this.isDarkTheme))
      Text(this.title).fontSize(AppFont.SIZE_BODY).fontFamily('HarmonyOS Sans SC')
        .fontWeight(FontWeight.Bold).fontColor(AppColors.textPrimary(this.isDarkTheme))
      Row().layoutWeight(1).height(1).backgroundColor(AppColors.divider(this.isDarkTheme))
      Text(this.detail).fontSize(AppFont.SIZE_CAPTION).fontFamily('HarmonyOS Sans SC')
        .fontColor(AppColors.textTertiary(this.isDarkTheme))
    }.width('100%').height(28).alignItems(VerticalAlign.Center)
  }
}
