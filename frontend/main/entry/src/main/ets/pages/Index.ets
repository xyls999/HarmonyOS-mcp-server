/**
 * 应用主入口 · 横屏主控面板
 */
import { ControlPanelPage } from './ControlPanelPage';

@Entry
@Component
struct Index {
  build() {
    Row() {
      ControlPanelPage()
    }
    .width('100%')
    .height('100%')
  }
}
