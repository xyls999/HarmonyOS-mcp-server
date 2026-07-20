/**
 * 克制动效规范
 * 取代旧 effects 目录的呼吸光/扫光/流动背景
 *
 * 阴影用法: 直接在组件上用 .shadow(ShadowStyle.OUTER_DEFAULT_MD)
 *           或内联 .shadow({ radius:8, color:'#1A000000', offsetX:0, offsetY:2 } as ShadowOptions)
 *           （ArkTS 不允许把 object 字面量存进变量再传，必须内联或用枚举）
 */

/**
 * 点击缩放比例常量
 * 用法: 组件绑定 .scale({ x: pressed ? 0.98 : 1, y: pressed ? 0.98 : 1 })
 *        配合 .animation({ duration: 200, curve: Curve.EaseInOut })
 */
export class TapEffect {
  static readonly PRESSED: number = 0.98;
  static readonly NORMAL: number = 1.0;
  static readonly DURATION: number = 200;
}
