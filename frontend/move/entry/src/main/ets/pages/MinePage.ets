import { AppUserAccount, AuthApi, UserLoginRecord } from '../api/authApi';
import { Http } from '../api/http';
import { AppCard } from '../components/AppCard';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct MinePage {
  @State user: AppUserAccount | null = null;
  @State loginRecords: UserLoginRecord[] = [];
  @State busy: boolean = false;
  @State message: string = '';
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;
  @StorageLink('isOfflineMode') isOfflineMode: boolean = false;
  onFaceDoor?: () => void;

  aboutToAppear(): void { this.load(); }

  private async load(): Promise<void> {
    if (this.isOfflineMode) return;
    this.user = AuthApi.getCurrentUser() || await AuthApi.restoreUser();
    this.loginRecords = await AuthApi.getLoginRecords();
  }

  private roleLabel(): string {
    if (this.user?.role === 'admin') return '管理员';
    if (this.user?.role === 'core') return '核心用户';
    return '访客';
  }

  private permissionText(): string {
    if (!this.user?.allowed) return '已停用';
    if (this.user.role === 'admin' || this.user.role === 'core') return '全部设备';
    return `${this.user.allowedDevices.length} 台设备`;
  }

  private async logout(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    await AuthApi.logout();
    this.busy = false;
  }

  private async retryService(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    const available = await Http.checkService();
    Http.setOfflineMode(!available);
    this.message = available ? '' : '仍未连接远程服务';
    this.busy = false;
  }

  @Builder
  dataRow(label: string, value: string, danger: boolean = false) {
    Row({ space: AppSpace.MD }) {
      Text(label).fontSize(AppFont.SIZE_BODY).fontColor(AppColors.textSecondary(this.isDarkTheme)).layoutWeight(1)
      Text(value).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
        .fontColor(danger ? AppColors.DANGER : AppColors.textPrimary(this.isDarkTheme))
        .maxLines(1).textOverflow({ overflow: TextOverflow.Ellipsis })
    }.width('100%').height(52).border({ width: { bottom: 1 }, color: AppColors.hairline(this.isDarkTheme) })
  }

  @Builder
  faceDoorEntry() {
    Row({ space: AppSpace.MD }) {
      Stack({ alignContent: Alignment.Center }) {
        Column().width(40).height(40).backgroundColor(AppColors.primaryBg(this.isDarkTheme))
        SymbolGlyph($r('sys.symbol.lock_open_fill')).fontSize(21)
          .fontColor([AppColors.primary(this.isDarkTheme)])
      }.width(40).height(40)
      Text('人脸门禁').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
        .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
      SymbolGlyph($r('sys.symbol.arrow_right')).fontSize(18)
        .fontColor([AppColors.textSecondary(this.isDarkTheme)])
    }.width('100%').height(64).padding({ left: AppSpace.BASE, right: AppSpace.BASE })
      .backgroundColor(AppColors.card(this.isDarkTheme))
      .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
      .onClick((): void => { if (this.onFaceDoor) this.onFaceDoor(); })
  }

  @Builder
  offlineAccount() {
    Column({ space: AppSpace.LG }) {
      Text('账号').fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
        .fontColor(AppColors.textPrimary(this.isDarkTheme)).width('100%')
      this.faceDoorEntry()
      AppCard({ innerPadding: AppSpace.LG, clickable: false }) {
        Column({ space: AppSpace.MD }) {
          SymbolGlyph($r('sys.symbol.wifi_slash')).fontSize(28).fontColor([AppColors.OFFLINE])
          Text('未连接远程服务').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.textPrimary(this.isDarkTheme))
        }.width('100%').alignItems(HorizontalAlign.Center)
      }
      Button(this.busy ? '检测中' : '重新检测')
        .width('100%').height(48).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
        .fontColor(AppColors.onPrimary(this.isDarkTheme)).backgroundColor(AppColors.primary(this.isDarkTheme))
        .enabled(!this.busy).onClick((): void => { this.retryService(); })
      if (this.message) {
        Text(this.message).width('100%').textAlign(TextAlign.Center)
          .fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.DANGER)
      }
    }.width('100%').padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING,
      top: AppSpace.PAGE_TOP, bottom: AppSpace.XL }).alignItems(HorizontalAlign.Start)
  }

  build() {
    Stack() {
      if (this.isOfflineMode) {
        this.offlineAccount()
      } else {
        Scroll() {
          Column({ space: AppSpace.LG }) {
            Text('账号').fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
              .fontColor(AppColors.textPrimary(this.isDarkTheme)).width('100%')

            this.faceDoorEntry()

            AppCard({ innerPadding: AppSpace.BASE, clickable: false }) {
              Column() {
                this.dataRow('昵称', this.user?.nickname ?? '--')
                this.dataRow('用户 ID', this.user?.id ?? '--')
                this.dataRow('角色', this.roleLabel())
                this.dataRow('权限', this.permissionText(), !this.user?.allowed)
                if (this.user?.createdAt) this.dataRow('注册日期', this.user.createdAt)
              }.width('100%')
            }

            if (this.user?.role === 'guest' && this.user.allowedDevices.length > 0) {
              Text('可用设备').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
                .fontColor(AppColors.textPrimary(this.isDarkTheme)).width('100%')
              AppCard({ innerPadding: AppSpace.MD, clickable: false }) {
                Column() {
                  ForEach(this.user.allowedDevices, (deviceId: string, index: number) => {
                    Row() {
                      Text(`${index + 1}`).width(28).fontSize(AppFont.SIZE_CAPTION)
                        .fontColor(AppColors.primary(this.isDarkTheme))
                      Text(deviceId).fontSize(AppFont.SIZE_BODY).fontColor(AppColors.textPrimary(this.isDarkTheme))
                    }.width('100%').height(38)
                  }, (deviceId: string) => deviceId)
                }.width('100%')
              }
            }

            Text('登录日期').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
              .fontColor(AppColors.textPrimary(this.isDarkTheme)).width('100%')
            AppCard({ innerPadding: AppSpace.BASE, clickable: false }) {
              if (this.loginRecords.length > 0) {
                Row({ space: AppSpace.MD }) {
                  SymbolGlyph($r('sys.symbol.checkmark_circle_fill')).fontSize(20)
                    .fontColor([AppColors.primary(this.isDarkTheme)])
                  Text(this.loginRecords[0].loginAt).fontSize(AppFont.SIZE_BODY)
                    .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
                }.width('100%').height(46)
              } else {
                Text('--').fontSize(AppFont.SIZE_BODY).fontColor(AppColors.textSecondary(this.isDarkTheme))
              }
            }

            Row({ space: AppSpace.SM }) {
              if (this.busy) {
                LoadingProgress().width(19).height(19).color(AppColors.textPrimary(this.isDarkTheme))
              } else {
                SymbolGlyph($r('sys.symbol.arrow_right')).fontSize(19)
                  .fontColor([AppColors.textPrimary(this.isDarkTheme)])
              }
              Text(this.busy ? '正在退出' : '退出登录').fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
                .fontColor(AppColors.textPrimary(this.isDarkTheme))
            }.width('100%').height(50).justifyContent(FlexAlign.Center)
              .backgroundColor(AppColors.card(this.isDarkTheme))
              .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
              .enabled(!this.busy).onClick((): void => { this.logout(); })
          }.width('100%').padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING,
            top: AppSpace.PAGE_TOP, bottom: AppSpace.XL }).alignItems(HorizontalAlign.Start)
        }.width('100%').height('100%').scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
      }
    }.width('100%').height('100%').backgroundColor(AppColors.page(this.isDarkTheme))
  }
}
