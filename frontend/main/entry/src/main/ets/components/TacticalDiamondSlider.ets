import { TacticalMotion, TacticalTheme } from '../theme/TacticalTheme';

/** 可复用设备滑轨：拖动只预览，松手或点击轨道才提交一次。 */
@Component
export struct TacticalDiamondSlider {
  @Prop label: string = '';
  @Prop @Watch('syncExternalValue') value: number = 0;
  @Prop min: number = 0;
  @Prop max: number = 100;
  @Prop step: number = 10;
  @Prop unit: string = '%';
  @Prop @Watch('syncEnabledState') isEnabled: boolean = true;
  @Prop isDark: boolean = true;
  onPreview?: (value: number) => void;
  onCommit?: (value: number) => void;
  @State previewValue: number = 0;
  @State dragging: boolean = false;

  aboutToAppear(): void {
    this.previewValue = this.clampAndSnap(this.value);
  }

  syncExternalValue(): void {
    if (!this.dragging) this.previewValue = this.clampAndSnap(this.value);
  }

  syncEnabledState(): void {
    // 指令提交会短暂禁用滑条；重新启用时不回填旧 Prop，等待真实硬件快照触发外部值同步。
    if (!this.isEnabled) this.dragging = false;
  }

  private clampAndSnap(value: number): number {
    const clamped = Math.max(this.min, Math.min(this.max, value));
    const snapped = this.min + Math.round((clamped - this.min) / this.step) * this.step;
    return Math.max(this.min, Math.min(this.max, snapped));
  }

  private diamondThumb(): SliderBlockStyle {
    return { type: SliderBlockType.IMAGE, image: $r('app.media.slider_diamond') };
  }

  private handleChange(value: number, mode: SliderChangeMode): void {
    const next = this.clampAndSnap(value);
    this.previewValue = next;
    if (mode === SliderChangeMode.Begin || mode === SliderChangeMode.Moving) {
      this.dragging = true;
      if (this.onPreview) this.onPreview(next);
      return;
    }
    if (mode === SliderChangeMode.End || mode === SliderChangeMode.Click) {
      this.dragging = false;
      if (this.onPreview) this.onPreview(next);
      if (this.onCommit) this.onCommit(next);
    }
  }

  build() {
    Row({ space: 10 }) {
      Text(this.label)
        .width(48)
        .fontSize(14)
        .fontColor(TacticalTheme.textSecondary(this.isDark))
      Slider({ value: this.previewValue, min: this.min, max: this.max, step: this.step,
        style: SliderStyle.OutSet, direction: Axis.Horizontal })
        .layoutWeight(1)
        .height(44)
        .blockSize({ width: 26, height: 26 })
        .blockStyle(this.diamondThumb())
        .blockBorderWidth(0)
        .trackThickness(6)
        .trackBorderRadius(0)
        .selectedBorderRadius(0)
        .trackColor(TacticalTheme.panelMuted(this.isDark))
        .selectedColor(TacticalTheme.accent(this.isDark))
        .showSteps(false)
        .showTips(false)
        .sliderInteractionMode(SliderInteraction.SLIDE_AND_CLICK_UP)
        .enabled(this.isEnabled)
        .opacity(this.isEnabled ? 1 : 0.42)
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
        .accessibilityText(`${this.label}${this.previewValue}${this.unit}`)
        .onChange((value: number, mode: SliderChangeMode) => this.handleChange(value, mode))
      Text(`${this.previewValue}${this.unit}`)
        .width(68)
        .fontSize(16)
        .fontWeight(FontWeight.Bold)
        .fontColor(this.isEnabled ? TacticalTheme.text(this.isDark) : TacticalTheme.textMuted(this.isDark))
        .textAlign(TextAlign.End)
    }
    .width('100%')
    .height(44)
    .alignItems(VerticalAlign.Center)
  }
}
