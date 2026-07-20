/**
 * 设备主控配色系统
 * 参考系统级智慧语音首页，白灰底、克制蓝色强调。
 */

export class AppColors {
  /** ===== 背景层 ===== */
  static readonly BG_PAGE: string = '#F5FAFF';
  static readonly BG_CARD: string = '#FFFFFF';
  static readonly BG_CARD_TAP: string = '#EEF3FA';
  static readonly BG_GROUP: string = '#EFF7FF';
  static readonly BG_INPUT: string = '#FFFFFF';

  /** ===== 分隔线 / 细线 ===== */
  static readonly DIVIDER: string = '#D9E9F7';
  static readonly HAIRLINE: string = '#0F4FA810';

  /** ===== 主交互色 ===== */
  static readonly PRIMARY: string = '#3B82F6';
  static readonly PRIMARY_TAP: string = '#2563EB';
  static readonly PRIMARY_LIGHT: string = '#D7ECFF';
  static readonly PRIMARY_BG: string = '#EFF6FF';

  /** ===== 文字层级 ===== */
  static readonly TEXT_PRIMARY: string = '#102A4C';
  static readonly TEXT_SECONDARY: string = '#365675';
  static readonly TEXT_TERTIARY: string = '#7890AA';
  static readonly TEXT_DISABLED: string = '#BFD3E8';
  static readonly TEXT_INVERSE: string = '#FFFFFF';

  /** ===== 功能语义色（统一蓝白体系） ===== */
  static readonly SUCCESS: string = '#2563EB';
  static readonly WARNING: string = '#3B82F6';
  static readonly DANGER: string = '#1D4ED8';
  static readonly ONLINE: string = '#2563EB';
  static readonly OFFLINE: string = '#A8B0BE';

  /** ===== 设备类型图标色（仅用于图标，蓝系区分深浅） ===== */
  static readonly DEVICE_FAN: string = '#3B82F6';
  static readonly DEVICE_AC: string = '#2563EB';
  static readonly DEVICE_DOOR: string = '#60A5FA';
  static readonly DEVICE_LIGHT: string = '#1D4ED8';
  static readonly DEVICE_CAMERA: string = '#0EA5E9';

  /** ===== 设备类型浅色背景（图标圆形底） ===== */
  static readonly DEVICE_FAN_BG: string = '#EFF6FF';
  static readonly DEVICE_AC_BG: string = '#DBEAFE';
  static readonly DEVICE_DOOR_BG: string = '#F0F7FF';
  static readonly DEVICE_LIGHT_BG: string = '#EAF2FF';
  static readonly DEVICE_CAMERA_BG: string = '#ECF8FF';

  /** ===== 传感器类型图标色 ===== */
  static readonly SENSOR_TEMP: string = '#1D4ED8';
  static readonly SENSOR_HUMID: string = '#0EA5E9';
  static readonly SENSOR_AIR: string = '#2563EB';
  static readonly SENSOR_LIGHT: string = '#3B82F6';
  static readonly SENSOR_PIR: string = '#60A5FA';
  static readonly SENSOR_DOOR: string = '#60A5FA';
  static readonly SENSOR_SMOKE: string = '#1D4ED8';
  static readonly SENSOR_POWER: string = '#3B82F6';

  // —— 兼容旧引用（统一指向新值，避免大范围改名出错）——
  static readonly BLUE: string = '#3B82F6';
  static readonly PURPLE: string = '#60A5FA';
  static readonly GREEN: string = '#2563EB';
  static readonly ORANGE: string = '#3B82F6';
  static readonly RED: string = '#1D4ED8';
  static readonly CYAN: string = '#0EA5E9';
  static readonly PINK: string = '#60A5FA';
  static readonly YELLOW: string = '#3B82F6';
  static readonly INDIGO: string = '#2563EB';
  static readonly TEAL: string = '#0EA5E9';
}
