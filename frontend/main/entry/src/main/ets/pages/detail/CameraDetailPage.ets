/**
 * 摄像头详情页 · 经典鸿蒙浅色
 */
import { AppCard } from '../../components/AppCard';
import { MonitorApi } from '../../api/monitorApi';
import { Camera, DeviceStatus } from '../../api/types';
import { AppColors } from '../../theme/Colors';
import { AppSpace } from '../../theme/Spacing';
import { AppFont } from '../../theme/Typography';
import { router } from '@kit.ArkUI';

interface CameraDetailParams {
  cameraId: string;
}

@Entry
@Component
struct CameraDetailPage {
  @State camera: Camera | null = null;
  @State cameraId: string = 'cam_01';

  aboutToAppear(): void {
    const params = router.getParams() as CameraDetailParams;
    if (params && params.cameraId) {
      this.cameraId = params.cameraId;
    }
    this.loadData();
  }

  async loadData(): Promise<void> {
    const cams = await MonitorApi.getCameras();
    const found = cams.find(c => c.id === this.cameraId);
    this.camera = found ?? null;
  }

  build() {
    Column() {
      if (this.camera) {
        Scroll() {
          Column({ space: AppSpace.BASE }) {
            Row() {
              SymbolGlyph($r('sys.symbol.chevron_left'))
                .fontSize(24)
                .fontColor([AppColors.TEXT_PRIMARY])
              Text(this.camera.name)
                .fontSize(AppFont.SIZE_TITLE)
                .fontColor(AppColors.TEXT_PRIMARY)
                .fontWeight(FontWeight.Bold)
                .layoutWeight(1)
                .textAlign(TextAlign.Center)
              SymbolGlyph($r('sys.symbol.ellipsis_circle'))
                .fontSize(20)
                .fontColor([AppColors.TEXT_TERTIARY])
            }
            .width('100%')
            .padding({ top: 44, bottom: AppSpace.MD })

            // 实时画面
            Stack() {
              Column()
                .width('100%')
                .height(220)
                .backgroundColor(this.camera.previewColor)
                .linearGradient({
                  angle: 135,
                  colors: [[`${this.camera.previewColor}CC`, 0], ['#1E5AA899', 1]]
                })

              if (this.camera.status === DeviceStatus.OFFLINE) {
                Column({ space: 8 }) {
                  SymbolGlyph($r('sys.symbol.camera_fill'))
                    .fontSize(36)
                    .fontColor([AppColors.TEXT_INVERSE])
                  Text('设备离线')
                    .fontSize(AppFont.SIZE_BODY)
                    .fontColor(AppColors.TEXT_INVERSE)
                }
                .justifyContent(FlexAlign.Center)
                .alignItems(HorizontalAlign.Center)
              } else {
                Column({ space: 8 }) {
                  SymbolGlyph($r('sys.symbol.video_fill'))
                    .fontSize(44)
                    .fontColor([AppColors.TEXT_INVERSE])
                  Text('实时画面')
                    .fontSize(AppFont.SIZE_CAPTION)
                    .fontColor('#FFFFFFCC')
                }
                .justifyContent(FlexAlign.Center)
                .alignItems(HorizontalAlign.Center)
              }

              Row() {
                if (this.camera.isRecording) {
                  Row({ space: 4 }) {
                    Circle({ width: 6, height: 6 }).fill(AppColors.DANGER)
                    Text('REC').fontSize(9).fontColor(AppColors.TEXT_INVERSE)
                  }
                  .padding({ left: 6, right: 6, top: 3, bottom: 3 })
                  .borderRadius(4)
                  .backgroundColor('#801E5AA8')
                }
                Blank()
                Text(this.camera.resolution)
                  .fontSize(9)
                  .fontColor(AppColors.TEXT_INVERSE)
                  .padding({ left: 6, right: 6, top: 3, bottom: 3 })
                  .borderRadius(4)
                  .backgroundColor('#801E5AA8')
              }
              .width('100%')
              .padding(AppSpace.SM)
              .alignItems(VerticalAlign.Top)
            }
            .width('100%')
            .height(220)
            .borderRadius(AppSpace.RADIUS_CARD)
            .clip(true)

            // 控制按钮组
            AppCard({ innerPadding: AppSpace.BASE }) {
              Row({ space: AppSpace.MD }) {
                this.ctrlBtn(this.camera.isRecording ? $r('sys.symbol.stop_circle_fill') : $r('sys.symbol.record_circle'), this.camera.isRecording ? '停止' : '录像',
                  async () => {
                    if (this.camera) {
                      const next = !this.camera.isRecording;
                      await MonitorApi.toggleRecord(this.camera.id, next);
                      const c = this.camera;
                      this.camera = {
                        id: c.id, name: c.name, room: c.room, status: c.status,
                        isRecording: next, resolution: c.resolution, previewColor: c.previewColor
                      };
                    }
                  })
                this.ctrlBtn($r('sys.symbol.camera_circle_fill'), '截图', () => {})
                this.ctrlBtn($r('sys.symbol.phone_fill'), '通话', () => {})
                this.ctrlBtn($r('sys.symbol.arrow_counterclockwise'), '回放', () => {})
              }
              .width('100%')
              .justifyContent(FlexAlign.SpaceAround)
            }

            // 云台控制
            AppCard({ innerPadding: AppSpace.LG }) {
              Column({ space: AppSpace.MD }) {
                Text('云台控制')
                  .fontSize(AppFont.SIZE_BODY_LG)
                  .fontColor(AppColors.TEXT_PRIMARY)
                  .fontWeight(FontWeight.Medium)
                Column({ space: AppSpace.SM }) {
                  this.ptzBtn($r('sys.symbol.chevron_up'))
                  Row({ space: AppSpace.LG }) {
                    this.ptzBtn($r('sys.symbol.chevron_left'))
                    Column() {
                      Text('●').fontSize(14).fontColor(AppColors.TEXT_TERTIARY)
                    }.width(44).height(44).borderRadius(22)
                      .backgroundColor(AppColors.BG_INPUT).justifyContent(FlexAlign.Center)
                      .alignItems(HorizontalAlign.Center)
                    this.ptzBtn($r('sys.symbol.chevron_right'))
                  }
                  this.ptzBtn($r('sys.symbol.chevron_down'))
                }
                .alignItems(HorizontalAlign.Center)
              }
              .width('100%')
              .alignItems(HorizontalAlign.Center)
            }

            // 设备信息
            AppCard({ innerPadding: AppSpace.BASE }) {
              Column({ space: AppSpace.MD }) {
                Text('设备信息')
                  .fontSize(AppFont.SIZE_BODY_LG)
                  .fontColor(AppColors.TEXT_PRIMARY)
                  .fontWeight(FontWeight.Medium)
                this.paramRow('位置', this.camera.room)
                this.paramRow('分辨率', this.camera.resolution)
                this.paramRow('状态', this.camera.status === DeviceStatus.OFFLINE ? '离线' : '在线')
                this.paramRow('录像', this.camera.isRecording ? '进行中' : '未开启')
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

  @Builder
  ctrlBtn(icon: Resource, label: string, action: () => void) {
    Column({ space: 4 }) {
      Column() {
        SymbolGlyph(icon)
          .fontSize(18)
          .fontColor([AppColors.TEXT_SECONDARY])
      }
      .width(44).height(44)
      .borderRadius(22)
      .backgroundColor(AppColors.BG_INPUT)
      .justifyContent(FlexAlign.Center)
      .alignItems(HorizontalAlign.Center)
      Text(label)
        .fontSize(AppFont.SIZE_CAPTION)
        .fontColor(AppColors.TEXT_TERTIARY)
    }
    .alignItems(HorizontalAlign.Center)
    .onClick(() => action())
  }

  @Builder
  ptzBtn(arrow: Resource) {
    Column() {
      SymbolGlyph(arrow)
        .fontSize(18)
        .fontColor([AppColors.TEXT_SECONDARY])
    }
    .width(44).height(44)
    .borderRadius(22)
    .backgroundColor(AppColors.BG_INPUT)
    .justifyContent(FlexAlign.Center)
    .alignItems(HorizontalAlign.Center)
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
