/**
 * 明日家居生活与生产主题。
 * 白天使用浅绿与白，夜间使用深蓝底、浅蓝与白，保证信息对比度。
 */
export class TacticalTheme {
  static page(dark: boolean): string { return dark ? '#0B1822' : '#F2F8F4'; }
  static panel(dark: boolean): string { return dark ? '#10222E' : '#F8FCF9'; }
  static panelRaised(dark: boolean): string { return dark ? '#162D3A' : '#FFFFFF'; }
  static panelMuted(dark: boolean): string { return dark ? '#1B3543' : '#E5F1E9'; }
  static input(dark: boolean): string { return dark ? '#102631' : '#FBFDFC'; }
  static text(dark: boolean): string { return dark ? '#FFFFFF' : '#173027'; }
  static textSecondary(dark: boolean): string { return dark ? '#D6EDF7' : '#355B4C'; }
  static textMuted(dark: boolean): string { return dark ? '#96B9C9' : '#678276'; }
  static border(dark: boolean): string { return dark ? '#315467' : '#B7CFC2'; }
  static borderStrong(dark: boolean): string { return dark ? '#89C5DD' : '#3F755F'; }
  static grid(dark: boolean): string { return dark ? '#274656' : '#D4E3DB'; }
  static gridStrong(dark: boolean): string { return dark ? '#5F91A7' : '#88AA99'; }
  static structural(dark: boolean): string { return dark ? '#122A37' : '#E7F2EB'; }
  static structuralRaised(dark: boolean): string { return dark ? '#1C3948' : '#F8FBF9'; }
  static ink(dark: boolean): string { return dark ? '#FFFFFF' : '#173027'; }
  static ghost(dark: boolean): string { return dark ? '#BDEBFF14' : '#4D8B700D'; }
  static accent(dark: boolean): string { return dark ? '#8FD3EE' : '#4D8B70'; }
  static accentSoft(dark: boolean): string { return dark ? '#244B5D' : '#DCEDE4'; }
  static inverse(dark: boolean): string { return dark ? '#0B1B25' : '#FFFFFF'; }
  static danger(dark: boolean): string { return dark ? '#BEEBFC' : '#356E57'; }
  static dangerSoft(dark: boolean): string { return dark ? '#203E4C' : '#E2EFE8'; }
  static offline(dark: boolean): string { return dark ? '#6F8793' : '#82958B'; }
  static humidity(dark: boolean): string { return dark ? '#BEEBFC' : '#5C9278'; }
  static scanline(dark: boolean): string { return dark ? '#BDEBFF14' : '#4D8B7014'; }
  // 门禁使用独立语义色：白天保证清晰的暖红/深绿对比，夜间提升亮度但不刺眼。
  static doorOpen(dark: boolean): string { return dark ? '#F3A77F' : '#B84A2B'; }
  static doorClose(dark: boolean): string { return dark ? '#67D8B6' : '#24785D'; }
  static alertDanger(dark: boolean): string { return dark ? '#FF735F' : '#B84A2B'; }
  static alertWarning(dark: boolean): string { return dark ? '#E9B85C' : '#9B6B17'; }
  static scrim(dark: boolean): string { return dark ? '#8A02070B' : '#6607110C'; }
}

export class TacticalMotion {
  static readonly PRESS: number = 140;
  static readonly SWITCH: number = 260;
  static readonly PAGE: number = 360;
  static readonly CURTAIN: number = 180;
  static readonly BOOT_STEP: number = 520;
  static readonly BOOT_TOTAL: number = 4600;
  // Match the routed motion timing from D:\Harmon\ Git source so the overlay
  // remains visible long enough to read instead of collapsing into a blank frame.
  // Deliberately slower than the source default so the routed state is readable on D6.
  static readonly ROUTE: number = 2400;
  static readonly THEME_ROUTE: number = 2600;
  static readonly SECTION_ROUTE: number = 1380;
}

export class TacticalSpace {
  static readonly HAIRLINE: number = 1;
  static readonly RADIUS_TIGHT: number = 2;
  static readonly RADIUS_CONTROL: number = 4;
  static readonly PAGE: number = 16;
  static readonly SECTION: number = 20;
}
