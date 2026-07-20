/**
 * 监控页 · 经典鸿蒙浅色
 */
import { CameraCard } from '../components/CameraCard';
import { SensorCard } from '../components/SensorCard';
import { SectionHeader } from '../components/SectionHeader';
import { AppCard } from '../components/AppCard';
import { MonitorApi } from '../api/monitorApi';
import { SensorApi } from '../api/sensorApi';
import { Camera, AlertMessage, Sensor, SensorGroup, RouterSensorParam, RouterCameraParam } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';
import { router } from '@kit.ArkUI';

@Component
export struct MonitorPage {
  @State cameras: Camera[] = [];
  @State sensors: Sensor[] = [];
  @State alerts: AlertMessage[] = [];

  aboutToAppear(): void {
    this.loadData();
  }

  async loadData(): Promise<void> {
    const camerasPromise = MonitorApi.getCameras();
    const sensorsPromise = SensorApi.getSensors();
    const alertsPromise = MonitorApi.getAlerts();
    this.cameras = await camerasPromise;
    this.sensors = await sensorsPromise;
    this.alerts = await alertsPromise;
  }

  private sensorsByGroup(group: SensorGroup): Sensor[] {
    return this.sensors.filter(s => s.group === group);
  }

  @Builder
  sensorGroup(title: string, group: SensorGroup) {
    Column({ space: AppSpace.SM }) {
      SectionHeader({ title: title, subtitle: `${this.sensorsByGroup(group).length} 个传感器` })
      Grid() {
        ForEach(this.sensorsByGroup(group), (s: Sensor) => {
          GridItem() {
            SensorCard({
              sensor: s,
              onTap: (sensor: Sensor) => {
                const p: RouterSensorParam = { sensorId: sensor.id };
                router.pushUrl({ url: 'pages/detail/SensorDetailPage', params: p });
              }
            })
          }
        }, (s: Sensor) => s.id)
      }
      .columnsTemplate('1fr 1fr')
      .columnsGap(AppSpace.CARD_GAP)
      .rowsGap(AppSpace.CARD_GAP)
      .width('100%')
      .height(Math.ceil(this.sensorsByGroup(group).length / 2) * 120)
    }
    .width('100%')
    .alignItems(HorizontalAlign.Start)
  }

  private levelColor(level: string): string {
    return level === 'danger' ? AppColors.DANGER : level === 'warning' ? AppColors.WARNING : AppColors.PRIMARY;
  }

  private timeAgo(ts: number): string {
    const diff = Date.now() - ts;
    const m = Math.floor(diff / 60000);
    if (m < 1) return '刚刚';
    if (m < 60) return `${m} 分钟前`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h} 小时前`;
    return `${Math.floor(h / 24)} 天前`;
  }

  build() {
    Scroll() {
      Column({ space: AppSpace.BASE }) {
        // 标题
        Column({ space: 2 }) {
          Text('监控中心')
            .fontSize(AppFont.SIZE_TITLE_LG)
            .fontColor(AppColors.TEXT_PRIMARY)
            .fontWeight(FontWeight.Bold)
          Text(`${this.cameras.length} 个摄像头 · ${this.sensors.length} 个传感器`)
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.TEXT_TERTIARY)
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)

        // ===== 1. 摄像头网格 =====
        Column({ space: AppSpace.SM }) {
          SectionHeader({ title: '实时监控', subtitle: '摄像头预览' })
          Grid() {
            ForEach(this.cameras, (c: Camera) => {
              GridItem() {
                CameraCard({
                  camera: c,
                  onTap: (cam: Camera) => {
                    const p: RouterCameraParam = { cameraId: cam.id };
                    router.pushUrl({ url: 'pages/detail/CameraDetailPage', params: p });
                  }
                })
              }
            }, (c: Camera) => c.id)
          }
          .columnsTemplate('1fr 1fr')
          .columnsGap(AppSpace.CARD_GAP)
          .rowsGap(AppSpace.CARD_GAP)
          .width('100%')
          .height(Math.ceil(this.cameras.length / 2) * 170)
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)

        // ===== 2. 传感器看板 =====
        this.sensorGroup('环境监测', SensorGroup.ENVIRONMENT)
        this.sensorGroup('安防', SensorGroup.SECURITY)
        this.sensorGroup('能耗', SensorGroup.ENERGY)
        this.sensorGroup('其他', SensorGroup.OTHER)

        // ===== 3. 警报消息流 =====
        Column({ space: AppSpace.SM }) {
          SectionHeader({ title: '警报消息', subtitle: `${this.alerts.filter(a => !a.isRead).length} 条未读` })
          ForEach(this.alerts, (a: AlertMessage) => {
            AppCard({ innerPadding: AppSpace.BASE }) {
              Row() {
                Column({ space: 4 }) {
                  Row({ space: 6 }) {
                    Circle({ width: 6, height: 6 }).fill(this.levelColor(a.level))
                    Text(a.source)
                      .fontSize(AppFont.SIZE_FOOTNOTE)
                      .fontColor(AppColors.TEXT_SECONDARY)
                      .fontWeight(FontWeight.Medium)
                    Blank()
                    Text(this.timeAgo(a.timestamp))
                      .fontSize(AppFont.SIZE_CAPTION)
                      .fontColor(AppColors.TEXT_TERTIARY)
                  }
                  .width('100%')
                  Text(a.content)
                    .fontSize(AppFont.SIZE_BODY)
                    .fontColor(AppColors.TEXT_PRIMARY)
                }
                .alignItems(HorizontalAlign.Start)
                .layoutWeight(1)
                if (!a.isRead) {
                  Circle({ width: 6, height: 6 }).fill(AppColors.PRIMARY)
                }
              }
              .width('100%')
              .alignItems(VerticalAlign.Top)
            }
          }, (a: AlertMessage) => a.id)
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)
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
}
