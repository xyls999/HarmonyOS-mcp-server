/**
 * 传感器详情页 · 经典鸿蒙浅色
 */
import { AppCard } from '../../components/AppCard';
import { AnimatedNumber } from '../../effects/AnimatedNumber';
import { SensorApi } from '../../api/sensorApi';
import { Sensor } from '../../api/types';
import { AppColors } from '../../theme/Colors';
import { AppSpace } from '../../theme/Spacing';
import { AppFont } from '../../theme/Typography';
import { router } from '@kit.ArkUI';

interface SensorDetailParams {
  sensorId: string;
}

@Entry
@Component
struct SensorDetailPage {
  @State sensor: Sensor | null = null;
  @State sensorId: string = 'temp_01';

  aboutToAppear(): void {
    const params = router.getParams() as SensorDetailParams;
    if (params && params.sensorId) {
      this.sensorId = params.sensorId;
    }
    this.loadData();
  }

  async loadData(): Promise<void> {
    const s = await SensorApi.getSensor(this.sensorId);
    this.sensor = s ?? null;
  }

  private get maxHistory(): number {
    if (!this.sensor || this.sensor.history.length === 0) return 1;
    let max: number = 1;
    for (let i = 0; i < this.sensor.history.length; i++) {
      if (this.sensor.history[i] > max) max = this.sensor.history[i];
    }
    return max;
  }

  build() {
    Column() {
      if (this.sensor) {
        Scroll() {
          Column({ space: AppSpace.BASE }) {
            Row() {
              SymbolGlyph($r('sys.symbol.chevron_left'))
                .fontSize(24)
                .fontColor([AppColors.TEXT_PRIMARY])
              Text(this.sensor.name)
                .fontSize(AppFont.SIZE_TITLE)
                .fontColor(AppColors.TEXT_PRIMARY)
                .fontWeight(FontWeight.Bold)
                .layoutWeight(1)
                .textAlign(TextAlign.Center)
              Column() {
                SymbolGlyph(this.sensor.icon)
                  .fontSize(24)
                  .fontColor([AppColors.PRIMARY])
              }
              .width(28)
            }
            .width('100%')
            .padding({ top: 44, bottom: AppSpace.MD })

            // 当前数值大卡
            AppCard({ innerPadding: AppSpace.XXL }) {
              Column({ space: AppSpace.SM }) {
                Text('当前读数')
                  .fontSize(AppFont.SIZE_BODY)
                  .fontColor(AppColors.TEXT_TERTIARY)
                Row({ space: 4 }) {
                  AnimatedNumber({
                    value: this.sensor.current.value,
                    decimals: this.sensor.current.value < 10 ? 1 : 0,
                    fontSize: AppFont.SIZE_HERO,
                    textColor: this.sensor.isAlert ? AppColors.DANGER : AppColors.TEXT_PRIMARY
                  })
                  Text(this.sensor.current.unit)
                    .fontSize(AppFont.SIZE_TITLE)
                    .fontColor(AppColors.TEXT_TERTIARY)
                    .margin({ bottom: 8 })
                }
                .alignItems(VerticalAlign.Bottom)
                Text(this.sensor.room + ' · ' + (this.sensor.protocol === 'starflash' ? '星闪' : 'WiFi'))
                  .fontSize(AppFont.SIZE_FOOTNOTE)
                  .fontColor(AppColors.TEXT_TERTIARY)
              }
              .alignItems(HorizontalAlign.Center)
            }

            // 24h 趋势
            AppCard({ innerPadding: AppSpace.BASE }) {
              Column({ space: AppSpace.MD }) {
                Text('24 小时趋势')
                  .fontSize(AppFont.SIZE_BODY_LG)
                  .fontColor(AppColors.TEXT_PRIMARY)
                  .fontWeight(FontWeight.Medium)
                Row() {
                  ForEach(this.sensor.history, (v: number, i: number) => {
                    Column()
                      .layoutWeight(1)
                      .height(Math.max(4, (v / this.maxHistory) * 110))
                      .backgroundColor(`${AppColors.PRIMARY}${this.toAlpha(0.3 + (i / 24) * 0.7)}`)
                      .borderRadius({ topLeft: 2, topRight: 2 })
                      .margin({ left: 1 })
                  }, (v: number, i: number) => `${i}`)
                }
                .width('100%')
                .height(110)
                .alignItems(VerticalAlign.Bottom)
                Row() {
                  Text('24h 前').fontSize(AppFont.SIZE_CAPTION).fontColor(AppColors.TEXT_TERTIARY)
                  Blank()
                  Text('现在').fontSize(AppFont.SIZE_CAPTION).fontColor(AppColors.TEXT_TERTIARY)
                }
                .width('100%')
              }
              .width('100%')
              .alignItems(HorizontalAlign.Start)
            }

            // 告警阈值
            AppCard({ innerPadding: AppSpace.BASE }) {
              Column({ space: AppSpace.MD }) {
                Text('告警阈值')
                  .fontSize(AppFont.SIZE_BODY_LG)
                  .fontColor(AppColors.TEXT_PRIMARY)
                  .fontWeight(FontWeight.Medium)
                if (this.sensor.thresholdMin !== undefined) {
                  this.paramRow('下限', `${this.sensor.thresholdMin} ${this.sensor.current.unit}`)
                }
                if (this.sensor.thresholdMax !== undefined) {
                  this.paramRow('上限', `${this.sensor.thresholdMax} ${this.sensor.current.unit}`)
                }
                this.paramRow('当前状态', this.sensor.isAlert ? '告警中' : '正常')
              }
              .width('100%')
              .alignItems(HorizontalAlign.Start)
            }
          }
          .width('100%')
          .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, bottom: 40 })
        }
        .layoutWeight(1)
        .backgroundColor(AppColors.BG_PAGE)
        .scrollBar(BarState.Off)
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor(AppColors.BG_PAGE)
  }

  private toAlpha(v: number): string {
    return Math.floor(Math.max(0, Math.min(1, v)) * 255).toString(16).padStart(2, '0');
  }

  @Builder
  paramRow(label: string, value: string) {
    Row() {
      Text(label).fontSize(AppFont.SIZE_BODY).fontColor(AppColors.TEXT_TERTIARY)
      Blank()
      Text(value).fontSize(AppFont.SIZE_BODY).fontColor(AppColors.TEXT_PRIMARY).fontWeight(FontWeight.Medium)
    }
    .width('100%')
    .padding({ top: AppSpace.SM, bottom: AppSpace.SM })
  }
}
