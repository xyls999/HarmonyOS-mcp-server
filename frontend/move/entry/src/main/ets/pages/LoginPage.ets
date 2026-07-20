import { AuthActionResult, AuthApi } from '../api/authApi';
import { AppColors } from '../theme/Colors';
import { AppFont } from '../theme/Typography';
import { AppSpace } from '../theme/Spacing';
import { hilog } from '@kit.PerformanceAnalysisKit';

@Component
export struct LoginPage {
  @State userId: string = '';
  @State password: string = '';
  @State loading: boolean = false;
  @State errorText: string = '';
  @State showPassword: boolean = false;
  @State outerAngle: number = 0;
  @State innerAngle: number = 0;
  @State driftX: number = -20;
  @State driftY: number = -16;
  @State scanY: number = -260;
  @State gradientAngle: number = 132;
  @State sweepX: number = 360;
  onLogin?: () => void;
  onFaceDoor?: () => void;

  aboutToAppear(): void {
    this.getUIContext().animateTo({ duration: 16000, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.outerAngle = 360;
    });
    this.getUIContext().animateTo({ duration: 11000, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.innerAngle = -360;
    });
    this.getUIContext().animateTo({ duration: 4800, curve: Curve.EaseInOut, iterations: -1, playMode: PlayMode.Alternate }, (): void => {
      this.driftX = 22;
      this.driftY = 18;
    });
    this.getUIContext().animateTo({ duration: 7600, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.scanY = 860;
    });
    this.getUIContext().animateTo({ duration: 15000, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.gradientAngle = 228;
    });
    this.getUIContext().animateTo({ duration: 6800, curve: Curve.EaseInOut, iterations: -1, playMode: PlayMode.Alternate }, (): void => {
      this.sweepX = -360;
    });
  }

  private async login(): Promise<void> {
    const id = this.userId.trim();
    if (!id || !this.password) {
      this.errorText = '请输入账号和密码';
      return;
    }
    if (id.length > 80 || this.password.length > 128) {
      this.errorText = '账号或密码长度不正确';
      return;
    }
    this.loading = true;
    this.errorText = '';
    const result: AuthActionResult = await AuthApi.authenticateUser(id, this.password);
    hilog.info(0x0000, 'SmartHomeLogin', 'login result=%{public}s', `${result.success}`);
    this.password = '';
    this.loading = false;
    if (!result.success) {
      this.errorText = result.message;
      return;
    }
    if (this.onLogin) this.onLogin();
  }

  @Builder
  brandMark() {
    Column({ space: AppSpace.MD }) {
      Stack({ alignContent: Alignment.Center }) {
        Column().width(4).height(46).backgroundColor(AppColors.MONO_WHITE).position({ x: 0, y: 7 })
        Row() {
          Text('明日').fontSize(32).fontFamily('HarmonyOS Sans SC')
            .fontWeight(FontWeight.Bolder).fontColor(AppColors.MONO_WHITE)
          Text('家居').fontSize(32).fontFamily('HarmonyOS Sans SC')
            .fontWeight(FontWeight.Bolder).fontColor(AppColors.MONO_MUTED)
        }.position({ x: 18, y: 10 })
        Column().width(9).height(9).border({ width: 1, color: AppColors.MONO_WHITE })
          .position({ x: 190, y: 39 }).rotate({ angle: 45 })
      }.width('100%').height(62)
      Row() {
        Column().width(52).height(3).backgroundColor(AppColors.MONO_WHITE)
        Column().layoutWeight(1).height(1).backgroundColor(AppColors.MONO_BORDER)
      }.width('100%').alignItems(VerticalAlign.Center)
    }.width('100%').alignItems(HorizontalAlign.Start).accessibilityText('明日家居')
  }

  @Builder
  animatedBackdrop() {
    Stack() {
      Column().width('100%').height('100%')
        .linearGradient({
          angle: this.gradientAngle,
          colors: [[AppColors.MONO_BLACK, 0], [AppColors.MONO_SURFACE, 0.5], [AppColors.MONO_BLACK, 1]]
        }).opacity(0.92)
      Column().width('145%').height(118)
        .linearGradient({
          angle: 90,
          colors: [[AppColors.MONO_SURFACE, 0], [AppColors.MONO_BORDER, 0.5], [AppColors.MONO_SURFACE, 1]]
        }).opacity(0.22).rotate({ angle: -34 })
        .translate({ x: this.sweepX, y: -this.sweepX * 0.4 })
      Column().width(1).height('100%').backgroundColor(AppColors.MONO_BORDER).opacity(0.14)
        .position({ x: 52, y: 0 })
      Column().width(1).height('100%').backgroundColor(AppColors.MONO_BORDER).opacity(0.08)
        .position({ x: 274, y: 0 })
      Column().width('100%').height(1).backgroundColor(AppColors.MONO_BORDER).opacity(0.12)
        .position({ x: 0, y: 238 }).translate({ y: this.driftY })
      Column().width(420).height(1).backgroundColor(AppColors.MONO_WHITE).opacity(0.14)
        .position({ x: -40, y: 430 }).rotate({ angle: 26 })
      Column().width(360).height(1).backgroundColor(AppColors.MONO_BORDER).opacity(0.22)
        .position({ x: 40, y: 790 }).rotate({ angle: -22 })
      Column().width(250).height(250).border({ width: 1, color: AppColors.MONO_BORDER })
        .opacity(0.2).position({ x: 198, y: 60 }).rotate({ angle: -24 + this.innerAngle * 0.35 })
      Column().width(132).height(132).border({ width: 1, color: AppColors.MONO_BORDER })
        .opacity(0.28).position({ x: 248, y: 112 })
        .translate({ x: this.driftX, y: this.driftY })
        .rotate({ angle: 45 + this.outerAngle })
      Column().width(72).height(72).border({ width: 1, color: AppColors.MONO_WHITE })
        .opacity(0.22).position({ x: 286, y: 142 })
        .rotate({ angle: this.innerAngle })
      Column().width(96).height(2).backgroundColor(AppColors.MONO_WHITE).opacity(0.18)
        .position({ x: 16, y: 610 }).translate({ x: this.driftX })
      Column().width(8).height(8).backgroundColor(AppColors.MONO_WHITE).opacity(0.24)
        .position({ x: 330, y: 690 }).translate({ y: this.driftY })
      Column().width('100%').height(1).backgroundColor(AppColors.MONO_WHITE).opacity(0.07)
        .translate({ y: this.scanY })
    }.width('100%').height('100%')
  }

  @Builder
  fieldLabel(title: string) {
    Text(title).width('100%').fontSize(AppFont.SIZE_BODY).fontFamily('HarmonyOS Sans SC')
      .fontWeight(FontWeight.Bold).fontColor(AppColors.MONO_WHITE)
  }

  build() {
    Stack() {
      this.animatedBackdrop()
      Scroll() {
        Column() {
          this.brandMark()

          Column({ space: AppSpace.SM }) {
            Text('登录').width('100%').fontSize(AppFont.SIZE_HEADLINE).fontFamily('HarmonyOS Sans SC')
              .fontWeight(FontWeight.Bolder).fontColor(AppColors.MONO_WHITE)
          }.width('100%').alignItems(HorizontalAlign.Start)
            .margin({ top: AppSpace.XXXL, bottom: AppSpace.XXL })

          Column({ space: AppSpace.MD }) {
            this.fieldLabel('账号')
            TextInput({ text: this.userId, placeholder: '请输入用户名' })
              .width('100%').height(56).fontSize(AppFont.SIZE_BODY_LG)
              .fontColor(AppColors.MONO_BLACK)
              .placeholderColor(AppColors.MONO_PLACEHOLDER)
              .backgroundColor(AppColors.MONO_WHITE)
              .border({ width: 1, color: AppColors.MONO_WHITE })
              .padding({ left: AppSpace.BASE, right: AppSpace.BASE })
              .onChange((value: string): void => { this.userId = value; this.errorText = ''; })

            this.fieldLabel('密码')
            Row({ space: AppSpace.SM }) {
              TextInput({ text: this.password, placeholder: '请输入密码' })
                .layoutWeight(1).height(56).type(this.showPassword ? InputType.Normal : InputType.Password)
                .fontSize(AppFont.SIZE_BODY_LG).fontColor(AppColors.MONO_BLACK)
                .placeholderColor(AppColors.MONO_PLACEHOLDER)
                .backgroundColor(AppColors.MONO_WHITE)
                .border({ width: 1, color: AppColors.MONO_WHITE })
                .padding({ left: AppSpace.BASE, right: AppSpace.BASE })
                .onChange((value: string): void => { this.password = value; this.errorText = ''; })
                .onSubmit((): void => { this.login(); })
              Stack() {
                Column().width(56).height(56).backgroundColor(AppColors.MONO_SURFACE)
                  .border({ width: 1, color: AppColors.MONO_WHITE })
                SymbolGlyph(this.showPassword ? $r('sys.symbol.eye_slash') : $r('sys.symbol.eye'))
                  .fontSize(21).fontColor([AppColors.MONO_WHITE])
              }.width(56).height(56).accessibilityText(this.showPassword ? '隐藏密码' : '显示密码')
                .onClick((): void => { this.showPassword = !this.showPassword; })
            }.width('100%')

            if (this.errorText) {
              Row({ space: AppSpace.SM }) {
                SymbolGlyph($r('sys.symbol.exclamationmark_circle_fill')).fontSize(20)
                  .fontColor([AppColors.MONO_WHITE])
                Text(this.errorText).fontSize(AppFont.SIZE_BODY).fontColor(AppColors.MONO_WHITE).layoutWeight(1)
              }.width('100%').padding(AppSpace.MD)
                .border({ width: 1, color: AppColors.MONO_BORDER })
            }

            Row({ space: AppSpace.SM }) {
              if (this.loading) {
                LoadingProgress().width(21).height(21).color(AppColors.MONO_BLACK)
              }
              Text(this.loading ? '正在登录' : '登录').fontSize(AppFont.SIZE_BODY_LG)
                .fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bold)
                .fontColor(AppColors.MONO_BLACK)
            }.width('100%').height(56).justifyContent(FlexAlign.Center)
              .backgroundColor(AppColors.MONO_WHITE)
              .opacity(this.loading ? 0.58 : 1).enabled(!this.loading)
              .margin({ top: AppSpace.SM })
              .onClick((): void => { this.login(); })
          }.width('100%').alignItems(HorizontalAlign.Start)
        }.width('100%').padding({ left: AppSpace.XL, right: AppSpace.XL, top: 72, bottom: AppSpace.XXXL })
      }.width('100%').height('100%').scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
      Row() {
        Blank()
        Row({ space: AppSpace.SM }) {
          SymbolGlyph($r('sys.symbol.lock_open_fill')).fontSize(18).fontColor([AppColors.MONO_WHITE])
          Text('刷脸开门').fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.MONO_WHITE)
        }.height(44).padding({ left: AppSpace.MD, right: AppSpace.MD })
          .backgroundColor(AppColors.MONO_SURFACE)
          .border({ width: 1, color: AppColors.MONO_BORDER })
          .onClick((): void => { if (this.onFaceDoor) this.onFaceDoor(); })
      }.width('100%').height(60).padding({ left: AppSpace.XL, right: AppSpace.XL, top: AppSpace.BASE })
        .position({ x: 0, y: 0 })
    }.width('100%').height('100%').backgroundColor(AppColors.MONO_BLACK)
  }
}
