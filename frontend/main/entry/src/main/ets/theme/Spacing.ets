/**
 * 间距与圆角系统 · 竖屏主控
 * 留白更充足，圆角更柔和。
 */

export class AppSpace {
  /** 间距 */
  static readonly XS: number = 4;
  static readonly SM: number = 8;
  static readonly MD: number = 10;
  static readonly BASE: number = 14;
  static readonly LG: number = 18;
  static readonly XL: number = 22;
  static readonly XXL: number = 28;
  static readonly XXXL: number = 36;

  /** 圆角 */
  static readonly RADIUS_SM: number = 10;
  static readonly RADIUS_BASE: number = 14;
  static readonly RADIUS_CARD: number = 24;
  static readonly RADIUS_PILL: number = 999;

  /** 页面安全边距 */
  static readonly PAGE_PADDING: number = 14;
  static readonly CARD_GAP: number = 12;
}
