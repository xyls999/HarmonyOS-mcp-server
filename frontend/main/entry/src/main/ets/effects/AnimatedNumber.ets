/**
 * 滚动数字 · 克制版
 * 数值变化时简单缓动到新值（无轮询，靠 @Watch 触发）
 * 动效: 数值滚动 + 字号脉冲放大
 */
@Component
export struct AnimatedNumber {
  @Prop @Watch('onValueChange') value: number = 0;
  @Prop decimals: number = 0;
  @Prop suffix: string = '';
  @Prop fontSize: number = 28;
  @Prop textColor: string = '#181818';
  @State display: number = 0;
  @State pulse: number = 1;
  private animating: boolean = false;

  aboutToAppear(): void {
    this.display = this.value;
  }

  onValueChange(): void {
    // 触发脉冲
    this.pulse = 1.08;
    setTimeout(() => { this.pulse = 1; }, 200);

    if (this.animating) return;
    this.animating = true;
    const start = this.display;
    const target = this.value;
    const startTime = Date.now();
    const dur = 400;
    const tick = (): void => {
      const t = Math.min(1, (Date.now() - startTime) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      this.display = start + (target - start) * eased;
      if (t < 1) {
        setTimeout(tick, 16);
      } else {
        this.display = target;
        this.animating = false;
      }
    };
    tick();
  }

  build() {
    Text(`${this.display.toFixed(this.decimals)}${this.suffix}`)
      .fontSize(this.fontSize)
      .fontColor(this.textColor)
      .fontWeight(FontWeight.Bold)
      .scale({ x: this.pulse, y: this.pulse })
      .animation({ duration: 200, curve: Curve.EaseOut })
  }
}
