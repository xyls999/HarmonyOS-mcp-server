# Spec: AI 分析可靠性与异常控制警戒

## Objective

让七日/当日日志分析无需依赖外部模型即可稳定返回；让复杂 AI 请求拥有足够的端到端等待时间；检测未经过主控授权的设备状态突变、门禁密码枚举和重复攻击，并把证据、处置、QQ 通知与蜂鸣器动作同步到助手和长期上下文。

## Assumptions

1. 通过 D6 网关成功执行的设备命令属于“主控授权命令”。
2. 设备轮询发现状态变化，但最近没有匹配的主控授权命令，属于“来源未知状态变化”；第一次只警告，不能仅凭一次物理按键就断言黑客入侵。
3. 满足门禁异常开启、短时间重复未知变化、门禁密码连续枚举或重复认证攻击时，才升级为“疑似明确入侵”，自动开启蜂鸣器。
4. 警戒自动执行安全收拢动作；普通 AI 调整和模糊计划仍需主人点击确认。

## Commands

- Python tests: `python -m unittest discover -s tests -p 'test_*.py' -q`
- Python syntax: `python -m py_compile backend/d6/gateway_v6.py backend/d6/security_anomaly_guard.py`
- ArkTS build: `hvigorw assembleHap --mode module -p product=default -p module=entry@default -p buildMode=debug`
- D6 health: `GET http://192.168.1.94:8080/health`

## Project Structure

- `backend/d6/gateway_v6.py`: HTTP、轮询、上下文、QQ、蜂鸣器集成。
- `backend/d6/security_anomaly_guard.py`: 可测试的异常状态与密码枚举判定状态机。
- `entry/src/main/ets/api/chatApi.ets`: AI 对话端到端超时和图表对齐。
- `entry/src/main/ets/api/http.ets`: 网络读取超时。
- `tests/`: 状态机、网关和前端契约测试。
- `docs/`: 功能展示与验收说明。

## Code Style

```python
decision = guard.observe_state("door_01", True, now=clock())
if decision and decision["critical"]:
    publish_security_incident(decision)
```

判定逻辑只返回结构化证据；QQ、助手、蜂鸣器等副作用由网关统一执行。

## Testing Strategy

- 单元测试覆盖授权变化、单次未知变化、门禁异常打开、重复状态突变、密码枚举升级。
- 契约测试覆盖日志分析本地快速路径、助手事件、QQ、蜂鸣器和 App 超时。
- D6 实测覆盖健康接口、日志分析耗时、AI 配置、事件持久化。

## Boundaries

- Always: 保存证据和时间戳；助手与 QQ 使用中文；高危才自动蜂鸣；安全动作不等待 AI。
- Ask first: 修改下位机协议、门禁密码、QQ 目标号码。
- Never: 因单次普通设备物理变化直接认定黑客；把密码或密钥写入事件内容；由 AI 绕过计划确认执行普通调整。

## Success Criteria

1. “分析七日趋势和当日趋势日志”在 D6 本地快速路径返回，不调用外部模型，并附非空七日、今日图表。
2. App 对复杂 AI 请求的等待时间大于单模型超时与一次兜底所需时间。
3. 授权设备变化不报警；单次未知变化写助手、上下文并发 QQ，但不开蜂鸣器。
4. 未授权开门、两分钟内同设备三次未知变化、五分钟五次门禁密码失败触发 Critical，自动蜂鸣、助手提醒、QQ 报警。
5. 三次门禁密码失败在两分钟内触发 High 提醒，但尚不启动蜂鸣器。
6. 所有新增行为有自动测试，并在功能展示文档中给出可复现验收方法。

## Open Questions

- 若未来下位机能提供物理按键来源字段，可把“来源未知”进一步区分为本地物理操作和网络异常操作；当前协议没有该字段。
