/**
 * 前端 MCP 风格工具适配层。
 * 服务端当前没有原生 /mcp 端点，本模块把 /api/ai/capabilities 与现有 REST API 规范成可枚举、可调用工具。
 */
import { DeviceApi } from './deviceApi';
import { LogApi } from './logApi';
import { SensorApi } from './sensorApi';
import { SystemStatsApi } from './systemStatsApi';
import { Http } from './http';

interface RawCapability {
  action?: string;
  params?: Record<string, Object>;
  desc?: string;
}

interface RawDeviceCapabilities {
  id?: string;
  name?: string;
  type?: string;
  room?: string;
  capabilities?: RawCapability[];
}

interface ToolCallData {
  deviceId: string;
  action: string;
}

export interface AiMcpTool {
  name: string;
  title: string;
  description: string;
  deviceId: string;
  action: string;
  parameters: string;
  source: 'backend' | 'frontend';
}

export interface AiMcpCallResult {
  success: boolean;
  toolName: string;
  message: string;
  data: Object | null;
}

function staticTool(name: string, title: string, description: string): AiMcpTool {
  return {
    name: name, title: title, description: description, deviceId: '', action: name,
    parameters: '{}', source: 'frontend'
  };
}

function numberArg(args: Record<string, Object>, key: string, fallback: number): number {
  const value = args[key];
  return typeof value === 'number' ? value : fallback;
}

function stringArg(args: Record<string, Object>, key: string, fallback: string): string {
  const value = args[key];
  return typeof value === 'string' ? value : fallback;
}

function boolArg(args: Record<string, Object>, key: string, fallback: boolean): boolean {
  const value = args[key];
  return typeof value === 'boolean' ? value : fallback;
}

export class AiMcpApi {
  static async listTools(): Promise<AiMcpTool[]> {
    const tools: AiMcpTool[] = [
      staticTool('home.status', '全屋状态', '读取设备、区域、环境与报警统计'),
      staticTool('sensor.list', '传感器状态', '读取全部传感器真实状态'),
      staticTool('log.daily', '每日日志汇总', '读取最近七天日志图表数据'),
      staticTool('log.today', '今日日志状态', '读取今日累计与实时连接数据'),
      staticTool('log.operations', '操作日志', '读取最新设备操作记录')
    ];
    const text = await Http.get('/api/ai/capabilities');
    if (!text) return tools;
    try {
      const parsed = JSON.parse(text) as Object;
      if (!Array.isArray(parsed)) return tools;
      const devices = parsed as RawDeviceCapabilities[];
      for (const device of devices) {
        if (!device.id || !device.capabilities) continue;
        for (const capability of device.capabilities) {
          if (!capability.action) continue;
          tools.push({
            name: `device.${device.id}.${capability.action}`,
            title: `${device.name || device.id} · ${capability.action}`,
            description: capability.desc || '',
            deviceId: device.id,
            action: capability.action,
            parameters: JSON.stringify(capability.params || {}),
            source: 'backend'
          });
        }
      }
    } catch (e) {
    }
    return tools;
  }

  static async callTool(toolName: string, args: Record<string, Object>): Promise<AiMcpCallResult> {
    if (toolName === 'home.status') return AiMcpApi.dataResult(toolName, await SystemStatsApi.getFeatureStats());
    if (toolName === 'sensor.list') return AiMcpApi.dataResult(toolName, await SensorApi.getSensorSnapshot());
    if (toolName === 'log.daily') return AiMcpApi.dataResult(toolName, await LogApi.getDaily(7));
    if (toolName === 'log.today') return AiMcpApi.dataResult(toolName, await LogApi.getToday());
    if (toolName === 'log.operations') return AiMcpApi.dataResult(toolName, await LogApi.getOperationFeed(100));

    const tools = await AiMcpApi.listTools();
    const tool = tools.find((item: AiMcpTool) => item.name === toolName && item.source === 'backend');
    if (!tool) return { success: false, toolName: toolName, message: '工具不存在或后端未声明此能力', data: null };
    const success = await AiMcpApi.callDeviceTool(tool, args);
    const data: ToolCallData = { deviceId: tool.deviceId, action: tool.action };
    return {
      success: success,
      toolName: toolName,
      message: success ? '设备命令已执行' : '设备命令执行失败',
      data: data
    };
  }

  private static async callDeviceTool(tool: AiMcpTool, args: Record<string, Object>): Promise<boolean> {
    if (tool.action === 'toggle') {
      return DeviceApi.toggle(tool.deviceId, boolArg(args, 'isOn', false), stringArg(args, 'doorPassword', ''));
    }
    if (tool.action === 'set_brightness') return DeviceApi.setBrightness(tool.deviceId, numberArg(args, 'value', 0));
    if (tool.action === 'set_speed') return DeviceApi.setFanSpeed(tool.deviceId, numberArg(args, 'value', 0));
    if (tool.action === 'set_temp') return DeviceApi.setAcTemperature(tool.deviceId, numberArg(args, 'value', 24));
    if (tool.action === 'set_mode') return DeviceApi.setAcMode(tool.deviceId, stringArg(args, 'mode', 'cool'));
    if (tool.action === 'set_fan') return DeviceApi.setAcFan(tool.deviceId, stringArg(args, 'mode', 'auto'));
    if (tool.action === 'set_swing') {
      return DeviceApi.setAcSwing(tool.deviceId, stringArg(args, 'mode', 'off') === 'on');
    }
    if (tool.action === 'set_position') return DeviceApi.setCurtainPosition(tool.deviceId, numberArg(args, 'value', 0));
    if (tool.action === 'stop') return DeviceApi.stopCurtain(tool.deviceId);
    return false;
  }

  private static dataResult(toolName: string, data: Object): AiMcpCallResult {
    return { success: true, toolName: toolName, message: '数据读取完成', data: data };
  }
}
