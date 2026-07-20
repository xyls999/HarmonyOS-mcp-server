import { AppColors } from '../theme/Colors';

@Component
export struct GeometricBackdrop {
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;
  @State outerAngle: number = 0;
  @State innerAngle: number = 0;
  @State driftX: number = -18;
  @State driftY: number = -12;
  @State scanY: number = -160;
  @State gradientAngle: number = 128;
  @State sweepX: number = -420;

  aboutToAppear(): void {
    this.getUIContext().animateTo({ duration: 18000, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.outerAngle = 360;
    });
    this.getUIContext().animateTo({ duration: 12000, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.innerAngle = -360;
    });
    this.getUIContext().animateTo({ duration: 5200, curve: Curve.EaseInOut, iterations: -1, playMode: PlayMode.Alternate }, (): void => {
      this.driftX = 20;
      this.driftY = 16;
    });
    this.getUIContext().animateTo({ duration: 6800, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.scanY = 760;
    });
    this.getUIContext().animateTo({ duration: 14000, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.gradientAngle = 228;
    });
    this.getUIContext().animateTo({ duration: 7200, curve: Curve.EaseInOut, iterations: -1, playMode: PlayMode.Alternate }, (): void => {
      this.sweepX = 420;
    });
  }

  build() {
    Stack() {
      Column().width('100%').height('100%').backgroundColor(AppColors.page(this.isDarkTheme))
      Column().width('100%').height('100%')
        .linearGradient({
          angle: this.gradientAngle,
          colors: [[AppColors.page(this.isDarkTheme), 0],
            [AppColors.group(this.isDarkTheme), 0.52],
            [AppColors.page(this.isDarkTheme), 1]]
        })
        .opacity(this.isDarkTheme ? 0.72 : 0.86)
      Column().width('145%').height(120)
        .linearGradient({
          angle: 90,
          colors: [[AppColors.group(this.isDarkTheme), 0],
            [AppColors.primaryBg(this.isDarkTheme), 0.5],
            [AppColors.group(this.isDarkTheme), 1]]
        })
        .opacity(this.isDarkTheme ? 0.2 : 0.3)
        .rotate({ angle: -34 })
        .translate({ x: this.sweepX, y: -this.sweepX * 0.34 })
      Column().width(3).height('100%').backgroundColor(AppColors.primary(this.isDarkTheme))
        .opacity(this.isDarkTheme ? 0.8 : 0.48).position({ x: 0, y: 0 })
      Column().width(1).height('100%').backgroundColor(AppColors.grid(this.isDarkTheme))
        .opacity(0.42).position({ x: '28%', y: 0 })
      Column().width(1).height('100%').backgroundColor(AppColors.grid(this.isDarkTheme))
        .opacity(0.3).position({ x: '72%', y: 0 })
      Column().width('100%').height(1).backgroundColor(AppColors.grid(this.isDarkTheme))
        .opacity(0.3).position({ x: 0, y: '34%' })
      Column().width(520).height(1).backgroundColor(AppColors.lineStrong(this.isDarkTheme))
        .opacity(this.isDarkTheme ? 0.34 : 0.2).position({ x: -88, y: 280 }).rotate({ angle: 63 })
      Column().width(440).height(1).backgroundColor(AppColors.lineStrong(this.isDarkTheme))
        .opacity(this.isDarkTheme ? 0.28 : 0.16).position({ x: 18, y: 510 }).rotate({ angle: -52 })
      Column().width(360).height(1).backgroundColor(AppColors.primary(this.isDarkTheme))
        .opacity(this.isDarkTheme ? 0.24 : 0.14).position({ x: 28, y: 760 }).rotate({ angle: 22 })
      Column().width(290).height(1).backgroundColor(AppColors.lineStrong(this.isDarkTheme))
        .opacity(this.isDarkTheme ? 0.2 : 0.12).position({ x: 240, y: 930 }).rotate({ angle: -24 })
      Column().width(290).height(290).border({ width: 1, color: AppColors.grid(this.isDarkTheme) })
        .opacity(this.isDarkTheme ? 0.16 : 0.1).position({ x: 174, y: 180 })
        .translate({ x: this.driftX * 0.5, y: this.driftY * 0.4 }).rotate({ angle: -22 + this.innerAngle * 0.4 })
      Column().width(210).height(210).border({ width: 1, color: AppColors.lineStrong(this.isDarkTheme) })
        .opacity(this.isDarkTheme ? 0.4 : 0.2).position({ x: 218, y: 72 })
        .translate({ x: this.driftX, y: this.driftY }).rotate({ angle: 45 + this.outerAngle })
      Column().width(126).height(126).border({ width: 1, color: AppColors.primary(this.isDarkTheme) })
        .opacity(this.isDarkTheme ? 0.34 : 0.18).position({ x: 256, y: 112 })
        .translate({ x: -this.driftX * 0.4, y: this.driftY * 0.5 }).rotate({ angle: this.innerAngle })
      Column().width('100%').height(1).backgroundColor(AppColors.primary(this.isDarkTheme))
        .opacity(this.isDarkTheme ? 0.24 : 0.12).translate({ y: this.scanY })
      Row().width(54).height(2).backgroundColor(AppColors.primary(this.isDarkTheme))
        .opacity(0.5).position({ x: '82%', y: '18%' }).translate({ x: this.driftX })
      Column().width(8).height(8).border({ width: 1, color: AppColors.primary(this.isDarkTheme) })
        .rotate({ angle: 45 }).opacity(0.48).position({ x: '88%', y: '20%' })
    }.width('100%').height('100%')
  }
}
