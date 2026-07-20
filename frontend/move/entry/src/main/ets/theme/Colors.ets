/** 明日家居青蓝夜间与鼠尾草白天视觉令牌。 */
export class AppColors {
  static readonly MONO_BLACK: string = '#080808';
  static readonly MONO_WHITE: string = '#FFFFFF';
  static readonly MONO_SURFACE: string = '#141414';
  static readonly MONO_BORDER: string = '#5C5C5C';
  static readonly MONO_MUTED: string = '#C8C8C8';
  static readonly MONO_PLACEHOLDER: string = '#6B6B6B';

  static readonly TRANSPARENT: string = '#00000000';
  static readonly BG_PAGE: string = '#F2F8F4';
  static readonly BG_CARD: string = '#F8FCF9';
  static readonly BG_CARD_TAP: string = '#E5F1E9';
  static readonly BG_GROUP: string = '#E7F2EB';
  static readonly BG_INPUT: string = '#FBFDFC';
  static readonly DIVIDER: string = '#B7CFC2';
  static readonly HAIRLINE: string = '#343F755F';

  static readonly PRIMARY: string = '#4D8B70';
  static readonly PRIMARY_TAP: string = '#3F755F';
  static readonly PRIMARY_LIGHT: string = '#144D8B70';
  static readonly PRIMARY_BG: string = '#DCEDE4';
  static readonly PRIMARY_ON_DARK: string = '#A8E1F8';

  static readonly NIGHT_BG_PAGE: string = '#05090D';
  static readonly NIGHT_BG_CARD: string = '#0B141C';
  static readonly NIGHT_BG_CARD_TAP: string = '#122432';
  static readonly NIGHT_BG_GROUP: string = '#0E1C26';
  static readonly NIGHT_BG_INPUT: string = '#08131B';
  static readonly NIGHT_TEXT_PRIMARY: string = '#F2FAFE';
  static readonly NIGHT_TEXT_SECONDARY: string = '#C5E3F0';
  static readonly NIGHT_TEXT_TERTIARY: string = '#7FA9BB';
  static readonly NIGHT_DIVIDER: string = '#29495A';
  static readonly NIGHT_HAIRLINE: string = '#6629495A';
  static readonly NIGHT_PRIMARY_BG: string = '#152D3A';

  static readonly TEXT_PRIMARY: string = '#173027';
  static readonly TEXT_SECONDARY: string = '#355B4C';
  static readonly TEXT_TERTIARY: string = '#678276';
  static readonly TEXT_DISABLED: string = '#82958B';
  static readonly TEXT_INVERSE: string = '#FFFFFF';

  static readonly SIGNAL_CYAN: string = '#8FD3EE';
  static readonly SIGNAL_YELLOW: string = '#D8B85C';
  static readonly SIGNAL_RED: string = '#FF554D';
  static readonly SIGNAL_GREEN: string = '#49D58B';
  static readonly PANEL_BLACK: string = '#050B10';
  static readonly GRID_DARK: string = '#70406B80';
  static readonly GRID_LIGHT: string = '#70D4E3DB';
  static readonly LINE_STRONG_DARK: string = '#807FBBD4';
  static readonly LINE_STRONG_LIGHT: string = '#8088AA99';

  static readonly SUCCESS: string = '#49D58B';
  static readonly WARNING: string = '#F4D849';
  static readonly DANGER: string = '#FF6B67';
  static readonly DANGER_BG: string = '#3B2228';
  static readonly ONLINE: string = '#70D4A7';
  static readonly OFFLINE: string = '#6F8793';

  static readonly DEVICE_FAN: string = '#24D7E6';
  static readonly DEVICE_AC: string = '#49D58B';
  static readonly DEVICE_DOOR: string = '#F4D849';
  static readonly DEVICE_LIGHT: string = '#F4D849';
  static readonly DEVICE_CAMERA: string = '#24D7E6';
  static readonly DEVICE_FAN_BG: string = '#12353B';
  static readonly DEVICE_AC_BG: string = '#153326';
  static readonly DEVICE_DOOR_BG: string = '#373119';
  static readonly DEVICE_LIGHT_BG: string = '#373119';
  static readonly DEVICE_CAMERA_BG: string = '#12353B';
  static readonly SENSOR_TEMP: string = '#FF8D4D';
  static readonly SENSOR_HUMID: string = '#24D7E6';
  static readonly SENSOR_AIR: string = '#49D58B';
  static readonly SENSOR_LIGHT: string = '#F4D849';
  static readonly SENSOR_PIR: string = '#C7A8FF';
  static readonly SENSOR_DOOR: string = '#FF554D';
  static readonly SENSOR_SMOKE: string = '#FF554D';
  static readonly SENSOR_POWER: string = '#24D7E6';

  static readonly BLUE: string = '#24D7E6';
  static readonly PURPLE: string = '#C7A8FF';
  static readonly GREEN: string = '#49D58B';
  static readonly ORANGE: string = '#FF8D4D';
  static readonly RED: string = '#FF554D';
  static readonly CYAN: string = '#24D7E6';
  static readonly PINK: string = '#FF7FA5';
  static readonly YELLOW: string = '#F4D849';
  static readonly INDIGO: string = '#8798FF';
  static readonly TEAL: string = '#24D7E6';

  static page(isDark: boolean): string { return isDark ? AppColors.NIGHT_BG_PAGE : AppColors.BG_PAGE; }
  static card(isDark: boolean): string { return isDark ? AppColors.NIGHT_BG_CARD : AppColors.BG_CARD; }
  static cardTap(isDark: boolean): string { return isDark ? AppColors.NIGHT_BG_CARD_TAP : AppColors.BG_CARD_TAP; }
  static group(isDark: boolean): string { return isDark ? AppColors.NIGHT_BG_GROUP : AppColors.BG_GROUP; }
  static input(isDark: boolean): string { return isDark ? AppColors.NIGHT_BG_INPUT : AppColors.BG_INPUT; }
  static divider(isDark: boolean): string { return isDark ? AppColors.NIGHT_DIVIDER : AppColors.DIVIDER; }
  static hairline(isDark: boolean): string { return isDark ? AppColors.NIGHT_HAIRLINE : AppColors.HAIRLINE; }
  static primary(isDark: boolean): string { return isDark ? AppColors.PRIMARY_ON_DARK : AppColors.PRIMARY; }
  static onPrimary(isDark: boolean): string { return isDark ? AppColors.PANEL_BLACK : AppColors.TEXT_INVERSE; }
  static primaryBg(isDark: boolean): string { return isDark ? AppColors.NIGHT_PRIMARY_BG : AppColors.PRIMARY_BG; }
  static textPrimary(isDark: boolean): string { return isDark ? AppColors.NIGHT_TEXT_PRIMARY : AppColors.TEXT_PRIMARY; }
  static textSecondary(isDark: boolean): string { return isDark ? AppColors.NIGHT_TEXT_SECONDARY : AppColors.TEXT_SECONDARY; }
  static textTertiary(isDark: boolean): string { return isDark ? AppColors.NIGHT_TEXT_TERTIARY : AppColors.TEXT_TERTIARY; }
  static grid(isDark: boolean): string { return isDark ? AppColors.GRID_DARK : AppColors.GRID_LIGHT; }
  static lineStrong(isDark: boolean): string { return isDark ? AppColors.LINE_STRONG_DARK : AppColors.LINE_STRONG_LIGHT; }
}
