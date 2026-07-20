import { ChatAction, ChatMessage, ChatRole, ChartConfig, ChartSeries } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';

@Component
export struct ChatBubble {
  @Prop message: ChatMessage;
  onSpeak?: (text: string) => void;
  onRate?: (message: ChatMessage) => void;
  @State appeared: boolean = false;
  @State imageFailed: boolean = false;
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;

  aboutToAppear(): void {
    setTimeout((): void => { this.appeared = true; }, 20);
  }

  private seriesText(series: ChartSeries): string {
    return series.data.map((value: number | string): string => `${value}`).join('  /  ');
  }

  private seriesMax(series: ChartSeries): number {
    let max = 1;
    series.data.forEach((value: number | string): void => {
      if (typeof value === 'number' && value > max) max = value;
    });
    return max;
  }

  private numericValue(value: number | string): number {
    return typeof value === 'number' ? Math.max(0, value) : 0;
  }

  @Builder
  actionSummary() {
    Column({ space: AppSpace.SM }) {
      Row() {
        Text(this.message.sceneName || '设备调整').fontSize(AppFont.SIZE_FOOTNOTE).fontWeight(FontWeight.Bold)
          .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
        Text(`${this.message.actions?.filter((item: ChatAction): boolean => item.success).length || 0}/${this.message.actions?.length || 0}`)
          .fontSize(AppFont.SIZE_CAPTION).fontColor(AppColors.primary(this.isDarkTheme))
      }.width('100%')
      ForEach(this.message.actions || [], (item: ChatAction) => {
        Row({ space: AppSpace.SM }) {
          SymbolGlyph(item.success ? $r('sys.symbol.checkmark_circle_fill') : $r('sys.symbol.exclamationmark_circle_fill'))
            .fontSize(16).fontColor([item.success ? AppColors.ONLINE : AppColors.DANGER])
          Text(item.deviceName).fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(AppColors.textSecondary(this.isDarkTheme)).layoutWeight(1)
          Text(item.action).fontSize(AppFont.SIZE_CAPTION)
            .fontColor(item.success ? AppColors.textPrimary(this.isDarkTheme) : AppColors.DANGER)
        }.width('100%')
      }, (item: ChatAction, index: number) => `${this.message.id}_${item.deviceId}_${index}`)
    }.width('100%').padding({ top: AppSpace.SM, bottom: AppSpace.SM })
      .border({ width: { top: 1, bottom: 1 }, color: AppColors.hairline(this.isDarkTheme) })
  }

  @Builder
  chartCardBuilder(chart: ChartConfig) {
    Column({ space: 8 }) {
      Row() {
        Text(chart.title)
          .fontSize(AppFont.SIZE_CAPTION)
          .fontColor(AppColors.textPrimary(this.isDarkTheme))
          .fontWeight(FontWeight.Medium)
        Blank()
        Text(chart.type.toUpperCase())
          .fontSize(9)
          .fontColor(AppColors.primary(this.isDarkTheme))
      }.width('100%')

      ForEach(chart.series, (series: ChartSeries, index: number) => {
        Column({ space: AppSpace.XS }) {
          Row() {
            Text(series.name || `数据 ${index + 1}`)
              .fontSize(10)
              .fontColor(AppColors.textTertiary(this.isDarkTheme))
            Blank()
            Text(this.seriesText(series))
              .fontSize(10)
              .fontColor(AppColors.textSecondary(this.isDarkTheme))
              .maxLines(1)
              .textOverflow({ overflow: TextOverflow.Ellipsis })
          }.width('100%')
          ForEach(series.data.slice(0, 6), (value: number | string, valueIndex: number) => {
            Row({ space: AppSpace.SM }) {
              Text(chart.xAxis?.data[valueIndex] || `${valueIndex + 1}`)
                .width(42).fontSize(AppFont.SIZE_CAPTION)
                .fontColor(AppColors.textTertiary(this.isDarkTheme)).maxLines(1)
              Progress({ value: this.numericValue(value), total: this.seriesMax(series), type: ProgressType.Linear })
                .layoutWeight(1).height(4).color(AppColors.primary(this.isDarkTheme))
                .backgroundColor(AppColors.grid(this.isDarkTheme)).style({ strokeWidth: 4 })
            }.width('100%')
          }, (value: number | string, valueIndex: number) => `${chart.id}_${index}_${valueIndex}_${value}`)
        }.width('100%')
      }, (series: ChartSeries, index: number) => `${chart.id}_${series.name || index}`)
    }
    .width('100%')
    .padding(10)
    .backgroundColor(AppColors.group(this.isDarkTheme))
    .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
    .borderRadius(AppSpace.XS)
  }

  @Builder
  assistantBubble() {
    Column({ space: AppSpace.SM }) {
      Row({ space: AppSpace.SM }) {
        Column().width(28).height(2).backgroundColor(AppColors.primary(this.isDarkTheme))
        Column().width(6).height(6).border({ width: 1, color: AppColors.primary(this.isDarkTheme) })
          .rotate({ angle: 45 })
      }.width('100%').alignItems(VerticalAlign.Center)

      if (this.message.content) {
        Text(this.message.content)
          .fontSize(AppFont.SIZE_BODY)
          .fontFamily('HarmonyOS Sans SC')
          .fontColor(this.message.isError ? AppColors.DANGER : AppColors.textPrimary(this.isDarkTheme))
          .lineHeight(23)
          .width('100%')
      }

      if (this.message.imageUrl) {
        if (this.imageFailed) {
          Row({ space: AppSpace.SM }) {
            SymbolGlyph($r('sys.symbol.exclamationmark_circle_fill'))
              .fontSize(AppFont.SIZE_TITLE)
              .fontColor([AppColors.textTertiary(this.isDarkTheme)])
            Text('图片加载失败')
              .fontSize(AppFont.SIZE_CAPTION)
              .fontColor(AppColors.textTertiary(this.isDarkTheme))
          }
          .width('100%')
          .height(AppSpace.CHAT_IMAGE_HEIGHT)
          .justifyContent(FlexAlign.Center)
          .backgroundColor(AppColors.group(this.isDarkTheme))
          .borderRadius(AppSpace.RADIUS_SM)
        } else {
          Image(this.message.imageUrl)
            .width('100%')
            .height(AppSpace.CHAT_IMAGE_HEIGHT)
            .objectFit(ImageFit.Contain)
            .backgroundColor(AppColors.group(this.isDarkTheme))
            .borderRadius(AppSpace.RADIUS_SM)
            .onError((): void => { this.imageFailed = true; })
        }
      }

      if (this.message.chartData && this.message.chartData.charts.length > 0) {
        Column({ space: 8 }) {
          ForEach(this.message.chartData.charts, (chart: ChartConfig) => {
            this.chartCardBuilder(chart)
          }, (chart: ChartConfig, index: number) => `${chart.id}_${index}`)
        }.width('100%')
      }

      if (this.message.actions && this.message.actions.length > 0) {
        this.actionSummary()
      }

      Row() {
        Column().layoutWeight(1).height(1).backgroundColor(AppColors.grid(this.isDarkTheme))
        Column().width(7).height(7).border({ width: 1, color: AppColors.primary(this.isDarkTheme) })
          .rotate({ angle: 45 })
        if (this.message.actions && this.message.actions.length > 0) {
          Text(this.message.feedbackScore ? `已评 ${this.message.feedbackScore}/5` : '评价')
            .fontSize(AppFont.SIZE_CAPTION).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.primary(this.isDarkTheme)).height(30).padding({ left: 10, right: 10 })
            .onClick((): void => {
              if (this.onRate) this.onRate(this.message);
            })
        }
        if (this.message.content && !this.message.isError) {
          SymbolGlyph($r('sys.symbol.speaker_wave_2_fill')).fontSize(17)
            .fontColor([AppColors.primary(this.isDarkTheme)])
            .width(34).height(30)
            .accessibilityText('朗读回复')
            .onClick((): void => {
              if (this.onSpeak) this.onSpeak(this.message.content);
            })
        }
      }.width('100%').alignItems(VerticalAlign.Bottom)
    }
    .width('84%')
    .padding({ left: 14, right: 12, top: 11, bottom: 9 })
    .backgroundColor(AppColors.card(this.isDarkTheme))
    .border({ width: { left: 3, top: 1, right: 1, bottom: 1 },
      color: this.message.isError ? AppColors.DANGER : AppColors.primary(this.isDarkTheme) })
    .borderRadius(AppSpace.XS)
  }

  @Builder
  userBubble() {
    Column({ space: AppSpace.SM }) {
      Text(this.message.content)
        .fontSize(AppFont.SIZE_BODY)
        .fontFamily('HarmonyOS Sans SC')
        .fontColor(AppColors.onPrimary(this.isDarkTheme))
        .lineHeight(23)
        .width('100%')
      Row() {
        Column().layoutWeight(1).height(1).backgroundColor(AppColors.onPrimary(this.isDarkTheme))
        Column().width(7).height(7).backgroundColor(AppColors.onPrimary(this.isDarkTheme)).rotate({ angle: 45 })
      }.width('100%').alignItems(VerticalAlign.Bottom).opacity(0.56)
    }
    .width('76%')
    .padding({ left: 14, right: 12, top: 11, bottom: 9 })
    .backgroundColor(AppColors.primary(this.isDarkTheme))
    .border({ width: { left: 1, top: 1, right: 3, bottom: 1 }, color: AppColors.primary(this.isDarkTheme) })
    .borderRadius(AppSpace.XS)
  }

  build() {
    Row() {
      if (this.message.role === ChatRole.USER) {
        Blank()
        this.userBubble()
      } else {
        this.assistantBubble()
        Blank()
      }
    }
    .width('100%')
    .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING })
    .opacity(this.appeared ? 1 : 0)
    .translate({ y: this.appeared ? 0 : 8 })
    .scale({ x: this.appeared ? 1 : 0.985, y: this.appeared ? 1 : 0.985 })
    .animation({ duration: 320, curve: Curve.EaseOut })
  }
}
