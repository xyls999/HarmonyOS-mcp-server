/**
 * 设备详情页 · 经典鸿蒙浅色
 */
import { AppCard } from '../../components/AppCard';
import { DeviceApi } from '../../api/deviceApi';
import { Device, DeviceType, DeviceStatus } from '../../api/types';
import { AppColors } from '../../theme/Colors';
import { AppSpace } from '../../theme/Spacing';
import { AppFont } from '../../theme/Typography';
import { router } from '@kit.ArkUI';

interface DeviceDetailParams {
  deviceId: string;
}

@Entry
@Component
struct DeviceDetailPage {
  @State device: Device | null = null;
  @State deviceId: string = 'light_01';

  aboutToAppear(): void {
    // 接收路由参数
    const params = router.getParams() as DeviceDetailParams;
    if (params && params.deviceId) {
      this.deviceId = params.deviceId;
    }
    this.loadData();
  }

  async loadData(): Promise<void> {
    const d = await DeviceApi.getDevice(this.deviceId);
    this.device = d ?? null;
  }

  build() {
    Column() {
      if (this.device) {
        Scroll() {
          Column({ space: AppSpace.BASE }) {
            // 返回 + 标题
            Row() {
              SymbolGlyph($r('sys.symbol.chevron_left'))
                .fontSize(24)
                .fontColor([AppColors.TEXT_PRIMARY])
              Text(this.device.name)
                .fontSize(AppFont.SIZE_TITLE)
                .fontColor(AppColors.TEXT_PRIMARY)
                .fontWeight(FontWeight.Bold)
                .layoutWeight(1)
                .textAlign(TextAlign.Center)
              Column() {
                SymbolGlyph(this.device.icon)
                  .fontSize(24)
                  .fontColor([AppColors.PRIMARY])
              }
              .width(28)
            }
            .width('100%')
            .padding({ top: 44, bottom: AppSpace.MD })

            this.detailContent()
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
  detailContent() {
    if (this.device) {
      Column({ space: AppSpace.BASE }) {
        // 主控制大卡
        AppCard({ innerPadding: AppSpace.XXL }) {
          Column({ space: AppSpace.MD }) {
            Column() {
              SymbolGlyph(this.device.icon)
                .fontSize(48)
                .fontColor([AppColors.PRIMARY])
            }
            .width(96).height(96)
            .borderRadius(48)
            .backgroundColor(AppColors.PRIMARY_BG)
            .justifyContent(FlexAlign.Center)
            .alignItems(HorizontalAlign.Center)
            Text(this.device.isOn ? '运行中' : '已关闭')
              .fontSize(AppFont.SIZE_BODY_LG)
              .fontColor(this.device.isOn ? AppColors.SUCCESS : AppColors.TEXT_TERTIARY)
            Text(this.device.room)
              .fontSize(AppFont.SIZE_FOOTNOTE)
              .fontColor(AppColors.TEXT_TERTIARY)

              Toggle({ type: ToggleType.Switch, isOn: this.device.isOn })
              .selectedColor(AppColors.PRIMARY)
              .width(56).height(32)
              .onChange(async (on: boolean) => {
                if (this.device) {
                  await DeviceApi.toggle(this.device.id, on);
                  if (this.device.type === DeviceType.LIGHT) {
                    await DeviceApi.sendBearPiCommand(`brightness:${this.device.id === 'light_01' ? 0 : 1}:${on ? this.device.primaryValue || 80 : 0}`);
                  }
                  const d = this.device;
                  this.device = {
                    id: d.id, name: d.name, type: d.type, status: d.status, room: d.room,
                    icon: d.icon, primaryValue: d.primaryValue, isOn: on, mode: d.mode, battery: d.battery
                  };
                }
              })
          }
          .alignItems(HorizontalAlign.Center)
        }

        // 设备参数
        AppCard({ innerPadding: AppSpace.BASE }) {
          Column({ space: AppSpace.MD }) {
            Text('设备参数')
              .fontSize(AppFont.SIZE_BODY_LG)
              .fontColor(AppColors.TEXT_PRIMARY)
              .fontWeight(FontWeight.Medium)
            this.paramRow('设备类型', this.device.type.toUpperCase())
            this.paramRow('安装位置', this.device.room)
            this.paramRow('在线状态', this.device.status === DeviceStatus.OFFLINE ? '离线' : '在线')
            this.paramRow('通信协议', 'WiFi')
            if (this.device.battery !== undefined) {
              this.paramRow('电量', `${this.device.battery}%`)
            }
            if (this.device.mode) {
              this.paramRow('运行模式', this.device.mode)
            }
          }
          .width('100%')
          .alignItems(HorizontalAlign.Start)
        }
      }
      .width('100%')
    }
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
