/**
 * 设备控制卡片 · 经典鸿蒙浅色
 */
import { AppCard } from './AppCard';
import { AppIcon } from './AppIcon';
import { Device, DeviceType, ControlParams } from '../api/types';
import { DeviceApi } from '../api/deviceApi';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct DeviceCard {
  @Prop device: Device;
  @State localOn: boolean = false;
  @State localValue: number = 0;
  @State localMode: string = '';
  @State iconBounce: number = 1;
  onTap?: (device: Device) => void;

  aboutToAppear(): void {
    this.localOn = this.device.isOn;
    this.localValue = this.device.primaryValue;
    this.localMode = this.device.mode || '';
  }

  private get iconColor(): string {
    if (this.device.type === DeviceType.FAN) return AppColors.DEVICE_FAN;
    if (this.device.type === DeviceType.AC) return AppColors.DEVICE_AC;
    if (this.device.type === DeviceType.DOOR) return AppColors.DEVICE_DOOR;
    if (this.device.type === DeviceType.LIGHT) return AppColors.DEVICE_LIGHT;
    return AppColors.PRIMARY;
  }

  private get iconBg(): string {
    if (this.device.type === DeviceType.FAN) return AppColors.DEVICE_FAN_BG;
    if (this.device.type === DeviceType.AC) return AppColors.DEVICE_AC_BG;
    if (this.device.type === DeviceType.DOOR) return AppColors.DEVICE_DOOR_BG;
    if (this.device.type === DeviceType.LIGHT) return AppColors.DEVICE_LIGHT_BG;
    return AppColors.PRIMARY_BG;
  }

  private get valueLabel(): string {
    if (this.device.type === DeviceType.FAN) return `${this.localValue} 档`;
    if (this.device.type === DeviceType.AC) return `${this.localValue}°C`;
    if (this.device.type === DeviceType.DOOR) return this.localOn ? '已开锁' : '已锁定';
    if (this.device.type === DeviceType.LIGHT) return `${this.localValue}%`;
    return '';
  }

  async toggle(): Promise<void> {
    this.localOn = !this.localOn;
    await DeviceApi.toggle(this.device.id, this.localOn);
    if (this.device.type === DeviceType.LIGHT) {
      await DeviceApi.sendBearPiCommand(`brightness:${this.device.id === 'light_01' ? 0 : 1}:${this.localOn ? this.localValue || 80 : 0}`);
    }
    // 图标弹跳反馈
    this.iconBounce = 1.2;
    setTimeout(() => { this.iconBounce = 1; }, 150);
  }

  async adjust(delta: number): Promise<void> {
    let next = this.localValue + delta;
    if (this.device.type === DeviceType.FAN) next = Math.max(0, Math.min(3, next));
    if (this.device.type === DeviceType.AC) next = Math.max(16, Math.min(30, next));
    if (this.device.type === DeviceType.LIGHT) next = Math.max(0, Math.min(100, next));
    this.localValue = next;
    const action = this.device.type === DeviceType.FAN ? 'set_speed'
      : this.device.type === DeviceType.AC ? 'set_temp' : 'set_brightness';
    const ctrlParams: ControlParams = { value: next };
    await DeviceApi.control(this.device.id, action, ctrlParams);
    if (this.device.type === DeviceType.LIGHT) {
      await DeviceApi.sendBearPiCommand(`brightness:${this.device.id === 'light_01' ? 0 : 1}:${next}`);
    }
  }

  @Builder
  controlArea() {
    if (this.device.type === DeviceType.FAN || this.device.type === DeviceType.AC || this.device.type === DeviceType.LIGHT) {
      Row() {
        Column() {
          SymbolGlyph($r('sys.symbol.minus'))
            .fontSize(16)
            .fontColor([AppColors.TEXT_PRIMARY])
        }
        .width(28).height(28)
        .borderRadius(14)
        .backgroundColor(AppColors.BG_INPUT)
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .onClick(() => this.adjust(-1))
        Text(this.valueLabel)
          .layoutWeight(1)
          .fontSize(AppFont.SIZE_TITLE)
          .fontColor(AppColors.TEXT_PRIMARY)
          .fontWeight(FontWeight.Medium)
          .textAlign(TextAlign.Center)
        Column() {
          SymbolGlyph($r('sys.symbol.plus'))
            .fontSize(16)
            .fontColor([AppColors.TEXT_PRIMARY])
        }
        .width(28).height(28)
        .borderRadius(14)
        .backgroundColor(AppColors.BG_INPUT)
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        .onClick(() => this.adjust(1))
      }
      .width('100%')
      .justifyContent(FlexAlign.SpaceBetween)
      .alignItems(VerticalAlign.Center)
    } else if (this.device.type === DeviceType.DOOR) {
      Row() {
        Text(this.valueLabel)
          .layoutWeight(1)
          .fontSize(AppFont.SIZE_BODY)
          .fontColor(this.localOn ? AppColors.WARNING : AppColors.TEXT_SECONDARY)
          .fontWeight(FontWeight.Medium)
        if (this.localOn) {
          Row({ space: 3 }) {
            Circle({ width: 5, height: 5 }).fill(AppColors.WARNING)
            Text('开启中')
              .fontSize(AppFont.SIZE_CAPTION)
              .fontColor(AppColors.WARNING)
          }
        }
      }
      .width('100%')
    }
  }

  build() {
    AppCard({
      innerPadding: AppSpace.BASE,
      cornerRadius: AppSpace.RADIUS_CARD,
      onClickAction: () => { if (this.onTap) this.onTap(this.device); }
    }) {
      Column({ space: AppSpace.MD }) {
        Row() {
          Column() {
            AppIcon({ iconRes: this.device.icon, iconSize: 20, iconColor: this.iconColor })
          }
          .width(40).height(40)
          .borderRadius(20)
          .backgroundColor(this.iconBg)
          .justifyContent(FlexAlign.Center)
          .alignItems(HorizontalAlign.Center)
          .scale({ x: this.iconBounce, y: this.iconBounce })
          .animation({ duration: 150, curve: Curve.EaseOut })
          Column({ space: 2 }) {
            Text(this.device.name)
              .fontSize(AppFont.SIZE_BODY)
              .fontColor(AppColors.TEXT_PRIMARY)
              .fontWeight(FontWeight.Medium)
              .maxLines(1)
              .textOverflow({ overflow: TextOverflow.Ellipsis })
            Text(this.device.room)
              .fontSize(AppFont.SIZE_CAPTION)
              .fontColor(AppColors.TEXT_TERTIARY)
          }
          .alignItems(HorizontalAlign.Start)
          .margin({ left: AppSpace.SM })
          .layoutWeight(1)

          Toggle({ type: ToggleType.Switch, isOn: this.localOn })
            .selectedColor(AppColors.PRIMARY)
            .width(40).height(24)
            .onChange((on: boolean) => this.toggle())
        }
        .width('100%')
        .alignItems(VerticalAlign.Center)

        this.controlArea()
      }
      .width('100%')
    }
  }
}
