import { ChartConfig, ChartData, ChartDatum, ChartGaugeData, ChartRadarIndicator, ChartSeries } from '../api/types';
import { TacticalTheme } from '../theme/TacticalTheme';

interface PiePoint {
  name: string;
  value: number;
}

function numericValue(value: number | string | ChartDatum): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = parseFloat(value);
    return parsed === parsed ? parsed : 0;
  }
  return typeof value.value === 'number' ? value.value : 0;
}

function validSample(value: number | string | ChartDatum): boolean {
  const number = numericValue(value);
  return number === number && number > -900;
}

function seriesSamples(chart: ChartConfig): number[] {
  const samples: number[] = [];
  for (const series of chart.series || []) {
    for (const value of series.data || []) {
      if (validSample(value) && (typeof value === 'number' || typeof value === 'string' ||
        typeof value.value === 'number')) samples.push(numericValue(value));
    }
  }
  return samples;
}

function radarSamples(chart: ChartConfig): number[] {
  const series = chart.series || [];
  if (series.length === 0 || !series[0].data || series[0].data.length === 0) return [];
  const first = series[0].data[0];
  if (typeof first === 'number' || typeof first === 'string' || !Array.isArray(first.value)) return [];
  return first.value.filter((value: number): boolean => value === value && value >= 0);
}

function meaningfulChart(chart: ChartConfig): boolean {
  if (chart.type === 'gauge') {
    const data = chart.data;
    if (!data) return false;
    return (data.total_requests || 0) > 0 || (data.total_devices || 0) > 0 ||
      (data.total_sensors || 0) > 0 || (data.total_security_events || 0) > 0;
  }
  if (chart.type === 'radar') {
    const values = radarSamples(chart);
    return (chart.radar?.indicator || []).length >= 3 && values.length >= 3 &&
      values.some((value: number): boolean => value > 0);
  }
  const samples = seriesSamples(chart);
  if (chart.type === 'line') {
    return (chart.xAxis?.data || []).length >= 2 && samples.length >= 2 &&
      samples.some((value: number): boolean => Math.abs(value) > 0.0001);
  }
  if (chart.type === 'pie') return samples.filter((value: number): boolean => value > 0).length >= 2;
  if (chart.type === 'bar') return samples.some((value: number): boolean => value > 0);
  return false;
}

export function meaningfulChartConfigs(chartData: ChartData): ChartConfig[] {
  return (chartData.charts || []).filter((chart: ChartConfig): boolean => meaningfulChart(chart));
}

@Component
struct ChartCanvas {
  @Prop chart: ChartConfig;
  @Prop isDark: boolean = true;
  @Prop canvasHeight: number = 144;
  private settings: RenderingContextSettings = new RenderingContextSettings(true);
  private context: CanvasRenderingContext2D = new CanvasRenderingContext2D(this.settings);

  private palette(): string[] {
    return this.isDark ? ['#8FD3EE', '#F3A77F', '#67D8B6', '#D6B7FF', '#F2D477', '#FF8EAC', '#96B9C9'] :
      ['#367A61', '#B84A2B', '#24785D', '#7656A8', '#A97918', '#B34D70', '#6D8F80'];
  }

  private ink(): string { return TacticalTheme.text(this.isDark); }
  private muted(): string { return TacticalTheme.textMuted(this.isDark); }
  private grid(): string { return TacticalTheme.border(this.isDark); }
  private series(): ChartSeries[] { return this.chart.series || []; }
  private categories(): string[] { return this.chart.xAxis?.data || []; }

  private maxValue(): number {
    let max = 1;
    for (const series of this.series()) {
      for (const value of series.data || []) if (validSample(value)) max = Math.max(max, numericValue(value));
    }
    return max;
  }

  private validSampleCount(): number {
    let count = 0;
    for (const series of this.series()) for (const value of series.data || []) if (validSample(value)) count++;
    return count;
  }

  private drawGrid(top: number, bottom: number): void {
    const context = this.context;
    context.strokeStyle = this.grid();
    context.lineWidth = 0.5;
    for (let line = 0; line <= 4; line++) {
      const y = top + (context.height - top - bottom) * line / 4;
      context.beginPath(); context.moveTo(24, y); context.lineTo(context.width - 4, y); context.stroke();
    }
  }

  private traceLine(values: Array<number | string | ChartDatum>, pointCount: number,
    top: number, bottom: number, max: number): void {
    this.context.beginPath();
    let segmentStarted = false;
    for (let index = 0; index < values.length; index++) {
      if (!validSample(values[index])) { segmentStarted = false; continue; }
      const x = 24 + (pointCount > 1 ? index / (pointCount - 1) * (this.context.width - 34) : 0);
      const y = this.context.height - bottom - numericValue(values[index]) / max *
        (this.context.height - top - bottom);
      if (!segmentStarted) { this.context.moveTo(x, y); segmentStarted = true; } else this.context.lineTo(x, y);
    }
  }

  private drawBar(): void {
    const context = this.context;
    const top = 22;
    const bottom = 24;
    const categories = this.categories();
    const series = this.series();
    const groupCount = Math.max(1, categories.length);
    const seriesCount = Math.max(1, series.length);
    const groupWidth = (context.width - 32) / groupCount;
    const barWidth = Math.max(3, groupWidth / (seriesCount + 1));
    const max = this.maxValue();
    const palette = this.palette();
    this.drawGrid(top, bottom);

    for (let sIndex = 0; sIndex < series.length; sIndex++) {
      const values = series[sIndex].data || [];
      context.fillStyle = palette[sIndex % palette.length];
      for (let index = 0; index < values.length; index++) {
        const value = numericValue(values[index]);
        const barHeight = value / max * (context.height - top - bottom);
        const x = 24 + index * groupWidth + (sIndex + 0.45) * barWidth;
        context.fillRect(x, context.height - bottom - barHeight, barWidth * 0.78, barHeight);
      }
    }
    context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'center'; context.fillStyle = this.muted();
    for (let index = 0; index < categories.length; index++) {
      context.fillText(categories[index], 24 + index * groupWidth + groupWidth / 2, context.height - 7);
    }
    context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'left';
    for (let index = 0; index < series.length; index++) {
      const x = 24 + index * 62;
      context.fillStyle = palette[index % palette.length]; context.fillRect(x, 4, 8, 8);
      context.fillStyle = this.muted(); context.fillText(series[index].name || '', x + 11, 12);
    }
  }

  private drawLine(): void {
    const context = this.context;
    const top = 22;
    const bottom = 24;
    const categories = this.categories();
    const series = this.series();
    const max = this.maxValue();
    const palette = this.palette();
    const pointCount = Math.max(1, categories.length);
    this.drawGrid(top, bottom);

    if (this.validSampleCount() === 0) {
      context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'center'; context.fillStyle = this.muted();
      context.fillText('设备离线，暂无有效采样', context.width / 2, context.height / 2);
      return;
    }

    for (let sIndex = 0; sIndex < series.length; sIndex++) {
      const values = series[sIndex].data || [];
      const color = palette[sIndex % palette.length];
      this.traceLine(values, pointCount, top, bottom, max);
      if (pointCount > 1 && this.validSampleCount() > 1) {
        const first = values.findIndex((value: number | string | ChartDatum): boolean => validSample(value));
        let last = -1;
        for (let index = values.length - 1; index >= 0; index--) {
          if (validSample(values[index])) { last = index; break; }
        }
        if (first >= 0 && last > first) {
          const firstX = 24 + first / (pointCount - 1) * (context.width - 34);
          const lastX = 24 + last / (pointCount - 1) * (context.width - 34);
          context.lineTo(lastX, context.height - bottom); context.lineTo(firstX, context.height - bottom);
          context.closePath(); context.fillStyle = this.isDark ? '#8FD3EE18' : '#4D8B7020'; context.fill();
          this.traceLine(values, pointCount, top, bottom, max);
        }
      }
      context.strokeStyle = color; context.lineWidth = 2.2; context.stroke();
      for (let index = 0; index < values.length; index++) {
        if (!validSample(values[index])) continue;
        const x = 24 + (pointCount > 1 ? index / (pointCount - 1) * (context.width - 34) : 0);
        const y = context.height - bottom - numericValue(values[index]) / max * (context.height - top - bottom);
        context.beginPath(); context.arc(x, y, 4.5, 0, Math.PI * 2); context.fillStyle = this.isDark ? '#07131ACC' : '#FFFFFFCC'; context.fill();
        context.beginPath(); context.arc(x, y, 2.8, 0, Math.PI * 2); context.fillStyle = color; context.fill();
      }
    }
    context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'center'; context.fillStyle = this.muted();
    for (let index = 0; index < categories.length; index++) {
      const x = 24 + (pointCount > 1 ? index / (pointCount - 1) * (context.width - 34) : 0);
      context.fillText(categories[index], x, context.height - 7);
    }
  }

  private piePoints(): PiePoint[] {
    const result: PiePoint[] = [];
    const series = this.series();
    if (series.length === 0) return result;
    const values = series[0].data || [];
    for (let index = 0; index < values.length; index++) {
      const item = values[index];
      if (typeof item === 'number' || typeof item === 'string') {
        result.push({ name: this.categories()[index] || `${index + 1}`, value: numericValue(item) });
      } else {
        result.push({ name: item.name || `${index + 1}`, value: typeof item.value === 'number' ? item.value : 0 });
      }
    }
    return result;
  }

  private drawPie(): void {
    const context = this.context;
    const palette = this.palette();
    const points = this.piePoints();
    let total = 0;
    for (const point of points) total += point.value;
    if (total <= 0) total = 1;
    const centerX = context.width * 0.34;
    const centerY = context.height / 2;
    const outer = Math.min(centerX, centerY) - 12;
    const inner = outer * 0.55;
    let start = -Math.PI / 2;
    for (let index = 0; index < points.length; index++) {
      const sweep = points[index].value / total * Math.PI * 2;
      context.beginPath(); context.arc(centerX, centerY, outer, start, start + sweep);
      context.arc(centerX, centerY, inner, start + sweep, start, true); context.closePath();
      context.fillStyle = palette[index % palette.length]; context.fill(); start += sweep;
    }
    context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'left';
    for (let index = 0; index < points.length; index++) {
      const x = context.width * 0.62; const y = 18 + index * 19;
      context.fillStyle = palette[index % palette.length]; context.fillRect(x, y - 7, 8, 8);
      context.fillStyle = this.ink(); context.fillText(`${points[index].name}: ${points[index].value}`, x + 12, y);
    }
  }

  private radarIndicators(): ChartRadarIndicator[] {
    return this.chart.radar?.indicator || [];
  }

  private radarValues(): number[] {
    const series = this.series();
    if (series.length === 0 || !series[0].data || series[0].data.length === 0) return [];
    const datum = series[0].data[0];
    if (typeof datum === 'number' || typeof datum === 'string' || !Array.isArray(datum.value)) return [];
    return datum.value;
  }

  private drawRadarPolygon(radiusScale: number, stroke: string): void {
    const context = this.context;
    const indicators = this.radarIndicators();
    if (indicators.length < 3) {
      context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'center'; context.fillStyle = this.muted();
      context.fillText('暂无足够警戒维度', context.width / 2, context.height / 2);
      context.font = '12px HarmonyOS Sans SC'; context.fillText('已保留真实事件记录', context.width / 2, context.height / 2 + 24);
      return;
    }
    const centerX = context.width / 2;
    const centerY = context.height / 2 + 5;
    const radius = Math.min(context.width, context.height) * 0.34 * radiusScale;
    context.beginPath();
    for (let index = 0; index < indicators.length; index++) {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / indicators.length;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius;
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    }
    context.closePath(); context.strokeStyle = stroke; context.lineWidth = 0.7; context.stroke();
  }

  private drawRadar(): void {
    const context = this.context;
    const indicators = this.radarIndicators();
    const values = this.radarValues();
    if (indicators.length < 3) {
      context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'center'; context.fillStyle = this.muted();
      context.fillText('暂无足够警戒维度', context.width / 2, context.height / 2);
      context.font = '12px HarmonyOS Sans SC'; context.fillText('已保留真实事件记录', context.width / 2, context.height / 2 + 24);
      return;
    }
    const centerX = context.width / 2;
    const centerY = context.height / 2 + 5;
    const radius = Math.min(context.width, context.height) * 0.34;
    for (let ring = 1; ring <= 4; ring++) this.drawRadarPolygon(ring / 4, this.grid());

    context.font = '16px HarmonyOS Sans SC'; context.textAlign = 'center'; context.fillStyle = this.muted();
    for (let index = 0; index < indicators.length; index++) {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / indicators.length;
      const edgeX = centerX + Math.cos(angle) * radius;
      const edgeY = centerY + Math.sin(angle) * radius;
      context.beginPath(); context.moveTo(centerX, centerY); context.lineTo(edgeX, edgeY);
      context.strokeStyle = this.grid(); context.lineWidth = 0.7; context.stroke();
      context.fillText(indicators[index].name || '', centerX + Math.cos(angle) * (radius + 14),
        centerY + Math.sin(angle) * (radius + 12) + 3);
    }

    if (values.length === 0) {
      context.font = '16px HarmonyOS Sans SC'; context.fillStyle = this.muted();
      context.fillText('暂无有效采样', centerX, centerY + 5);
      return;
    }
    context.beginPath();
    for (let index = 0; index < indicators.length; index++) {
      const max = Math.max(1, indicators[index].max || 100);
      const scale = Math.max(0, Math.min(1, (values[index] || 0) / max));
      const angle = -Math.PI / 2 + index * Math.PI * 2 / indicators.length;
      const x = centerX + Math.cos(angle) * radius * scale;
      const y = centerY + Math.sin(angle) * radius * scale;
      if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
    }
    context.closePath();
    context.fillStyle = this.isDark ? '#F3A77F66' : '#B84A2B33'; context.fill();
    context.strokeStyle = TacticalTheme.accent(this.isDark); context.lineWidth = 2; context.stroke();
  }

  private draw(): void {
    this.context.clearRect(0, 0, this.context.width, this.context.height);
    if (this.chart.type === 'bar') this.drawBar();
    else if (this.chart.type === 'line') this.drawLine();
    else if (this.chart.type === 'pie') this.drawPie();
    else if (this.chart.type === 'radar') this.drawRadar();
  }

  build() {
    Canvas(this.context).width('100%').height(this.canvasHeight).onReady(() => { this.draw(); })
  }
}

@Component
export struct ChatChartPanel {
  @Prop chartData: ChartData;
  @Prop isDark: boolean = true;

  private surface(): string { return TacticalTheme.panel(this.isDark); }
  private text(): string { return TacticalTheme.text(this.isDark); }
  private muted(): string { return TacticalTheme.textMuted(this.isDark); }
  private frameColor(): string { return TacticalTheme.border(this.isDark); }
  private charts(): ChartConfig[] { return meaningfulChartConfigs(this.chartData); }

  @Builder
  title(chart: ChartConfig) {
    Row({ space: 8 }) {
      Column().width(3).height(18).backgroundColor(TacticalTheme.accent(this.isDark))
      Text(chart.title || '数据图表').fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
      Blank()
      Text(chart.type === 'line' ? '趋势' : chart.type === 'pie' ? '构成' : chart.type === 'radar' ? '画像' : '概览')
        .fontSize(14).fontColor(this.muted())
    }.width('100%').height(24).alignItems(VerticalAlign.Center)
  }

  @Builder
  metric(value: string, label: string, emphasized: boolean) {
    Column({ space: 3 }) {
      Text(value).fontSize(18).fontWeight(FontWeight.Bold)
        .fontColor(emphasized ? TacticalTheme.accent(this.isDark) : this.text())
      Text(label).fontSize(14).fontColor(this.muted())
    }.width('33%').height(58).padding(6).alignItems(HorizontalAlign.Start)
  }

  @Builder
  gauge(data: ChartGaugeData) {
    Flex({ wrap: FlexWrap.Wrap }) {
      this.metric(`${data.total_requests || 0}`, '请求', true)
      this.metric(`${data.total_chat || 0}`, '对话', false)
      this.metric(`${data.total_device_ops || 0}`, '设备操作', false)
      this.metric(`${data.online_devices || 0}/${data.total_devices || 0}`, '设备在线', true)
      this.metric(`${data.online_sensors || 0}/${data.total_sensors || 0}`, '传感器在线', false)
      this.metric(`${data.total_security_events || 0}`, '安全事件', false)
    }.width('100%')
  }

  @Builder
  card(chart: ChartConfig) {
    Column({ space: 5 }) {
      this.title(chart)
      if (chart.type === 'gauge' && chart.data) {
        this.gauge(chart.data)
      } else if (chart.type === 'bar' || chart.type === 'line' || chart.type === 'pie' || chart.type === 'radar') {
        ChartCanvas({ chart: chart, isDark: this.isDark,
          canvasHeight: chart.type === 'radar' ? 176 : chart.type === 'bar' ? 148 : 142 })
      } else {
        Text('暂不支持此图表类型').fontSize(14).fontColor(this.muted()).padding(12)
      }
    }
    .width('100%').padding({ top: 10, bottom: 10, left: 10, right: 10 }).backgroundColor(this.surface())
    .border({ width: 1, color: this.frameColor() }).borderRadius(3)
  }

  build() {
    Column({ space: 8 }) {
      ForEach(this.charts(), (chart: ChartConfig, index: number) => {
        this.card(chart)
      }, (chart: ChartConfig, index: number) => `${chart.id || 'chart'}_${index}_${this.isDark}`)
    }.width('100%')
  }
}
