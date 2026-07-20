/**
 * 服务端管理面板 · 经典鸿蒙浅色
 */
import { AppCard } from './AppCard';
import { ServerStatus } from '../api/types';
import { UserApi } from '../api/userApi';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct ServerManagerPanel {
  @Prop server: ServerStatus;
  @State restartLoading: boolean = false;

  @Builder
  metricBar(label: string, value: number, color: string) {
    Column({ space: 4 }) {
      Row() {
        Text(label)
          .fontSize(AppFont.SIZE_CAPTION)
          .fontColor(AppColors.TEXT_TERTIARY)
        Blank()
        Text(`${Math.round(value)}%`)
          .fontSize(AppFont.SIZE_CAPTION)
          .fontColor(AppColors.TEXT_SECONDARY)
      }
      .width('100%')
      Progress({ value: value, total: 100, type: ProgressType.Linear })
        .width('100%')
        .color(color)
        .backgroundColor(AppColors.BG_INPUT)
        .style({ strokeWidth: 4 })
    }
    .width('100%')
  }

  build() {
    AppCard({ innerPadding: AppSpace.BASE }) {
      Column({ space: AppSpace.MD }) {
        // 顶部: 标题 + 状态
        Row() {
          Row({ space: 8 }) {
            Circle({ width: 8, height: 8 })
              .fill(this.server.isOnline ? AppColors.ONLINE : AppColors.OFFLINE)
            Text('服务端')
              .fontSize(AppFont.SIZE_BODY_LG)
              .fontColor(AppColors.TEXT_PRIMARY)
              .fontWeight(FontWeight.Medium)
          }
          .alignItems(VerticalAlign.Center)
          .layoutWeight(1)

          Text(this.server.isOnline ? '运行中' : '离线')
            .fontSize(AppFont.SIZE_CAPTION)
            .fontColor(this.server.isOnline ? AppColors.SUCCESS : AppColors.DANGER)
            .padding({ left: 8, right: 8, top: 3, bottom: 3 })
            .borderRadius(AppSpace.RADIUS_PILL)
            .backgroundColor(this.server.isOnline ? '#EFF6FF' : '#EAF2FF')
        }
        .width('100%')

        // 连接信息
        Column({ space: 2 }) {
          Text(this.server.host + ':' + this.server.port)
            .fontSize(AppFont.SIZE_BODY)
            .fontColor(AppColors.TEXT_PRIMARY)
            .fontFamily('monospace')
          Row({ space: 6 }) {
            Text(this.server.protocol === 'starflash' ? '星闪' : 'WiFi')
              .fontSize(AppFont.SIZE_CAPTION)
              .fontColor(AppColors.PRIMARY)
            Text('·')
              .fontSize(AppFont.SIZE_CAPTION)
              .fontColor(AppColors.TEXT_TERTIARY)
            Text(`${this.server.latency}ms`)
              .fontSize(AppFont.SIZE_CAPTION)
              .fontColor(this.server.latency < 50 ? AppColors.SUCCESS : AppColors.WARNING)
          }
        }
        .alignItems(HorizontalAlign.Start)
        .width('100%')

        // 资源用量
        this.metricBar('CPU', this.server.cpuUsage, AppColors.PRIMARY)
        this.metricBar('内存', this.server.memUsage, AppColors.PURPLE)
        this.metricBar('存储', this.server.storageUsage, AppColors.ORANGE)

        // 操作按钮
        Row({ space: AppSpace.SM }) {
          Button('重启服务')
            .layoutWeight(1)
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.TEXT_PRIMARY)
            .backgroundColor(AppColors.BG_INPUT)
            .borderRadius(AppSpace.RADIUS_BASE)
            .height(36)
            .onClick(async () => {
              this.restartLoading = true;
              await UserApi.restartServer();
              this.restartLoading = false;
            })
          Button('重新连接')
            .layoutWeight(1)
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.TEXT_INVERSE)
            .backgroundColor(AppColors.PRIMARY)
            .borderRadius(AppSpace.RADIUS_BASE)
            .height(36)
            .onClick(async () => {
              await UserApi.connectServer(this.server.host, this.server.port, this.server.protocol);
            })
        }
        .width('100%')
      }
      .width('100%')
    }
  }
}
