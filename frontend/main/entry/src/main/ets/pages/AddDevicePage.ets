/**
 * 添加设备页 · 经典鸿蒙浅色
 * 选择类型 → 填名称 → 选房间 → 确认添加
 */
import { AppCard } from '../components/AppCard';
import { AppIcon } from '../components/AppIcon';
import { DeviceApi } from '../api/deviceApi';
import { GatewayApi } from '../api/gatewayApi';
import { Device, DeviceType, DeviceStatus } from '../api/types';
import { AppColors } from '../theme/Colors';
import { AppSpace } from '../theme/Spacing';
import { AppFont } from '../theme/Typography';
import { router, promptAction } from '@kit.ArkUI';

interface TypeOption {
  type: DeviceType;
  label: string;
  icon: Resource;
  color: string;
  bg: string;
  defaultVal: number;
}

interface ScanTypeOption {
  key: string;
  label: string;
  icon: Resource;
  color: string;
  bg: string;
}

@Entry
@Component
struct AddDevicePage {
  private readonly typeOptions: TypeOption[] = [
    { type: DeviceType.FAN, label: '风扇', icon: $r('sys.symbol.fan_fill_1'), color: AppColors.DEVICE_FAN, bg: AppColors.DEVICE_FAN_BG, defaultVal: 1 },
    { type: DeviceType.AC, label: '空调', icon: $r('sys.symbol.air_fill'), color: AppColors.DEVICE_AC, bg: AppColors.DEVICE_AC_BG, defaultVal: 24 },
    { type: DeviceType.DOOR, label: '门禁', icon: $r('sys.symbol.doors_and_windows_closed'), color: AppColors.DEVICE_DOOR, bg: AppColors.DEVICE_DOOR_BG, defaultVal: 0 },
    { type: DeviceType.LIGHT, label: '灯光', icon: $r('sys.symbol.lightbulb'), color: AppColors.DEVICE_LIGHT, bg: AppColors.DEVICE_LIGHT_BG, defaultVal: 60 }
  ];
  private readonly rooms: string[] = ['客厅', '主卧', '次卧', '厨房', '卫生间', '玄关', '书房', '车库'];
  private readonly manufacturers: string[] = ['自研', '米家兼容', '涂鸦兼容', 'Home Assistant', '其他'];
  private readonly devBoards: string[] = ['ESP32', 'ESP32-S3', 'ESP8266', 'Hi3861', 'BearPi', '树莓派', 'Arduino', '自定义网关'];
  private readonly scanTypeOptions: ScanTypeOption[] = [
    { key: 'light', label: '灯光', icon: $r('sys.symbol.lightbulb'), color: AppColors.DEVICE_LIGHT, bg: AppColors.DEVICE_LIGHT_BG },
    { key: 'fan', label: '风扇', icon: $r('sys.symbol.fan_fill_1'), color: AppColors.DEVICE_FAN, bg: AppColors.DEVICE_FAN_BG },
    { key: 'ac', label: '空调', icon: $r('sys.symbol.air_fill'), color: AppColors.DEVICE_AC, bg: AppColors.DEVICE_AC_BG },
    { key: 'curtain', label: '窗帘', icon: $r('sys.symbol.doors_and_windows_closed'), color: AppColors.PRIMARY, bg: AppColors.PRIMARY_BG },
    { key: 'switch', label: '智能开关', icon: $r('sys.symbol.lightbulb'), color: AppColors.PRIMARY, bg: AppColors.PRIMARY_BG },
    { key: 'socket', label: '智能插座', icon: $r('sys.symbol.bolt_fill'), color: AppColors.DEVICE_AC, bg: AppColors.DEVICE_AC_BG },
    { key: 'sensor', label: '环境传感器', icon: $r('sys.symbol.thermometer'), color: AppColors.SUCCESS, bg: AppColors.PRIMARY_BG },
    { key: 'camera', label: '摄像头', icon: $r('sys.symbol.camera_fill'), color: AppColors.WARNING, bg: AppColors.DEVICE_CAMERA_BG }
  ];
  @State selectedType: DeviceType = DeviceType.FAN;
  @State selectedScanType: string = 'light';
  @State deviceName: string = '';
  @State selectedRoom: string = '客厅';
  @State selectedManufacturer: string = '自研';
  @State selectedBoard: string = 'ESP32';
  @State adding: boolean = false;
  @State discovering: boolean = false;
  @State addError: string = '';
  @State scanResult: Device | undefined = undefined;
  @State scanStage: string = '';
  @State protocolMatched: boolean = false;
  @State protocolCount: number = 0;

  private get canSubmit(): boolean {
    return this.deviceName.trim().length > 0 && !this.adding;
  }

  private safeCurrentOption(): TypeOption {
    const options = this.typeOptions || [];
    const found = options.find((o: TypeOption) => o.type === this.selectedType);
    return found || {
      type: DeviceType.FAN, label: '风扇', icon: $r('sys.symbol.fan_fill_1'),
      color: AppColors.DEVICE_FAN, bg: AppColors.DEVICE_FAN_BG, defaultVal: 1
    };
  }

  async submit(): Promise<void> {
    if (!this.canSubmit) return;
    this.adding = true;
    this.addError = '';
    try {
      const id = DeviceApi.genId(this.selectedType);
      const opt = this.safeCurrentOption();
      const device: Device = {
        id: id, name: this.deviceName.trim(), type: this.selectedType,
        status: DeviceStatus.ONLINE, room: this.selectedRoom, icon: opt.icon,
        primaryValue: opt.defaultVal, isOn: false
      };
      const ok = await DeviceApi.addDevice(device);
      if (!ok) throw new Error('设备端未确认注册');
      promptAction.showToast({ message: `已添加「${device.name}」`, duration: 2000 });
      router.back();
    } catch (e) {
      this.addError = '添加失败，请检查设备端连接后重试。';
      promptAction.showToast({ message: this.addError, duration: 2200 });
    } finally {
      this.adding = false;
    }
  }

  private selectedScanOption(): ScanTypeOption {
    const found = this.scanTypeOptions.find((item: ScanTypeOption) => item.key === this.selectedScanType);
    return found || this.scanTypeOptions[0];
  }

  async scanDevice(): Promise<void> {
    if (this.discovering) return;
    this.discovering = true;
    this.addError = '';
    this.scanResult = undefined;
    this.protocolMatched = false;
    this.scanStage = '正在扫描局域网设备…';
    try {
      const device = await DeviceApi.scanCustomDevice(this.selectedScanType, this.deviceName.trim(), this.selectedRoom, false,
        this.selectedManufacturer, this.selectedBoard);
      if (!device) throw new Error('未发现设备');
      this.scanResult = device;
      this.scanStage = '设备在线，正在匹配协议…';
      const catalog = await GatewayApi.getProtocolCatalog();
      this.protocolCount = catalog.protocols.length;
      await new Promise<void>((resolve: () => void) => setTimeout(resolve, 1600));
      this.protocolMatched = true;
      this.scanStage = '协议匹配成功，请确认接入';
    } catch (e) {
      this.addError = '暂未发现匹配设备，请确认设备已上电并与主控在同一局域网。';
      promptAction.showToast({ message: this.addError, duration: 2400 });
    } finally {
      this.discovering = false;
    }
  }

  async confirmScanResult(): Promise<void> {
    const result = this.scanResult;
    if (!result || !this.protocolMatched || this.discovering) return;
    this.discovering = true;
    const ok = await DeviceApi.registerScannedDevice(result.id);
    this.discovering = false;
    if (!ok) {
      this.addError = '接入失败，请重新扫描后再试。';
      return;
    }
    promptAction.showToast({ message: `已接入「${result.name}」`, duration: 2200 });
    router.back();
  }

  build() {
    Column() {
      // 顶部返回栏
      Row() {
        SymbolGlyph($r('sys.symbol.chevron_left'))
          .fontSize(24)
          .fontColor([AppColors.TEXT_PRIMARY])
          .onClick(() => router.back())
        Text('添加设备')
          .fontSize(AppFont.SIZE_TITLE)
          .fontColor(AppColors.TEXT_PRIMARY)
          .fontWeight(FontWeight.Bold)
          .layoutWeight(1)
          .textAlign(TextAlign.Center)
        Column().width(24)
      }
      .width('100%')
      .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: 48, bottom: AppSpace.MD })

      Scroll() {
        Column({ space: AppSpace.BASE }) {
          // ===== 1. 设备类型选择 =====
          Column({ space: AppSpace.SM }) {
            Text('选择扫描类型')
              .fontSize(AppFont.SIZE_BODY_LG)
              .fontColor(AppColors.TEXT_PRIMARY)
              .fontWeight(FontWeight.Medium)
            Grid() {
              ForEach(this.scanTypeOptions, (opt: ScanTypeOption) => {
                GridItem() {
                  Column({ space: AppSpace.SM }) {
                    Column() {
                      AppIcon({ iconRes: opt.icon, iconSize: 28, iconColor: opt.color })
                    }
                    .width(56).height(56)
                    .borderRadius(28)
                    .backgroundColor(this.selectedScanType === opt.key ? opt.bg : AppColors.BG_INPUT)
                    .justifyContent(FlexAlign.Center)
                    .alignItems(HorizontalAlign.Center)
                    Text(opt.label)
                      .fontSize(AppFont.SIZE_FOOTNOTE)
                      .fontColor(this.selectedScanType === opt.key ? opt.color : AppColors.TEXT_TERTIARY)
                      .fontWeight(this.selectedScanType === opt.key ? FontWeight.Medium : FontWeight.Regular)
                  }
                  .padding(AppSpace.SM)
                  .borderRadius(AppSpace.RADIUS_CARD)
                  .border(this.selectedScanType === opt.key ? { width: 1.5, color: opt.color } : { width: 0, color: '#00000000' })
                  .backgroundColor(this.selectedScanType === opt.key ? `${opt.color}0A` : AppColors.BG_CARD)
                  .alignItems(HorizontalAlign.Center)
                  .onClick(() => { this.selectedScanType = opt.key; })
                }
              }, (opt: ScanTypeOption) => opt.key)
            }
            .columnsTemplate('1fr 1fr 1fr 1fr')
            .columnsGap(AppSpace.SM)
            .rowsGap(AppSpace.SM)
            .width('100%')
            .height(220)
          }
          .width('100%')
          .alignItems(HorizontalAlign.Start)

          Column({ space: AppSpace.SM }) {
            Text('设备样板与厂家').fontSize(AppFont.SIZE_BODY_LG).fontColor(AppColors.TEXT_PRIMARY).fontWeight(FontWeight.Medium)
            Text('厂家').fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.TEXT_TERTIARY)
            Flex({ wrap: FlexWrap.Wrap }) {
              ForEach(this.manufacturers, (item: string) => {
                Text(item).fontSize(AppFont.SIZE_FOOTNOTE)
                  .fontColor(this.selectedManufacturer === item ? AppColors.PRIMARY : AppColors.TEXT_SECONDARY)
                  .padding({ left: 10, right: 10, top: 6, bottom: 6 }).margin({ right: 6, bottom: 6 })
                  .backgroundColor(this.selectedManufacturer === item ? AppColors.PRIMARY_BG : AppColors.BG_INPUT)
                  .border({ width: 1, color: this.selectedManufacturer === item ? AppColors.PRIMARY : AppColors.DIVIDER })
                  .borderRadius(3).onClick(() => { this.selectedManufacturer = item; })
              }, (item: string) => item)
            }.width('100%')
            Text('开发板').fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.TEXT_TERTIARY)
            Flex({ wrap: FlexWrap.Wrap }) {
              ForEach(this.devBoards, (item: string) => {
                Text(item).fontSize(AppFont.SIZE_FOOTNOTE)
                  .fontColor(this.selectedBoard === item ? AppColors.PRIMARY : AppColors.TEXT_SECONDARY)
                  .padding({ left: 10, right: 10, top: 6, bottom: 6 }).margin({ right: 6, bottom: 6 })
                  .backgroundColor(this.selectedBoard === item ? AppColors.PRIMARY_BG : AppColors.BG_INPUT)
                  .border({ width: 1, color: this.selectedBoard === item ? AppColors.PRIMARY : AppColors.DIVIDER })
                  .borderRadius(3).onClick(() => { this.selectedBoard = item; })
              }, (item: string) => item)
            }.width('100%')
          }.width('100%').alignItems(HorizontalAlign.Start)

          // ===== 2. 设备名称 =====
          Column({ space: AppSpace.SM }) {
            Text('设备名称')
              .fontSize(AppFont.SIZE_BODY_LG)
              .fontColor(AppColors.TEXT_PRIMARY)
              .fontWeight(FontWeight.Medium)
            TextInput({ placeholder: `可选，例如：客厅${this.selectedScanOption().label}`, text: this.deviceName })
              .height(48)
              .fontSize(AppFont.SIZE_BODY)
              .fontColor(AppColors.TEXT_PRIMARY)
              .placeholderColor(AppColors.TEXT_TERTIARY)
              .borderRadius(AppSpace.RADIUS_BASE)
              .backgroundColor(AppColors.BG_INPUT)
              .padding({ left: AppSpace.BASE, right: AppSpace.BASE })
              .onChange((v: string) => { this.deviceName = v; })
          }
          .width('100%')
          .alignItems(HorizontalAlign.Start)

          // ===== 3. 房间选择 =====
          Column({ space: AppSpace.SM }) {
            Text('安装位置')
              .fontSize(AppFont.SIZE_BODY_LG)
              .fontColor(AppColors.TEXT_PRIMARY)
              .fontWeight(FontWeight.Medium)
            Flex({ wrap: FlexWrap.Wrap }) {
              ForEach(this.rooms, (room: string) => {
                Text(room)
                  .fontSize(AppFont.SIZE_FOOTNOTE)
                  .fontColor(this.selectedRoom === room ? AppColors.PRIMARY : AppColors.TEXT_SECONDARY)
                  .padding({ left: AppSpace.BASE, right: AppSpace.BASE, top: AppSpace.SM, bottom: AppSpace.SM })
                  .margin({ right: AppSpace.SM, bottom: AppSpace.SM })
                  .borderRadius(AppSpace.RADIUS_PILL)
                  .backgroundColor(this.selectedRoom === room ? AppColors.PRIMARY_BG : AppColors.BG_INPUT)
                  .fontWeight(this.selectedRoom === room ? FontWeight.Medium : FontWeight.Regular)
                  .onClick(() => { this.selectedRoom = room; })
              }, (room: string) => room)
            }
            .width('100%')
          }
          .width('100%')
          .alignItems(HorizontalAlign.Start)

          // ===== 4. 预览 =====
          AppCard({ innerPadding: AppSpace.BASE }) {
            Row({ space: AppSpace.MD }) {
              Column() {
                AppIcon({ iconRes: this.selectedScanOption().icon, iconSize: 24, iconColor: this.selectedScanOption().color })
              }
              .width(44).height(44)
              .borderRadius(22)
              .backgroundColor(this.selectedScanOption().bg)
              .justifyContent(FlexAlign.Center)
              .alignItems(HorizontalAlign.Center)
              Column({ space: 2 }) {
                Text(this.deviceName.trim() || '设备名称')
                  .fontSize(AppFont.SIZE_BODY)
                  .fontColor(AppColors.TEXT_PRIMARY)
                  .fontWeight(FontWeight.Medium)
                Text(`${this.selectedScanOption().label} · ${this.selectedRoom}`)
                  .fontSize(AppFont.SIZE_FOOTNOTE)
                  .fontColor(AppColors.TEXT_TERTIARY)
                Text(`${this.selectedManufacturer} · ${this.selectedBoard}`)
                  .fontSize(AppFont.SIZE_FOOTNOTE)
                  .fontColor(AppColors.TEXT_TERTIARY)
              }
              .alignItems(HorizontalAlign.Start)
              .layoutWeight(1)
            }
            .width('100%')
            .alignItems(VerticalAlign.Center)
          }

          if (this.addError.length > 0) {
            Text(this.addError).fontSize(14).fontColor('#FF6B6B').width('100%')
          }

          Text('仅扫描当前局域网内的匹配设备；当前发现源支持灯光设备，其他类型接入相应适配器后即可使用。')
            .fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.TEXT_TERTIARY).width('100%')

          if (this.scanResult !== undefined) {
            AppCard({ innerPadding: AppSpace.BASE }) {
              Column({ space: 8 }) {
                Row({ space: 8 }) {
                  AppIcon({ iconRes: this.selectedScanOption().icon, iconSize: 24, iconColor: this.selectedScanOption().color })
                  Column({ space: 2 }) {
                    Text('扫描结果').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold).fontColor(AppColors.TEXT_PRIMARY)
                    Text(this.scanResult.name).fontSize(AppFont.SIZE_BODY).fontColor(AppColors.TEXT_SECONDARY)
                  }.layoutWeight(1).alignItems(HorizontalAlign.Start)
                  Text(this.protocolMatched ? '匹配成功' : '匹配中')
                    .fontSize(AppFont.SIZE_FOOTNOTE).fontColor(this.protocolMatched ? AppColors.SUCCESS : AppColors.TEXT_TERTIARY)
                }.width('100%')
                Row({ space: 8 }) {
                  SymbolGlyph($r('sys.symbol.gearshape_fill'))
                    .fontSize(18).fontColor([this.protocolMatched ? AppColors.SUCCESS : AppColors.PRIMARY])
                  Text('协议库').fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.PRIMARY)
                  Text(this.scanStage).fontSize(AppFont.SIZE_BODY).fontColor(AppColors.TEXT_SECONDARY).layoutWeight(1)
                }.width('100%')
                Text(`协议库：HTTP · HTTPS · MQTT · WebSocket · CoAP（已读取 ${this.protocolCount} 项）`)
                  .fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.TEXT_TERTIARY).width('100%').maxLines(2)
                Button(this.discovering ? '接入中…' : '确认接入设备')
                  .width('100%').height(44).fontSize(AppFont.SIZE_BODY)
                  .fontColor(this.protocolMatched ? AppColors.TEXT_INVERSE : AppColors.TEXT_TERTIARY)
                  .backgroundColor(this.protocolMatched ? AppColors.PRIMARY : AppColors.BG_INPUT)
                  .borderRadius(AppSpace.RADIUS_BASE).enabled(this.protocolMatched && !this.discovering)
                  .onClick(() => this.confirmScanResult())
              }.width('100%').alignItems(HorizontalAlign.Start)
            }
          }

          Column().height(AppSpace.XXL)
        }
        .width('100%')
        .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, bottom: 100 })
      }
      .layoutWeight(1)
      .scrollBar(BarState.Off)
      .edgeEffect(EdgeEffect.Spring)

      // 底部扫描按钮
      Row() {
        Button(this.discovering ? '正在探测在线设备…' : '开始扫描')
          .width('100%')
          .height(48)
          .fontSize(AppFont.SIZE_BODY_LG)
          .fontColor(this.discovering ? AppColors.TEXT_TERTIARY : AppColors.TEXT_INVERSE)
          .backgroundColor(this.discovering ? AppColors.BG_INPUT : AppColors.PRIMARY)
          .borderRadius(AppSpace.RADIUS_BASE)
          .enabled(!this.discovering)
          .onClick(() => this.scanDevice())
      }
      .width('100%')
      .padding({ left: AppSpace.PAGE_PADDING, right: AppSpace.PAGE_PADDING, top: AppSpace.SM, bottom: AppSpace.LG })
      .backgroundColor(AppColors.BG_CARD)
    }
    .width('100%')
    .height('100%')
    .backgroundColor(AppColors.BG_PAGE)
  }
}
