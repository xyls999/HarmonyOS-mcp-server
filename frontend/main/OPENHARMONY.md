# OpenHarmony 兼容版本

此目录是 `D:\Harmon_LandscapeControl` 的 OpenHarmony API 12 兼容副本。原 HarmonyOS 工程未被替换。

OpenHarmony 包名为 `com.smarthome.openharmony`，可与 HarmonyOS 版 `com.smarthome.harmony` 并存安装，避免跨平台产物互相覆盖时触发签名或 SDK 发布类型冲突。

## 兼容范围

- 保留现有页面、ArkUI 组件、Canvas 图表、动画和后端接口实现。
- 运行平台改为 `OpenHarmony`，编译、兼容和目标 SDK 均为 API 12。
- 仅将 OpenHarmony API 12 不提供的两个系统符号替换为同套系统符号中的近义图标。
- 移除 HarmonyOS 新版 SDK 生成的自定义 `syscap.json`，由 OpenHarmony SDK 自动解析系统能力。

## 构建

使用 DevEco Studio 打开本目录，确认 SDK 路径为 `D:\ohos12`。也可以运行 `tools/build-openharmony.ps1` 完成构建和本地测试签名。

命令行构建产物位于：

`entry/build/default/outputs/default/entry-default-signed.hap`

## 安装前签名

构建脚本使用 OpenHarmony SDK 本地测试签名，仅用于受信任的 OpenHarmony 开发镜像或模拟器。HarmonyOS 适配产物必须使用 HarmonyOS 签名另行构建，不要混用两套平台的签名文件。

## DevEco Studio 预览与运行

如果 Previewer 提示 `Getting sdk path error`，请打开 `File > Settings > OpenHarmony SDK`：

1. 将 OpenHarmony SDK 位置设置为 `D:\ohos12`。
2. 接受 OpenHarmony SDK 许可协议。
3. 确认 ArkTS、Toolchains 和 Previewer 均为 `5.0.0.71 (API 12)`。
4. 执行 `File > Sync and Refresh Project`。

同步成功后，在运行目标中选择 `entry` 和 RK3568。不要选择临时的 `Hvigor [clean]` 配置，该配置只清理构建目录，不会安装或启动应用。
