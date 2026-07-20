import { TacticalMotion, TacticalTheme } from '../theme/TacticalTheme';


@Component
export struct TacticalToggle {
  @Link @Watch('syncToggleProgress') isOn: boolean;
  @Prop disabled: boolean = false;
  @Prop isDark: boolean = true;
  onToggle?: (enabled: boolean) => void;
  @State pressed: boolean = false;
  @State toggleProgress: number = 0;

  private syncToggleProgress(): void {
    this.toggleProgress = this.isOn ? 1 : 0;
  }

  aboutToAppear(): void {
    this.syncToggleProgress();
  }

  private toggleOrbit(): number { return this.toggleProgress * 28 - 14; }

  build() {
    Stack({ alignContent: Alignment.Center }) {
      Column()
        .width(52)
        .height(26)
        .borderRadius(0)
        .backgroundColor(this.isOn ? TacticalTheme.accentSoft(this.isDark) : TacticalTheme.panel(this.isDark))
        .border({
          width: 1,
          color: this.isOn ? TacticalTheme.accent(this.isDark) : TacticalTheme.border(this.isDark)
        })
      Column()
        .width(18)
        .height(18)
        .borderRadius(0)
        .backgroundColor(this.isOn ? TacticalTheme.accent(this.isDark) : TacticalTheme.textMuted(this.isDark))
        .rotate({ angle: this.toggleProgress * 180 })
        .translate({ x: this.toggleOrbit() })
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
      Column().width(8).height(2)
        .backgroundColor(this.isOn ? TacticalTheme.inverse(this.isDark) : TacticalTheme.panel(this.isDark))
        .rotate({ angle: this.toggleProgress * 180 })
        .translate({ x: this.toggleOrbit() })
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    }
    .width(60)
    .height(44)
    .opacity(this.disabled ? 0.42 : this.pressed ? 0.72 : 1)
    .scale({ x: this.pressed ? 0.96 : 1, y: this.pressed ? 0.96 : 1 })
    .animation({ duration: TacticalMotion.PRESS, curve: Curve.EaseOut })
    .enabled(!this.disabled)
    .accessibilityText(this.isOn ? '已开启' : '已关闭')
    .onTouch((event: TouchEvent) => {
      if (event.type === TouchType.Down) this.pressed = true;
      if (event.type === TouchType.Up || event.type === TouchType.Cancel) this.pressed = false;
    })
    .onClick(() => {
      if (this.disabled) return;
      const next = !this.isOn;
      this.toggleProgress = next ? 1 : 0;
      this.isOn = next;
      if (this.onToggle) this.onToggle(next);
    })
  }
}

/**
 * 设备页专用开关：视觉和设置页 TacticalToggle 完全共用同一套轨道、旋转和按压节奏，
 * 但接收只读设备状态，避免在 ForEach 中强行伪造 @Link。父页面回写真实状态后，
 * @Watch 会把旋钮从当前值平滑收敛到权威值；请求失败时由父页面回滚即可。
 */
@Component
export struct TacticalDeviceToggle {
  @Prop @Watch('syncToggleProgress') isOn: boolean = false;
  @Prop disabled: boolean = false;
  @Prop isDark: boolean = true;
  onToggle?: (enabled: boolean) => void;
  @State pressed: boolean = false;
  @State toggleProgress: number = 0;
  @State visualOn: boolean = false;

  private syncToggleProgress(): void {
    this.visualOn = this.isOn;
    this.toggleProgress = this.isOn ? 1 : 0;
  }

  aboutToAppear(): void {
    this.syncToggleProgress();
  }

  private toggleOrbit(): number { return this.toggleProgress * 28 - 14; }

  build() {
    Stack({ alignContent: Alignment.Center }) {
      Column()
        .width(52)
        .height(26)
        .borderRadius(0)
        .backgroundColor(this.visualOn ? TacticalTheme.accentSoft(this.isDark) : TacticalTheme.panel(this.isDark))
        .border({
          width: 1,
          color: this.visualOn ? TacticalTheme.accent(this.isDark) : TacticalTheme.border(this.isDark)
        })
      Column()
        .width(18)
        .height(18)
        .borderRadius(0)
        .backgroundColor(this.visualOn ? TacticalTheme.accent(this.isDark) : TacticalTheme.textMuted(this.isDark))
        .rotate({ angle: this.toggleProgress * 180 })
        .translate({ x: this.toggleOrbit() })
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
      Column().width(8).height(2)
        .backgroundColor(this.visualOn ? TacticalTheme.inverse(this.isDark) : TacticalTheme.panel(this.isDark))
        .rotate({ angle: this.toggleProgress * 180 })
        .translate({ x: this.toggleOrbit() })
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    }
    .width(60)
    .height(44)
    .opacity(this.disabled ? 0.42 : this.pressed ? 0.72 : 1)
    .scale({ x: this.pressed ? 0.96 : 1, y: this.pressed ? 0.96 : 1 })
    .animation({ duration: TacticalMotion.PRESS, curve: Curve.EaseOut })
    .enabled(!this.disabled)
    .accessibilityText(this.visualOn ? '已开启' : '已关闭')
    .onTouch((event: TouchEvent) => {
      if (event.type === TouchType.Down) this.pressed = true;
      if (event.type === TouchType.Up || event.type === TouchType.Cancel) this.pressed = false;
    })
    .onClick(() => {
      if (this.disabled) return;
      const next = !this.visualOn;
      this.visualOn = next;
      this.toggleProgress = next ? 1 : 0;
      if (this.onToggle) this.onToggle(next);
    })
  }
}


@Component
export struct TacticalSettingRow {
  @Link isOn: boolean;
  @Prop title: string = '';
  @Prop description: string = '';
  @Prop disabled: boolean = false;
  @Prop isDark: boolean = true;
  onToggle?: (enabled: boolean) => void;

  build() {
    Row({ space: 12 }) {
      Column({ space: 5 }) {
        Text(this.title)
          .fontSize(16)
          .fontWeight(FontWeight.Bold)
          .fontColor(TacticalTheme.text(this.isDark))
        Text(this.description)
          .fontSize(14)
          .fontColor(TacticalTheme.textMuted(this.isDark))
          .maxLines(2)
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
      Text(this.isOn ? '开启' : '关闭')
        .fontSize(14)
        .fontWeight(FontWeight.Medium)
        .fontColor(this.isOn ? TacticalTheme.accent(this.isDark) : TacticalTheme.textMuted(this.isDark))
      TacticalToggle({
        isOn: $isOn,
        disabled: this.disabled,
        isDark: this.isDark,
        onToggle: (next: boolean) => {
          if (this.onToggle) this.onToggle(next);
        }
      })
    }
    .width('100%')
    .height(68)
    .padding({ left: 2, right: 2 })
    .border({ width: { bottom: 1 }, color: TacticalTheme.border(this.isDark) })
    .accessibilityText(`${this.title}${this.isOn ? '已开启' : '已关闭'}`)
  }
}
