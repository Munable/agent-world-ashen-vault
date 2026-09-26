# G2 Phase A：当前规则边界

源码 `e9d345b3` / 0.3.0a1，规则来源固定为 SRD 5.2.1。本文描述有限实现，不宣称完整 SRD、完整职业或通用自然语言 DM。

## 正常流程与规则夹具

现有六区域单人主链支持 Fighter / Rogue / Wizard，从一级到二级，完成守印考验后取得三级升级。`campaign.available` 在完成三级升级后不再提供后续冒险动作。

**处理器已实现，不等于普通玩法已到达。** Fast Hands、Steady Aim、Blur、Scorching Ray、Potent Cantrip 等三级机制的定点测试包含直接设置 XP 或构造战斗状态；不能写成玩家已在正常主链使用过全部三级能力。当前不把补三级后内容列为 Runtime 必做项。

## Fighter

保留 Second Wind、Action Surge、Tactical Mind、Sap 及二级的 Defense／Dueling 选择。三级固定 Champion，扩展重击参与攻击判定，Remarkable Athlete 的先攻／Athletics 部分有实现；重击后免机会攻击移动的部分未开放。不是完整 Champion。

## Rogue

Sneak Attack 由武器条件、优势／盟友支持和每回合标记判定；Vex 影响后续对应攻击。Cunning Action 当前为附赠动作 Dash / Disengage，不包含完整 Hide。

三级有 Steady Aim 和 Fast Hands 处理器。trial_winch 在构造的三级遭遇中消费附赠动作并施加有界减速；正常主链的守印考验发生在二级，故没有据此证明三级 Fast Hands 的正常冒险可达性。Second-Story Work 当前只记录攀爬速度／跳跃属性，不构成完整环境规则。

## Wizard

有限实现集合：Ray of Frost；Mage Armor、Magic Missile、Shield；Blur、Scorching Ray。spellbook 中其他名字不代表可准备或可施放。准备窗口、容量、法术位和 Arcane Recovery 由规则约束；组件检查目前覆盖固定构筑的法器条件，不代表所有组件／占手情况。

Shield 在符合条件的命中后、伤害前保存反应窗口，玩家通过结构化 react 选择继续，复用原攻击骰。Blur 的专注、受伤豁免和相关劣势有有限实现；二环及 Evoker 测试不等于正常主链已有三级后施法流程。

升级不隐含免费治疗当前 HP。具体资源与动作语义以代码及对应测试为准，本轮不重新宣称完整规则审计通过。

## 共享状态与旧存档

party:<id> 保存 1–3 独立身份的成员、battle、奖励账本、休息请求与共享时间；资格通过 Runtime 0.14.0 的授权专用查询检查。只验证共享战斗、回合控制和休息共识，不代表完整多人探索、信息交流或公裁系统。

world/function/view 合同为 v2，state_version 保持 1，旧 G1 Fighter 通过兼容 schema 与惰性规范化延续，下一次真实写入才持久化新字段。旧已完成守印奖励补为 600 XP，不重建身份、切职业或免费治疗。

未实现的完整法术、远程装备、Hide/Search/Help/Ready、死亡救助、多人战役和更高等级不作为 Runtime 的基础规则缺口。后续是否扩展由独立世界需求决定。来源与许可仍见 NOTICE / srd-source，测试证据见 [G2_VALIDATION](G2_VALIDATION.md)。
