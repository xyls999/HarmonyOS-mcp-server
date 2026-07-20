import { TacticalMotion, TacticalTheme } from '../theme/TacticalTheme';

/** 统一的棱角按钮：干净直角主体，状态装饰全部收进边框内部。 */
@Component
export struct TacticalCutCornerButton {
  @Prop label: string = '';
  @Prop isEnabled: boolean = true;
  @Prop isDark: boolean = true;
  @Prop buttonWidth: number = 96;
  @Prop buttonHeight: number = 44;
  @Prop active: boolean = false;
  @Prop accentOverride: string = '';
  @Prop fillWidth: boolean = false;
  onTap?: () => void;
  @State pressed: boolean = false;
  @State rotationAngle: number = 0;

  private accent(): string { return this.accentOverride.length > 0 ? this.accentOverride : TacticalTheme.accent(this.isDark); }
  private text(): string { return TacticalTheme.text(this.isDark); }
  private panel(): string { return TacticalTheme.panel(this.isDark); }
  private frameColor(): string { return TacticalTheme.border(this.isDark); }

  @Builder
  innerRail() {
    Column()
      .width(3)
      .height(this.buttonHeight - 12)
      .backgroundColor(this.accent())
      .opacity(this.active ? 1 : 0.56)
      .position({ x: 4, y: 6 })
      .enabled(false)
  }

  @Builder
  stateMarker() {
    Column()
      .width(12)
      .height(2)
      .backgroundColor(this.active ? TacticalTheme.inverse(this.isDark) : this.accent())
      .position({ x: this.fillWidth ? 0 : this.buttonWidth - 18, y: this.buttonHeight - 6 })
      .rotate({ angle: this.rotationAngle })
      .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
      .enabled(false)
  }

  build() {
    Stack() {
      Button(this.label, { type: ButtonType.Normal })
        .width(this.fillWidth ? '100%' : this.buttonWidth).height(this.buttonHeight).fontSize(14).fontWeight(FontWeight.Medium)
        .fontColor(this.active ? TacticalTheme.inverse(this.isDark) : this.text())
        .backgroundColor(this.active ? this.accent() : this.panel())
        .border({ width: 1, color: this.active ? this.accent() : this.frameColor() })
        .borderRadius(0).enabled(this.isEnabled)
        .onClick(() => {
          if (!this.isEnabled) return;
          this.rotationAngle += 180;
          if (this.onTap) this.onTap();
        })
      this.innerRail()
      this.stateMarker()
    }
    .width(this.fillWidth ? '100%' : this.buttonWidth).height(this.buttonHeight)
    .opacity(this.isEnabled ? (this.pressed ? 0.7 : 1) : 0.42)
    .scale({ x: this.pressed ? 0.96 : 1, y: this.pressed ? 0.96 : 1 })
    .animation({ duration: TacticalMotion.PRESS, curve: Curve.EaseOut })
    .onTouch((event: TouchEvent) => {
      if (event.type === TouchType.Down) this.pressed = true;
      if (event.type === TouchType.Up || event.type === TouchType.Cancel) this.pressed = false;
    })
    .accessibilityText(this.label)
  }
}
