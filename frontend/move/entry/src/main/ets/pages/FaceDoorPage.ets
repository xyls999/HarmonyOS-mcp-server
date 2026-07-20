import { FaceCamera, FaceCameraCallbacks } from '../api/faceCamera';
import { FaceDoorApi, FaceDoorResult, FaceDoorStatusResult, FaceHealthResult } from '../api/faceDoorApi';
import { AppContext } from '../api/appContext';
import { AppColors } from '../theme/Colors';
import { AppFont } from '../theme/Typography';
import { AppSpace } from '../theme/Spacing';

@Component
export struct FaceDoorPage {
  mode: number = 0;
  onClose?: () => void;
  @State managing: boolean = false;
  @State cameraVisible: boolean = false;
  @State cameraReady: boolean = false;
  @State processing: boolean = false;
  @State operation: string = 'open';
  @State statusText: string = '';
  @State resultState: string = 'idle';
  @State personName: string = '';
  @State retryCount: number = 0;
  @State scanY: number = -230;
  @State faces: string[] = [];
  @State health: FaceHealthResult | null = null;
  @State doorStatus: FaceDoorStatusResult | null = null;
  @State listLoading: boolean = false;
  @State deleteTarget: string = '';
  private controller: XComponentController = new XComponentController();
  private faceCamera: FaceCamera = new FaceCamera();
  private timers: number[] = [];

  aboutToAppear(): void {
    this.managing = this.mode === 1;
    if (this.managing) this.loadManagement();
    else this.startScan('open');
  }

  aboutToDisappear(): void {
    this.clearTimers();
    this.faceCamera.release();
  }

  private clearTimers(): void {
    for (const timer of this.timers) clearTimeout(timer);
    this.timers = [];
  }

  private later(delay: number, action: () => void): void {
    this.timers.push(setTimeout(action, delay));
  }

  private startScan(operation: string): void {
    this.clearTimers();
    this.operation = operation;
    this.resultState = 'idle';
    this.statusText = operation === 'open' ? '正在启用前置摄像头' : '输入姓名后开始录入';
    this.retryCount = 0;
    this.cameraReady = false;
    this.processing = false;
    this.cameraVisible = true;
  }

  private async initializeCamera(): Promise<void> {
    const context = AppContext.abilityContext;
    if (!context) {
      this.showFailure('无法获取相机运行环境');
      return;
    }
    const surfaceId = this.controller.getXComponentSurfaceId();
    const callbacks: FaceCameraCallbacks = {
      onReady: (): void => {
        this.cameraReady = true;
        this.statusText = this.operation === 'open' ? '请正对摄像头' : '输入姓名后开始录入';
        this.animateScanner();
        if (this.operation === 'open') this.later(1300, (): void => { this.capture(); });
      },
      onPhoto: (data: ArrayBuffer): void => { this.handlePhoto(data); },
      onError: (message: string): void => { this.showFailure(message); }
    };
    await this.faceCamera.start(context, surfaceId, callbacks);
  }

  private animateScanner(): void {
    this.scanY = -230;
    this.getUIContext().animateTo({ duration: 2100, curve: Curve.Linear, iterations: -1 }, (): void => {
      this.scanY = 230;
    });
  }

  private async capture(): Promise<void> {
    if (!this.cameraReady || this.processing) return;
    if (this.operation === 'register' && !this.personName.trim()) {
      this.statusText = '请输入姓名';
      return;
    }
    this.processing = true;
    this.statusText = '正在拍摄';
    await this.faceCamera.capture();
  }

  private async handlePhoto(data: ArrayBuffer): Promise<void> {
    this.statusText = this.operation === 'open' ? '正在识别' : '正在保存';
    if (this.operation === 'register') {
      await this.registerFace(data);
      return;
    }
    const result = await FaceDoorApi.openDoor(data);
    this.processing = false;
    if (result.success && result.recognized && result.doorState === 'open') {
      this.resultState = 'success';
      this.statusText = result.name ? `${result.name}，门已打开` : '门已打开';
      return;
    }
    if (result.stage === 'detection' && this.retryCount < 2) {
      this.retryCount += 1;
      this.statusText = '未检测到人脸，请正对摄像头';
      this.later(2600, (): void => { this.capture(); });
      return;
    }
    this.resultState = result.stage === 'recognition' ? 'denied' : 'error';
    this.statusText = this.resultMessage(result);
  }

  private resultMessage(result: FaceDoorResult): string {
    if (result.stage === 'detection') return '未检测到人脸，请正对摄像头';
    if (result.stage === 'recognition') return '人脸未识别';
    if (result.stage === 'door' && result.recognized) return '开门失败，请联系管理员';
    return result.error || '门禁请求失败';
  }

  private async registerFace(data: ArrayBuffer): Promise<void> {
    const name = this.personName.trim();
    const result = await FaceDoorApi.register(name, data);
    this.processing = false;
    if (!result.success) {
      this.resultState = 'error';
      this.statusText = result.error || '人脸录入失败';
      return;
    }
    const reload = await FaceDoorApi.reload();
    if (!reload.success) {
      this.resultState = 'error';
      this.statusText = reload.error || '人脸已保存，刷新数据库失败';
      return;
    }
    this.resultState = 'success';
    this.statusText = `${name} 已录入`;
    this.later(1100, (): void => { this.finishRegister(); });
  }

  private async finishRegister(): Promise<void> {
    await this.stopCamera();
    this.personName = '';
    this.managing = true;
    await this.loadManagement();
  }

  private showFailure(message: string): void {
    this.processing = false;
    this.resultState = 'error';
    this.statusText = message;
  }

  private async stopCamera(): Promise<void> {
    this.cameraVisible = false;
    this.cameraReady = false;
    await this.faceCamera.release();
  }

  private async close(): Promise<void> {
    this.clearTimers();
    await this.stopCamera();
    if (this.onClose) this.onClose();
  }

  private async showManagement(): Promise<void> {
    await this.stopCamera();
    this.managing = true;
    await this.loadManagement();
  }

  private async loadManagement(): Promise<void> {
    if (this.listLoading) return;
    this.listLoading = true;
    const list = await FaceDoorApi.listFaces();
    this.faces = list.faces;
    this.health = await FaceDoorApi.health();
    this.doorStatus = await FaceDoorApi.doorStatus();
    this.statusText = list.success ? '' : list.error;
    this.listLoading = false;
  }

  private async deleteFace(name: string): Promise<void> {
    if (this.listLoading) return;
    this.listLoading = true;
    const result = await FaceDoorApi.deleteFace(name);
    if (result.success) {
      await FaceDoorApi.reload();
      this.deleteTarget = '';
      const list = await FaceDoorApi.listFaces();
      this.faces = list.faces;
      this.statusText = `${name} 已删除`;
    } else {
      this.statusText = result.error || '删除失败';
    }
    this.listLoading = false;
  }

  private accentColor(): string {
    if (this.resultState === 'success') return AppColors.SUCCESS;
    if (this.resultState === 'denied' || this.resultState === 'error') return AppColors.DANGER;
    return AppColors.SIGNAL_CYAN;
  }

  @Builder
  header(title: string) {
    Row() {
      Stack({ alignContent: Alignment.Center }) {
        Column().width(42).height(42).backgroundColor(AppColors.MONO_SURFACE)
          .border({ width: 1, color: AppColors.MONO_BORDER })
        SymbolGlyph($r('sys.symbol.chevron_left')).fontSize(21).fontColor([AppColors.MONO_WHITE])
      }.width(42).height(42).accessibilityText('返回').onClick((): void => { this.close(); })
      Text(title).fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
        .fontColor(AppColors.MONO_WHITE).margin({ left: AppSpace.BASE })
      Blank()
      if (!this.managing && this.mode === 1) {
        Text('管理').fontSize(AppFont.SIZE_BODY).fontWeight(FontWeight.Bold).fontColor(AppColors.SIGNAL_CYAN)
          .height(42).padding({ left: AppSpace.MD, right: AppSpace.MD })
          .onClick((): void => { this.showManagement(); })
      }
    }.width('100%').height(66).padding({ left: AppSpace.BASE, right: AppSpace.BASE })
      .backgroundColor(AppColors.MONO_BLACK)
  }

  @Builder
  cameraView() {
    Column() {
      this.header(this.operation === 'open' ? '刷脸开门' : '录入人脸')
      Stack({ alignContent: Alignment.Center }) {
        if (this.cameraVisible) {
          XComponent({ id: 'faceDoorPreview', type: XComponentType.SURFACE, controller: this.controller })
            .width('100%').height('100%').scale({ x: -1, y: 1 })
            .onLoad((): void => { this.initializeCamera(); })
        }
        Column().width('100%').height('100%')
          .linearGradient({ angle: 180, colors: [[AppColors.MONO_BLACK, 0], ['#00101010', 0.5], [AppColors.MONO_BLACK, 1]] })
          .enabled(false)
        Column().width(236).height(300).border({ width: 1, color: this.accentColor() })
          .enabled(false)
        Column().width(210).height(1).backgroundColor(this.accentColor()).opacity(0.82)
          .translate({ y: this.scanY }).enabled(false)
        if (!this.cameraReady && this.resultState === 'idle') {
          LoadingProgress().width(38).height(38).color(AppColors.SIGNAL_CYAN)
        }
        if (this.resultState === 'success') {
          Stack({ alignContent: Alignment.Center }) {
            Column().width(88).height(88).backgroundColor('#D949D58B')
            SymbolGlyph($r('sys.symbol.checkmark')).fontSize(42).fontColor([AppColors.MONO_BLACK])
          }.width(88).height(88)
        } else if (this.resultState === 'denied' || this.resultState === 'error') {
          Stack({ alignContent: Alignment.Center }) {
            Column().width(88).height(88).backgroundColor('#E6FF6B67')
            SymbolGlyph($r('sys.symbol.xmark')).fontSize(38).fontColor([AppColors.MONO_BLACK])
          }.width(88).height(88)
        }
      }.layoutWeight(1).width('100%').clip(true)

      Column({ space: AppSpace.MD }) {
        Text(this.statusText).fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
          .fontColor(this.accentColor()).textAlign(TextAlign.Center).width('100%').maxLines(2)
        if (this.operation === 'register') {
          TextInput({ text: this.personName, placeholder: '姓名' })
            .width('100%').height(52).fontSize(AppFont.SIZE_BODY_LG)
            .fontColor(AppColors.MONO_BLACK).backgroundColor(AppColors.MONO_WHITE)
            .padding({ left: AppSpace.BASE, right: AppSpace.BASE })
            .maxLength(50)
            .enabled(!this.processing).onChange((value: string): void => { this.personName = value; })
          Button(this.processing ? '保存中' : '开始录入')
            .width('100%').height(52).fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.MONO_BLACK).backgroundColor(AppColors.MONO_WHITE)
            .enabled(this.cameraReady && !this.processing)
            .onClick((): void => { this.capture(); })
        } else if (this.resultState !== 'idle') {
          Button(this.resultState === 'success' ? '完成' : '重新识别')
            .width('100%').height(52).fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.MONO_BLACK).backgroundColor(AppColors.MONO_WHITE)
            .onClick((): void => {
              if (this.resultState === 'success') this.close();
              else { this.resultState = 'idle'; this.statusText = '请正对摄像头'; this.capture(); }
            })
        }
      }.width('100%').padding({ left: AppSpace.XL, right: AppSpace.XL, top: AppSpace.LG, bottom: AppSpace.XL })
        .backgroundColor(AppColors.MONO_BLACK)
    }.width('100%').height('100%').backgroundColor(AppColors.MONO_BLACK)
  }

  @Builder
  managementView() {
    Column() {
      this.header('人脸门禁')
      Scroll() {
        Column({ space: AppSpace.LG }) {
          Row({ space: AppSpace.MD }) {
            Column({ space: AppSpace.XS }) {
              Text('门禁').fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.MONO_MUTED)
              Text(this.doorStatus?.success ? (this.doorStatus?.state === 'open' ? '已打开' : '已关闭') : '设备异常')
                .fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold)
                .fontColor(this.doorStatus?.success ? AppColors.SUCCESS : AppColors.DANGER)
            }.layoutWeight(1).alignItems(HorizontalAlign.Start)
            Column({ space: AppSpace.XS }) {
              Text('人脸库').fontSize(AppFont.SIZE_FOOTNOTE).fontColor(AppColors.MONO_MUTED)
              Text(`${this.health?.facesLoaded ?? this.faces.length}`)
                .fontSize(AppFont.SIZE_TITLE).fontWeight(FontWeight.Bold).fontColor(AppColors.MONO_WHITE)
            }.layoutWeight(1).alignItems(HorizontalAlign.Start)
          }.width('100%').padding(AppSpace.LG).backgroundColor(AppColors.MONO_SURFACE)
            .border({ width: 1, color: AppColors.MONO_BORDER })

          Button('录入人脸')
            .width('100%').height(52).fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
            .fontColor(AppColors.MONO_BLACK).backgroundColor(AppColors.MONO_WHITE)
            .onClick((): void => { this.managing = false; this.startScan('register'); })

          Row() {
            Text('已录入').fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold).fontColor(AppColors.MONO_WHITE)
            Blank()
            if (this.listLoading) LoadingProgress().width(20).height(20).color(AppColors.SIGNAL_CYAN)
          }.width('100%').height(32)

          if (!this.listLoading && this.faces.length === 0) {
            Text('暂无人脸信息').width('100%').height(72).textAlign(TextAlign.Center)
              .fontSize(AppFont.SIZE_BODY).fontColor(AppColors.MONO_MUTED)
          }
          ForEach(this.faces, (name: string) => {
            Column() {
              Row({ space: AppSpace.MD }) {
                Stack({ alignContent: Alignment.Center }) {
                  Column().width(38).height(38).backgroundColor(AppColors.MONO_WHITE)
                  SymbolGlyph($r('sys.symbol.face_smiling')).fontSize(21).fontColor([AppColors.MONO_BLACK])
                }.width(38).height(38)
                Text(name).fontSize(AppFont.SIZE_BODY_LG).fontWeight(FontWeight.Bold)
                  .fontColor(AppColors.MONO_WHITE).layoutWeight(1).maxLines(1)
                SymbolGlyph($r('sys.symbol.trash')).fontSize(20).fontColor([AppColors.DANGER])
                  .width(44).height(44).accessibilityText(`删除 ${name}`)
                  .onClick((): void => { this.deleteTarget = this.deleteTarget === name ? '' : name; })
              }.width('100%').height(62)
              if (this.deleteTarget === name) {
                Row({ space: AppSpace.SM }) {
                  Button('取消').layoutWeight(1).height(42).backgroundColor(AppColors.MONO_SURFACE)
                    .fontColor(AppColors.MONO_WHITE).border({ width: 1, color: AppColors.MONO_BORDER })
                    .onClick((): void => { this.deleteTarget = ''; })
                  Button('确认删除').layoutWeight(1).height(42).backgroundColor(AppColors.DANGER)
                    .fontColor(AppColors.MONO_BLACK).fontWeight(FontWeight.Bold)
                    .enabled(!this.listLoading).onClick((): void => { this.deleteFace(name); })
                }.width('100%').padding({ bottom: AppSpace.MD })
              }
            }.width('100%').padding({ left: AppSpace.BASE, right: AppSpace.BASE })
              .backgroundColor(AppColors.MONO_SURFACE).border({ width: 1, color: AppColors.MONO_BORDER })
          }, (name: string) => name)

          if (this.statusText) {
            Text(this.statusText).width('100%').fontSize(AppFont.SIZE_BODY)
              .fontColor(this.statusText.includes('已删除') ? AppColors.SUCCESS : AppColors.DANGER)
              .textAlign(TextAlign.Center)
          }
        }.width('100%').padding({ left: AppSpace.BASE, right: AppSpace.BASE, top: AppSpace.LG, bottom: AppSpace.XXL })
      }.layoutWeight(1).width('100%').scrollBar(BarState.Off)
    }.width('100%').height('100%').backgroundColor(AppColors.MONO_BLACK)
  }

  build() {
    if (this.managing) this.managementView()
    else this.cameraView()
  }
}
