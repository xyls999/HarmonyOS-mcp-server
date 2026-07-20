/**
 * 我的页 · 经典鸿蒙浅色
 */
import { AppCard } from '../components/AppCard';
import { ServerManagerPanel } from '../components/ServerManagerPanel';
import { SectionHeader } from '../components/SectionHeader';
import { UserApi } from '../api/userApi';
import { UserProfile, ServerStatus } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct MinePage {
  @State user: UserProfile | null = null;
  @State server: ServerStatus | null = null;

  aboutToAppear(): void {
    this.loadData();
  }

  async loadData(): Promise<void> {
    const profilePromise = UserApi.getProfile();
    const serverPromise = UserApi.getServerStatus();
    this.user = await profilePromise;
    this.server = await serverPromise;
  }

  @Builder
  settingItem(icon: Resource, label: string, value: string = '', color: string = AppColors.PRIMARY) {
    Row() {
      Row({ space: AppSpace.BASE }) {
        Column() {
          SymbolGlyph(icon)
            .fontSize(15)
            .fontColor([color])
        }
        .width(28).height(28)
        .borderRadius(14)
        .backgroundColor(`${color}1A`)
        .justifyContent(FlexAlign.Center)
        .alignItems(HorizontalAlign.Center)
        Text(label)
          .fontSize(AppFont.SIZE_BODY)
          .fontColor(AppColors.TEXT_PRIMARY)
      }
      .alignItems(VerticalAlign.Center)
      .layoutWeight(1)
      if (value) {
        Text(value)
          .fontSize(AppFont.SIZE_FOOTNOTE)
          .fontColor(AppColors.TEXT_TERTIARY)
      }
      SymbolGlyph($r('sys.symbol.chevron_right'))
        .fontSize(14)
        .fontColor([AppColors.TEXT_TERTIARY])
    }
    .width('100%')
    .padding({ top: AppSpace.MD, bottom: AppSpace.MD })
    .alignItems(VerticalAlign.Center)
  }

  build() {
    Scroll() {
      Column({ space: AppSpace.BASE }) {
        Text('我的')
          .fontSize(AppFont.SIZE_TITLE_LG)
          .fontColor(AppColors.TEXT_PRIMARY)
          .fontWeight(FontWeight.Bold)
          .width('100%')

        // 用户信息卡
        if (this.user) {
          AppCard({ innerPadding: AppSpace.LG }) {
            Column({ space: AppSpace.BASE }) {
              Row({ space: AppSpace.BASE }) {
                Text(this.user.nickname.charAt(0))
                  .fontSize(AppFont.SIZE_LARGE)
                  .fontColor(AppColors.PRIMARY)
                  .fontWeight(FontWeight.Bold)
                  .width(56).height(56)
                  .borderRadius(28)
                  .backgroundColor(AppColors.PRIMARY_BG)
                  .textAlign(TextAlign.Center)
                Column({ space: 4 }) {
                  Text(this.user.nickname)
                    .fontSize(AppFont.SIZE_TITLE)
                    .fontColor(AppColors.TEXT_PRIMARY)
                    .fontWeight(FontWeight.Bold)
                  Text(this.user.homeName)
                    .fontSize(AppFont.SIZE_FOOTNOTE)
                    .fontColor(AppColors.TEXT_TERTIARY)
                }
                .alignItems(HorizontalAlign.Start)
                .layoutWeight(1)
              }
              .width('100%')

              // 统计数据
              Row() {
                Column({ space: 2 }) {
                  Text(`${this.user.deviceCount}`)
                    .fontSize(AppFont.SIZE_TITLE_LG)
                    .fontColor(AppColors.TEXT_PRIMARY)
                    .fontWeight(FontWeight.Bold)
                  Text('设备')
                    .fontSize(AppFont.SIZE_CAPTION)
                    .fontColor(AppColors.TEXT_TERTIARY)
                }
                .layoutWeight(1)
                .alignItems(HorizontalAlign.Center)
                Column().width(0.5).height(28).backgroundColor(AppColors.DIVIDER)
                Column({ space: 2 }) {
                  Text(`${this.user.memberCount}`)
                    .fontSize(AppFont.SIZE_TITLE_LG)
                    .fontColor(AppColors.TEXT_PRIMARY)
                    .fontWeight(FontWeight.Bold)
                  Text('成员')
                    .fontSize(AppFont.SIZE_CAPTION)
                    .fontColor(AppColors.TEXT_TERTIARY)
                }
                .layoutWeight(1)
                .alignItems(HorizontalAlign.Center)
                Column().width(0.5).height(28).backgroundColor(AppColors.DIVIDER)
                Column({ space: 2 }) {
                  Text('Pro')
                    .fontSize(AppFont.SIZE_TITLE_LG)
                    .fontColor(AppColors.WARNING)
                    .fontWeight(FontWeight.Bold)
                  Text('会员')
                    .fontSize(AppFont.SIZE_CAPTION)
                    .fontColor(AppColors.TEXT_TERTIARY)
                }
                .layoutWeight(1)
                .alignItems(HorizontalAlign.Center)
              }
              .width('100%')
            }
            .width('100%')
          }
        }

        // 服务端管理
        if (this.server) {
          Column({ space: AppSpace.SM }) {
            SectionHeader({ title: '服务端管理', subtitle: 'WiFi · 星闪通信' })
            ServerManagerPanel({ server: this.server })
          }
          .width('100%')
          .alignItems(HorizontalAlign.Start)
        }

        // 设置项
        Column({ space: AppSpace.SM }) {
          SectionHeader({ title: '设置', subtitle: '偏好与帮助' })
          AppCard({ innerPadding: AppSpace.BASE }) {
            Column() {
              this.settingItem($r('sys.symbol.bell_fill'), '消息通知', '已开启', AppColors.DANGER)
              Divider().color(AppColors.DIVIDER).strokeWidth(0.5)
              this.settingItem($r('sys.symbol.moon_fill'), '深色模式', '跟随系统', AppColors.INDIGO)
              Divider().color(AppColors.DIVIDER).strokeWidth(0.5)
              this.settingItem($r('sys.symbol.lock_fill'), '隐私与安全', '', AppColors.SUCCESS)
              Divider().color(AppColors.DIVIDER).strokeWidth(0.5)
              this.settingItem($r('sys.symbol.wifi'), '网络设置', 'WiFi 已连接', AppColors.PRIMARY)
              Divider().color(AppColors.DIVIDER).strokeWidth(0.5)
              this.settingItem($r('sys.symbol.questionmark_circle'), '帮助与反馈', '', AppColors.ORANGE)
              Divider().color(AppColors.DIVIDER).strokeWidth(0.5)
              this.settingItem($r('sys.symbol.info_circle'), '关于', 'v1.0.0', AppColors.PURPLE)
            }
            .width('100%')
          }
        }
        .width('100%')
        .alignItems(HorizontalAlign.Start)

        // 退出登录
        Text('退出登录')
          .fontSize(AppFont.SIZE_BODY)
          .fontColor(AppColors.DANGER)
          .textAlign(TextAlign.Center)
          .width('100%')
          .padding(AppSpace.BASE)
          .borderRadius(AppSpace.RADIUS_CARD)
          .backgroundColor(AppColors.BG_CARD)
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
