# G2 当前规则边界

版本：0.3.0a1。规则基线仍固定为 SRD 5.2.1。本文描述已经由服务器裁决并有测试覆盖的有限菜单，不是整个 SRD、完整三个职业或通用 DM 系统。

## 成长

三个固定起始构筑都从 1 级开始，并沿同一个“失落火种”冒险成长。

| 职业 | 2级 | 3级 |
|---|---|---|
| Fighter | Action Surge、Tactical Mind | 固定 Champion；扩展重击、体能相关实现 |
| Rogue | Cunning Action | 固定 Thief；Sneak Attack 2d6、Steady Aim、Fast Hands、攀爬/跳跃数据 |
| Wizard | Scholar/Arcana 专精数据、更多一环位 | 固定 Evoker；二环位、Potent Cantrip、有限 Evocation 法术 |

升级只增加最大 HP 和对应资源，不免费恢复当前 HP。

## Rogue

Sneak Attack 由服务器判断优势/盟友支持、武器条件和“每回合一次”标记。Vex 命中后给下一次对应攻击优势，并在实际使用或规则时限后清理。

Cunning Action 花 Bonus Action 执行已实现的 Dash / Disengage。Steady Aim 要求本回合尚未移动，花 Bonus Action，把本回合 Speed 归零并给下一次攻击优势。

Thief 的 Fast Hands 不是标签：当前作者场景在守印考验中提供一个可利用的绞盘，花 Bonus Action 产生受规则约束的短期减速。Second-Story Work 目前兑现攀爬速度和跳跃属性数据，但没有因此声称实现所有环境攀爬/跳跃裁定。

## Wizard

当前法术闭包只包括：

- Cantrip：Ray of Frost
- 1环：Mage Armor、Magic Missile、Shield
- 2环：Blur、Scorching Ray

法术书可以记录更多名字，但未列入实现集合的法术不能被准备或施放，也不会被近似成“差不多成功”。

法术位和 Arcane Recovery 是持久资源。完成 Long Rest 后打开一次准备窗口；只能在法术书、实现集合和准备容量范围内增删已准备法术。

Mage Armor 检查当前构筑所需的奥术法器来源。Shield 不是普通回合按钮：攻击先完成命中骰，若满足条件则生成“命中后、伤害前”的反应窗口；玩家可施放或放弃，随后服务器用同一次攻击骰继续结算，绝不重掷攻击。

Blur 使用专注。攻击 Blur 目标受到劣势；目标受到伤害时按服务器骰进行专注豁免，失败或失去行动能力会结束专注。当前没有宣称实现所有专注来源与所有法术组件边界。

## Fighter

G1 的 Second Wind、Action Surge、Tactical Mind、Sap、两种 2 级战斗风格继续保留。3 级固定进入 Champion；19–20 的扩展重击由攻击规则直接判断，Remarkable Athlete 已用于先攻与作者 Athletics 检定。**重击后立即移动至多一半 Speed 且不触发机会攻击的部分尚未开放**，因此 Champion 仍是部分闭包。

## 合作预览

合作状态存放于 party:<id>，不是“每人一个单机存档加队伍名称”。每个成员有独立身份和 seat，共享 battle / rewards / rest_requests / fictional time。

当前合作玩法重点验收身份边界、轮到谁谁行动、NPC 世界控制、奖励一次性分配和多人休息共识。它还不是完整多人化六区域战役，也没有为每个职业复制全部单人菜单。

## 仍然不支持

完整 SRD 法术表、完整远程武器与装备切换、完整 Hide/Search/Help/Ready、自由文本 DM 裁定、所有状态与死亡后救助流程、完整多人探索任务、角色编辑器和 1–20 级成长都不在 0.3.0a1 的承诺范围内。


## G1 存档与共享状态基础设施

G2 将 world/function/view 合同显式升到 v2，但保持 state_version=1 并接受 G1 顶层状态形状。旧存档在读取时按原 Fighter 规范化，在下一次真实写入时持久为 G2 数据；已完成旧守印考验的 0 XP 记录补为当前 600 XP，而不换 role_id、不免费治疗。再次 `adventure.join` 不能把旧 Fighter 改成别的职业。

party 成员授权使用 Agent World 0.14.0 的受限 `authorization_state` 查询完成。该查询只允许在 `state_authorizer` 回调执行期间使用；世界不再直接读取 SQLite 连接。
