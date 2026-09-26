# 当前世界包架构

源码基线：`e9d345b3` / 0.3.0a1。依赖 Agent World 0.14.0 / `b65ddabea74b75a387e90ebcadcba0df680588cf`。实验范围见 [GAME_DESIGN](GAME_DESIGN.md)，这里不维护另一份产品路线图。

## 分层与结构化执行

rules.py 实现有限机械规则；engine.py 处理遭遇、移动预算、回合和待决反应；campaign_content / characters 提供有限作者内容；campaign.py 处理单人推进；campaign_world.py 以 SDK 暴露 adventure.*；coop.py 保存共享 party 及其函数。服务器组合现有 HTTP/MCP 与页面，不另写鉴权协议。

客户端提交符合函数 schema 的 JSON 参数，不提交权威骰点、伤害或奖励。文本是数据，不从自然语言推断动作或确认。规则复制输入并验证，SDK 在事务中提交状态与结果。脚本 NPC 由世界代码有限推进，在真人决定点停止，不调用模型或冒充玩家。

## 三类不同标识

operation_id 去重同一次请求；revision / turn_id / window_id 拒绝不再适用的动作；持久 rewards 的来源 ID 防止不同请求重复领取。三者不能互相替代，不能靠统一网络重试 ID 自动解决业务唯一性。

待决反应保存原攻击或移动上下文、反应者及窗口 ID。后续结构化操作验证窗口再继续，不靠挂起协程保存过程，不重掷已经接受的攻击。原回执保留当时提交结果，最终位置／效果由后续状态和事件确认。

## 身份与世界状态

用户凭据和私人 Agent 记忆不保存在世界内容中。当前依赖的凭据仍绑定 universe，这是实现限制，不改变统一跨世界身份的产品目标。provision 为本地操作员配置工具，不是新的用户所有权系统。

M1 的双席位夹具与 G1/G2 的单人 campaign 使用不同 universe。每个 campaign 挂接认证 role_id；party 是多个角色共享的独立状态，不把多份单人存档当作多人世界。

party 授权通过 `authorization_state(scope,key)` 读取成员依据，不使用 legacy ctx.conn。它只在 state_authorizer 回调内可用；成员资格与具体行动权限仍由世界规则定义。此用法不表示 Runtime 所有 legacy raw SQL 路径已经安全，底座已知偏差由其现行合同记录。

G2 的 world/function/view 合同为 v2，**state_version 仍为 1**。接受旧 G1 顶层形状，读取时按原 Fighter 惰性规范化，下次真实写入持久化新字段；不是安装时枚举全库的 v1→v2 数据迁移。旧守印奖励从 0 XP 解释为 600 XP，不换角色或免费治疗。

## 观察、缓存与表现

campaign 使用按角色授权的 ViewSpec timeline 与 EventSpec / PresentationCue；快照及锚点由同次观察取得。私密 campaign 不发布到 M1 的公开流。未探索完整房间和其他角色状态不进入当前投影，前端隐藏不代替服务器授权。

世界 payload 将已确认语义映射到占位资源。两套资源包使用同一事实；动画不决定伤害、奖励或回合完成。scene 数据帧用于提交后的表现，不是持续写入渲染帧；终态与待决信息仍须从持久 campaign 状态恢复。

静态几何与返回投影分离复制，避免调用者修改结果污染规则常量。缓存过期时重取获准状态，不伪造历史。页面凭据只用于鉴权；退出／撤销清理页面副本，不承诺清除用户已保存的外部信息。

## 当前限制

三职业完整主链可到三级，但主链随后结束。部分三级机制只有人工构造状态的规则测试，不代表正常流程可用。party 仍是共享战斗／休息预览；获准快照、共享状态和脚本测试不证明长期自主 Agent 协作。规则边界与证据只分别在 G2_RULES、G2_VALIDATION 维护。
