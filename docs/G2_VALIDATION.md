# G2 实施与验证记录

版本：0.3.0a1。本文把不同层级的证据分开记录，不用脚本通关率冒充真人体验，也不把旧提交上的浏览器测试写成最终候选已经全部重新跑过。

## 已实现

- 三个固定合法方向：Fighter / Rogue / Wizard，从 1 级成长到 3 级。
- Fighter 继续闭合 G1 能力，并增加 3 级 Champion 规则。
- Rogue 有真实 Sneak Attack / Vex / Cunning Action / Steady Aim / Fast Hands。
- Wizard 有真实法术位、Arcane Recovery、有限准备、组件门槛、Shield 反应继续点和 Blur 专注。
- 旧 G1 世界状态提供 v1→v2 迁移，保留已有角色进度。
- 1–3 身份合作预览使用真实共享状态、成员授权、一次性奖励和休息共识。
- Runtime 的 world.describe 已合并；Agent 不必靠猜测理解世界入口。
- Runtime 旧 FunctionContext.conn 绕过 managed state schema/authorization 的问题已合并修复。

## 本地与隔离验证

在 Windows 开发机上，G2 基础分支曾完成 **154 项 Python 单元/集成测试**，包含 HTTP、MCP、三职业基础成长和多人 party 权限；同一机器还完成真实浏览器 1→3 Fighter 路径、Node 播放器和 M1 浏览器回归。Runtime 在合并 world.describe 与状态安全修复后完成 **175 项本地测试**。

最后一批 Shield / 专注 / Fast Hands / Evoker 收口之后，由于 Desktop Commander 月度额度已用尽，没有再启动 GitHub Actions。候选代码改为通过 Git 对象创建而不挂分支，并在会话隔离 Linux 环境重建规则层验证：

- 72 项 rules + engine 回归通过。
- Shield 命中后/伤害前继续点、Blur 专注中断、Wizard 准备/组件、Thief Fast Hands、Scorching Ray、Potent Cantrip 定点测试通过。
- 900 条固定策略完整成长轨迹通过：支付/战斗/交涉三路线各 300。
- 5075 次服务端提供动作探索通过，并验证 5075 次 stale revision 在掷骰前拒绝。
- 最后一批规则改动之后没有重新跑真实 Playwright 浏览器整链，因此不能把旧浏览器结果冒充最终候选的浏览器复核。

900 条轨迹的结果：

| 路线 | 完成 | 被俘 | 到达3级 |
|---|---:|---:|---:|
| 支付 | 297 | 3 | 297 |
| 战斗 | 292 | 8 | 292 |
| 交涉 | 295 | 5 | 295 |

这些数字只说明当前固定策略和服务器规则在大量确定性种子下能闭环，不代表人类/LLM 实际胜率或游戏平衡评分。

## 本轮发现并修正的边界

- G2 初版只增加了新状态字段，却没有提升 WorldDefinition/state version。旧 G1 数据会被 Runtime 正确拒绝安装；现已增加 v1→v2 迁移。
- Wizard 不能只在角色卡上写 spellbook。现已把有限准备、组件、法术位和专注纳入权威状态。
- Shield 必须在已知攻击命中后、伤害结算前暂停；继续时复用原攻击骰，不允许重掷。
- 测试最初选了一个 Shield 后仍然命中的攻击骰，导致测试意图本身错误；已改为基础 AC 命中、Shield 后转为未命中的合法边界值。
- Rogue 3 的 Fast Hands 不能只写在升级 features 数组里；现在有一个明确作者对象使用点并真实花 Bonus Action。
- 多人休息冲突不会偷偷推进世界时间；只有所有当前成员请求同一休息类型才结算。

## 当前评价

G2 已从“职业名字和等级数据”推进到有限但真正受规则裁决的三职业 1→3 系统，并证明 Runtime 能承载独立身份共享一个权威世界状态。

仍不应称为完整 D&D 游戏或完成版多人序章。下一阶段高收益工作是：把合作预览接入完整探索/任务、补死亡与战后救助边界、扩展有限法术与场景反馈，并在有可控本地测试资源时重新跑最终候选的真实浏览器验收。
