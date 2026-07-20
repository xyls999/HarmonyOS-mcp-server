/**
 * 通用面板组件 · 设备控制台风格
 * 细边框、低阴影、轻微按压反馈。
 */
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
  @BuilderParam content: () => void;
  onClickAction?: () => void;

  aboutToAppear(): void {
    if (this.animateIn) {
      setTimeout(() => { this.appeared = true; }, 30);
    } else {
      this.appeared = true;
    }
  }

  build() {
    Column() {
      this.content()
    }
    .width('100%')
    .padding(this.innerPadding)
    .borderRadius(this.cornerRadius)
    .backgroundColor(this.pressed ? AppColors.BG_CARD_TAP : this.bgColor)
    .border({ width: 1, color: AppColors.DIVIDER })
    .shadow(this.pressed ? { radius: 0, color: '#00000000', offsetX: 0, offsetY: 0 } : {
      radius: 2, color: '#143B82F6', offsetX: 0, offsetY: 1
    })
    .opacity(this.appeared ? 1 : 0)
    .animation({ duration: 140, curve: Curve.EaseOut })
    .onClick(() => { if (this.onClickAction) this.onClickAction(); })
    .onTouch((e: TouchEvent) => {
      if (!this.clickable) return;
      if (e.type === TouchType.Down) {
        this.pressed = true;
      } else if (e.type === TouchType.Up || e.type === TouchType.Cancel) {
        this.pressed = false;
      }
    })
  }
}
