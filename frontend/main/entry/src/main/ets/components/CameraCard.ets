/**
 * 摄像头预览卡 · 经典鸿蒙浅色
 */
import { AppCard } from './AppCard';
import { Camera, DeviceStatus } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct CameraCard {
  @Prop camera: Camera;
  onTap?: (camera: Camera) => void;

  build() {
    AppCard({
      innerPadding: 0,
      cornerRadius: AppSpace.RADIUS_CARD,
      onClickAction: () => { if (this.onTap) this.onTap(this.camera); }
    }) {
      Column() {
        // 预览区（浅色占位）
        Stack({ alignContent: Alignment.TopStart }) {
          Column()
            .width('100%')
            .height(96)
            .backgroundColor(this.camera.previewColor)
            .linearGradient({
              angle: 135,
              colors: [[`${this.camera.previewColor}FF`, 0], ['#801E5AA8', 1]]
            })

          Text(this.camera.name)
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.TEXT_INVERSE)
            .fontWeight(FontWeight.Medium)
            .padding({ left: AppSpace.SM, top: AppSpace.SM })

          // 右上: 状态角标
          Row({ space: 4 }) {
            if (this.camera.isRecording) {
              Row({ space: 3 }) {
                Circle({ width: 5, height: 5 }).fill(AppColors.DANGER)
                Text('REC')
                  .fontSize(9)
                  .fontColor(AppColors.TEXT_INVERSE)
              }
              .padding({ left: 6, right: 6, top: 2, bottom: 2 })
              .borderRadius(4)
              .backgroundColor('#801E5AA8')
            }
          }
          .position({ x: '62%', y: AppSpace.SM })
        }
        .width('100%')
        .height(96)
        .borderRadius({ topLeft: AppSpace.RADIUS_CARD, topRight: AppSpace.RADIUS_CARD })
        .clip(true)

        // 底部信息栏
        Row() {
          Column({ space: 2 }) {
            Text(this.camera.room)
              .fontSize(AppFont.SIZE_FOOTNOTE)
              .fontColor(AppColors.TEXT_SECONDARY)
            Row({ space: 4 }) {
              Circle({ width: 5, height: 5 })
                .fill(this.camera.status === DeviceStatus.OFFLINE ? AppColors.OFFLINE : AppColors.ONLINE)
              Text(this.camera.status === DeviceStatus.OFFLINE ? '离线' : '在线')
                .fontSize(AppFont.SIZE_CAPTION)
                .fontColor(AppColors.TEXT_TERTIARY)
            }
          }
          .alignItems(HorizontalAlign.Start)
          .layoutWeight(1)

          Text(this.camera.resolution)
            .fontSize(AppFont.SIZE_CAPTION)
            .fontColor(AppColors.TEXT_TERTIARY)
            .padding({ left: 6, right: 6, top: 2, bottom: 2 })
            .borderRadius(4)
            .backgroundColor(AppColors.BG_INPUT)
        }
        .width('100%')
        .padding(AppSpace.SM)
        .justifyContent(FlexAlign.SpaceBetween)
        .alignItems(VerticalAlign.Center)
      }
      .width('100%')
    }
  }
}
