import { TacticalTheme } from '../theme/TacticalTheme';


@Component
export struct TacticalMotionCore {
  @Prop progress: number = 0;
  @Prop outerAngle: number = 0;
  @Prop innerAngle: number = 0;
  @Prop title: string = '明日家居';
  @Prop icon: Resource = $r('sys.symbol.house_fill');
  @Prop isDark: boolean = true;

  private normalizedProgress(): number {
    return Math.max(0, Math.min(100, this.progress));
  }

  @Builder
  motionRail() {
    Stack({ alignContent: Alignment.Center }) {
      Column()
        .width(184)
        .height(3)
        .backgroundColor(TacticalTheme.grid(this.isDark))
      Column()
        .width(184)
        .height(3)
        .backgroundColor(TacticalTheme.accent(this.isDark))
        .scale({ x: Math.max(0.001, this.normalizedProgress() / 100), y: 1 })
        .translate({ x: -92 * (1 - this.normalizedProgress() / 100) })
      Column()
        .width(10)
        .height(10)
        .borderRadius(1)
        .backgroundColor(TacticalTheme.text(this.isDark))
        .rotate({ angle: 45 })
        .translate({ x: -87 + 1.74 * this.normalizedProgress() })
    }
    .width(184)
    .height(14)
    .clip(true)
  }

  build() {
    Column({ space: 18 }) {
      Stack({ alignContent: Alignment.Center }) {
        Column()
          .width(164)
          .height(164)
          .border({ width: 1, color: TacticalTheme.grid(this.isDark) })
          .rotate({ angle: 45 + this.outerAngle })
          .opacity(0.48)
        Column()
          .width(136)
          .height(136)
          .border({ width: 1, color: TacticalTheme.gridStrong(this.isDark) })
          .rotate({ angle: this.innerAngle })
          .opacity(0.78)
        Column()
          .width(96)
          .height(96)
          .border({ width: 1, color: TacticalTheme.accent(this.isDark) })
          .rotate({ angle: 45 + this.outerAngle * 1.18 })
        Column()
          .width(10)
          .height(10)
          .backgroundColor(TacticalTheme.text(this.isDark))
          .position({ x: 8, y: 166 })
          .rotate({ angle: 45 + this.outerAngle * 0.22 })
          .opacity(this.progress < 70 ? 0 : 1)
        Column()
          .width(10)
          .height(10)
          .backgroundColor(TacticalTheme.accent(this.isDark))
          .position({ x: 166, y: 8 })
          .rotate({ angle: 45 + this.innerAngle * 0.22 })
          .opacity(this.progress < 85 ? 0 : 1)
        Stack({ alignContent: Alignment.Center }) {
          Column().width(54).height(54).backgroundColor(TacticalTheme.accent(this.isDark))
          SymbolGlyph(this.icon).fontSize(25).fontColor([TacticalTheme.inverse(this.isDark)])
        }
        .width(54)
        .height(54)
        .scale({ x: this.progress < 55 ? 0.84 : 1, y: this.progress < 55 ? 0.84 : 1 })
        .animation({ duration: 320, curve: Curve.EaseOut })
      }
      .width(184)
      .height(184)
      this.motionRail()
      Row({ space: 8 }) {
        Column().width(24).height(2).backgroundColor(TacticalTheme.accent(this.isDark))
        Text(this.title)
          .fontSize(28)
          .fontWeight(FontWeight.Bolder)
          .fontColor(TacticalTheme.text(this.isDark))
        Column().width(24).height(2).backgroundColor(TacticalTheme.accent(this.isDark))
      }
      .height(44)
      .alignItems(VerticalAlign.Center)
    }
    .alignItems(HorizontalAlign.Center)
  }
}
