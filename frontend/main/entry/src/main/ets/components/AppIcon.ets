/**
 * 统一图标组件 · 封装 SymbolGlyph 系统图标库
 * 用法: AppIcon({ icon: $r('sys.symbol.fan_fill_1'), size: 22, color: '#007DFF' })
 *
 * 注意 ArkTS 规则:
 *  - @Prop 不能用 color/size/icon 等组件通用属性名（已避开: iconSize/iconColor/iconRes）
 *  - SymbolGlyph.fontColor 参数是 Array<ResourceColor>，必须传数组
 */
@Component
export struct AppIcon {
  /** sys.symbol.xxx 资源 */
  @Prop iconRes: Resource;
  /** 图标尺寸（vp） */
  @Prop iconSize: number = 22;
  /** 图标颜色（hex 字符串） */
  @Prop iconColor: string = '#102A4C';

  build() {
    SymbolGlyph(this.iconRes)
      .fontSize(this.iconSize)
      .fontColor([this.iconColor])
      .renderingStrategy(SymbolRenderingStrategy.SINGLE)
  }
}
