/**
 * 首页 · 经典鸿蒙浅色
 */
import { DeviceCard } from '../components/DeviceCard';
import { SectionHeader } from '../components/SectionHeader';
import { StatRing } from '../components/StatRing';
import { AppCard } from '../components/AppCard';
import { AppIcon } from '../components/AppIcon';
import { DeviceApi } from '../api/deviceApi';
import { SensorApi } from '../api/sensorApi';
import { Device, Sensor, Scene, SensorGroup, DeviceType, RouterDeviceParam } from '../api/types';
import { MockData } from '../mock/mockData';
import { router, promptAction } from '@kit.ArkUI';
import { SceneApi } from '../api/sceneApi';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct HomePage {
  @State devices: Device[] = [];
  @State envSensors: Sensor[] = [];
  @State scenes: Scene[] = [];
  @State activeSceneId: string = 's1';
  @State gradAngle: number = 135;
  private gradTimer: number = -1;

  aboutToAppear(): void {
    setTimeout(() => {
      this.loadData();
    }, 0);
    // 顶部渐变缓慢流动（30s 一圈）
    this.gradTimer = setInterval(() => {
      this.gradAngle = (this.gradAngle + 2) % 360;
    }, 500);
  }

  aboutToDisappear(): void {
    if (this.gradTimer !== -1) clearInterval(this.gradTimer);
  }

  async loadData(): Promise<void> {
    const devicePromise = DeviceApi.getDevices();
    const sensorPromise = SensorApi.getByGroup(SensorGroup.ENVIRONMENT);
    const devices = await devicePromise;
    const sensors = await sensorPromise;
    this.devices = devices;
    this.envSensors = sensors.slice(0, 4);
    this.scenes = MockData.scenes;
  }

  private getGreeting(): string {
    const h = new Date().getHours();
    if (h < 6) return '夜深了';
    if (h < 11) return '早上好';
    if (h < 14) return '中午好';
    if (h < 18) return '下午好';
    return '晚上好';
  }

  build() {
    Scroll() {
      Column({ space: AppSpace.BASE }) {
        // ===== 1. 问候头图（带柔和渐变流动背景）=====
        Stack({ alignContent: Alignment.TopStart }) {
          // 流动渐变背景层（极淡）
          Column()
            .width('100%')
            .height(120)
            .linearGradient({
              angle: this.gradAngle,
              colors: [['#0A007DFF', 0.0], ['#143B82F6', 0.5], ['#0A60A5FA', 1.0]]
            })
            .animation({ duration: 500, curve: Curve.Linear })

          // 内容层
          Row() {
            Column({ space: 4 }) {
              Text(`${this.getGreeting()}，${MockData.user.nickname}`)
                .fontSize(AppFont.SIZE_TITLE_LG)
                .fontColor(AppColors.TEXT_PRIMARY)
                .fontWeight(FontWeight.Bold)
              Row({ space: 6 }) {
                AppIcon({ iconRes: MockData.weather.icon, iconSize: 14, iconColor: AppColors.TEXT_TERTIARY })
                Text(`${MockData.weather.city} · ${MockData.weather.condition} ${MockData.weather.temp}°C`)
                  .fontSize(AppFont.SIZE_FOOTNOTE)
                  .fontColor(AppColors.TEXT_TERTIARY)
              }
            }
            .alignItems(HorizontalAlign.Start)
            .layoutWeight(1)
            Column() {
              Text(MockData.user.nickname.charAt(0))
                .fontSize(AppFont.SIZE_BODY_LG)
                .fontColor(AppColors.PRIMARY)
                .fontWeight(FontWeight.Medium)
            }
            .width(44).height(44)
            .borderRadius(22)
            .backgroundColor(AppColors.BG_CARD)
            .justifyContent(FlexAlign.Center)
            .alignItems(HorizontalAlign.Center)
          }
          .width('100%')
          .alignItems(VerticalAlign.Center)
          .padding({ left: AppSpace.BASE, right: AppSpace.BASE, top: AppSpace.LG, bottom: AppSpace.LG })
        }
        .width('100%')
        .clip(true)
        .borderRadius(AppSpace.RADIUS_CARD)

        // ===== 2. 场景快捷 =====
        Column({ space: AppSpace.SM }) {
          SectionHeader({ title: '场景模式', subtitle: '一键切换家居状态' })
          Scroll() {
            Row({ space: AppSpace.SM }) {
              ForEach(this.scenes, (s: Scene) => {
                Column({ space: 4 }) {
                  Column() {
                    AppIcon({
                      iconRes: s.icon,
                      iconSize: 22,
                      iconColor: s.isActive ? AppColors.PRIMARY : AppColors.TEXT_TERTIARY
                    })
                  }
                  .width(52).height(52)
                  .borderRadius(26)
                  .backgroundColor(s.isActive ? AppColors.PRIMARY_BG : AppColors.BG_CARD)
                  .justifyContent(FlexAlign.Center)
                  .alignItems(HorizontalAlign.Center)
                  Text(s.name)
                    .fontSize(AppFont.SIZE_CAPTION)
                    .fontColor(s.isActive ? AppColors.PRIMARY : AppColors.TEXT_TERTIARY)
                    .fontWeight(s.isActive ? FontWeight.Medium : FontWeight.Regular)
                }
                .width(64)
                .alignItems(HorizontalAlign.Center)
                .onClick(async () => {
                  const msg = await SceneApi.activate(s.id);
                  promptAction.showToast({ message: msg, duration: 2000 });
                  this.scenes = MockData.scenes.slice();
                  this.devices = await DeviceApi.getDevices();
                })
              }, (s: Scene) => s.id)
            }
            .padding({ top: AppSpace.XS })
          }
          .scrollable(ScrollDirection.Horizontal)
          .scrollBar(BarState.Off)
          .width('100%')
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)

        // ===== 3. 设备卡片网格 =====
        Column({ space: AppSpace.SM }) {
          Row() {
            Column({ space: 2 }) {
              Text('我的设备')
                .fontSize(AppFont.SIZE_BODY_LG)
                .fontColor(AppColors.TEXT_PRIMARY)
                .fontWeight(FontWeight.Medium)
              Text(`${this.devices.length} 台设备`)
                .fontSize(AppFont.SIZE_FOOTNOTE)
                .fontColor(AppColors.TEXT_TERTIARY)
            }
            .alignItems(HorizontalAlign.Start)
            .layoutWeight(1)
            // 添加设备按钮
            Column() {
              SymbolGlyph($r('sys.symbol.plus'))
                .fontSize(16)
                .fontColor([AppColors.PRIMARY])
            }
            .width(32).height(32)
            .borderRadius(16)
            .backgroundColor(AppColors.PRIMARY_BG)
            .justifyContent(FlexAlign.Center)
            .alignItems(HorizontalAlign.Center)
            .onClick(() => {
              router.pushUrl({ url: 'pages/AddDevicePage' });
            })
          }
          .width('100%')
          .alignItems(VerticalAlign.Center)
          Grid() {
            ForEach(this.devices.filter((d: Device) => d.type !== DeviceType.CAMERA), (d: Device) => {
              GridItem() {
                DeviceCard({
                  device: d,
                  onTap: (dev: Device) => {
                    const p: RouterDeviceParam = { deviceId: dev.id };
                    router.pushUrl({ url: 'pages/detail/DeviceDetailPage', params: p });
                  }
                })
              }
            }, (d: Device) => d.id)
          }
          .columnsTemplate('1fr 1fr')
          .columnsGap(AppSpace.CARD_GAP)
          .rowsGap(AppSpace.CARD_GAP)
          .width('100%')
          .height(this.devices.filter((d: Device) => d.type !== DeviceType.CAMERA).length * 120)
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)

        // ===== 4. 环境概览 =====
        Column({ space: AppSpace.SM }) {
          SectionHeader({ title: '环境概览', subtitle: '实时环境数据' })
          AppCard({ innerPadding: AppSpace.BASE }) {
            Row() {
              ForEach(this.envSensors, (s: Sensor) => {
                Column({ space: AppSpace.XS }) {
                  StatRing({
                    value: s.current.value,
                    max: s.thresholdMax || 100,
                    unit: s.current.unit,
                    ringColor: this.sensorColor(s),
                    ringSize: 64,
                    decimals: s.current.value < 10 ? 1 : 0
                  })
                  Text(s.name.replace('客厅', ''))
                    .fontSize(AppFont.SIZE_CAPTION)
                    .fontColor(AppColors.TEXT_TERTIARY)
                    .maxLines(1)
                }
                .layoutWeight(1)
                .alignItems(HorizontalAlign.Center)
              }, (s: Sensor) => s.id)
            }
            .width('100%')
            .justifyContent(FlexAlign.SpaceAround)
          }
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)

        // ===== 5. AI 快捷入口 =====
        AppCard({
          innerPadding: AppSpace.BASE,
          onClickAction: () => {}
        }) {
          Row() {
            Column() {
              AppIcon({ iconRes: $r('sys.symbol.mic_fill'), iconSize: 20, iconColor: AppColors.PRIMARY })
            }
            .width(40).height(40)
            .borderRadius(20)
            .backgroundColor(AppColors.PRIMARY_BG)
            .justifyContent(FlexAlign.Center)
            .alignItems(HorizontalAlign.Center)
            Column({ space: 2 }) {
              Text('和智能助手对话')
                .fontSize(AppFont.SIZE_BODY)
                .fontColor(AppColors.TEXT_PRIMARY)
                .fontWeight(FontWeight.Medium)
              Text('"帮我打开空调" · "家里安全吗"')
                .fontSize(AppFont.SIZE_FOOTNOTE)
                .fontColor(AppColors.TEXT_TERTIARY)
            }
            .alignItems(HorizontalAlign.Start)
            .margin({ left: AppSpace.SM })
            .layoutWeight(1)
            SymbolGlyph($r('sys.symbol.chevron_right'))
              .fontSize(16)
              .fontColor([AppColors.TEXT_TERTIARY])
          }
          .width('100%')
          .alignItems(VerticalAlign.Center)
        }
      }
      .width('100%')
      .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: 48, bottom: 100 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor(AppColors.BG_PAGE)
    .scrollBar(BarState.Off)
    .edgeEffect(EdgeEffect.Spring)
  }

  private sensorColor(s: Sensor): string {
    const map: Record<string, string> = {
      'temperature': AppColors.SENSOR_TEMP,
      'humidity': AppColors.SENSOR_HUMID,
      'air_quality': AppColors.SENSOR_AIR,
      'illuminance': AppColors.SENSOR_LIGHT
    };
    return map[s.type] || AppColors.PRIMARY;
  }
}
