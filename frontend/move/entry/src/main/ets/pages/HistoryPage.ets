import { V5Api } from '../api/v5Api';
import { AlertMessage, OperationRecord, SecurityEvent, Stats } from '../api/types';
import { GeometricBackdrop } from '../components/GeometricBackdrop';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct HistoryPage {
  @State stats: Stats | null = null;
  @State operations: OperationRecord[] = [];
  @State alerts: AlertMessage[] = [];
  @State securityEvents: SecurityEvent[] = [];
  @State activeSection: number = 0;
  @State pressedSection: number = -1;
  @State loading: boolean = false;
  @State loadError: string = '';
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;

  aboutToAppear(): void { this.load(); }

  async load(): Promise<void> {
    if (this.loading) return;
    this.loading = true;
    this.loadError = '';
    const statsTask = V5Api.getStats();
    const operationsTask = V5Api.getOperations();
    const alertsTask = V5Api.getAlerts();
    const securityTask = V5Api.getSecurityEvents();
    this.stats = await statsTask;
    this.operations = await operationsTask;
    this.alerts = await alertsTask;
    this.securityEvents = await securityTask;
    this.loadError = this.stats ? '' : '设备离线';
    this.loading = false;
  }

  private show(value: number | null | undefined, suffix: string = ''): string {
    return value === null || value === undefined ? '--' : `${value}${suffix}`;
  }

  private time(timestamp: number): string {
    return new Date(timestamp).toLocaleString();
  }

  private levelText(level: 'info' | 'warning' | 'danger'): string {
    if (level === 'danger') return '紧急';
    if (level === 'warning') return '注意';
    return '信息';
  }

  private levelColor(level: 'info' | 'warning' | 'danger'): string {
    if (level === 'danger') return AppColors.DANGER;
    if (level === 'warning') return AppColors.WARNING;
    return AppColors.primary(this.isDarkTheme);
  }

  @Builder
  metric(title: string, value: string, subtitle: string, alert: boolean = false) {
    Column({ space: AppSpace.SM }) {
      Row() {
        Column().width(28).height(2).backgroundColor(alert ? AppColors.DANGER : AppColors.primary(this.isDarkTheme))
        Blank()
        Circle({ width: 7, height: 7 }).fill(alert ? AppColors.DANGER : AppColors.ONLINE)
      }.width('100%')
      Text(value).fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
        .fontColor(alert ? AppColors.DANGER : AppColors.textPrimary(this.isDarkTheme)).width('100%')
      Text(title).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
        .fontColor(AppColors.textSecondary(this.isDarkTheme)).width('100%')
      Text(subtitle).fontSize(AppFont.SIZE_CAPTION)
        .fontColor(AppColors.textTertiary(this.isDarkTheme)).width('100%')
    }.height(132).padding(AppSpace.MD).backgroundColor(AppColors.card(this.isDarkTheme))
      .border({ width: 1, color: alert ? AppColors.DANGER : AppColors.hairline(this.isDarkTheme) })
      .alignItems(HorizontalAlign.Start)
  }

  @Builder
  sectionSelector(index: number, label: string, icon: Resource) {
    Stack({ alignContent: Alignment.BottomStart }) {
      Row({ space: AppSpace.SM }) {
        SymbolGlyph(icon).fontSize(18)
          .fontColor([this.activeSection === index ? AppColors.onPrimary(this.isDarkTheme) : AppColors.primary(this.isDarkTheme)])
        Text(label).fontSize(AppFont.SIZE_FOOTNOTE).fontWeight(FontWeight.Bold)
          .fontColor(this.activeSection === index ? AppColors.onPrimary(this.isDarkTheme) : AppColors.textPrimary(this.isDarkTheme))
      }.width('100%').height(50).justifyContent(FlexAlign.Center)
      Column().width(this.activeSection === index ? '100%' : 22).height(3)
        .backgroundColor(this.activeSection === index ? AppColors.onPrimary(this.isDarkTheme) : AppColors.primary(this.isDarkTheme))
        .animation({ duration: 220, curve: Curve.EaseOut })
    }.layoutWeight(1).height(54)
      .backgroundColor(this.activeSection === index ? AppColors.primary(this.isDarkTheme) : AppColors.card(this.isDarkTheme))
      .border({ width: 1, color: this.activeSection === index ? AppColors.primary(this.isDarkTheme) : AppColors.hairline(this.isDarkTheme) })
      .opacity(this.pressedSection === index ? 0.72 : 1)
      .scale({ x: this.pressedSection === index ? 0.97 : 1, y: this.pressedSection === index ? 0.97 : 1 })
      .animation({ duration: 140, curve: Curve.EaseOut })
      .onTouch((event: TouchEvent): void => { this.pressedSection = event.type === TouchType.Down ? index : -1; })
      .onClick((): void => { this.activeSection = index; })
  }

  @Builder
  emptyState(label: string) {
    Text(label).width('100%').height(88).textAlign(TextAlign.Center)
      .fontSize(AppFont.SIZE_BODY).fontColor(AppColors.textSecondary(this.isDarkTheme))
      .backgroundColor(AppColors.card(this.isDarkTheme))
      .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
  }

  @Builder
  operationRow(item: OperationRecord) {
    Row({ space: AppSpace.MD }) {
      SymbolGlyph(item.success ? $r('sys.symbol.checkmark_circle_fill') : $r('sys.symbol.exclamationmark_circle_fill'))
        .fontSize(20).fontColor([item.success ? AppColors.primary(this.isDarkTheme) : AppColors.DANGER])
      Column({ space: AppSpace.XS }) {
        Text(`${item.deviceName} · ${item.action}`).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
          .fontColor(AppColors.textPrimary(this.isDarkTheme))
        Text(item.message || this.time(item.timestamp)).fontSize(AppFont.SIZE_CAPTION)
          .fontColor(AppColors.textTertiary(this.isDarkTheme)).maxLines(2)
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Text(item.success ? '完成' : '失败').fontSize(AppFont.SIZE_CAPTION).fontWeight(FontWeight.Bold)
        .fontColor(item.success ? AppColors.primary(this.isDarkTheme) : AppColors.DANGER)
    }.width('100%').padding(AppSpace.MD).backgroundColor(AppColors.card(this.isDarkTheme))
      .border({ width: { bottom: 1 }, color: AppColors.hairline(this.isDarkTheme) })
  }

  @Builder
  alertRow(item: AlertMessage) {
    Row({ space: AppSpace.MD }) {
      Column().width(4).height(52).backgroundColor(this.levelColor(item.level))
      Column({ space: AppSpace.XS }) {
        Row() {
          Text(item.source).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
          Text(this.levelText(item.level)).fontSize(AppFont.SIZE_CAPTION).fontWeight(FontWeight.Bold)
            .fontColor(this.levelColor(item.level))
        }.width('100%')
        Text(item.content).fontSize(AppFont.SIZE_FOOTNOTE)
          .fontColor(AppColors.textSecondary(this.isDarkTheme)).maxLines(2)
        Text(this.time(item.timestamp)).fontSize(AppFont.SIZE_CAPTION)
          .fontColor(AppColors.textTertiary(this.isDarkTheme))
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
    }.width('100%').padding(AppSpace.MD).backgroundColor(AppColors.card(this.isDarkTheme))
      .border({ width: { bottom: 1 }, color: AppColors.hairline(this.isDarkTheme) })
  }

  @Builder
  securityRow(item: SecurityEvent) {
    Row({ space: AppSpace.MD }) {
      SymbolGlyph($r('sys.symbol.bell_fill')).fontSize(19).fontColor([this.levelColor(item.level)])
      Column({ space: AppSpace.XS }) {
        Text(`${item.room} · ${item.source}`).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
          .fontColor(AppColors.textPrimary(this.isDarkTheme))
        Text(item.content).fontSize(AppFont.SIZE_FOOTNOTE)
          .fontColor(AppColors.textSecondary(this.isDarkTheme)).maxLines(2)
        Text(this.time(item.timestamp)).fontSize(AppFont.SIZE_CAPTION)
          .fontColor(AppColors.textTertiary(this.isDarkTheme))
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
    }.width('100%').padding(AppSpace.MD).backgroundColor(AppColors.group(this.isDarkTheme))
      .border({ width: { bottom: 1 }, color: AppColors.hairline(this.isDarkTheme) })
  }

  build() {
    Stack() {
      GeometricBackdrop()
      Scroll() {
        Column({ space: AppSpace.LG }) {
          Row() {
            Text('记录').fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
              .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
            SymbolGlyph($r('sys.symbol.arrow_counterclockwise')).fontSize(19)
              .fontColor([AppColors.primary(this.isDarkTheme)]).width(40).height(40)
              .enabled(!this.loading).opacity(this.loading ? 0.45 : 1)
              .accessibilityText('刷新记录').onClick((): void => { this.load(); })
          }.width('100%').alignItems(VerticalAlign.Center)

          Row({ space: AppSpace.XS }) {
            this.sectionSelector(0, '环境', $r('sys.symbol.thermometer'))
            this.sectionSelector(1, '操作', $r('sys.symbol.clock_fill'))
            this.sectionSelector(2, '安全', $r('sys.symbol.bell_fill'))
          }.width('100%')

          if (this.loadError) {
            Row({ space: AppSpace.SM }) {
              SymbolGlyph($r('sys.symbol.exclamationmark_circle_fill')).fontSize(18).fontColor([AppColors.DANGER])
              Text(this.loadError).fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.DANGER).layoutWeight(1)
            }.width('100%').padding(AppSpace.MD).backgroundColor(AppColors.card(this.isDarkTheme))
              .border({ width: 1, color: AppColors.DANGER })
          }

          if (this.activeSection === 0) {
            Grid() {
              GridItem() { this.metric('客厅温度', this.show(this.stats?.living_temperature.value, '°C'), '阈值 28°C', this.stats?.living_temperature.is_alert) }
              GridItem() { this.metric('客厅湿度', this.show(this.stats?.living_humidity.value, '%'), '阈值 70%', this.stats?.living_humidity.is_alert) }
              GridItem() { this.metric('厨房烟雾', this.stats?.kitchen_smoke.online ? (this.stats.kitchen_smoke.smoke_alarm ? '报警' : '正常') : '--', '烟雾传感器', this.stats?.kitchen_smoke.smoke_alarm === true) }
              GridItem() { this.metric('厨房热敏', this.show(this.stats?.kitchen_thermal.thermal_mv, 'mV'), '阈值 1400mV', this.stats?.kitchen_thermal.temp_alarm === true) }
              GridItem() { this.metric('卫生间风扇', this.stats?.bathroom_fan.online ? `${this.stats.bathroom_fan.motor_speed ?? 0}%` : '--', this.stats?.bathroom_fan.motor_running ? '运行中' : '已停止') }
              GridItem() { this.metric('卧室窗帘', this.show(this.stats?.bedroom_curtain.position, '%'), this.stats?.bedroom_curtain.moving ? '移动中' : '已定位') }
            }.columnsTemplate('1fr 1fr').columnsGap(AppSpace.SM).rowsGap(AppSpace.SM).width('100%')
          } else if (this.activeSection === 1) {
            if (this.operations.length === 0 && !this.loading) this.emptyState('暂无操作记录')
            Column() {
              ForEach(this.operations, (item: OperationRecord) => { this.operationRow(item) },
                (item: OperationRecord) => item.id)
            }.width('100%').border({ width: this.operations.length > 0 ? 1 : 0, color: AppColors.hairline(this.isDarkTheme) })
          } else {
            Text('告警').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
              .fontColor(AppColors.textPrimary(this.isDarkTheme)).width('100%')
            if (this.alerts.length === 0 && !this.loading) this.emptyState('暂无告警')
            Column() {
              ForEach(this.alerts, (item: AlertMessage) => { this.alertRow(item) },
                (item: AlertMessage) => item.id)
            }.width('100%').border({ width: this.alerts.length > 0 ? 1 : 0, color: AppColors.hairline(this.isDarkTheme) })

            Text('安全事件').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
              .fontColor(AppColors.textPrimary(this.isDarkTheme)).width('100%')
            if (this.securityEvents.length === 0 && !this.loading) this.emptyState('暂无安全事件')
            Column() {
              ForEach(this.securityEvents, (item: SecurityEvent) => { this.securityRow(item) },
                (item: SecurityEvent) => item.id)
            }.width('100%').border({ width: this.securityEvents.length > 0 ? 1 : 0, color: AppColors.hairline(this.isDarkTheme) })
          }
        }.width('100%').padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING,
          top: AppSpace.PAGE_TOP, bottom: AppSpace.XL }).alignItems(HorizontalAlign.Start)
      }.width('100%').height('100%').scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
    }.width('100%').height('100%').backgroundColor(AppColors.page(this.isDarkTheme))
  }
}
