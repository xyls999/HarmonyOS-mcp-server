import { promptAction } from '@kit.ArkUI';
import { DeviceApi } from '../api/deviceApi';
import { router } from '@kit.ArkUI';
import { GuardApi, TelemetryMetadata } from '../api/guardApi';
import { Device, DeviceStatus, DeviceType } from '../api/types';
import { TacticalTheme } from '../theme/TacticalTheme';
import { TacticalCutCornerButton } from '../components/TacticalCutCornerButton';
import { TacticalDeviceToggle } from '../components/TacticalToggle';
import { TacticalDiamondSlider } from '../components/TacticalDiamondSlider';

@Component
export struct DeviceCenterPage {
  @Prop isDark: boolean = true;
  @State devices: Device[] = [];
  @State available: boolean = false;
  @State busyId: string = '';
  @State pressedActionKey: string = '';
  @State lastActionResult: string = '';
  @State doorPassword: string = '';
  @State doorActionState: string = '';
  @State passwordConsumed: boolean = false;
  @State showDoorPasswordDialog: boolean = false;
  @State doorDialogError: string = '';
  @State acTemperature: number = 26;
  private refreshTimer: number = -1;
  private devicesFingerprint: string = '';
  private pendingDeviceStates: Record<string, boolean | undefined> = {};
  private pendingDeviceDeadlines: Record<string, number> = {};
  private pendingDeviceValues: Record<string, number | undefined> = {};
  private pendingValueDeadlines: Record<string, number> = {};
  private reconcileTimerFast: number = -1;
  private reconcileTimerSlow: number = -1;
  private authoritative: Record<string, Device> = {};
  private loadSequence: number = 0;
  private appliedLoadSequence: number = 0;
  private hiddenDeviceIds: string[] = ['alarm_01', 'camera_01', 'nfc_01', 'radar_01'];

  aboutToAppear(): void {
    this.loadData();
    this.refreshTimer = setInterval(() => this.loadData(), 5000);
    GuardApi.recordTelemetry('page_view', 'devices', 'open', 'ok');
  }

  aboutToDisappear(): void {
    if (this.refreshTimer !== -1) clearInterval(this.refreshTimer);
    this.refreshTimer = -1;
    if (this.reconcileTimerFast !== -1) clearTimeout(this.reconcileTimerFast);
    if (this.reconcileTimerSlow !== -1) clearTimeout(this.reconcileTimerSlow);
    this.reconcileTimerFast = -1;
    this.reconcileTimerSlow = -1;
  }

  private page(): string { return TacticalTheme.page(this.isDark); }
  private panel(): string { return TacticalTheme.panel(this.isDark); }
  private raised(): string { return TacticalTheme.panelRaised(this.isDark); }
  private text(): string { return TacticalTheme.text(this.isDark); }
  private secondary(): string { return TacticalTheme.textSecondary(this.isDark); }
  private muted(): string { return TacticalTheme.textMuted(this.isDark); }
  private accent(): string { return TacticalTheme.accent(this.isDark); }
  private borderTone(): string { return TacticalTheme.border(this.isDark); }

  private async loadData(): Promise<void> {
    const requestId = ++this.loadSequence;
    const deviceSnapshot = await DeviceApi.getDeviceSnapshot();
    if (requestId < this.appliedLoadSequence) return;
    this.appliedLoadSequence = requestId;
    const mergedDevices = deviceSnapshot.devices
      .filter((device: Device) => this.isSurfaceDevice(device))
      .map((device: Device) => this.mergePendingValue(this.mergePendingState(device)));
    this.authoritative = {};
    for (const device of deviceSnapshot.devices) this.authoritative[device.id] = device;
    const fingerprint = mergedDevices.map((device: Device) =>
      `${device.id}:${device.status}:${device.isOn}:${device.primaryValue}:${device.mode || ''}`).join('|');
    if (fingerprint !== this.devicesFingerprint) {
      this.devices = mergedDevices;
      this.devicesFingerprint = fingerprint;
    }
    this.available = deviceSnapshot.available;
  }

  private async runAction(deviceId: string, actionName: string,
    action: () => Promise<boolean>, expectedState?: boolean, expectedValue?: number): Promise<void> {
    if (this.busyId.length > 0) return;
    const previous = this.devices.find((device: Device) => device.id === deviceId);
    if (expectedState !== undefined) this.applyOptimisticState(deviceId, expectedState);
    if (expectedValue !== undefined) this.applyOptimisticValue(deviceId, expectedValue);
    this.busyId = deviceId;
    this.lastActionResult = '';
    let ok = false;
    try {
      ok = await action();
    } catch (e) {
      ok = false;
    }
    this.lastActionResult = ok ? `${deviceId}:ok` : `${deviceId}:failed`;
    if (actionName === 'unlock' || actionName === 'lock') {
      this.doorActionState = ok ? '已确认' : (actionName === 'unlock' ? '开门失败，请检查密码' : '关门失败，请稍后重试');
    }
    if (!ok && previous && expectedState !== undefined) {
      this.devices = this.devices.map((device: Device) => device.id === deviceId ? previous : device);
      this.pendingDeviceStates[deviceId] = undefined;
      this.pendingDeviceDeadlines[deviceId] = 0;
      this.pendingDeviceValues[deviceId] = undefined;
      this.pendingValueDeadlines[deviceId] = 0;
    }
    this.busyId = '';
    const metadata: TelemetryMetadata = { deviceId: deviceId };
    await GuardApi.recordTelemetry('button_result', 'devices', `${deviceId}.${actionName}`, ok ? 'ok' : 'failed', metadata);
    promptAction.showToast({ message: ok ? '设备指令已执行' : '设备指令执行失败', duration: 1800 });
    await this.loadData();
    if (ok) this.scheduleReconciliation();
  }

  private copyWithState(device: Device, isOn: boolean): Device {
    return { id: device.id, name: device.name, type: device.type, status: device.status, room: device.room,
      icon: device.icon, primaryValue: device.primaryValue, isOn: isOn, mode: device.mode, battery: device.battery,
      uptimeSeconds: device.uptimeSeconds, lastSeen: device.lastSeen, onlineSince: device.onlineSince };
  }

  private applyOptimisticState(deviceId: string, expectedState: boolean): void {
    this.pendingDeviceStates[deviceId] = expectedState;
    this.pendingDeviceDeadlines[deviceId] = Date.now() + 8000;
    this.devices = this.devices.map((device: Device) =>
      device.id === deviceId ? this.copyWithState(device, expectedState) : device);
    this.devicesFingerprint = '';
  }

  private copyWithValue(device: Device, primaryValue: number): Device {
    return { id: device.id, name: device.name, type: device.type, status: device.status, room: device.room,
      icon: device.icon, primaryValue: primaryValue, isOn: device.isOn, mode: device.mode, battery: device.battery,
      uptimeSeconds: device.uptimeSeconds, lastSeen: device.lastSeen, onlineSince: device.onlineSince };
  }

  private applyOptimisticValue(deviceId: string, expectedValue: number): void {
    this.pendingDeviceValues[deviceId] = expectedValue;
    this.pendingValueDeadlines[deviceId] = Date.now() + 8000;
    this.devices = this.devices.map((device: Device) =>
      device.id === deviceId ? this.copyWithValue(device, expectedValue) : device);
    this.devicesFingerprint = '';
  }

  private mergePendingState(device: Device): Device {
    const expected = this.pendingDeviceStates[device.id];
    if (expected === undefined) return device;
    if (device.isOn === expected || Date.now() > (this.pendingDeviceDeadlines[device.id] || 0)) {
      this.pendingDeviceStates[device.id] = undefined;
      this.pendingDeviceDeadlines[device.id] = 0;
      return device;
    }
    return this.copyWithState(device, expected);
  }

  private mergePendingValue(device: Device): Device {
    const expected = this.pendingDeviceValues[device.id];
    if (expected === undefined) return device;
    if (Math.abs(device.primaryValue - expected) < 0.1 || Date.now() > (this.pendingValueDeadlines[device.id] || 0)) {
      this.pendingDeviceValues[device.id] = undefined;
      this.pendingValueDeadlines[device.id] = 0;
      return device;
    }
    return this.copyWithValue(device, expected);
  }

  private scheduleReconciliation(): void {
    if (this.reconcileTimerFast !== -1) clearTimeout(this.reconcileTimerFast);
    if (this.reconcileTimerSlow !== -1) clearTimeout(this.reconcileTimerSlow);
    this.reconcileTimerFast = setTimeout(() => { this.reconcileTimerFast = -1; this.loadData(); }, 350);
    this.reconcileTimerSlow = setTimeout(() => { this.reconcileTimerSlow = -1; this.loadData(); }, 1600);
  }

  private isOnline(device: Device): boolean {
    // 语音控制是网关虚拟设备；串口运行状态仍在设置页显示，但开关入口始终可用。
    if (device.id === 'voice_01') return true;
    return device.status !== DeviceStatus.OFFLINE;
  }

  private isSurfaceDevice(device: Device): boolean {
    return this.hiddenDeviceIds.indexOf(device.id) < 0;
  }

  private deviceCategoryOf(device: Device): number {
    if (device.type === DeviceType.DOOR || device.id === 'door_01') return 0;
    if (device.type === DeviceType.AC || device.type === DeviceType.FAN || device.id === 'fan_02') return 1;
    if (device.type === DeviceType.LIGHT || device.type === DeviceType.CURTAIN ||
      device.id === 'curtain_01') return 2;
    return 3;
  }

  private friendlyDeviceName(device: Device): string {
    if (device.id === 'voice_01') return '语音控制';
    if (device.name && device.name.indexOf('_') < 0) return device.name;
    if (device.type === DeviceType.DOOR) return '门禁';
    if (device.type === DeviceType.AC) return '空调';
    if (device.type === DeviceType.FAN) return '风扇';
    if (device.type === DeviceType.LIGHT) return '灯光';
    if (device.type === DeviceType.CURTAIN) return '窗帘';
    return '设备';
  }

  private devicesForCategory(category: number): Device[] {
    return this.devices.filter((device: Device) => this.deviceCategoryOf(device) === category);
  }

  private deviceRenderKey(device: Device): string {
    // 保持设备卡片身份稳定，让 TacticalDeviceToggle 的 @Watch 接住状态变化并播放完整动效，
    // 而不是因状态变化重建节点、直接跳到终态。
    return device.id;
  }

  private currentDeviceIsOn(deviceId: string): boolean {
    const current = this.devices.find((device: Device) => device.id === deviceId);
    return current ? current.isOn : false;
  }

  private toggleDeviceById(deviceId: string): void {
    const current = this.devices.find((device: Device) => device.id === deviceId);
    if (!current || !this.isOnline(current) || this.busyId.length > 0) return;
    this.setDevicePower(deviceId, !current.isOn);
  }

  private setDevicePower(deviceId: string, nextState: boolean): void {
    const current = this.devices.find((device: Device) => device.id === deviceId);
    if (!current || !this.isOnline(current) || this.busyId.length > 0 || current.isOn === nextState) return;
    this.runAction(deviceId, nextState ? 'on' : 'off',
      () => DeviceApi.toggle(deviceId, nextState), nextState);
  }

  private openDoorPasswordDialog(device: Device): void {
    if (!this.isOnline(device) || this.busyId.length > 0) return;
    this.doorPassword = '';
    this.doorDialogError = '';
    this.showDoorPasswordDialog = true;
  }

  private cancelDoorPasswordDialog(): void {
    if (this.busyId.length > 0) return;
    this.showDoorPasswordDialog = false;
    this.doorPassword = '';
    this.doorDialogError = '';
  }

  private confirmDoorUnlock(device: Device): void {
    const password = this.doorPassword.trim();
    if (password.length === 0 || this.busyId.length > 0) {
      this.doorDialogError = '请输入本次开门密码';
      return;
    }
    this.showDoorPasswordDialog = false;
    this.doorPassword = '';
    this.passwordConsumed = true;
    this.runAction(device.id, 'unlock', () => DeviceApi.unlockDoor(device.id, password));
  }

  private commitBrightness(device: Device, value: number): void {
    this.runAction(device.id, `brightness_${value}`, () => DeviceApi.setBrightness(device.id, value), value > 0, value);
  }

  private commitFanSpeed(device: Device, value: number): void {
    this.runAction(device.id, `speed_${value}`, () => DeviceApi.setFanSpeed(device.id, value), value > 0, value);
  }

  private commitCurtain(device: Device, value: number): void {
    this.runAction(device.id, `position_${value}`, () => DeviceApi.setCurtainPosition(device.id, value), value > 0, value);
  }

  private commitAcTemperature(device: Device, value: number): void {
    this.acTemperature = value;
    this.runAction(device.id, `temperature_${value}`, () => DeviceApi.setAcTemperature(device.id, value));
  }

  @Builder
  actionButton(label: string, enabled: boolean, action: () => void) {
    TacticalCutCornerButton({ label: this.busyId.length > 0 ? '执行中' : label,
        isEnabled: enabled && this.busyId.length === 0, isDark: this.isDark, buttonWidth: 104, buttonHeight: 44,
        onTap: (): void => { action(); } })
  }

  @Builder
  doorActionButton(label: string, enabled: boolean, active: boolean, action: () => void) {
    TacticalCutCornerButton({ label: this.busyId.length > 0 ? '正在验证' : label,
      isEnabled: enabled && this.busyId.length === 0, isDark: this.isDark,
      buttonWidth: 164, buttonHeight: 48, active: active && enabled,
      accentOverride: label === '开门' ? TacticalTheme.doorOpen(this.isDark) : TacticalTheme.doorClose(this.isDark),
      onTap: (): void => { action(); } })
  }

  @Builder
  stateToggle(device: Device) {
    TacticalDeviceToggle({
      isOn: this.currentDeviceIsOn(device.id),
      disabled: !this.isOnline(device) || this.busyId.length > 0,
      isDark: this.isDark,
      onToggle: (next: boolean): void => { this.setDevicePower(device.id, next); }
    })
  }

  @Builder
  deviceActionGrid() {
    Row({ space: 6 }) {
      Column().width(18).height(2).backgroundColor(this.accent())
      Column().layoutWeight(1).height(1).backgroundColor(this.borderTone())
    }.width('100%').height(2)
  }

  @Builder
  standardControls(device: Device) {
    Column({ space: 5 }) {
      if (device.type === DeviceType.LIGHT) {
        TacticalDiamondSlider({ label: '亮度', value: Math.max(0, Math.min(100, device.primaryValue)),
          min: 0, max: 100, step: 10, unit: '%',
          isEnabled: this.isOnline(device) && this.busyId.length === 0, isDark: this.isDark,
          onCommit: (value: number): void => { this.commitBrightness(device, value); } })
      }
      if (device.type === DeviceType.FAN || device.id === 'fan_02') {
        TacticalDiamondSlider({ label: '风速', value: Math.max(0, Math.min(100, device.primaryValue)),
          min: 0, max: 100, step: 10, unit: '%',
          isEnabled: this.isOnline(device) && this.busyId.length === 0, isDark: this.isDark,
          onCommit: (value: number): void => { this.commitFanSpeed(device, value); } })
      }
      if (device.type === DeviceType.CUSTOM) {
        Row({ space: 6 }) {
          this.actionButton('红', this.isOnline(device), () => {
            this.runAction(device.id, 'color_red', () => DeviceApi.control(device.id, 'set_color', { color: 'red' }));
          })
          this.actionButton('绿', this.isOnline(device), () => {
            this.runAction(device.id, 'color_green', () => DeviceApi.control(device.id, 'set_color', { color: 'green' }));
          })
          this.actionButton('蓝', this.isOnline(device), () => {
            this.runAction(device.id, 'color_blue', () => DeviceApi.control(device.id, 'set_color', { color: 'blue' }));
          })
        }.width('100%')
      }
    }
    .width('100%')
  }

  @Builder
  acControls(device: Device) {
    Column({ space: 5 }) {
      Row({ space: 5 }) {
        this.actionButton('制冷 26℃', this.isOnline(device), () => {
          this.runAction(device.id, 'cool_26', () => DeviceApi.applyAcProfile(device.id, 'COOL_26_AUTO'));
        })
        this.actionButton('除湿', this.isOnline(device), () => {
          this.runAction(device.id, 'dry', () => DeviceApi.applyAcProfile(device.id, 'DRY_26_AUTO'));
        })
      }.width('100%')
      Row({ space: 5 }) {
        this.actionButton('送风', this.isOnline(device), () => {
          this.runAction(device.id, 'fan', () => DeviceApi.applyAcProfile(device.id, 'FAN_26_AUTO'));
        })
      }.width('100%')
      TacticalDiamondSlider({ label: '温度', value: this.acTemperature,
        min: 16, max: 30, step: 1, unit: '℃',
        isEnabled: this.isOnline(device) && this.busyId.length === 0, isDark: this.isDark,
        onPreview: (value: number): void => { this.acTemperature = value; },
        onCommit: (value: number): void => { this.commitAcTemperature(device, value); } })
    }.width('100%')
  }

  @Builder
  curtainControls(device: Device) {
    Row({ space: 8 }) {
      Column() {
        TacticalDiamondSlider({ label: '位置', value: Math.max(0, Math.min(100, device.primaryValue)),
          min: 0, max: 100, step: 10, unit: '%',
          isEnabled: this.isOnline(device) && this.busyId.length === 0, isDark: this.isDark,
          onCommit: (value: number): void => { this.commitCurtain(device, value); } })
      }.layoutWeight(1)
      this.actionButton('急停', this.isOnline(device), () => {
        this.runAction(device.id, 'stop', () => DeviceApi.stopCurtain(device.id));
      })
    }.width('100%')
  }

  @Builder
  doorControls(device: Device) {
    Column({ space: 8 }) {
      Row({ space: 8 }) {
        SymbolGlyph($r('sys.symbol.lock_fill')).fontSize(18).fontColor([TacticalTheme.doorOpen(this.isDark)])
        Column({ space: 2 }) {
          Text('门禁控制').fontSize(15).fontWeight(FontWeight.Bold).fontColor(this.text())
          Text('开门验证密码，关门无需密码').fontSize(14).fontColor(this.secondary())
        }.alignItems(HorizontalAlign.Start)
        Blank()
        Text(device.isOn ? '门已开启' : '门已关闭').fontSize(14).fontWeight(FontWeight.Medium)
          .fontColor(device.isOn ? TacticalTheme.doorOpen(this.isDark) : TacticalTheme.doorClose(this.isDark))
      }.width('100%')
      Row({ space: 5 }) {
        this.doorActionButton('开门', this.isOnline(device) && !device.isOn, true, () => {
          this.openDoorPasswordDialog(device);
        })
        this.doorActionButton('关门', this.isOnline(device) && device.isOn, true, () => {
          this.runAction(device.id, 'lock', () => DeviceApi.toggle(device.id, false), false);
        })
      }.width('100%').justifyContent(FlexAlign.SpaceBetween)
      if (this.doorActionState.length > 0) {
        Text(this.doorActionState).fontSize(14)
          .fontColor(this.doorActionState === '已确认' ? this.accent() : '#FF7A7A')
          .width('100%').textAlign(TextAlign.Center)
      }
    }
  }

  @Builder
  doorPasswordDialog(device: Device) {
    Stack() {
      Column().width('100%').height('100%').backgroundColor('#99000000')
      Column({ space: 14 }) {
        Row({ space: 8 }) {
          SymbolGlyph($r('sys.symbol.lock_fill')).fontSize(22).fontColor([TacticalTheme.doorOpen(this.isDark)])
          Text('开门验证').fontSize(20).fontWeight(FontWeight.Bold).fontColor(this.text()).layoutWeight(1)
          Text('×').fontSize(24).fontColor(this.secondary()).onClick(() => this.cancelDoorPasswordDialog())
        }.width('100%')
        Text('请输入本次门禁密码，关门不需要密码。').fontSize(14).fontColor(this.secondary()).width('100%')
        TextInput({ placeholder: '本次开门密码', text: this.doorPassword })
          .type(InputType.Password).height(48).width('100%').fontSize(17)
          .fontColor(this.text()).placeholderColor(this.muted()).backgroundColor(this.page())
          .border({ width: 1, color: TacticalTheme.doorOpen(this.isDark) })
          .onChange((value: string) => { this.doorPassword = value; this.doorDialogError = ''; })
        if (this.doorDialogError.length > 0) {
          Text(this.doorDialogError).fontSize(14).fontColor('#FF8E7A').width('100%')
        }
        Row({ space: 8 }) {
          TacticalCutCornerButton({ label: '取消', buttonWidth: 126, buttonHeight: 46, isDark: this.isDark,
            accentOverride: '#70899A', onTap: (): void => { this.cancelDoorPasswordDialog(); } })
          TacticalCutCornerButton({ label: '确认开门', buttonWidth: 170, buttonHeight: 46, isDark: this.isDark,
            active: true, accentOverride: TacticalTheme.doorOpen(this.isDark), onTap: (): void => { this.confirmDoorUnlock(device); } })
        }.width('100%').justifyContent(FlexAlign.End)
      }.width('88%').padding(18).backgroundColor(this.raised())
        .border({ width: 1, color: TacticalTheme.doorOpen(this.isDark) }).borderRadius(4)
    }.width('100%').height('100%')
  }

  @Builder
  doorPasswordOverlay() {
    ForEach(this.devices.filter((item: Device) => item.id === 'door_01'), (door: Device) => {
      this.doorPasswordDialog(door);
    }, (door: Device) => door.id)
  }

  @Builder
  deviceCard(device: Device) {
    Column({ space: 11 }) {
      Row({ space: 8 }) {
        SymbolGlyph(device.icon).fontSize(19).fontColor([this.accent()])
        Column({ space: 2 }) {
          Text(this.friendlyDeviceName(device)).fontSize(14).fontWeight(FontWeight.Bold).fontColor(this.text()).maxLines(1)
          Text(`${device.room}  ${this.isOnline(device) ? '在线' : '离线'}`)
            .fontSize(14).fontColor(this.muted()).maxLines(1)
        }
        .layoutWeight(1).alignItems(HorizontalAlign.Start)
        if (device.type === DeviceType.DOOR || device.id === 'door_01') {
          Text(this.busyId === device.id ? '执行中' : device.isOn ? '开启' : '关闭')
            .fontSize(14).fontColor(device.isOn ? this.accent() : this.muted())
        } else {
          this.stateToggle(device)
        }
      }
      .width('100%')

      this.deviceActionGrid()

      if (this.lastActionResult.indexOf(`${device.id}:`) === 0) {
        Text(this.lastActionResult.endsWith(':ok') ? '最近指令：已确认' : '最近指令：执行失败')
          .fontSize(14).fontColor(this.lastActionResult.endsWith(':ok') ? this.accent() : '#FF7A7A')
      }

      if (device.type === DeviceType.DOOR || device.id === 'door_01') {
        this.doorControls(device)
      } else if (device.type === DeviceType.AC || device.id === 'ac_01') {
        this.acControls(device)
      } else if (device.type === DeviceType.CURTAIN || device.id === 'curtain_01') {
        this.curtainControls(device)
      } else {
        this.standardControls(device)
      }
    }
    .width('100%')
    .padding({ left: 12, right: 12, top: 11, bottom: 12 })
    .backgroundColor(this.raised())
    .border({ width: { left: 2, right: 1, top: 1, bottom: 1 },
      color: { left: this.accent(), right: this.borderTone(), top: this.borderTone(), bottom: this.borderTone() } })
    .borderRadius(0)
  }

  @Builder
  deviceCategory(title: string, category: number) {
    if (this.devicesForCategory(category).length > 0) {
      Column({ space: 10 }) {
        Row({ space: 10 }) {
          Column().width(4).height(38).backgroundColor(this.accent())
          Text(title).fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
            .layoutWeight(1)
          Text(`${this.devicesForCategory(category).length}`)
            .fontSize(18).fontWeight(FontWeight.Bold).fontColor(this.accent())
        }.width('100%').alignItems(VerticalAlign.Center)

        Column({ space: 10 }) {
          ForEach(this.devicesForCategory(category), (device: Device) => {
            this.deviceCard(device)
          }, (device: Device) => this.deviceRenderKey(device))
        }.width('100%')
      }
      .width('100%')
      .padding({ top: 8, bottom: 8 })
    }
  }

  build() {
    Stack() {
      Scroll() {
      Column({ space: 8 }) {
        Column({ space: 4 }) {
          Text('设备').fontSize(22).fontWeight(FontWeight.Bold).fontColor(this.text())
          Text(this.available ? `${this.devices.length} 台设备` : '设备暂不可用')
            .fontSize(14).fontColor(this.available ? this.accent() : '#FF7A7A')
        }.width('100%').alignItems(HorizontalAlign.Start)

        if (this.devices.length === 0) {
          Text(this.available ? '暂无可控设备' : '暂时无法读取设备')
            .width('100%').height(64).textAlign(TextAlign.Center)
            .fontSize(14).fontColor(this.muted()).backgroundColor(this.panel())
        }
        this.deviceCategory('门禁与出入口', 0)
        this.deviceCategory('温控与空气', 1)
        this.deviceCategory('照明与遮阳', 2)
        this.deviceCategory('自定义设备', 3)
        this.customDeviceEntry()
      }
      .width('100%')
      .padding({ left: 12, right: 12, top: 10, bottom: 24 })
      }
      .width('100%').height('100%').scrollBar(BarState.Auto)
      .edgeEffect(EdgeEffect.Spring).backgroundColor(this.page())
      if (this.showDoorPasswordDialog) {
        this.doorPasswordOverlay()
      }
    }.width('100%').height('100%')
  }

  @Builder
  customDeviceEntry() {
    Column({ space: 8 }) {
      Row({ space: 8 }) {
        Column().width(4).height(34).backgroundColor(this.accent())
        Column({ space: 3 }) {
          Text('扫描自定义设备').fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.text())
          Text('选择设备类型，扫描并接入局域网设备').fontSize(14).fontColor(this.muted())
        }.layoutWeight(1).alignItems(HorizontalAlign.Start)
        TacticalCutCornerButton({ label: '扫描', isEnabled: true, isDark: this.isDark,
          buttonWidth: 86, buttonHeight: 44, onTap: (): void => {
            router.pushUrl({ url: 'pages/AddDevicePage' });
          } })
      }.width('100%').alignItems(VerticalAlign.Center)
    }.width('100%').padding(10).backgroundColor(this.raised())
      .border({ width: 1, color: this.borderTone() }).borderRadius(0)
  }
}
