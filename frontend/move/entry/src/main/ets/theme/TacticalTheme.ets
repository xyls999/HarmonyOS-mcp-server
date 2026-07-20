export class TacticalTheme {
  static page(dark: boolean): string { return dark ? '#05090D' : '#F2F8F4'; }
  static panel(dark: boolean): string { return dark ? '#08131B' : '#F8FCF9'; }
  static panelRaised(dark: boolean): string { return dark ? '#0B141C' : '#FFFFFF'; }
  static panelMuted(dark: boolean): string { return dark ? '#0E1C26' : '#E5F1E9'; }
  static input(dark: boolean): string { return dark ? '#071118' : '#FBFDFC'; }
  static text(dark: boolean): string { return dark ? '#F2FAFE' : '#173027'; }
  static textSecondary(dark: boolean): string { return dark ? '#C5E3F0' : '#355B4C'; }
  static textMuted(dark: boolean): string { return dark ? '#7FA9BB' : '#678276'; }
  static border(dark: boolean): string { return dark ? '#29495A' : '#B7CFC2'; }
  static borderStrong(dark: boolean): string { return dark ? '#A8E1F8' : '#3F755F'; }
  static grid(dark: boolean): string { return dark ? '#244250' : '#D4E3DB'; }
  static gridStrong(dark: boolean): string { return dark ? '#629AB3' : '#88AA99'; }
  static structural(dark: boolean): string { return dark ? '#0D1A23' : '#E7F2EB'; }
  static ghost(dark: boolean): string { return dark ? '#14BDEBFF' : '#0D4D8B70'; }
  static accent(dark: boolean): string { return dark ? '#A8E1F8' : '#4D8B70'; }
  static accentSoft(dark: boolean): string { return dark ? '#152D3A' : '#DCEDE4'; }
  static inverse(dark: boolean): string { return dark ? '#050B10' : '#FFFFFF'; }
  static scanline(dark: boolean): string { return dark ? '#14BDEBFF' : '#144D8B70'; }
}

export class TacticalMotion {
  static readonly PRESS: number = 140;
  static readonly SWITCH: number = 220;
  static readonly PAGE: number = 280;
  static readonly CURTAIN: number = 180;
  static readonly BOOT_STEP: number = 240;
  static readonly ROUTE: number = 1800;
  static readonly THEME_ROUTE: number = 2000;
}
