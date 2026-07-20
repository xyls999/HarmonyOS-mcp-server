/**
 * 间距与圆角系统 · 经典鸿蒙克制风格
 * 圆角比玻璃风更小（卡片 16 / 按钮 10），更接近米家/华为系统卡片
 */

export class AppSpace {
  /** 间距 */
  static readonly XS: number = 4;
  static readonly SM: number = 8;
  static readonly MD: number = 12;
  static readonly BASE: number = 16;
  static readonly LG: number = 20;
  static readonly XL: number = 24;
  static readonly XXL: number = 32;
  static readonly XXXL: number = 40;

  /** 圆角（克制） */
  static readonly RADIUS_SM: number = 6;
  static readonly RADIUS_BASE: number = 8;
  static readonly RADIUS_CARD: number = 8;
  static readonly RADIUS_PILL: number = 999;

  /** 页面安全边距 */
  static readonly PAGE_PADDING: number = 16;
  static readonly CARD_GAP: number = 12;
  static readonly PAGE_TOP: number = 16;
  static readonly PAGE_BOTTOM: number = 100;
  static readonly ACTION_HEIGHT: number = 40;
  static readonly CONTROL_HEIGHT: number = 30;
  static readonly DEVICE_ICON_SIZE: number = 40;
  static readonly DEVICE_ROW_HEIGHT: number = 64;
  static readonly CHAT_IMAGE_HEIGHT: number = 200;
}
