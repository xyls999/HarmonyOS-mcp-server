import { promptAction } from '@kit.ArkUI';
import { ChatApi } from '../api/chatApi';
import { AiApi } from '../api/aiApi';
import { AssistantApi, AssistantFeedItem, ExternalFeedItem } from '../api/assistantApi';
import { GuardApi } from '../api/guardApi';
import { ChartData, ChatMessage, ChatRole } from '../api/types';
import { ChatChartPanel } from '../components/ChatChartPanel';
import { HarmonChatBubble } from '../components/HarmonChatBubble';
import { TacticalMotionCore } from '../components/TacticalMotionCore';
import { TacticalCutCornerButton } from '../components/TacticalCutCornerButton';
import { HistoryPage } from './HistoryPage';
import { DeviceCenterPage } from './DeviceCenterPage';
import { SettingsPage } from './SettingsPage';
import { TacticalMotion, TacticalTheme } from '../theme/TacticalTheme';

interface TimelineEntry {
  id: string;
  kind: string;
  timestamp: number;
  message?: ChatMessage;
  event?: AssistantFeedItem;
}

class FeedbackDraft {
  itemId: number;
  score: number = 0;
  choice: string = '';
  note: string = '';
  submitting: boolean = false;

  constructor(itemId: number) {
    this.itemId = itemId;
  }
}

@Component
export struct ControlPanelPage {
  private static readonly MAX_VISIBLE_SYSTEM_FEED: number = 3;
  private static readonly FEED_SPEECH_COOLDOWN_MS: number = 30000;
  @State activePage: number = 0;
  @State isDark: boolean = true;
  @State inputText: string = '';
  @State messages: ChatMessage[] = [];
  @State assistantFeed: AssistantFeedItem[] = [];
  @State externalItems: ExternalFeedItem[] = [];
  @State isResponding: boolean = false;
  @State isListening: boolean = false;
  @State booting: boolean = true;
  @State loadingProgress: number = 0;
  @State loadingStage: string = '正在连接本地服务';
  @State contentVisible: boolean = true;
  @State pageDirection: number = 1;
  @State pageSwitching: boolean = false;
  @State switchProgress: number = 0;
  @State themeSwitching: boolean = false;
  @State themeProgress: number = 0;
  @State themeTargetDark: boolean = true;
  @State motionTick: number = 0;
  @State loadingOuterAngle: number = 0;
  @State loadingInnerAngle: number = 0;
  @State themeGradientAngle: number = 34;
  @State themeSweep: number = 580;
  @State transitionVisible: boolean = false;
  @State transitionProgress: number = 0;
  @State transitionClosing: boolean = false;
  @State transitionKind: number = 0;
  @State targetPage: number = 0;
  @State targetDark: boolean = true;
  @State sourceDark: boolean = true;
  @State themePhrase: string = '';
  @State themeSpeechCategory: string = 'theme';
  @State manualThemeUntil: number = 0;
  @State checkingStatus: boolean = false;
  @State pressedKey: string = '';
  @State feedbackDrafts: FeedbackDraft[] = [];
  @State pendingAcknowledgementId: number = 0;
  @State acknowledgingAlert: boolean = false;
  @State showThinking: boolean = false;
  @State thinkingAngle: number = 0;
  @State thinkingProgress: number = 4;
  @State thinkingTick: number = 0;
  @State thinkingFinishing: boolean = false;
  private chatScroller: Scroller = new Scroller();
  private timers: number[] = [];
  private feedTimer: number = -1;
  private motionTimer: number = -1;
  private msgId: number = 1;
  private thinkingStartedAt: number = 0;
  private thinkingTimer: number = -1;
  private thinkingProgressTimer: number = -1;
  private thinkingRunId: number = 0;
  private hiddenFeedIds: number[] = [];
  private spokenFeedIds: number[] = [];
  private lastFeedSpeechAt: number = 0;
  private lastExternalDigestKey: string = '';
  private feedInitialized: boolean = false;
  private feedOpenedAt: number = 0;
  private transitionGeneration: number = 0;
  private autoThemeTimer: number = -1;
  private externalTimer: number = -1;

  aboutToAppear(): void {
    this.messages = [{ id: 'msg_0', role: ChatRole.ASSISTANT, content: '系统已就绪。需要我检查什么？', timestamp: Date.now() }];
    this.feedOpenedAt = Date.now() / 1000;
    this.startBootSequence();
    this.loadAssistantFeed();
    this.loadExternalFeed();
    this.feedTimer = setInterval(() => this.loadAssistantFeed(), 30000);
    this.externalTimer = setInterval(() => this.loadExternalFeed(), 600000);
    this.autoThemeTimer = setInterval(() => this.syncClockTheme(), 60000);
    this.motionTimer = setInterval(() => {
      this.motionTick = (this.motionTick + 4) % 360;
      if (this.booting) {
        this.loadingOuterAngle = (this.loadingOuterAngle + 3) % 360;
        this.loadingInnerAngle = (this.loadingInnerAngle - 2) % 360;
      }
    }, 40);
  }

  aboutToDisappear(): void {
    this.resetTransition();
    if (this.feedTimer !== -1) clearInterval(this.feedTimer);
    this.feedTimer = -1;
    if (this.externalTimer !== -1) clearInterval(this.externalTimer);
    this.externalTimer = -1;
    if (this.autoThemeTimer !== -1) clearInterval(this.autoThemeTimer);
    this.autoThemeTimer = -1;
    if (this.motionTimer !== -1) clearInterval(this.motionTimer);
    this.motionTimer = -1;
    if (this.thinkingTimer >= 0) clearTimeout(this.thinkingTimer);
    if (this.thinkingProgressTimer >= 0) clearTimeout(this.thinkingProgressTimer);
    this.thinkingRunId++;
    this.showThinking = false;
  }

  private page(): string { return TacticalTheme.page(this.isDark); }
  private panel(): string { return TacticalTheme.panel(this.isDark); }
  private raised(): string { return TacticalTheme.panelRaised(this.isDark); }
  private input(): string { return TacticalTheme.input(this.isDark); }
  private text(): string { return TacticalTheme.text(this.isDark); }
  private secondary(): string { return TacticalTheme.textSecondary(this.isDark); }
  private muted(): string { return TacticalTheme.textMuted(this.isDark); }
  private accent(): string { return TacticalTheme.accent(this.isDark); }
  private accentSoft(): string { return TacticalTheme.accentSoft(this.isDark); }
  private borderTone(): string { return TacticalTheme.border(this.isDark); }

  private later(delay: number, action: () => void): void { this.timers.push(setTimeout(action, delay)); }

  private clearTimers(): void {
    for (const timer of this.timers) clearTimeout(timer);
    this.timers = [];
  }

  private transitionAt(ratio: number): number {
    const duration = this.transitionKind === 1 ? TacticalMotion.THEME_ROUTE : TacticalMotion.ROUTE;
    return Math.round(duration * ratio);
  }

  private laterForTransition(ratio: number, generation: number, action: () => void): void {
    this.later(this.transitionAt(ratio), () => {
      if (generation === this.transitionGeneration) action();
    });
  }

  private resetTransition(): void {
    this.transitionGeneration++;
    this.clearTimers();
    this.transitionVisible = false;
    this.transitionClosing = false;
    this.pageSwitching = false;
    this.themeSwitching = false;
    this.transitionProgress = 0;
    this.themePhrase = '';
  }

  private startBootSequence(): void {
    this.loadingProgress = 0;
    this.loadingStage = '正在连接本地服务';
    this.later(800, () => { this.loadingProgress = 12; this.loadingStage = '正在读取设备目录'; });
    this.later(1900, () => { this.loadingProgress = 28; this.loadingStage = '正在读取设备目录'; });
    this.later(3300, () => { this.loadingProgress = 48; this.loadingStage = '正在载入安全规则'; });
    this.later(5000, () => { this.loadingProgress = 68; this.loadingStage = '正在整理家庭数据'; });
    this.later(6500, () => { this.loadingProgress = 86; this.loadingStage = '正在准备助手'; });
    this.later(7500, () => { this.loadingProgress = 96; this.loadingStage = '即将完成'; });
    this.later(8000, () => {
      this.loadingProgress = 100;
      this.loadingStage = '系统已就绪';
      this.booting = false;
      this.syncClockTheme();
    });
  }

  private async loadAssistantFeed(): Promise<void> {
    const incoming = await AssistantApi.getFeed(0, 20);
    if (incoming.length === 0) return;
    const merged: AssistantFeedItem[] = [];
    const newItems: AssistantFeedItem[] = [];
    for (const item of incoming.concat(this.assistantFeed)) {
      if (this.hiddenFeedIds.indexOf(item.id) >= 0) continue;
      if (!this.isConversationFeedItem(item)) continue;
      // Keep the recent pre-conversation window so events that happened just before
      // the latest chat message remain visible in their true chronological position.
      if (item.createdTs !== undefined && item.createdTs < this.feedOpenedAt - 600) continue;
      if (!merged.some((old: AssistantFeedItem) => old.id === item.id)) merged.push(item);
      if (this.spokenFeedIds.indexOf(item.id) < 0) {
        this.spokenFeedIds.push(item.id);
        newItems.push(item);
      }
    }
    merged.sort((a: AssistantFeedItem, b: AssistantFeedItem) => Math.abs(b.id) - Math.abs(a.id));
    const compact: AssistantFeedItem[] = [];
    let stableSummarySeen = false;
    for (const item of merged) {
      const stableSummary = item.kind === 'summary' && item.severity === 'info' && item.summary.indexOf('无明显变化') >= 0;
      if (stableSummary) {
        if (stableSummarySeen) continue;
        stableSummarySeen = true;
      }
      compact.push(item);
    }
    const visible = compact.slice(0, ControlPanelPage.MAX_VISIBLE_SYSTEM_FEED);
    this.assistantFeed = visible;
    this.selectPendingAcknowledgement(visible);
    if (this.feedInitialized) {
      const candidate = newItems.find((item: AssistantFeedItem): boolean =>
        visible.some((current: AssistantFeedItem): boolean => current.id === item.id));
      if (candidate) this.speakFeedItemOnce(candidate, true);
    }
    this.feedInitialized = true;
  }

  private async manualStatusCheck(): Promise<void> {
    if (this.checkingStatus || this.isResponding) return;
    this.checkingStatus = true;
    const reports = await AssistantApi.runStatusCheck();
    if (reports.length > 0) {
      const visibleReports = reports.filter((item: AssistantFeedItem): boolean => this.isConversationFeedItem(item));
      const merged = visibleReports.concat(this.assistantFeed)
        .filter((item: AssistantFeedItem, index: number, all: AssistantFeedItem[]): boolean =>
          all.findIndex((current: AssistantFeedItem): boolean => current.id === item.id) === index)
        .sort((a: AssistantFeedItem, b: AssistantFeedItem): number => Math.abs(b.id) - Math.abs(a.id));
      this.assistantFeed = merged.slice(0, ControlPanelPage.MAX_VISIBLE_SYSTEM_FEED);
      this.selectPendingAcknowledgement(this.assistantFeed);
      for (const item of visibleReports) this.speakFeedItemOnce(item, true);
    } else {
      await this.loadAssistantFeed();
    }
    this.checkingStatus = false;
    promptAction.showToast({ message: reports.length > 0 ? '状态检测完成，结果已写入助手' : '状态检测完成，当前没有新增调整', duration: 2000 });
  }

  private selectPendingAcknowledgement(items: AssistantFeedItem[]): void {
    if (this.pendingAcknowledgementId !== 0) {
      const current = items.find((item: AssistantFeedItem): boolean =>
        item.id === this.pendingAcknowledgementId && item.acknowledged !== true);
      if (current) return;
    }
    const next = items.find((item: AssistantFeedItem): boolean => item.requiresAcknowledgement === true &&
      item.acknowledged !== true && (item.kind === 'automation_adjustment' ||
        item.severity === 'warning' || item.severity === 'danger'));
    this.pendingAcknowledgementId = next ? next.id : 0;
  }

  private async confirmAlertAcknowledgement(item: AssistantFeedItem): Promise<void> {
    if (this.acknowledgingAlert) return;
    this.acknowledgingAlert = true;
    const ok = await AssistantApi.acknowledgeAlert(item.id);
    this.acknowledgingAlert = false;
    if (!ok) {
      promptAction.showToast({ message: '确认失败，请检查后端连接', duration: 1800 });
      return;
    }
    for (const current of this.assistantFeed) {
      if (current.id === item.id) current.acknowledged = true;
    }
    this.assistantFeed = this.assistantFeed.slice();
    this.pendingAcknowledgementId = 0;
    this.selectPendingAcknowledgement(this.assistantFeed);
  }

  private speakFeedItemOnce(item: AssistantFeedItem, alreadySeen: boolean = false): void {
    if (item.kind === 'external_digest') {
      this.speakExternalCollected();
      return;
    }
    const isSystemAnalysis = item.kind === 'summary' || item.kind === 'automation_adjustment' ||
      item.severity === 'danger' || item.severity === 'warning';
    if (!isSystemAnalysis) return;
    if (!alreadySeen && this.spokenFeedIds.indexOf(item.id) >= 0) return;
    if (!alreadySeen) this.spokenFeedIds.push(item.id);
    const now = Date.now();
    if (now - this.lastFeedSpeechAt < ControlPanelPage.FEED_SPEECH_COOLDOWN_MS) return;
    this.lastFeedSpeechAt = now;
    // 只播报系统分析、警戒和调整建议；手动设备操作已在上方过滤。
    ChatApi.speak(this.assistantEventText(item));
  }

  private isConversationFeedItem(item: AssistantFeedItem): boolean {
    // 手动设备操作只进入后端上下文和日志，不占用助手对话区。
    // 对话区只呈现系统分析、风险判断和可执行调整建议。
    if (item.kind === 'device_operation') return false;
    if (item.kind === 'external_digest') return false;
    if (item.kind === 'summary') return true;
    return item.kind === 'repeated_toggle' || item.kind === 'automation_adjustment' ||
      item.severity === 'danger' || item.severity === 'warning';
  }

  private eventTimestamp(item: AssistantFeedItem): number {
    if (item.createdTs !== undefined) return item.createdTs * 1000;
    if (item.createdAt) {
      const parsed = Date.parse(item.createdAt.replace(' ', 'T') + '+08:00');
      if (!Number.isNaN(parsed)) return parsed;
    }
    return 0;
  }

  private timelineEntries(): TimelineEntry[] {
    const entries: TimelineEntry[] = [];
    for (const message of this.messages) {
      entries.push({ id: `message_${message.id}`, kind: 'message', timestamp: message.timestamp, message: message });
    }
    for (const item of this.assistantFeed) {
      entries.push({ id: `event_${item.id}`, kind: 'event', timestamp: this.eventTimestamp(item), event: item });
    }
    entries.sort((a: TimelineEntry, b: TimelineEntry): number => {
      if (a.timestamp === b.timestamp) return a.kind === 'event' ? -1 : 1;
      return a.timestamp - b.timestamp;
    });
    return entries;
  }

  private clearConversation(): void {
    AiApi.clearContext();
    for (const item of this.assistantFeed) {
      if (this.hiddenFeedIds.indexOf(item.id) < 0) this.hiddenFeedIds.push(item.id);
    }
    this.assistantFeed = [];
    this.pendingAcknowledgementId = 0;
    this.messages = [{ id: 'msg_0', role: ChatRole.ASSISTANT, content: '系统已就绪。需要我检查什么？', timestamp: Date.now() }];
    this.feedbackDrafts = [];
    this.showThinking = false;
    promptAction.showToast({ message: '助手对话已清空', duration: 1600 });
  }

  private friendlyTrigger(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') {
      const value = item.evidence['triggerReason'] as string;
      if (value && value.length > 0) return value;
    }
    if (item.kind === 'external_digest') return '十分钟外部信息摘要周期';
    if (item.kind === 'device_operation') return '用户在设备页面执行控制';
    if (item.kind === 'summary') return '系统到达十分钟汇总周期';
    if (item.kind === 'repeated_toggle') return '设备在短时间内反复开关';
    if (item.title === 'kitchen_smoke_or_heat_alarm') return '厨房烟雾或热敏传感器报警';
    if (item.title === 'sensor_offline') return '传感器失去连接';
    if (item.title === 'door_event_monitor') return '门禁状态发生变化';
    if (item.title === 'home_absence_device_on') return '毫米波连续确认无人，但空调或换气设备仍开启';
    return '系统主动警戒规则命中';
  }

  private friendlyMode(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment') return '智能调整';
    if (item.kind === 'automation_alarm') return '确定性安全联动';
    if (item.kind === 'external_digest') return '外部信息（不播报、不进入状态上下文）';
    if (item.kind === 'device_operation') return '确定性自动管理 / 设备服务';
    if (item.kind === 'repeated_toggle') return 'AI 智能警戒建议';
    if (item.severity === 'danger' || item.severity === 'warning') return '确定性安全联动';
    return '系统记录';
  }

  private friendlyDevice(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') {
      const value = item.evidence['deviceSummary'] as string;
      if (value && value.length > 0) return value;
    }
    if (item.kind === 'external_digest') return '外部信息源';
    if (item.kind === 'device_operation') return item.title.replace('设备操作：', '');
    if (item.title === 'kitchen_smoke_or_heat_alarm') return '厨房烟雾传感器、热敏传感器、蜂鸣器、换气扇';
    if (item.title === 'sensor_offline') return '客厅温湿度传感器';
    if (item.kind === 'repeated_toggle') return '发生反复切换的设备';
    if (item.kind === 'summary') return '家庭设备与传感器';
    if (item.title === 'door_event_monitor') return '客厅门禁';
    if (item.title === 'home_absence_device_on') return '毫米波存在传感器、空调与换气设备';
    return '家庭自动化系统';
  }

  private friendlyDescription(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') {
      const concise = item.evidence['analysisSummary'] as string;
      if (concise && concise.length > 0) return concise;
      const value = item.evidence['description'] as string;
      return value && value.length > 0 ? value : item.summary;
    }
    if (item.kind === 'external_digest') return item.summary || '已更新科技、新闻和其他外部信息。';
    if (item.kind === 'device_operation') return item.summary;
    if (item.kind === 'summary' || item.kind === 'repeated_toggle') return item.summary;
    if (item.title === 'kitchen_smoke_or_heat_alarm') return '厨房传感器报警位持续有效，系统已按实时采样执行安全处置。';
    if (item.title === 'sensor_offline') return '环境传感器暂时离线，系统已记录并继续观察恢复状态。';
    if (item.title === 'home_absence_device_on') return '在线毫米波传感器连续三次确认无人，同时检测到允许自动关闭的设备仍在运行。';
    if (item.kind === 'repeated_toggle') return '同一设备在短时间内多次切换，可能存在误触、规则冲突或设备异常。';
    if (item.kind === 'summary') return '系统汇总最近十分钟的重要状态、操作和待处理提醒。';
    return '系统检测到需要主人确认的家庭状态变化。';
  }

  private friendlyAction(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') {
      const value = item.evidence['actionSummary'] as string;
      if (value && value.length > 0) return value;
    }
    if (item.kind === 'external_digest') return '仅在助手中展示，不执行设备操作。';
    if (item.kind === 'device_operation') return item.summary;
    if (item.kind === 'summary') {
      const suggestions = item.evidence['suggestions'] as string[];
      return suggestions && suggestions.length > 0 ? suggestions.join('；') : '继续观察当前状态';
    }
    if (item.kind === 'repeated_toggle') return '暂不自动改变设备状态，建议检查规则或设备反馈。';
    if (item.title === 'kitchen_smoke_or_heat_alarm') return '打开蜂鸣器；开启换气扇；进行语音播报；记录门禁与报警日志。';
    if (item.title === 'sensor_offline') return '未擅自改变设备状态；记录离线事件并等待恢复。';
    if (item.title === 'home_absence_device_on') return '关闭仍在运行的空调或换气设备；记录执行结果和状态证据。';
    if (item.kind === 'repeated_toggle') return '未自动改变设备状态；生成提醒，等待主人评价。';
    if (item.kind === 'summary') return '未执行设备动作；生成状态汇总和趋势数据。';
    return '记录事件并等待主人确认。';
  }

  private friendlyResult(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') {
      const value = item.evidence['resultSummary'] as string;
      if (value && value.length > 0) return value;
    }
    if (item.kind === 'external_digest') return '信息已更新，不触发语音播报。';
    if (item.severity === 'danger') return '安全处置已完成，等待主人确认本次行为。';
    if (item.severity === 'warning') return '提醒已生成，暂不扩大自动操作范围。';
    return '记录完成，可在下方提交评分。';
  }

  private friendlyEvidence(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') {
      const value = item.evidence['evidenceSummary'] as string;
      if (value && value.length > 0) return value;
    }
    if (item.title === 'kitchen_smoke_or_heat_alarm') return '厨房烟雾或热敏报警位为 1，连续采样确认后触发。';
    if (item.title === 'home_absence_device_on') return '在线毫米波连续三次返回无人，且目标设备仍为开启状态。';
    if (item.title === 'sensor_offline') return '设备心跳或采样时间超过允许范围。';
    return '已核验当前传感器、设备状态和规则条件。';
  }

  private friendlyTriggerTime(item: AssistantFeedItem): string {
    if (item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') {
      const value = item.evidence['triggerTime'] as string;
      if (value && value.length > 0) return value;
    }
    return item.createdAt || '刚刚';
  }

  private friendlyAdvice(item: AssistantFeedItem): string {
    if (item.kind === 'external_digest') return '外部信息与十分钟状态判断隔离。';
    if (item.title === 'sensor_offline') return '检查传感器供电、网络和设备心跳。';
    if (item.feedbackEnabled === true) return '请评价本次自动调整，系统会将反馈加入长期策略。';
    if (item.kind === 'repeated_toggle') return '系统未改变设备状态，本次仅记录观察，继续等待下一次变化。';
    if (item.title === 'kitchen_smoke_or_heat_alarm') return '请确认厨房现场；若报警持续，不要关闭安全联动。';
    if (item.title === 'home_absence_device_on') return '如果本次判断不符合实际，请评分并说明毫米波误判情况。';
    return '本次没有设备调整，继续观察即可。';
  }

  private assistantEventText(item: AssistantFeedItem): string {
    if (item.kind === 'external_digest') {
      return `外部信息摘要\n时间：${item.createdAt || '刚刚'}\n内容：${this.friendlyDescription(item)}\n处理：${this.friendlyAction(item)}`;
    }
    if (item.kind === 'summary') {
      return `状态汇报\n时间：${item.createdAt || '刚刚'}\n当前判断：${this.friendlyDescription(item)}\n调整建议：${this.friendlyAction(item)}`;
    }
    return `触发模式：${this.friendlyMode(item)}\n触发时间：${this.friendlyTriggerTime(item)}\n触发原因：${this.friendlyTrigger(item)}\n实时证据：${this.friendlyEvidence(item)}\n设备：${this.friendlyDevice(item)}\n描述：${this.friendlyDescription(item)}\n具体操作：${this.friendlyAction(item)}\n操作结果：${this.friendlyResult(item)}\n建议：${this.friendlyAdvice(item)}`;
  }

  private feedChartData(item: AssistantFeedItem): ChartData | undefined {
    const labels = item.chart['labels'] as string[];
    const values = item.chart['values'] as number[];
    if (!labels || !values || labels.length !== values.length) return undefined;
    const safeLabels: string[] = [];
    const safeValues: number[] = [];
    for (let index = 0; index < values.length; index++) {
      const value = values[index];
      if (value === value && value > -900 && labels[index] && labels[index].length > 0) {
        safeLabels.push(labels[index]);
        safeValues.push(Math.max(0, value));
      }
    }
    const positiveCount = safeValues.filter((value: number): boolean => value > 0).length;
    if (positiveCount < 2) return undefined;
    const isTimeline = item.kind === 'repeated_toggle';
    return { charts: [{ id: `feed_${item.id}`, title: isTimeline ? '设备变化趋势' : '实时状态构成',
      type: isTimeline ? 'line' : 'pie', xAxis: { type: 'category', data: safeLabels },
      series: [{ name: isTimeline ? '变化' : '状态', type: isTimeline ? 'line' : 'pie',
        smooth: isTimeline, data: safeValues }] }] };
  }

  private feedChartHasData(item: AssistantFeedItem): boolean {
    return this.feedChartData(item) !== undefined;
  }

  private feedbackDraft(itemId: number): FeedbackDraft {
    for (const draft of this.feedbackDrafts) {
      if (draft.itemId === itemId) return draft;
    }
    const created = new FeedbackDraft(itemId);
    this.feedbackDrafts.push(created);
    return created;
  }

  private updateFeedback(itemId: number, score: number, choice: string, note: string, submitting: boolean): void {
    const current = this.feedbackDraft(itemId);
    current.score = score;
    current.choice = choice;
    current.note = note;
    current.submitting = submitting;
    this.feedbackDrafts = this.feedbackDrafts.slice();
  }

  private async submitAssistantFeedback(item: AssistantFeedItem): Promise<void> {
    const draft = this.feedbackDraft(item.id);
    if (draft.score < 1 || draft.submitting) return;
    this.updateFeedback(item.id, draft.score, draft.choice, draft.note, true);
    const ok = await AssistantApi.submitFeedback(item.id, draft.score, draft.choice, draft.note);
    this.updateFeedback(item.id, draft.score, draft.choice, draft.note, false);
    if (!ok) return;
    // Rated adjustments become long-term learning data; keep the live stream compact.
    this.assistantFeed = this.assistantFeed.filter((current: AssistantFeedItem): boolean => current.id !== item.id);
    this.messages = this.messages.filter((message: ChatMessage): boolean => message.id !== `feed_${item.id}`);
    promptAction.showToast({ message: '已记录评价，系统会用于后续策略调整' });
    this.feedbackDrafts = this.feedbackDrafts.filter((draft: FeedbackDraft): boolean => draft.itemId !== item.id);
  }

  private switchPage(index: number): void {
    if (index === this.activePage && !this.pageSwitching && !this.themeSwitching) return;
    if (this.pageSwitching || this.themeSwitching) this.resetTransition();
    this.transitionKind = 0;
    this.targetPage = index;
    this.targetDark = this.isDark;
    this.sourceDark = this.isDark;
    this.prepareTransition();
    const generation = this.transitionGeneration;
    this.laterForTransition(0.48, generation, () => { this.activePage = this.targetPage; });
    this.laterForTransition(0.88, generation, () => { this.transitionProgress = 100; });
    this.laterForTransition(0.94, generation, () => { this.transitionClosing = true; });
    this.laterForTransition(1, generation, () => this.resetTransition());
  }

  private async loadExternalFeed(): Promise<void> {
    const items = await AssistantApi.getExternalFeed();
    const next = items.slice(0, 4);
    this.externalItems = next;
    const key = next.map((item: ExternalFeedItem): string => `${item.category}:${item.title}`).join('|');
    if (next.length > 0 && key !== this.lastExternalDigestKey) {
      this.lastExternalDigestKey = key;
      this.speakExternalCollected();
    }
  }

  private speakExternalCollected(): void {
    const now = Date.now();
    if (now - this.lastFeedSpeechAt < ControlPanelPage.FEED_SPEECH_COOLDOWN_MS) return;
    this.lastFeedSpeechAt = now;
    ChatApi.speak('新闻信息已收集', 'external_notice');
  }

  private externalCategory(item: ExternalFeedItem): string {
    if (item.category === 'weather') return '天气';
    if (item.category === 'traffic') return '交通';
    if (item.category === 'news') return '新闻';
    if (item.category === 'technology') return '科技';
    if (item.category === 'market') return '行情';
    return '外部信息';
  }

  @Builder
  externalDigest() {
    if (this.externalItems.length > 0) {
      Column({ space: 8 }) {
        Row({ space: 8 }) {
          Column().width(4).height(24).backgroundColor(this.accent())
          Text('外部信息摘要').fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
          Blank()
          Text('来源已标注').fontSize(14).fontColor(this.muted())
        }.width('100%')
        ForEach(this.externalItems, (item: ExternalFeedItem) => {
          Row({ space: 8 }) {
            if (item.image_url && item.image_url.length > 0) {
              Image(item.image_url).width(86).height(54).objectFit(ImageFit.Cover)
                .borderRadius(2).accessibilityText(`${this.externalCategory(item)}图片`)
            }
            Column({ space: 3 }) {
              Text(`${this.externalCategory(item)} · ${item.title}`).fontSize(14).fontWeight(FontWeight.Medium)
                .fontColor(this.text()).maxLines(2)
              Text(`${item.source_name || '中文网站'}${item.stale ? ' · 旧数据' : ''}`).fontSize(14).fontColor(this.muted()).maxLines(1)
            }.layoutWeight(1).alignItems(HorizontalAlign.Start)
          }.width('100%').padding({ top: 4, bottom: 4 })
        }, (item: ExternalFeedItem) => `${item.category}:${item.title}`)
      }.width('100%').padding(12).backgroundColor(this.raised())
        .border({ width: 1, color: this.borderTone() }).borderRadius(3)
    }
  }

  private syncClockTheme(): void {
    if (this.booting) return;
    if (Date.now() < this.manualThemeUntil) return;
    const hour = new Date().getHours();
    const shouldBeDark = hour < 7 || hour >= 18;
    if (shouldBeDark !== this.isDark && !this.pageSwitching && !this.themeSwitching) {
      this.applyThemeForTarget(shouldBeDark, false);
    }
  }

  private applyThemeForTarget(target: boolean, announce: boolean): void {
    if (this.pageSwitching || this.themeSwitching) this.resetTransition();
    this.transitionKind = 1;
    this.sourceDark = this.isDark;
    this.targetDark = target;
    this.targetPage = this.activePage;
    this.themePhrase = this.targetDark ? '夜幕落下，系统转入低光守护' : '天光接管，居所进入明昼模式';
    this.prepareTransition();
    const generation = this.transitionGeneration;
    this.laterForTransition(0.48, generation, () => {
      this.isDark = this.targetDark;
      if (announce) ChatApi.speak(this.themePhrase, 'theme');
    });
    this.laterForTransition(0.88, generation, () => { this.transitionProgress = 100; });
    this.laterForTransition(0.94, generation, () => { this.transitionClosing = true; });
    this.laterForTransition(1, generation, () => this.resetTransition());
  }

  private toggleTheme(): void {
    this.manualThemeUntil = Date.now() + 4 * 60 * 60 * 1000;
    this.applyThemeForTarget(!this.isDark, true);
  }

  private prepareTransition(): void {
    this.transitionGeneration++;
    const generation = this.transitionGeneration;
    this.pageSwitching = this.transitionKind === 0;
    this.themeSwitching = this.transitionKind === 1;
    this.transitionVisible = true;
    this.transitionClosing = false;
    this.transitionProgress = 0;
    this.loadingOuterAngle = 0;
    this.loadingInnerAngle = 0;
    this.themeGradientAngle = 34;
    this.themeSweep = 580;
    const duration: number = this.transitionAt(0.8);
    this.laterForTransition(0.08, generation, () => {
      this.getUIContext().animateTo({ duration: duration, curve: Curve.EaseInOut }, () => {
        this.transitionProgress = 100;
        this.loadingOuterAngle = 240;
        this.loadingInnerAngle = -240;
        if (this.transitionKind === 1) {
          this.themeGradientAngle = 62;
          this.themeSweep = -580;
        }
      });
    });
  }
  private touch(key: string, event: TouchEvent): void {
    if (event.type === TouchType.Down) this.pressedKey = key;
    if (event.type === TouchType.Up || event.type === TouchType.Cancel) this.pressedKey = '';
  }

  async send(): Promise<void> {
    const text = this.inputText.trim();
    if (text.length > 0) await this.submitMessage(text);
  }

  private startThinking(): void {
    if (this.thinkingProgressTimer >= 0) clearTimeout(this.thinkingProgressTimer);
    this.showThinking = true;
    this.thinkingAngle = 0;
    this.thinkingProgress = 4;
    this.thinkingTick = 0;
    this.thinkingFinishing = false;
    this.thinkingStartedAt = Date.now();
    const runId: number = ++this.thinkingRunId;
    this.advanceThinking(runId);
    this.later(24, () => {
      this.getUIContext().animateTo({ duration: 2200, curve: Curve.Linear, iterations: -1 }, () => {
        this.thinkingAngle = 360;
      });
    });
  }

  private advanceThinking(runId: number): void {
    if (runId !== this.thinkingRunId || !this.showThinking || this.thinkingFinishing) return;
    this.thinkingTick += 1;
    this.thinkingProgress = Math.min(92, 4 + this.thinkingTick * 4);
    this.thinkingProgressTimer = setTimeout(() => this.advanceThinking(runId), 140);
  }

  private finishThinking(after: () => void): void {
    const remaining: number = Math.max(0, 1800 - (Date.now() - this.thinkingStartedAt));
    const complete = (): void => {
      if (!this.showThinking) return;
      if (this.thinkingProgressTimer >= 0) clearTimeout(this.thinkingProgressTimer);
      this.thinkingRunId++;
      this.thinkingFinishing = true;
      this.thinkingProgress = 100;
      this.thinkingTimer = setTimeout(() => {
        this.showThinking = false;
        this.thinkingFinishing = false;
        this.thinkingTimer = -1;
        after();
      }, 320);
    };
    if (remaining === 0) complete();
    else this.thinkingTimer = setTimeout(complete, remaining);
  }

  private thinkingLabel(): string {
    if (this.thinkingFinishing) return '已完成';
    if (this.thinkingProgress < 35) return '正在读取';
    if (this.thinkingProgress < 70) return '正在整理';
    return '即将完成';
  }

  private thinkingStep(): number { return Math.min(3, Math.floor(this.thinkingProgress / 25)); }

  private async submitMessage(text: string, planNonce?: string): Promise<void> {
    if (this.isResponding) return;
    this.isResponding = true;
    this.messages = this.messages.concat([{ id: `msg_${this.msgId++}`, role: ChatRole.USER, content: text, timestamp: Date.now() }]);
    this.inputText = '';
    setTimeout((): void => this.chatScroller.scrollEdge(Edge.Bottom), 50);
    this.startThinking();
    let reply = '暂未收到有效回复';
    let chartData: ChartData | undefined = undefined;
    let planDigest: string | undefined = undefined;
    try {
      const response = await ChatApi.sendComplete(this.messages, planNonce);
      reply = response.content;
      chartData = response.chartData;
      planNonce = response.planNonce;
      planDigest = response.planDigest;
    } catch (e) {
      reply = (e as Error).message || '智能服务暂时无法连接';
    }
    this.finishThinking(() => {
      this.messages = this.messages.concat([{ id: `msg_${this.msgId++}`, role: ChatRole.ASSISTANT, content: reply,
        timestamp: Date.now(), chartData: chartData, planNonce: planNonce, planDigest: planDigest }]);
      this.isResponding = false;
      setTimeout((): void => this.chatScroller.scrollEdge(Edge.Bottom), 50);
    });
  }

  async startVoice(): Promise<void> {
    if (this.isListening || this.isResponding) return;
    this.isListening = true;
    try { this.inputText = (await ChatApi.voiceToText('')).trim(); if (this.inputText.length > 0) await this.send(); }
    finally { this.isListening = false; }
  }

  @Builder
  loadingScreen() {
    Column({ space: 18 }) {
      TacticalMotionCore({
        progress: this.loadingProgress,
        outerAngle: this.loadingOuterAngle,
        innerAngle: this.loadingInnerAngle,
        title: '明日家居',
        icon: $r('sys.symbol.house_fill'),
        isDark: this.isDark
      })
      Text(this.loadingStage).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.secondary())
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
      .backgroundColor(this.page())
  }

  @Builder
  brandMark() {
    Stack({ alignContent: Alignment.Center }) {
      Column().width(184).height(50).backgroundColor('#FFFFFF')
        .border({ width: { bottom: 2 }, color: this.accent() })
      Text('明').fontSize(42).fontWeight(FontWeight.Bold).fontColor('#D6EDF7').position({ x: 12, y: -6 })
      Column().width(4).height(36).backgroundColor(this.accent()).position({ x: 0, y: 7 })
      Row({ space: 0 }) {
        Text('明日').fontSize(27).fontWeight(FontWeight.Bolder).fontColor('#0B1B25')
        Text('家居').fontSize(27).fontWeight(FontWeight.Bolder).fontColor(this.accent())
      }
    }.width(184).height(50).accessibilityText('明日家居')
  }

  @Builder
  header() {
    Row({ space: 12 }) {
      this.brandMark()
      Text(this.activePage === 0 ? '助手' : this.activePage === 1 ? '设备' : this.activePage === 2 ? '数据管理' : '设置')
        .fontSize(14).fontColor(this.accent())
      Blank()
      Stack() {
        Column().width(30).height(30).backgroundColor(this.panel()).border({ width: 1, color: this.accent() })
        SymbolGlyph(this.isDark ? $r('sys.symbol.sun_max') : $r('sys.symbol.moon_fill')).fontSize(16).fontColor([this.accent()])
      }.width(42).height(42).onTouch((event: TouchEvent) => this.touch('theme', event)).onClick(() => this.toggleTheme())
    }.width('100%').height(58).padding({ left: 18, right: 14 }).backgroundColor(this.raised())
      .border({ width: { bottom: 1 }, color: this.borderTone() })
  }

  @Builder
  transitionOverlay() {
    if (this.transitionVisible) {
      Stack() {
        if (this.transitionKind === 1) {
          Column().width('100%').height('100%').linearGradient({
            angle: this.themeGradientAngle,
            colors: [[TacticalTheme.page(this.targetDark), 0],
              [TacticalTheme.structural(this.targetDark), 0.24],
              [TacticalTheme.accentSoft(this.targetDark), 0.46],
              [TacticalTheme.structural(this.targetDark), 0.72],
              [TacticalTheme.page(this.targetDark), 1]]
          }).animation({ duration: 1720, curve: Curve.EaseInOut })
          Column().width('100%').height('100%').backgroundColor(TacticalTheme.page(this.sourceDark))
            .opacity(this.transitionProgress < 58 ? 1 : 0).animation({ duration: 520, curve: Curve.EaseInOut })
          Column().width('150%').height('135%').linearGradient({
            angle: 44,
            colors: [[TacticalTheme.page(this.targetDark), 0],
              [TacticalTheme.structural(this.targetDark), 0.28],
              [TacticalTheme.accentSoft(this.targetDark), 0.52],
              [TacticalTheme.page(this.targetDark), 0.78],
              [TacticalTheme.structural(this.targetDark), 1]]
          }).opacity(0.98).rotate({ angle: -36 })
            .translate({ x: this.themeSweep, y: -this.themeSweep * 1.2 })
        } else {
          Column().width('100%').height('100%').backgroundColor(TacticalTheme.page(this.isDark))
        }
        Column({ space: 20 }) {
          TacticalMotionCore({
            progress: this.transitionProgress,
            outerAngle: this.loadingOuterAngle,
            innerAngle: this.loadingInnerAngle,
            title: this.transitionTitle(),
            icon: this.transitionIcon(),
            isDark: this.transitionKind === 1 ? this.targetDark : this.isDark
          })
          if (this.transitionKind === 1 && this.themePhrase.length > 0) {
            Text(this.themePhrase)
              .fontSize(16)
              .fontWeight(FontWeight.Medium)
              .fontColor(TacticalTheme.text(this.targetDark))
          }
        }.width('100%').height('100%').justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
      }.width('100%').height('100%').clip(true).opacity(this.transitionClosing ? 0 : 1)
        .animation({ duration: 140, curve: Curve.EaseIn }).enabled(false)
    }
  }

  private transitionTitle(): string {
    if (this.transitionKind === 1) return this.targetDark ? '静夜' : '明昼';
    if (this.targetPage === 0) return '助手';
    if (this.targetPage === 1) return '设备';
    if (this.targetPage === 2) return '数据';
    return '设置';
  }

  private transitionIcon(): Resource {
    if (this.transitionKind === 1) return this.targetDark ? $r('sys.symbol.moon_fill') : $r('sys.symbol.sun_max');
    if (this.targetPage === 0) return $r('sys.symbol.mic_fill');
    if (this.targetPage === 1) return $r('sys.symbol.house_fill');
    if (this.targetPage === 2) return $r('sys.symbol.clock_fill');
    return $r('sys.symbol.gearshape_fill');
  }

  @Builder
  scoreRow(item: AssistantFeedItem) {
    Column({ space: 10 }) {
      Text('本次评分：').fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.text())
      Row({ space: 4 }) {
        ForEach([1,2,3,4,5,6,7,8,9,10], (score: number) => {
          TacticalCutCornerButton({ label: `${score}`, buttonWidth: 62, buttonHeight: 40, isDark: this.isDark,
            active: this.feedbackDraft(item.id).score === score,
            onTap: (): void => {
              const current = this.feedbackDraft(item.id);
              this.updateFeedback(item.id, score, current.choice, current.note, current.submitting);
            } })
        }, (score: number) => `${item.id}_${score}`)
      }.width('100%')
      Text('改进方式：').fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.text())
      TextInput({ text: this.feedbackDraft(item.id).note, placeholder: '写下更好的处理方式' })
        .width('100%').height(44).fontSize(14).fontColor(this.text()).placeholderColor(this.muted())
        .backgroundColor(this.input()).border({ width: 1, color: this.borderTone() })
        .onChange((value: string) => {
          const current = this.feedbackDraft(item.id);
          this.updateFeedback(item.id, current.score, current.choice, value, current.submitting);
        })
      Flex({ wrap: FlexWrap.Wrap, justifyContent: FlexAlign.SpaceBetween }) {
        ForEach(['A 保持当前','B 减少动作','C 只提醒','D 使用填写方案'], (choice: string) => {
          TacticalCutCornerButton({ label: choice, buttonWidth: 318, buttonHeight: 44, isDark: this.isDark,
            active: this.feedbackDraft(item.id).choice === choice.substring(0, 1),
            onTap: (): void => {
              const current = this.feedbackDraft(item.id);
              this.updateFeedback(item.id, current.score, choice.substring(0, 1), current.note, current.submitting);
            } })
            .margin({ bottom: 6 })
        }, (choice: string) => `${item.id}_${choice}`)
      }.width('100%')
      Row() {
        Blank()
        TacticalCutCornerButton({ label: this.feedbackDraft(item.id).submitting ? '提交中' : '提交',
          buttonWidth: 112, buttonHeight: 44, isDark: this.isDark,
          isEnabled: this.feedbackDraft(item.id).score > 0 && !this.feedbackDraft(item.id).submitting,
          active: this.feedbackDraft(item.id).score > 0,
          onTap: (): void => { this.submitAssistantFeedback(item); } })
      }.width('100%')
    }.width('100%')
  }

  @Builder
  assistantEvent(item: AssistantFeedItem) {
    Column({ space: 8 }) {
      HarmonChatBubble({ message: { id: `feed_${item.id}`, role: ChatRole.ASSISTANT,
        content: this.assistantEventText(item), timestamp: 0 }, isDark: this.isDark,
        onSpeak: (text: string): void => { ChatApi.speak(text); } })
      if (this.feedChartHasData(item)) {
        ChatChartPanel({ chartData: this.feedChartData(item) as ChartData, isDark: this.isDark })
      }
      if (item.feedback) {
        Text(`本次评分：${item.feedback.score}/10`).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.accent())
      } else if (item.feedbackEnabled === true) {
        this.scoreRow(item)
      }
    }.width('100%').padding(12).backgroundColor(this.raised()).border({ width: 1, color: this.borderTone() })
  }

  @Builder
  chatMessage(message: ChatMessage) {
    Column({ space: 6 }) {
      HarmonChatBubble({ message: message, isDark: this.isDark, onSpeak: (text: string): void => { ChatApi.speak(text); } })
    }.width('100%')
  }

  @Builder
  thinkingIndicator() {
    Row() {
      Blank()
      Row({ space: 10 }) {
        Stack({ alignContent: Alignment.Center }) {
          Progress({ value: this.thinkingProgress, total: 100, type: ProgressType.Ring })
            .width(44).height(44).color(this.accent()).style({ strokeWidth: 2 })
            .animation({ duration: this.thinkingFinishing ? 320 : 280, curve: Curve.EaseOut })
            .rotate({ angle: this.thinkingAngle * 0.48 })
          Column().width(34).height(34).border({ width: 1, color: this.borderTone() })
            .rotate({ angle: this.thinkingFinishing ? 45 : 45 + this.thinkingAngle })
            .scale({ x: this.thinkingFinishing ? 0.82 : 1, y: this.thinkingFinishing ? 0.82 : 1 })
            .opacity(this.thinkingFinishing ? 0.42 : 0.9)
            .animation({ duration: this.thinkingFinishing ? 360 : 220, curve: Curve.EaseOut })
          Column().width(22).height(22).border({ width: 1, color: this.accent() })
            .backgroundColor(this.panel())
            .rotate({ angle: this.thinkingFinishing ? 45 : 45 - this.thinkingAngle * 1.35 })
            .scale({ x: this.thinkingFinishing ? 0.68 : 1, y: this.thinkingFinishing ? 0.68 : 1 })
            .animation({ duration: this.thinkingFinishing ? 360 : 220, curve: Curve.EaseOut })
          if (this.thinkingFinishing) {
            SymbolGlyph($r('sys.symbol.checkmark')).fontSize(15).fontColor([this.accent()])
          } else {
            Column().width(6).height(6).backgroundColor(this.accent())
              .scale({ x: this.thinkingTick % 2 === 0 ? 0.66 : 1, y: this.thinkingTick % 2 === 0 ? 0.66 : 1 })
              .animation({ duration: 220, curve: Curve.EaseInOut })
          }
        }.width(46).height(46)
        Column({ space: 6 }) {
          Text(this.thinkingLabel()).fontSize(14).fontWeight(FontWeight.Medium).fontColor(this.secondary())
          Row({ space: 4 }) {
            ForEach([0, 1, 2, 3], (index: number) => {
              Column().width(20).height(3)
                .backgroundColor(index <= this.thinkingStep() ? this.accent() : this.borderTone())
                .opacity(index === this.thinkingStep() && !this.thinkingFinishing ? 0.62 : 1)
                .animation({ duration: 280, curve: Curve.EaseOut })
            }, (index: number) => `${index}`)
          }.height(4)
        }.width(86).alignItems(HorizontalAlign.Start)
      }.padding({ left: 11, right: 12, top: 9, bottom: 9 })
        .backgroundColor(this.raised())
        .border({ width: { right: 2, top: 1, left: 1, bottom: 1 }, color: this.accent() })
        .borderRadius(3)
    }.width('100%').padding({ left: 14, right: 14 })
  }

  @Builder
  acknowledgementOverlay() {
    ForEach(this.assistantFeed.filter((item: AssistantFeedItem): boolean =>
      item.id === this.pendingAcknowledgementId), (item: AssistantFeedItem) => {
      Stack({ alignContent: Alignment.Center }) {
        Column().width('100%').height('100%').backgroundColor(TacticalTheme.scrim(this.isDark))
        Column({ space: 12 }) {
          Row({ space: 9 }) {
            Column().width(5).height(28)
              .backgroundColor(item.severity === 'danger' ? TacticalTheme.alertDanger(this.isDark) :
                TacticalTheme.alertWarning(this.isDark))
            Column({ space: 2 }) {
              Text((item.kind === 'automation_adjustment' || item.kind === 'automation_alarm') ? item.title :
                item.severity === 'danger' ? '安全警报' : '状态警报')
                .fontSize(19).fontWeight(FontWeight.Bold).fontColor(this.text())
              Text(item.createdAt || '刚刚').fontSize(14).fontColor(this.muted())
            }.layoutWeight(1).alignItems(HorizontalAlign.Start)
          }.width('100%')
          Text(this.friendlyDescription(item)).width('100%').fontSize(16).lineHeight(24)
            .fontColor(this.secondary()).maxLines(5)
          Text(`设备：${this.friendlyDevice(item)}`)
            .width('100%').fontSize(14).fontColor(this.secondary()).maxLines(2)
          Text(`具体操作：${this.friendlyAction(item)}`)
            .width('100%').fontSize(14).fontColor(this.secondary()).maxLines(3)
          Text(`操作结果：${this.friendlyResult(item)}`)
            .width('100%').fontSize(14).fontColor(this.muted()).maxLines(3)
          Text('完整记录已保留在助手对话中。')
            .width('100%').fontSize(14).fontColor(this.muted())
          TacticalCutCornerButton({ label: this.acknowledgingAlert ? '正在确认' : '我已知晓',
            buttonWidth: 318, buttonHeight: 46, isDark: this.isDark, active: true,
            isEnabled: !this.acknowledgingAlert,
            onTap: (): void => { this.confirmAlertAcknowledgement(item); } })
        }
        .width(354).padding({ left: 16, right: 16, top: 16, bottom: 15 })
        .backgroundColor(this.raised())
        .border({ width: { left: 3, right: 1, top: 1, bottom: 1 },
          color: { left: item.severity === 'danger' ? TacticalTheme.alertDanger(this.isDark) :
            TacticalTheme.alertWarning(this.isDark),
            right: this.borderTone(), top: this.borderTone(), bottom: this.borderTone() } })
      }.width('100%').height('100%')
    }, (item: AssistantFeedItem) => `ack_${item.id}`)
  }

  @Builder
  assistantPage() {
    Column({ space: 8 }) {
      Scroll(this.chatScroller) {
        Column({ space: 8 }) {
          this.externalDigest()
          ForEach(this.timelineEntries(), (entry: TimelineEntry) => {
            if (entry.kind === 'message' && entry.message) this.chatMessage(entry.message);
            if (entry.kind === 'event' && entry.event) this.assistantEvent(entry.event);
          }, (entry: TimelineEntry) => entry.id)
          if (this.showThinking) this.thinkingIndicator()
        }.width('100%').padding({ left: 14, right: 14, top: 10, bottom: 10 })
      }.layoutWeight(1).width('100%').scrollBar(BarState.Off)
      Row({ space: 6 }) {
        TextInput({ text: this.inputText, placeholder: this.isListening ? '正在聆听…' : '输入消息' }).layoutWeight(1).height(46)
          .fontSize(15).fontColor(this.text()).placeholderColor(this.muted()).backgroundColor(this.input())
          .border({ width: 1, color: this.borderTone() }).onChange((value: string) => { this.inputText = value; }).onSubmit(() => this.send())
        Stack() {
          SymbolGlyph($r('sys.symbol.mic_fill'))
            .fontSize(20).fontColor([this.accent()])
        }.width(54).height(42).backgroundColor(this.panel())
          .border({ width: 1, color: this.borderTone() }).borderRadius(6)
          .opacity(this.isResponding ? 0.45 : 1).accessibilityText(this.isListening ? '停止语音输入' : '语音输入')
          .onClick(() => this.startVoice())
        Stack() {
          SymbolGlyph($r('sys.symbol.paperplane_fill')).fontSize(19)
            .fontColor([TacticalTheme.inverse(this.isDark)])
        }.width(54).height(42).backgroundColor(this.accent()).borderRadius(6)
          .opacity(this.isResponding ? 0.45 : 1).accessibilityText('发送消息')
          .onClick(() => { if (!this.isResponding) this.send(); })
      }.width('100%').padding(8).backgroundColor(this.raised()).border({ width: 1, color: this.borderTone() })
    }.width('100%').height('100%')
  }

  @Builder
  navItem(index: number, label: string, icon: Resource) {
    Column({ space: 4 }) {
      SymbolGlyph(icon).fontSize(18).fontColor([this.activePage === index ? TacticalTheme.inverse(this.isDark) : this.accent()])
      Text(label).fontSize(14).fontWeight(FontWeight.Medium)
        .fontColor(this.activePage === index ? TacticalTheme.inverse(this.isDark) : this.secondary())
    }.layoutWeight(1).height(62).justifyContent(FlexAlign.Center)
      .backgroundColor(this.activePage === index ? this.accent() : this.panel())
      .border({ width: 1, color: this.borderTone() }).onTouch((event: TouchEvent) => this.touch(`nav_${index}`, event)).onClick(() => this.switchPage(index))
  }

  @Builder
  bottomNav() {
    Row({ space: 5 }) {
      this.navItem(0, '助手', $r('sys.symbol.mic_fill'))
      this.navItem(1, '设备', $r('sys.symbol.house_fill'))
      this.navItem(2, '数据管理', $r('sys.symbol.clock_fill'))
      this.navItem(3, '设置', $r('sys.symbol.gearshape_fill'))
    }.width('100%').height(78).padding({ left: 10, right: 10, top: 8, bottom: 8 }).backgroundColor(this.raised())
  }

  build() {
    Stack() {
      Column() {
        if (!this.booting) this.header()
        Column() {
          if (this.booting) {
            this.loadingScreen()
          } else if (this.activePage === 0) {
            this.assistantPage()
          } else if (this.activePage === 1) {
            DeviceCenterPage({ isDark: this.isDark })
          } else if (this.activePage === 2) {
            Scroll() { HistoryPage({ isDark: this.isDark, onAnalyzeChart: (title: string, context: string): void => {
              this.activePage = 0; this.submitMessage(`请分析“${title}”图表。`);
            } }) }.width('100%').height('100%').scrollBar(BarState.Off)
          } else {
            SettingsPage({ isDark: this.isDark, onClearConversation: (): void => this.clearConversation() })
          }
        }.layoutWeight(1).width('100%').opacity(this.booting || this.contentVisible ? 1 : 0)
          .translate({ x: this.contentVisible ? 0 : this.pageDirection * 14 }).animation({ duration: 220, curve: Curve.EaseOut })
        if (!this.booting) this.bottomNav()
      }.width('100%').height('100%')
      if (this.pageSwitching || this.themeSwitching) this.transitionOverlay()
      if (!this.booting && this.pendingAcknowledgementId !== 0) this.acknowledgementOverlay()
    }.width('100%').height('100%').backgroundColor(this.page())
  }
}
