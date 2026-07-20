import { HomePage } from './HomePage';
import { HistoryPage } from './HistoryPage';
import { ChatPage } from './ChatPage';
import { MinePage } from './MinePage';
import { LoginPage } from './LoginPage';
import { FaceDoorPage } from './FaceDoorPage';
import { Http } from '../api/http';
import { AuthApi } from '../api/authApi';
import { TacticalMotion, TacticalTheme } from '../theme/TacticalTheme';
import { hilog } from '@kit.PerformanceAnalysisKit';

@Entry
@Component
struct Index {
  @State currentIndex: number = 0;
  @State pressedKey: string = '';

  @State checkingService: boolean = true;
  @State switching: boolean = false;
  @State loadingOuterAngle: number = 0;
  @State loadingInnerAngle: number = 0;
  @State themeGradientAngle: number = 34;
  @State themeSweep: number = 580;
  @State transitionVisible: boolean = false;
  @State transitionProgress: number = 0;
  @State transitionClosing: boolean = false;
  @State transitionKind: number = 0;
  @State targetIndex: number = 0;
  @State targetDark: boolean = true;
  @State sourceDark: boolean = true;
  @State faceDoorVisible: boolean = false;
  @State faceDoorMode: number = 0;
  @StorageLink('isDarkTheme') isDarkTheme: boolean = true;
  @StorageLink('isAuthenticated') isAuthenticated: boolean = false;
  @StorageLink('isOfflineMode') isOfflineMode: boolean = false;
  private timers: number[] = [];

  aboutToAppear(): void {
    this.resolveAccessMode();
  }
  aboutToDisappear(): void {
    for (const timer of this.timers) clearTimeout(timer);
    this.timers = [];
  }
  private later(delay: number, action: () => void): void { this.timers.push(setTimeout(action, delay)); }
  private async resolveAccessMode(): Promise<void> {
    const serviceAvailable = await Http.checkService();
    Http.setOfflineMode(!serviceAvailable);
    if (serviceAvailable && Http.hasSession()) {
      const user = await AuthApi.restoreUser();
      this.isAuthenticated = user !== null;
    } else if (serviceAvailable) {
      this.isAuthenticated = false;
    }
    this.checkingService = false;
    if (this.isAuthenticated || !serviceAvailable) this.startMainShell();
  }
  private startMainShell(): void {
    this.currentIndex = 0;
  }
  private pressed(key: string): boolean { return this.pressedKey === key; }
  private touchKey(key: string, event: TouchEvent): void {
    this.pressedKey = event.type === TouchType.Down ? key : '';
  }
  private brandInk(): string { return this.isDarkTheme ? '#0B1B25' : '#173027'; }
  private brandAccent(): string { return this.isDarkTheme ? '#8FD3EE' : '#4D8B70'; }
  private brandGhost(): string { return this.isDarkTheme ? '#DDECF2' : '#E3EEE8'; }
  private switchPage(index: number): void {
    if (index === this.currentIndex || this.switching) return;
    this.transitionKind = 0;
    this.targetIndex = index;
    this.targetDark = this.isDarkTheme;
    this.sourceDark = this.isDarkTheme;
    this.startPageTransition();
  }

  private prepareTransition(): void {
    this.switching = true;
    this.transitionVisible = true;
    this.transitionClosing = false;
    this.transitionProgress = 0;
    this.loadingOuterAngle = 0;
    this.loadingInnerAngle = 0;
    this.themeGradientAngle = 34;
    this.themeSweep = 580;
    const duration: number = this.transitionKind === 1 ?
      TacticalMotion.THEME_ROUTE - 180 : TacticalMotion.ROUTE - 180;
    this.later(24, (): void => {
      this.getUIContext().animateTo({ duration: duration, curve: Curve.Linear }, (): void => {
        this.transitionProgress = 100;
        this.loadingOuterAngle = 360;
        this.loadingInnerAngle = -360;
        if (this.transitionKind === 1) {
          this.themeGradientAngle = 62;
          this.themeSweep = -580;
        }
      });
    });
  }

  private finishTransition(duration: number): void {
    this.later(duration, (): void => {
      this.transitionVisible = false;
      this.transitionClosing = false;
      this.switching = false;
    });
  }

  private startPageTransition(): void {
    this.prepareTransition();
    this.later(840, (): void => { this.currentIndex = this.targetIndex; });
    this.later(1660, (): void => { this.transitionClosing = true; });
    this.finishTransition(TacticalMotion.ROUTE);
  }

  private toggleTheme(): void {
    if (this.switching) return;
    this.transitionKind = 1;
    this.sourceDark = this.isDarkTheme;
    this.targetDark = !this.isDarkTheme;
    this.targetIndex = this.currentIndex;
    this.prepareTransition();
    this.later(1060, (): void => { this.isDarkTheme = this.targetDark; });
    this.later(1840, (): void => { this.transitionClosing = true; });
    this.finishTransition(TacticalMotion.THEME_ROUTE);
  }

  private transitionTitle(): string {
    if (this.transitionKind === 1) return this.targetDark ? '静夜' : '明昼';
    if (this.targetIndex === 0) return '中枢';
    if (this.targetIndex === 1) return '记录';
    if (this.targetIndex === 2) return '助手';
    return '账号';
  }

  private transitionIcon(): Resource {
    if (this.transitionKind === 1) {
      return this.targetDark ? $r('sys.symbol.moon_fill') : $r('sys.symbol.sun_max');
    }
    if (this.targetIndex === 0) return $r('sys.symbol.house_fill');
    if (this.targetIndex === 1) return $r('sys.symbol.clock_fill');
    if (this.targetIndex === 2) return $r('sys.symbol.Celia');
    return $r('sys.symbol.person_fill');
  }

  @Builder pageContent() {
    if (this.currentIndex === 0) HomePage()
    else if (this.currentIndex === 1) HistoryPage()
    else if (this.currentIndex === 2) ChatPage()
    else MinePage({ onFaceDoor: (): void => { this.openFaceDoor(1); } })
  }

  private openFaceDoor(mode: number): void {
    this.faceDoorMode = mode;
    this.faceDoorVisible = true;
  }

  @Builder brandMark() {
    Stack({ alignContent: Alignment.Center }) {
      Column().width(184).height(50).backgroundColor('#FFFFFF')
        .border({ width: { bottom: 2 }, color: this.brandAccent() })
      Text('明').fontSize(43).fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bold)
        .fontColor(this.brandGhost()).opacity(0.58).position({ x: 10, y: -6 })
      Column().width(4).height(36).backgroundColor(this.brandAccent()).position({ x: 0, y: 7 })
      Column().width(34).height(2).backgroundColor(this.brandAccent()).position({ x: 150, y: 0 })
      Column().width(16).height(1).backgroundColor(this.brandInk()).position({ x: 168, y: 6 })
      Column().width(8).height(8).border({ width: 1, color: this.brandAccent() })
        .position({ x: 170, y: 36 }).rotate({ angle: 45 })
      Column().width(1).height(24).backgroundColor(this.brandGhost()).position({ x: 142, y: 13 })
      Stack() {
        Row({ space: 0 }) {
          Text('明日').fontSize(27).fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bolder)
            .fontColor(this.brandGhost())
          Text('家居').fontSize(27).fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bolder)
            .fontColor(this.brandGhost())
        }.translate({ x: 2, y: 2 })
        Row({ space: 0 }) {
          Text('明日').fontSize(27).fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bolder)
            .fontColor(this.brandInk())
          Text('家居').fontSize(27).fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bolder)
            .fontColor(this.brandAccent())
        }
      }.width(136).height(38)
    }.width(184).height(50).accessibilityText('明日家居')
  }

  @Builder topBar() {
    Row({ space: 10 }) {
      this.brandMark()
      Blank()
      Stack() {
        Column().width(48).height(48)
          .backgroundColor(this.pressed('theme') ? TacticalTheme.accentSoft(this.isDarkTheme) : TacticalTheme.panel(this.isDarkTheme))
          .border({ width: 1, color: TacticalTheme.accent(this.isDarkTheme) })
        SymbolGlyph(this.isDarkTheme ? $r('sys.symbol.sun_max') : $r('sys.symbol.moon_fill'))
          .fontSize(21).fontColor([TacticalTheme.accent(this.isDarkTheme)])
      }.width(48).height(48)
        .opacity(this.pressed('theme') ? 0.72 : 1)
        .scale({ x: this.pressed('theme') ? 0.94 : 1, y: this.pressed('theme') ? 0.94 : 1 })
        .animation({ duration: TacticalMotion.PRESS, curve: Curve.EaseOut })
        .accessibilityText(this.isDarkTheme ? '切换到白天模式' : '切换到黑夜模式')
        .onTouch((event: TouchEvent): void => { this.touchKey('theme', event); })
        .onClick((): void => { this.toggleTheme(); })
    }.width('100%').height(68).padding({ left: 18, right: 16, top: 9, bottom: 9 })
      .backgroundColor(TacticalTheme.panel(this.isDarkTheme))
      .border({ width: { bottom: 1 }, color: TacticalTheme.border(this.isDarkTheme) })
  }

  @Builder artTitle(title: string, dark: boolean) {
    Row({ space: 8 }) {
      Column().width(26).height(2).backgroundColor(TacticalTheme.accent(dark))
      Stack({ alignContent: Alignment.Center }) {
        Text(title).fontSize(28).fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bolder)
          .fontColor(TacticalTheme.gridStrong(dark)).translate({ x: 2, y: 2 })
        Text(title).fontSize(28).fontFamily('HarmonyOS Sans SC').fontWeight(FontWeight.Bolder)
          .fontColor(TacticalTheme.text(dark))
      }.height(44)
      Column().width(26).height(2).backgroundColor(TacticalTheme.accent(dark))
    }.height(44).alignItems(VerticalAlign.Center).accessibilityText(title)
  }

  @Builder loadingCore(progress: number, title: string, icon: Resource, dark: boolean) {
    Column({ space: 18 }) {
      Stack({ alignContent: Alignment.Center }) {
        Column().width(164).height(164)
          .border({ width: 1, color: TacticalTheme.grid(dark) })
          .rotate({ angle: 45 + this.loadingOuterAngle }).opacity(0.52)
        Column().width(136).height(136)
          .border({ width: 1, color: TacticalTheme.gridStrong(dark) })
          .rotate({ angle: this.loadingInnerAngle }).opacity(0.82)
        Column().width(96).height(96)
          .border({ width: 1, color: TacticalTheme.accent(dark) })
          .rotate({ angle: 45 + this.loadingOuterAngle * 1.18 }).opacity(0.96)

        Column().width(10).height(10).backgroundColor(TacticalTheme.text(dark))
          .position({ x: 8, y: 166 }).rotate({ angle: 45 + this.loadingOuterAngle * 0.22 })
          .opacity(progress < 70 ? 0 : 1)
          .animation({ duration: 280, curve: Curve.EaseOut })
        Column().width(10).height(10).backgroundColor(TacticalTheme.accent(dark))
          .position({ x: 166, y: 8 }).rotate({ angle: 45 + this.loadingInnerAngle * 0.22 })
          .opacity(progress < 85 ? 0 : 1)
          .animation({ duration: 280, curve: Curve.EaseOut })

        Stack() {
          Column().width(54).height(54).backgroundColor(TacticalTheme.accent(dark))
          SymbolGlyph(icon).fontSize(25).fontColor([TacticalTheme.inverse(dark)])
        }.width(54).height(54)
          .scale({ x: progress < 55 ? 0.84 : 1, y: progress < 55 ? 0.84 : 1 })
          .animation({ duration: 320, curve: Curve.EaseOut })
      }.width(184).height(184)

      Progress({ value: progress, total: 100, type: ProgressType.Linear })
        .width(184).height(4)
        .color(TacticalTheme.accent(dark))
        .backgroundColor(TacticalTheme.grid(dark))
        .style({ strokeWidth: 4 })

      this.artTitle(title, dark)
    }.alignItems(HorizontalAlign.Center)
  }

  @Builder navItem(index: number, label: string, icon: Resource) {
    Stack({ alignContent: Alignment.BottomStart }) {
      Column({ space: 4 }) {
        SymbolGlyph(icon).fontSize(19).fontColor([this.currentIndex === index ? TacticalTheme.inverse(this.isDarkTheme) : TacticalTheme.accent(this.isDarkTheme)])
        Text(label).fontSize(10).fontWeight(FontWeight.Bold)
          .fontFamily('HarmonyOS Sans SC')
          .fontColor(this.currentIndex === index ? TacticalTheme.inverse(this.isDarkTheme) : TacticalTheme.textSecondary(this.isDarkTheme))
      }.width('100%').height(52).justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
      Column().width(this.currentIndex === index ? '100%' : 18).height(3)
        .backgroundColor(this.currentIndex === index ? TacticalTheme.inverse(this.isDarkTheme) : TacticalTheme.accent(this.isDarkTheme))
        .animation({ duration: TacticalMotion.SWITCH, curve: Curve.EaseOut })
    }.layoutWeight(1).height(56)
      .backgroundColor(this.currentIndex === index ? TacticalTheme.accent(this.isDarkTheme) : TacticalTheme.panel(this.isDarkTheme))
      .border({ width: 1, color: this.currentIndex === index ? TacticalTheme.accent(this.isDarkTheme) : TacticalTheme.border(this.isDarkTheme) })
      .opacity(this.pressed(`nav_${index}`) ? 0.72 : 1)
      .scale({ x: this.pressed(`nav_${index}`) ? 0.95 : 1, y: this.pressed(`nav_${index}`) ? 0.95 : 1 })
      .animation({ duration: TacticalMotion.PRESS, curve: Curve.EaseOut })
      .onTouch((event: TouchEvent): void => { this.touchKey(`nav_${index}`, event); })
      .onClick((): void => { this.switchPage(index); })
  }

  @Builder transitionOverlay() {
    if (this.transitionVisible) {
      Stack() {
        if (this.transitionKind === 1) {
          Column().width('100%').height('100%')
            .linearGradient({
              angle: this.themeGradientAngle,
              colors: [[TacticalTheme.page(this.targetDark), 0],
                [TacticalTheme.structural(this.targetDark), 0.24],
                [TacticalTheme.accentSoft(this.targetDark), 0.46],
                [TacticalTheme.structural(this.targetDark), 0.72],
                [TacticalTheme.page(this.targetDark), 1]]
            })
            .animation({ duration: 1720, curve: Curve.EaseInOut })

          Column().width('100%').height('100%')
            .backgroundColor(TacticalTheme.page(this.sourceDark))
            .opacity(this.transitionProgress < 58 ? 1 : 0)
            .animation({ duration: 520, curve: Curve.EaseInOut })

          Column().width('150%').height('135%')
            .linearGradient({
              angle: 44,
              colors: [[TacticalTheme.page(this.targetDark), 0],
                [TacticalTheme.structural(this.targetDark), 0.28],
                [TacticalTheme.accentSoft(this.targetDark), 0.52],
                [TacticalTheme.page(this.targetDark), 0.78],
                [TacticalTheme.structural(this.targetDark), 1]]
            })
            .opacity(0.98)
            .rotate({ angle: -36 })
            .translate({ x: this.themeSweep, y: -this.themeSweep * 1.2 })
        } else {
          Column().width('100%').height('100%').backgroundColor(TacticalTheme.page(this.isDarkTheme))
        }

        if (this.transitionKind === 0) {
          Column().width(1).height('100%')
            .backgroundColor(TacticalTheme.grid(this.isDarkTheme))
            .position({ x: '33%', y: 0 }).opacity(0.3)
          Column().width(1).height('100%')
            .backgroundColor(TacticalTheme.grid(this.isDarkTheme))
            .position({ x: '66%', y: 0 }).opacity(0.3)
          Column().width(1).height('100%')
            .backgroundColor(TacticalTheme.grid(this.isDarkTheme))
            .position({ x: '50%', y: 0 }).opacity(0.16)

          Column().width('145%').height(1)
            .backgroundColor(TacticalTheme.gridStrong(this.isDarkTheme))
            .rotate({ angle: -34 }).opacity(0.34)
          Column().width('145%').height(1)
            .backgroundColor(TacticalTheme.gridStrong(this.isDarkTheme))
            .rotate({ angle: 34 }).opacity(0.24)
        }

        Column({ space: 20 }) {
          this.loadingCore(this.transitionProgress, this.transitionTitle(), this.transitionIcon(),
            this.transitionKind === 1 ? this.targetDark : this.isDarkTheme)
        }.width('100%').height('100%').justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)

        Column().width(3).height('100%')
          .backgroundColor(TacticalTheme.accent(this.transitionKind === 1 ? this.targetDark : this.isDarkTheme))
          .position({ x: 0, y: 0 })
      }.width('100%').height('100%')
        .opacity(this.transitionClosing ? 0 : 1)
        .animation({ duration: 140, curve: Curve.EaseIn })
        .enabled(false)
    }
  }

  @Builder serviceCheckScreen() {
    Column() {
      this.artTitle('明日家居', this.isDarkTheme)
    }.width('100%').height('100%').justifyContent(FlexAlign.Center).alignItems(HorizontalAlign.Center)
  }

  build() {
    Stack() {
      if (this.checkingService) {
        this.serviceCheckScreen()
      } else if (!this.isAuthenticated && !this.isOfflineMode) {
        LoginPage({
          onLogin: (): void => {
            hilog.info(0x0000, 'SmartHomeIndex', 'login callback: enter main shell');
            this.isAuthenticated = true;
            this.startMainShell();
          },
          onFaceDoor: (): void => { this.openFaceDoor(0); }
        })
      } else {
        Column() {
          this.topBar()
          Column() { this.pageContent() }.layoutWeight(1).width('100%')
          Row({ space: 5 }) {
            this.navItem(0, '中枢', $r('sys.symbol.house_fill'))
            this.navItem(1, '记录', $r('sys.symbol.clock_fill'))
            this.navItem(2, '助手', $r('sys.symbol.Celia'))
            this.navItem(3, '账号', $r('sys.symbol.person_fill'))
          }.width('100%').height(80).padding({ left: 8, right: 8, top: 8, bottom: 12 })
            .backgroundColor(TacticalTheme.panelRaised(this.isDarkTheme))
            .border({ width: { top: 1 }, color: TacticalTheme.border(this.isDarkTheme) })
        }.width('100%').height('100%')
          .opacity(this.switching ? 0 : 1)
        this.transitionOverlay()
      }
      if (this.faceDoorVisible) {
        FaceDoorPage({
          mode: this.faceDoorMode,
          onClose: (): void => { this.faceDoorVisible = false; }
        })
      }
    }.width('100%').height('100%').backgroundColor(TacticalTheme.page(this.isDarkTheme))
  }
}
