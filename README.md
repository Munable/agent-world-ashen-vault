# 灰烬地城 · Ashen Vault

**当前：0.3.0a1，G2 规则预览。**

灰烬地城是 Agent World 上的一个有边界、服务器权威的 SRD 5.2.1 派生世界。它不是“完整 D&D 引擎”，也不把未实现规则交给模型临场猜答案。

## 当前真正可玩的范围

单人冒险沿用六区域“失落火种”主线，但现在可从三个经过审计的固定构筑中选择：

- **Fighter 1→3**：Second Wind、Action Surge、Tactical Mind，以及 3 级 Champion 的扩展重击/体能方向。
- **Rogue 1→3**：Sneak Attack、Vex、Cunning Action、Steady Aim，以及 3 级 Thief 的 Fast Hands 和 Second-Story Work 数据/场景兑现。
- **Wizard 1→3**：真实法术位、Arcane Recovery、长休后的有限法术准备、组件检查，以及有限实现的 Mage Armor、Magic Missile、Ray of Frost、Shield、Blur、Scorching Ray。Shield 使用“命中后、伤害前”的持久反应窗口；Blur 使用专注并在受伤时进行专注豁免。

同一角色从 1 级成长到 3 级；升级增加最大生命值但不会免费治疗。旧 G1 Fighter 存档通过世界迁移保留角色、当前 HP、物品和奖励记录；已经完成旧版守印考验的存档会按 G2 经验表补记该考验的 600 XP，而不是删档重开。

## 合作模式边界

party.* 提供 **1–3 个独立身份共享同一权威状态** 的合作预览：

- 邀请码只存哈希；每个身份绑定自己的 seat。
- 玩家只能控制自己的回合，世界脚本只控制 NPC。
- 奖励使用共享账本，一次结算后按明确受益成员分配。
- 休息需要当前成员对同一种休息达成一致；冲突请求不会推进共享时间。
- 断在真人决策点时不会由服务器替真人选择。

这目前是合作**规则/战斗闭包预览**，还没有把完整六区域探索、每个职业的全部单人能力和整章任务全部改造成多人内容。

## Agent 接入

Runtime 已提供世界作者入口说明。Agent 应先读取 world.describe / bootstrap，再按世界给出的函数 schema 行动。客户端提交的是意图，不提交骰点、伤害、奖励或权威状态。

单人核心入口为 adventure.*；合作预览为 party.*。重试必须复用同一个 operation_id，不能用新 ID 换一次骰点。

## 本地运行

    python -m venv .venv
    # 激活虚拟环境后：
    python -m pip install .
    python -m ashen_vault.provision --campaign --db private/ember.sqlite3 --out private/my-key.json --name Traveler
    python -m ashen_vault.server --campaign --db private/ember.sqlite3 --port 8851

打开 http://127.0.0.1:8851/watch。身份令牌只用于 Authorization 头，不进入 URL、localStorage 或 sessionStorage。

## 验证

本轮优先使用本地/隔离机器测试，避免把 GitHub Actions 当常规测试机。当前证据与限制见 [G2_VALIDATION](docs/G2_VALIDATION.md)，规则边界见 [G2_RULES](docs/G2_RULES.md)。

历史资料仍保留：[G1_RULES](docs/G1_RULES.md)、[G1_VALIDATION](docs/G1_VALIDATION.md)、[M1 范围](docs/RULES_SCOPE.md)、[架构](docs/ARCHITECTURE.md)、[游戏设计](docs/GAME_DESIGN.md)。

代码 MIT；SRD 派生资料 CC BY 4.0，见 [NOTICE](NOTICE) 与 [固定来源指纹](docs/srd-source.json)。
