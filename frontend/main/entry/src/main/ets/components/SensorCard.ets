/**
 * 传感器数据卡 · 经典鸿蒙浅色
 */
import { AppCard } from './AppCard';
import { AppIcon } from './AppIcon';
import { Sensor, SensorType } from '../api/types';
import { AnimatedNumber } from '../effects/AnimatedNumber';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct SensorCard {
  @Prop sensor: Sensor;
  onTap?: (sensor: Sensor) => void;

  private get iconColor(): string {
    switch (this.sensor.type) {
      case SensorType.TEMPERATURE: return AppColors.SENSOR_TEMP;
      case SensorType.HUMIDITY: return AppColors.SENSOR_HUMID;
      case SensorType.AIR_QUALITY: return AppColors.SENSOR_AIR;
      case SensorType.ILLUMINANCE: return AppColors.SENSOR_LIGHT;
      case SensorType.PIR: return AppColors.SENSOR_PIR;
      case SensorType.DOOR_WINDOW: return AppColors.SENSOR_DOOR;
      case SensorType.SMOKE:
      case SensorType.WATER_LEAK: return AppColors.SENSOR_SMOKE;
      case SensorType.POWER: return AppColors.SENSOR_POWER;
      default: return AppColors.PRIMARY;
    }
  }

  private get decimals(): number {
    const u = this.sensor.current.unit;
    if (u === '触发' || u === '关闭' || u === '正常' || u.includes('开') || u.includes('关')) return 0;
    return this.sensor.current.value < 10 ? 1 : 0;
  }

  build() {
    AppCard({
      innerPadding: AppSpace.BASE,
      cornerRadius: AppSpace.RADIUS_CARD,
      onClickAction: () => { if (this.onTap) this.onTap(this.sensor); }
    }) {
      Column({ space: AppSpace.SM }) {
        Row() {
          // 传感器图标（彩色底）
          Column() {
            AppIcon({ iconRes: this.sensor.icon, iconSize: 18, iconColor: this.iconColor })
          }
          .width(32).height(32)
          .borderRadius(16)
          .backgroundColor(`${this.iconColor}1A`)
          .justifyContent(FlexAlign.Center)
          .alignItems(HorizontalAlign.Center)
          Text(this.sensor.name)
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.TEXT_SECONDARY)
            .margin({ left: AppSpace.SM })
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
            .layoutWeight(1)
          if (this.sensor.isAlert) {
            Text('●')
              .fontSize(10)
              .fontColor(AppColors.DANGER)
          }
        }
        .width('100%')

        // 数值
        Row({ space: 2 }) {
          AnimatedNumber({
            value: this.sensor.current.value,
            decimals: this.decimals,
            fontSize: AppFont.SIZE_HEADLINE,
            textColor: this.sensor.isAlert ? AppColors.DANGER : AppColors.TEXT_PRIMARY
          })
          Text(this.sensor.current.unit)
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.TEXT_TERTIARY)
            .margin({ top: 8 })
        }
        .alignItems(VerticalAlign.Top)

        // 协议标签
        Row() {
          Text(this.sensor.protocol === 'starflash' ? '星闪' : 'WiFi')
            .fontSize(9)
            .fontColor(AppColors.TEXT_TERTIARY)
            .padding({ left: 6, right: 6, top: 2, bottom: 2 })
            .borderRadius(4)
            .backgroundColor(AppColors.BG_INPUT)
          Blank()
          Text(this.sensor.room)
            .fontSize(9)
            .fontColor(AppColors.TEXT_TERTIARY)
        }
        .width('100%')
      }
      .width('100%')
    }
  }
}
