import { DeviceApi } from '../api/deviceApi';
import { SensorApi } from '../api/sensorApi';
import { V5Api } from '../api/v5Api';
import { ApiActionResult, AreaStatus, ControlParams, Device, DeviceType, Sensor, Stats } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';
import { GeometricBackdrop } from '../components/GeometricBackdrop';
import { hilog } from '@kit.PerformanceAnalysisKit';

interface AreaDefinition { key: string; name: string; }

@Component
export struct HomePage {
  @State devices: Device[] = DeviceApi.getInventory();
  @State sensors: Sensor[] = [];
  @State stats: Stats | null = null;
  @State loading: boolean = false;
  @State loadMessage: string = '';
  @State busyDeviceId: string = '';
  @State actionMessage: string = '';
  @State actionError: boolean = false;
  @State doorDialogVisible: boolean = false;
  @State doorPassword: string = '';
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;
  @StorageLink('isOfflineMode') isOfflineMode: boolean = false;
  private readonly areas: AreaDefinition[] = [
    { key: 'living_room', name: '客厅' },
    { key: 'kitchen', name: '厨房' },
    { key: 'bathroom', name: '卫生间' },
    { key: 'bedroom', name: '卧室' }
  ];
  private readonly rooms: string[] = ['客厅', '厨房', '卫生间', '卧室'];

  aboutToAppear(): void { this.load(); }
  async load(): Promise<void> {
    if (this.loading) return;
    this.loading = true;
    this.loadMessage = '';
    const deviceTask = DeviceApi.getDevicesResult();
    const sensorTask = SensorApi.getSensorsResult();
    const statsTask = V5Api.getStats();
    const deviceResult = await deviceTask;
    this.devices = deviceResult.devices;
    hilog.info(0x0000, 'SmartHomeHome', 'devices=%{public}d error=%{public}s',
      this.devices.length, deviceResult.error);
    const sensorResult = await sensorTask;
    this.sensors = sensorResult.sensors;
    this.stats = await statsTask;
    const errors: string[] = [];
    if (deviceResult.error) errors.push(deviceResult.error);
    if (sensorResult.error) errors.push(sensorResult.error);
    this.loadMessage = errors.join('；');
    this.loading = false;
  }
  private devicesInRoom(room: string): Device[] { return this.devices.filter((device: Device) => device.room === room); }
  private sensorsInRoom(room: string): Sensor[] { return this.sensors.filter((sensor: Sensor) => sensor.room === room); }
  private areaStatus(key: string): AreaStatus | undefined { return this.stats?.area_connectivity[key]; }
  private areaOnline(area: AreaDefinition): boolean {
    const status = this.areaStatus(area.key);
    if (status) return status.online;
    return this.devicesInRoom(area.name).some((device: Device): boolean => device.online) ||
      this.sensorsInRoom(area.name).some((sensor: Sensor): boolean => sensor.online);
  }
  private statusText(device: Device): string {
    if (this.isOfflineMode) return '状态未同步';
    if (!device.online) return '设备离线';
    if (device.type === DeviceType.CURTAIN) return `位置 ${device.primaryValue ?? 0}%`;
    if (device.type === DeviceType.FAN) return device.isOn ? `运行 ${device.primaryValue ?? 0}%` : '已停止';
    if (device.type === DeviceType.DOOR) return device.isOn ? '已打开' : '已关闭';
    if (device.type === DeviceType.ALARM) return device.isOn ? '报警中' : '待命';
    if (device.type === DeviceType.LIGHT && device.isOn) {
      return device.primaryValue !== null && device.primaryValue > 0 ? `亮度 ${device.primaryValue}%` : '已开启';
    }
    return device.isOn ? '已开启' : '已关闭';
  }

  private sensorValue(sensor: Sensor): string {
    if (!sensor.online || !sensor.current || sensor.current.value === null) return '离线';
    if (sensor.current.unit === '正常') return sensor.current.unit;
    if (sensor.current.unit.includes('报警')) return sensor.current.value === 0 ? '正常' : '报警';
    return `${sensor.current.value}${sensor.current.unit}`;
  }

  private extendedControl(device: Device): boolean {
    return device.type === DeviceType.FAN || device.type === DeviceType.CURTAIN || device.type === DeviceType.AC;
  }

  async toggle(device: Device): Promise<void> {
    if (!device.online || this.busyDeviceId.length > 0) return;
    if (device.type === DeviceType.DOOR && !device.isOn) {
      this.doorPassword = '';
      this.doorDialogVisible = true;
      return;
    }
    this.busyDeviceId = device.id;
    let result: ApiActionResult;
    if (device.type === DeviceType.DOOR) result = await DeviceApi.doorResult('close');
    else result = await DeviceApi.toggleResult(device.id, !device.isOn);
    this.showResult(result);
    if (result.success) await this.load();
    this.busyDeviceId = '';
  }
  async control(device: Device, action: string, value?: number): Promise<void> {
    if (!device.online || this.busyDeviceId.length > 0) return;
    this.busyDeviceId = device.id;
    const params: ControlParams = {};
    if (value !== undefined) params.value = value;
    const result = await DeviceApi.controlResult(device.id, action, params);
    this.showResult(result);
    if (result.success) await this.load();
    this.busyDeviceId = '';
  }

  private showResult(result: ApiActionResult): void {
    this.actionMessage = result.message;
    this.actionError = !result.success;
  }

  private async submitDoorPassword(): Promise<void> {
    if (!this.doorPassword.trim()) {
      this.actionMessage = '请输入门禁密码';
      this.actionError = true;
      return;
    }
    this.busyDeviceId = 'door_01';
    const result = await DeviceApi.doorResult('open', this.doorPassword);
    this.doorDialogVisible = false;
    this.doorPassword = '';
    this.showResult(result);
    if (result.success) await this.load();
    this.busyDeviceId = '';
  }

  @Builder
  areaItem(area: AreaDefinition) {
    Row({ space: AppSpace.MD }) {
      Text(area.name).fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
        .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
      Circle({ width: 8, height: 8 })
        .fill(this.areaOnline(area) ? AppColors.ONLINE : AppColors.OFFLINE)
      Text(this.isOfflineMode ? '未同步' : this.areaOnline(area) ? '在线' : '离线')
        .fontSize(AppFont.SIZE_FOOTNOTE)
        .fontColor(this.areaOnline(area) ? AppColors.textSecondary(this.isDarkTheme) : AppColors.OFFLINE)
    }
    .height(72)
    .padding({ left: AppSpace.BASE, right: AppSpace.BASE })
    .backgroundColor(AppColors.card(this.isDarkTheme))
    .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
    .alignItems(VerticalAlign.Center)
  }

  @Builder
  compactButton(label: string, enabled: boolean, selected: boolean, action: () => void) {
    Button(label)
      .height(36)
      .fontSize(AppFont.SIZE_FOOTNOTE)
      .fontWeight(FontWeight.Bold)
      .fontColor(selected && enabled ? AppColors.onPrimary(this.isDarkTheme) : AppColors.textSecondary(this.isDarkTheme))
      .backgroundColor(selected && enabled ? AppColors.primary(this.isDarkTheme) : AppColors.group(this.isDarkTheme))
      .border({ width: 1, color: selected ? AppColors.primary(this.isDarkTheme) : AppColors.hairline(this.isDarkTheme) })
      .borderRadius(AppSpace.RADIUS_SM)
      .enabled(enabled)
      .opacity(enabled ? 1 : 0.42)
      .onClick(action)
  }

  @Builder
  deviceControl(device: Device) {
    if (device.type === DeviceType.FAN) {
      Row({ space: AppSpace.XS }) {
        this.compactButton('反转', device.online, device.isOn && device.mode === 'reverse',
          (): void => { this.control(device, 'reverse', device.primaryValue !== null && device.primaryValue > 0 ? device.primaryValue : 60); })
        this.compactButton('停止', device.online, !device.isOn, (): void => { this.control(device, 'stop'); })
        this.compactButton('正转', device.online, device.isOn && device.mode !== 'reverse',
          (): void => { this.control(device, 'forward', device.primaryValue !== null && device.primaryValue > 0 ? device.primaryValue : 60); })
      }
    } else if (device.type === DeviceType.CURTAIN) {
      Row({ space: AppSpace.XS }) {
        this.compactButton('关闭', device.online, device.primaryValue === 0, (): void => { this.control(device, 'position', 0); })
        this.compactButton('停止', device.online, false, (): void => { this.control(device, 'stop'); })
        this.compactButton('打开', device.online, device.primaryValue === 100, (): void => { this.control(device, 'position', 100); })
      }
    } else if (device.type === DeviceType.AC) {
      Row({ space: AppSpace.XS }) {
        this.compactButton('−', device.online && (device.primaryValue ?? 24) > 16, false,
          (): void => { this.control(device, 'set_temperature', Math.max(16, (device.primaryValue ?? 24) - 1)); })
        Text(`${device.primaryValue ?? 24}°C`).fontSize(AppFont.SIZE_FOOTNOTE).fontWeight(FontWeight.Bold)
          .fontColor(AppColors.textSecondary(this.isDarkTheme)).width(52).textAlign(TextAlign.Center)
        this.compactButton('+', device.online && 30 > (device.primaryValue ?? 24), false,
          (): void => { this.control(device, 'set_temperature', Math.min(30, (device.primaryValue ?? 24) + 1)); })
      }
    } else if (device.type === DeviceType.DOOR) {
      this.compactButton(device.isOn ? '关闭' : '打开', device.online, device.isOn, (): void => { this.toggle(device); })
    } else {
      Toggle({ type: ToggleType.Switch, isOn: device.online && device.isOn })
        .selectedColor(AppColors.primary(this.isDarkTheme))
        .enabled(device.online && this.busyDeviceId.length === 0)
        .opacity(device.online ? 1 : 0.4)
        .onChange((): void => { this.toggle(device); })
    }
  }

  @Builder
  deviceRow(device: Device, isLast: boolean) {
    Column() {
      Row({ space: AppSpace.MD }) {
        Stack() {
          Column().width(38).height(38).border({ width: 1, color: device.online ? AppColors.primary(this.isDarkTheme) : AppColors.OFFLINE })
          SymbolGlyph(device.icon).fontSize(20).fontColor([device.online ? AppColors.primary(this.isDarkTheme) : AppColors.OFFLINE])
        }.width(40).height(40).alignContent(Alignment.Center)
        Column({ space: 3 }) {
          Row({ space: 6 }) {
            Text(device.name).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold).fontColor(AppColors.textPrimary(this.isDarkTheme))
          }
          Text(this.busyDeviceId === device.id ? '正在执行...' : this.statusText(device))
            .fontSize(AppFont.SIZE_FOOTNOTE)
            .fontColor(device.online ? AppColors.textTertiary(this.isDarkTheme) : AppColors.OFFLINE)
        }.alignItems(HorizontalAlign.Start).layoutWeight(1)
        if (!this.extendedControl(device)) {
          this.deviceControl(device)
        }
      }.width('100%').height(64).alignItems(VerticalAlign.Center)
      if (this.extendedControl(device)) {
        Row() {
          Blank().width(52)
          this.deviceControl(device)
        }.width('100%').padding({ bottom: AppSpace.MD })
      }
      if (!isLast) Divider().strokeWidth(1).color(AppColors.hairline(this.isDarkTheme)).margin({ left: 52 })
    }.width('100%')
  }

  @Builder
  sensorRow(sensor: Sensor, isLast: boolean) {
    Row({ space: AppSpace.MD }) {
      SymbolGlyph(sensor.icon).fontSize(19)
        .fontColor([sensor.isAlert ? AppColors.DANGER : sensor.online ? AppColors.primary(this.isDarkTheme) : AppColors.OFFLINE])
        .width(32)
      Column({ space: 3 }) {
        Text(sensor.name).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
          .fontColor(AppColors.textPrimary(this.isDarkTheme))
        Text(sensor.online ? '已同步' : '设备离线').fontSize(AppFont.SIZE_FOOTNOTE)
          .fontColor(AppColors.textTertiary(this.isDarkTheme))
      }.alignItems(HorizontalAlign.Start).layoutWeight(1)
      Text(this.sensorValue(sensor)).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
        .fontColor(sensor.isAlert ? AppColors.DANGER : AppColors.textPrimary(this.isDarkTheme))
    }.width('100%').height(AppSpace.DEVICE_ROW_HEIGHT)
      .border({ width: { bottom: isLast ? 0 : 1 }, color: AppColors.hairline(this.isDarkTheme) })
  }

  @Builder
  doorPasswordDialog() {
    Column({ space: AppSpace.MD }) {
      Row() {
        Text('打开门禁').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
          .fontColor(AppColors.textPrimary(this.isDarkTheme))
        Blank()
        SymbolGlyph($r('sys.symbol.xmark')).fontSize(18).fontColor([AppColors.textSecondary(this.isDarkTheme)])
          .onClick((): void => { this.doorDialogVisible = false; this.doorPassword = ''; })
      }.width('100%')
      TextInput({ text: this.doorPassword, placeholder: '门禁密码' })
        .type(InputType.Password).width('100%').height(48)
        .fontColor(AppColors.textPrimary(this.isDarkTheme))
        .placeholderColor(AppColors.textTertiary(this.isDarkTheme))
        .backgroundColor(AppColors.input(this.isDarkTheme))
        .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
        .padding({ left: AppSpace.MD, right: AppSpace.MD })
        .onChange((value: string): void => { this.doorPassword = value; })
      Button('确认打开')
        .width('100%').height(46).fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold)
        .fontColor(AppColors.onPrimary(this.isDarkTheme))
        .backgroundColor(AppColors.primary(this.isDarkTheme))
        .onClick((): void => { this.submitDoorPassword(); })
    }
    .width('86%')
    .padding(AppSpace.LG)
    .backgroundColor(AppColors.card(this.isDarkTheme))
    .border({ width: 1, color: AppColors.primary(this.isDarkTheme) })
  }

  build() {
    Stack() {
      GeometricBackdrop()
      Scroll() {
      Column({ space: AppSpace.LG }) {
          if (this.isOfflineMode) {
            Row({ space: AppSpace.SM }) {
              SymbolGlyph($r('sys.symbol.wifi_slash')).fontSize(18).fontColor([AppColors.WARNING])
              Text('远程服务不可用，设备状态暂未同步').fontSize(AppFont.SIZE_FOOTNOTE)
                .fontColor(AppColors.textSecondary(this.isDarkTheme))
            }.width('100%').padding(AppSpace.MD)
              .backgroundColor(AppColors.card(this.isDarkTheme))
              .border({ width: 1, color: AppColors.WARNING })
          }
          Text('区域').fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.textPrimary(this.isDarkTheme)).width('100%')
          Grid() {
            ForEach(this.areas, (area: AreaDefinition) => { GridItem() { this.areaItem(area) } }, (area: AreaDefinition) => area.key)
          }.columnsTemplate('1fr 1fr').columnsGap(AppSpace.SM).rowsGap(AppSpace.SM).width('100%')

          if (this.actionMessage || this.loadMessage) {
            Row({ space: AppSpace.SM }) {
              SymbolGlyph(this.actionError || this.loadMessage ? $r('sys.symbol.exclamationmark_circle_fill') : $r('sys.symbol.checkmark_circle_fill'))
                .fontSize(18).fontColor([this.actionError || this.loadMessage ? AppColors.DANGER : AppColors.primary(this.isDarkTheme)])
              Text(this.loadMessage || this.actionMessage).fontSize(AppFont.SIZE_FOOTNOTE)
                .fontColor(this.actionError || this.loadMessage ? AppColors.DANGER : AppColors.textSecondary(this.isDarkTheme))
            }.width('100%').padding(AppSpace.MD).backgroundColor(AppColors.card(this.isDarkTheme))
              .border({ width: 1, color: this.actionError || this.loadMessage ? AppColors.DANGER : AppColors.hairline(this.isDarkTheme) })
          }

          Row() {
            Text('设备').fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
              .fontColor(AppColors.textPrimary(this.isDarkTheme)).layoutWeight(1)
            Stack() {
              SymbolGlyph($r('sys.symbol.arrow_counterclockwise')).fontSize(19)
                .fontColor([AppColors.primary(this.isDarkTheme)])
            }.width(40).height(40).enabled(!this.loading).opacity(this.loading ? 0.45 : 1)
              .accessibilityText('刷新设备状态').onClick((): void => { this.load(); })
          }.width('100%').alignItems(VerticalAlign.Center)
          if (!this.loading && this.devices.length === 0 && !this.loadMessage) {
            Text('暂无设备').width('100%').padding(AppSpace.LG).textAlign(TextAlign.Center)
              .fontSize(AppFont.SIZE_BODY).fontColor(AppColors.textSecondary(this.isDarkTheme))
              .backgroundColor(AppColors.card(this.isDarkTheme))
              .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
          }
          ForEach(this.rooms, (room: string, roomIndex: number) => {
            if (this.devicesInRoom(room).length > 0 || this.sensorsInRoom(room).length > 0) {
              Column({ space: AppSpace.SM }) {
                Text(room).fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
                  .fontColor(AppColors.textSecondary(this.isDarkTheme)).width('100%')
                if (this.devicesInRoom(room).length > 0) {
                  Column() {
                    ForEach(this.devicesInRoom(room), (device: Device, index: number) => {
                      this.deviceRow(device, index === this.devicesInRoom(room).length - 1)
                    }, (device: Device) => `${device.id}_${device.online}_${device.isOn}_${device.primaryValue}_${device.mode || ''}`)
                  }.width('100%').padding({ left: AppSpace.BASE, right: AppSpace.BASE })
                    .backgroundColor(AppColors.card(this.isDarkTheme))
                    .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
                }
                if (this.sensorsInRoom(room).length > 0) {
                  Column() {
                    ForEach(this.sensorsInRoom(room), (sensor: Sensor, index: number) => {
                      this.sensorRow(sensor, index === this.sensorsInRoom(room).length - 1)
                    }, (sensor: Sensor) => sensor.id)
                  }.width('100%').padding({ left: AppSpace.BASE, right: AppSpace.BASE })
                    .backgroundColor(AppColors.group(this.isDarkTheme))
                    .border({ width: 1, color: AppColors.hairline(this.isDarkTheme) })
                }
              }.width('100%').alignItems(HorizontalAlign.Start)
            }
          }, (room: string) => room)
      }
      .width('100%')
      .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: AppSpace.XL, bottom: AppSpace.XL })
      .alignItems(HorizontalAlign.Start)
      }.width('100%').height('100%').scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)
      if (this.doorDialogVisible) {
        Column() { this.doorPasswordDialog() }
          .width('100%').height('100%').justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
          .backgroundColor('#99000000')
      }
    }.width('100%').height('100%').backgroundColor(AppColors.page(this.isDarkTheme))
  }
}
