import { AppColors } from '../theme/Colors';
import { AppFont } from '../theme/Typography';
import { AppSpace } from '../theme/Spacing';

@Component
export struct MinimalHeader {
  @Prop code: string = '';
  @Prop title: string = '';
  @Prop subtitle: string = '';
  @Prop status: string = '';
  @Prop alert: boolean = false;
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;

  build() {
    Row({ space: AppSpace.MD }) {
      Column().width(3).height(50).backgroundColor(AppColors.primary(this.isDarkTheme))
      Column({ space: AppSpace.XS }) {
        if (this.code) {
          Text(this.code).fontSize(9).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.primary(this.isDarkTheme))
        }
        Stack({ alignContent: Alignment.Start }) {
          Text(this.title).fontSize(AppFont.SIZE_TITLE_LG).fontFamily('HarmonyOS Sans SC')
            .fontWeight(FontWeight.Bolder).fontColor(AppColors.grid(this.isDarkTheme))
            .translate({ x: 2, y: 2 })
          Text(this.title).fontSize(AppFont.SIZE_TITLE_LG).fontFamily('HarmonyOS Sans SC')
            .fontWeight(FontWeight.Bolder).fontColor(AppColors.textPrimary(this.isDarkTheme))
        }.width('100%').height(30)
        Text(this.subtitle)
          .fontSize(AppFont.SIZE_FOOTNOTE)
          .fontFamily('HarmonyOS Sans SC')
          .fontColor(AppColors.textTertiary(this.isDarkTheme))
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Column({ space: 7 }) {
        Row({ space: 6 }) {
          Circle({ width: 6, height: 6 }).fill(this.alert ? AppColors.DANGER : AppColors.primary(this.isDarkTheme))
          Text(this.status).fontSize(AppFont.SIZE_CAPTION)
            .fontFamily('HarmonyOS Sans SC')
            .fontColor(this.alert ? AppColors.DANGER : AppColors.textTertiary(this.isDarkTheme))
        }
        Row({ space: 4 }) {
          Column().width(18).height(2).backgroundColor(AppColors.primary(this.isDarkTheme))
          Column().width(6).height(6).border({ width: 1, color: AppColors.lineStrong(this.isDarkTheme) }).rotate({ angle: 45 })
        }
      }.alignItems(HorizontalAlign.End)
    }.width('100%').height(58).alignItems(VerticalAlign.Center)
      .border({ width: { bottom: 1 }, color: AppColors.hairline(this.isDarkTheme) })
  }
}
