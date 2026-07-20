import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';

@Component
export struct AppCard {
  @Prop innerPadding: number = AppSpace.BASE;
  @Prop cornerRadius: number = AppSpace.RADIUS_CARD;
  @Prop bgColor: string = AppColors.BG_CARD;
  @Prop clickable: boolean = true;
  @Prop animateIn: boolean = true;
  @State pressed: boolean = false;
  @State appeared: boolean = false;
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;
  @BuilderParam content: () => void;
  onClickAction?: () => void;

  aboutToAppear(): void {
    if (this.animateIn) setTimeout((): void => { this.appeared = true; }, 20);
    else this.appeared = true;
  }
  private cardBg(): string {
    if (this.bgColor !== AppColors.BG_CARD) return this.bgColor;
    return this.pressed ? AppColors.cardTap(this.isDarkTheme) : AppColors.card(this.isDarkTheme);
  }
  build() {
    Column() { this.content() }
      .width('100%')
      .padding(this.innerPadding)
      .borderRadius(this.cornerRadius)
      .backgroundColor(this.cardBg())
      .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
      .shadow(this.pressed ? { radius: 0, color: AppColors.TRANSPARENT, offsetX: 0, offsetY: 0 } : {
        radius: 2, color: this.isDarkTheme ? '#48000000' : '#181769AA', offsetX: 0, offsetY: 1
      })
      .opacity(this.appeared ? 1 : 0)
      .translate({ y: this.appeared ? 0 : 5 })
      .animation({ duration: 140, curve: Curve.EaseOut })
      .onClick((): void => { if (this.onClickAction) this.onClickAction(); })
      .onTouch((event: TouchEvent): void => {
        if (!this.clickable) return;
        this.pressed = event.type === TouchType.Down;
      })
  }
}
