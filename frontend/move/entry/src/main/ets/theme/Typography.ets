/**
 * 字体系统 · 统一字重与字号
 */

export class AppFont {
  /** 字号 */
  static readonly SIZE_CAPTION: number = 11;   // 辅助说明
  static readonly SIZE_FOOTNOTE: number = 13;  // 脚注
  static readonly SIZE_BODY: number = 15;      // 正文
  static readonly SIZE_BODY_LG: number = 17;   // 大正文
  static readonly SIZE_TITLE: number = 20;     // 标题
  static readonly SIZE_TITLE_LG: number = 24;  // 大标题
  static readonly SIZE_HEADLINE: number = 28;  // 头条
  static readonly SIZE_LARGE: number = 34;     // 大数字
  static readonly SIZE_HERO: number = 56;      // 英雄数字

  /** 字重 */
  static readonly WEIGHT_REGULAR: number = 400;
  static readonly WEIGHT_MEDIUM: number = 500;
  static readonly WEIGHT_BOLD: number = 700;
}
