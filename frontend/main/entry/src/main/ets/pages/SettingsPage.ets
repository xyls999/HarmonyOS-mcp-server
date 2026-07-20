import { promptAction } from '@kit.ArkUI';
import { common } from '@kit.AbilityKit';
import { GuardApi, GuardStatus } from '../api/guardApi';
import { AssistantApi } from '../api/assistantApi';
import { TacticalSettingRow } from '../components/TacticalToggle';
import { TacticalCutCornerButton } from '../components/TacticalCutCornerButton';
import { TacticalTheme } from '../theme/TacticalTheme';
import { ChatApi, OfflineModelConfig, VoiceConfig } from '../api/chatApi';


@Component
export struct SettingsPage {
  @Prop isDark: boolean = true;
  onClearConversation?: () => void;
  @State guard: GuardStatus = {
    available: false,
    enabled: true,
    activeAiEnabled: true,
    feedbackAutomationEnabled: true,
    planConfirmationEnabled: false,
    mode: 'offline',
    guardLevel: 0,
    pendingFeedback: 0,
    recentIncidents: []
  };
  @State linkageEnabled: boolean = true;
  @State activeAiEnabled: boolean = true;
  @State feedbackAutomationEnabled: boolean = true;
  @State radarEnabled: boolean = true;
  @State externalEnabled: boolean = true;
  @State externalHydrated: boolean = false;
  @State voiceConfig: VoiceConfig = {
    enabled: true, serialPort: '自动识别', running: false, pid: 0, frames: 0,
    lastCommand: '', lastError: '串口未配置', inputMode: 'D6串口语音'
  };
  @State voiceHydrated: boolean = false;
  @State voiceEnabled: boolean = true;
  @State offlineModel: OfflineModelConfig = {
    enabled: true, baseUrl: 'http://192.168.1.11:8080/v1', endpoint: '', model: 'local-model', fallback: ['deepseek', 'codex']
  };
  @State offlineModelEnabled: boolean = true;
  @State offlineModelHydrated: boolean = false;
  @State settingsHydrated: boolean = false;
  @State settingsLoadError: boolean = false;
  @State checkingStatus: boolean = false;
  @State savingKey: string = '';
  private refreshTimer: number = -1;
  private loadSequence: number = 0;
  private appliedLoadSequence: number = 0;

  aboutToAppear(): void {
    this.loadData();
    this.refreshTimer = setInterval(() => this.loadData(), 10000);
    GuardApi.recordTelemetry('page_view', 'settings', 'open', 'ok');
  }

  aboutToDisappear(): void {
    if (this.refreshTimer !== -1) clearInterval(this.refreshTimer);
    this.refreshTimer = -1;
  }

  private page(): string { return TacticalTheme.page(this.isDark); }
  private panel(): string { return TacticalTheme.panel(this.isDark); }
  private raised(): string { return TacticalTheme.panelRaised(this.isDark); }
  private text(): string { return TacticalTheme.text(this.isDark); }
  private muted(): string { return TacticalTheme.textMuted(this.isDark); }
  private accent(): string { return TacticalTheme.accent(this.isDark); }
  private borderTone(): string { return TacticalTheme.border(this.isDark); }

  private voiceStateLabel(): string {
    if (!this.voiceHydrated) return '状态读取中';
    return this.voiceEnabled ? '已开启' : '已关闭';
  }

  private voiceStateDescription(): string {
    if (!this.voiceHydrated) return '正在读取 D6 设备端语音模块状态';
    if (!this.voiceEnabled) return '关闭后不接收语音控制指令';
    if (this.voiceConfig.running) return '正在监听设备端语音模块';
    return this.voiceConfig.lastError || '已开启，等待设备端语音模块连接';
  }

  private async loadData(): Promise<void> {
    const requestId = ++this.loadSequence;
    const statusRequest = GuardApi.getStatus();
    const radarRequest = GuardApi.getRadarEnabled();
    const externalRequest = AssistantApi.getExternalConfig();
    const voiceRequest = ChatApi.getVoiceConfig();
    const offlineRequest = ChatApi.getOfflineModelConfig();
    const nextGuard = await statusRequest;
    const nextRadar = await radarRequest;
    const nextExternal = await externalRequest;
    const nextVoice = await voiceRequest;
    const nextOffline = await offlineRequest;
    if (requestId < this.appliedLoadSequence) return;
    this.appliedLoadSequence = requestId;
    this.guard = nextGuard;
    this.settingsLoadError = !nextGuard.available;
    if (this.savingKey.length === 0) {
      this.linkageEnabled = nextGuard.enabled;
      this.activeAiEnabled = nextGuard.activeAiEnabled;
      this.feedbackAutomationEnabled = nextGuard.feedbackAutomationEnabled;
      if (nextRadar !== null) this.radarEnabled = nextRadar;
      this.settingsHydrated = nextGuard.available;
      if (nextExternal) {
        this.externalEnabled = nextExternal.enabled;
        this.externalHydrated = true;
      }
      if (nextVoice) {
        this.voiceConfig = nextVoice;
        this.voiceEnabled = nextVoice.enabled;
        this.voiceHydrated = true;
      }
      if (nextOffline) {
        this.offlineModel = nextOffline;
        this.offlineModelEnabled = nextOffline.enabled;
        this.offlineModelHydrated = true;
      }
    }
  }

  private rollbackSetting(key: string): void {
    if (key === 'linkage') this.linkageEnabled = !this.linkageEnabled;
    if (key === 'active_ai') this.activeAiEnabled = !this.activeAiEnabled;
    if (key === 'feedback_auto') this.feedbackAutomationEnabled = !this.feedbackAutomationEnabled;
    if (key === 'radar') this.radarEnabled = !this.radarEnabled;
  }

  private async updateGuard(enabled: boolean, activeAi: boolean, feedbackAutomationEnabled: boolean,
    action: string, key: string): Promise<void> {
    if (this.savingKey.length > 0) return;
    const previousGuard = this.guard;
    this.savingKey = key;
    this.guard = {
      available: previousGuard.available,
      enabled: enabled,
      activeAiEnabled: activeAi,
      feedbackAutomationEnabled: feedbackAutomationEnabled,
      planConfirmationEnabled: false,
      mode: enabled ? 'active' : 'passive',
      guardLevel: previousGuard.guardLevel,
      pendingFeedback: previousGuard.pendingFeedback,
      recentIncidents: previousGuard.recentIncidents
    };
    const ok = await GuardApi.updateConfig(enabled, activeAi, feedbackAutomationEnabled);
    await GuardApi.recordTelemetry('setting_change', 'settings', action, ok ? 'ok' : 'failed');
    if (!ok) {
      this.guard = previousGuard;
      this.rollbackSetting(key);
    }
    this.savingKey = '';
    promptAction.showToast({ message: ok ? '设置已同步' : '同步失败，已恢复原状态', duration: 1800 });
    if (ok) await this.loadData();
  }

  private async updateRadar(enabled: boolean): Promise<void> {
    if (this.savingKey.length > 0) return;
    this.savingKey = 'radar';
    const ok = await GuardApi.setRadarEnabled(enabled);
    await GuardApi.recordTelemetry('setting_change', 'settings', 'radar_presence', ok ? 'ok' : 'failed');
    if (!ok) this.rollbackSetting('radar');
    this.savingKey = '';
    promptAction.showToast({ message: ok ? '毫米波存在感知已更新' : '毫米波设置失败', duration: 1800 });
    if (ok) await this.loadData();
  }

  private async updateExternal(enabled: boolean): Promise<void> {
    if (this.savingKey.length > 0) return;
    const previous = this.externalEnabled;
    this.externalEnabled = enabled;
    this.savingKey = 'external';
    const ok = await AssistantApi.setExternalEnabled(enabled);
    await GuardApi.recordTelemetry('setting_change', 'settings', 'external_intelligence', ok ? 'ok' : 'failed');
    if (!ok) this.externalEnabled = previous;
    this.savingKey = '';
    promptAction.showToast({ message: ok ? '外部信息设置已同步' : '外部信息设置失败，已恢复', duration: 1800 });
  }

  private async updateVoice(enabled: boolean): Promise<void> {
    if (this.savingKey.length > 0) return;
    const previous = this.voiceConfig;
    this.savingKey = 'voice';
    const ok = await ChatApi.setVoiceEnabled(enabled);
    await GuardApi.recordTelemetry('setting_change', 'settings', 'voice_control', ok ? 'ok' : 'failed');
    const latest = await ChatApi.getVoiceConfig();
    if (ok && latest) {
      this.voiceConfig = latest;
      this.voiceEnabled = latest.enabled;
    } else {
      this.voiceConfig = previous;
      this.voiceEnabled = previous.enabled;
    }
    this.savingKey = '';
    promptAction.showToast({ message: ok ? (enabled ? '语音控制已开启，正在自动识别' : '语音控制已关闭') : '语音控制自动识别失败', duration: 2000 });
  }

  private async updateOfflineModel(enabled: boolean): Promise<void> {
    if (this.savingKey.length > 0) return;
    const previous = this.offlineModelEnabled;
    this.offlineModelEnabled = enabled;
    this.savingKey = 'offline_model';
    const ok = await ChatApi.setOfflineModelEnabled(enabled);
    await GuardApi.recordTelemetry('setting_change', 'settings', 'offline_model', ok ? 'ok' : 'failed');
    if (!ok) this.offlineModelEnabled = previous;
    const latest = await ChatApi.getOfflineModelConfig();
    if (latest) this.offlineModel = latest;
    this.savingKey = '';
    promptAction.showToast({ message: ok ? (enabled ? '离线模型已开启' : '离线模型已关闭') : '离线模型设置失败，已恢复', duration: 2000 });
  }

  private async runImmediateStatusCheck(): Promise<void> {
    if (this.checkingStatus || this.savingKey.length > 0 || !this.settingsHydrated) return;
    this.checkingStatus = true;
    const reports = await AssistantApi.runStatusCheck();
    await GuardApi.recordTelemetry('manual_status_check', 'settings', 'status_check', reports.length > 0 ? 'ok' : 'empty');
    this.checkingStatus = false;
    promptAction.showToast({
      message: reports.length > 0 ? '检测完成，结果已写入助手' : '检测完成，当前没有新增调整',
      duration: 2000
    });
  }

  private exitApp(): void {
    const context = getContext(this) as common.UIAbilityContext;
    context.terminateSelf();
  }

  @Builder
  voiceSettings() {
    Column({ space: 0 }) {
      Row({ space: 12 }) {
        Column().width(5).height(34).backgroundColor(this.accent())
        Text('语音控制').fontSize(20).fontWeight(FontWeight.Bold).fontColor(this.text())
        Blank()
        Text(this.voiceStateLabel())
          .fontSize(14)
          .fontWeight(FontWeight.Bold)
          .fontColor(this.voiceHydrated && this.voiceEnabled ? this.accent() : this.muted())
      }.width('100%').height(52)
      TacticalSettingRow({
        isOn: $voiceEnabled,
        title: '语音控制开关',
        description: this.voiceStateDescription(),
        disabled: !this.voiceHydrated || this.savingKey.length > 0,
        isDark: this.isDark,
        onToggle: (value: boolean) => this.updateVoice(value)
      })
      if (!this.voiceHydrated) {
        Text('状态尚未读取完成，开关暂时不可操作。')
          .fontSize(14).fontColor(this.muted()).width('100%').padding({ top: 8, bottom: 4 })
      }
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 8, bottom: 10 })
    .backgroundColor(this.raised())
    .border({ width: 1, color: this.borderTone() })
    .borderRadius(3)
  }

  @Builder
  guardSettings() {
    Column({ space: 0 }) {
      Row({ space: 12 }) {
        Column().width(5).height(34).backgroundColor(this.accent())
        Text('智能与联动').fontSize(20).fontWeight(FontWeight.Bold).fontColor(this.text())
        Blank()
        Text(this.guard.available ? 'D6 在线' : 'D6 离线')
          .fontSize(14)
          .fontWeight(FontWeight.Medium)
          .fontColor(this.guard.available ? this.accent() : this.muted())
      }.width('100%').height(52)

      if (!this.settingsHydrated && !this.settingsLoadError) {
        Text('正在读取设备端设置…').fontSize(14).fontColor(this.muted())
          .width('100%').textAlign(TextAlign.Center).padding({ top: 8, bottom: 8 })
      }
      if (this.settingsLoadError) {
        Text('无法读取设备端设置，已停止显示默认开关。请稍后重试。')
          .fontSize(14).fontColor(this.muted()).width('100%').textAlign(TextAlign.Center)
          .padding({ top: 8, bottom: 8 })
      }

      TacticalSettingRow({
        isOn: $linkageEnabled,
        title: '联动自动管理',
        description: '温湿度、厨房、门禁、光敏灯',
        disabled: !this.settingsHydrated || this.savingKey.length > 0 || !this.guard.available,
        isDark: this.isDark,
        onToggle: (value: boolean) => this.updateGuard(value, this.activeAiEnabled,
          this.feedbackAutomationEnabled, 'guard_enabled', 'linkage')
      })
      TacticalSettingRow({
        isOn: $activeAiEnabled,
        title: '主动 AI 警戒',
        description: '读取环境与历史行为',
        disabled: !this.settingsHydrated || this.savingKey.length > 0 || !this.guard.available,
        isDark: this.isDark,
        onToggle: (value: boolean) => this.updateGuard(this.linkageEnabled, value,
          this.feedbackAutomationEnabled, 'active_ai', 'active_ai')
      })
      TacticalSettingRow({
        isOn: $feedbackAutomationEnabled,
        title: '评分自动触发',
        description: '高分策略自动复用',
        disabled: !this.settingsHydrated || this.savingKey.length > 0 || !this.guard.available,
        isDark: this.isDark,
        onToggle: (value: boolean) => this.updateGuard(this.linkageEnabled,
          this.activeAiEnabled, value, 'feedback_automation', 'feedback_auto')
      })
      TacticalSettingRow({
        isOn: $radarEnabled,
        title: '毫米波存在感知',
        description: '人体存在检测',
        disabled: !this.settingsHydrated || this.savingKey.length > 0 || !this.guard.available,
        isDark: this.isDark,
        onToggle: (value: boolean) => this.updateRadar(value)
      })
      TacticalSettingRow({
        isOn: $externalEnabled,
        title: '外部信息摘要',
        description: '天气、新闻、交通、科技、行情',
        disabled: !this.externalHydrated || this.savingKey.length > 0,
        isDark: this.isDark,
        onToggle: (value: boolean) => this.updateExternal(value)
      })
      TacticalSettingRow({
        isOn: $offlineModelEnabled,
        title: '离线模型',
        description: '本地不可达时自动回退在线模型',
        disabled: !this.offlineModelHydrated || this.savingKey.length > 0,
        isDark: this.isDark,
        onToggle: (value: boolean) => this.updateOfflineModel(value)
      })
      Text(`本地模型：${this.offlineModel.model}`)
        .fontSize(14).fontColor(this.muted()).width('100%').maxLines(1)
      TacticalCutCornerButton({
        label: this.checkingStatus ? '检测中' : '立即检测',
        isEnabled: this.settingsHydrated && !this.checkingStatus && this.savingKey.length === 0,
        isDark: this.isDark, fillWidth: true, buttonWidth: 1, buttonHeight: 48,
        active: !this.checkingStatus,
        onTap: (): void => { this.runImmediateStatusCheck(); }
      })
    }
    .width('100%')
    .padding({ left: 16, right: 16, top: 8, bottom: 10 })
    .backgroundColor(this.raised())
    .border({ width: 1, color: this.borderTone() })
    .borderRadius(3)
  }


  @Builder
  utilityButton(title: string, danger: boolean, action: () => void) {
    Column() {
      TacticalCutCornerButton({ label: title, isEnabled: true, isDark: this.isDark, fillWidth: true, buttonWidth: 1, buttonHeight: 48,
        onTap: (): void => { action(); } })
    }.width('100%').justifyContent(FlexAlign.Center)
  }

  build() {
    Scroll() {
      Column({ space: 14 }) {
        Row({ space: 10 }) {
          Column().width(6).height(40).backgroundColor(this.accent())
          Text('设置').fontSize(28).fontWeight(FontWeight.Bold).fontColor(this.text())
        }.width('100%')
        this.voiceSettings()
        this.guardSettings()
        this.utilityButton('清空助手对话', false, () => {
          if (this.onClearConversation) this.onClearConversation();
        })
        this.utilityButton('退出软件', true, () => this.exitApp())
      }
      .width('100%')
      .alignItems(HorizontalAlign.Start)
      .padding({ left: 16, right: 16, top: 16, bottom: 36 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor(this.page())
    .scrollBar(BarState.Auto)
  }
}
