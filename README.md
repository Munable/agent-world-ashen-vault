# 灰烬地城 · Ashen Vault

**当前：0.2.0a2。保留 M1 规则验收场，继续收口 G1 单人冒险可玩预览。**

G1 已有一个角色从 1→2 级的实际链路：六区域探索、交涉/付费/战斗/特定潜行通行、补给购买与箱子、火种交还、经验与持久领奖、休息与资源、升级选择、用新能力完成后续考验。固定 Halfling Fighter 构筑中的 Brave、Naturally Stealthy、矮人语和木匠工具现在都有受规则约束的作者场景，而不是只挂在角色卡上。敌人由规则脚本驱动，玩家不需要第二个敌方账号。

前端用两套几何占位资源表现移动、攻击/未命中、血量、反应、奖励和升级；同一服务器事件轨迹可以替换资源包，规则不变。不是完整三职业游戏、完整 SRD 实现、公开运营版本或“任意素材零适配”产品。

## 运行单人冒险

```sh
python -m venv .venv
# 激活虚拟环境后安装：
python -m pip install .
python -m ashen_vault.provision --campaign --db private/ember.sqlite3 --out private/my-key.json --name Traveler
python -m ashen_vault.server --campaign --db private/ember.sqlite3 --port 8851
```

打开 `http://127.0.0.1:8851/watch`。把自己保存的身份文件中的 `identity_token` 私下粘贴到连接框。它只在当前页面内存中用于向本服务发送认证头，不进入 URL、localStorage 或 sessionStorage。刷新后重新提供原令牌，恢复同一角色；不自动新建替身。

Agent 可读取 `/agent`，验证 `/v1/whoami`，读取 `/v1/bootstrap`，再发现 `adventure.` 工具。`adventure.look` 返回获准的当前状态、可用操作和 `revision`；普通战斗操作另带当前 `turn_id`。HTTP 和 MCP `/mcp` 使用相同服务器规则。

**G1 universe 是 `ashen-vault-ember`，M1 是 `ashen-vault`。** 令牌可以交给不同可信客户端，但不能跨 universe 越权。示例使用不同数据库文件，避免把旧测试场误当成新的冒险存档。

## 保留原 M1 模式

```sh
python -m ashen_vault.provision --db private/melee.sqlite3 --out private/warden-key.json --name Warden
python -m ashen_vault.provision --db private/melee.sqlite3 --out private/sentinel-key.json --name Sentinel
python -m ashen_vault.server --db private/melee.sqlite3 --port 8850
```

默认模式仍是两个用户分别控制近战 NPC 的规则夹具，用于回归原先的回合、机会攻击和幂等合同。它不是 G1 的敌人控制方式。

## 文档

[设计目标](docs/GAME_DESIGN.md) 与 [实施顺序](docs/ROADMAP.md) 定义完整游戏方向。
[当前 G1 规则范围](docs/G1_RULES.md) 明确固定构筑、作者裁定、已开放能力和缺项。
[本轮测试与评价](docs/G1_VALIDATION.md) 区分真实 HTTP/MCP/浏览器、确定性策略探索和没有完成的模型/真人验证。
[架构](docs/ARCHITECTURE.md) 说明内核与世界二次开发的分工。
原 [M1 范围](docs/RULES_SCOPE.md) 和 [M1 验证记录](docs/VALIDATION.md) 是历史基线，不改写成新成绩。

## 验证命令

```sh
python -m unittest discover -s tests -q
python -m pip install playwright
python -m playwright install chromium
python tools/check_browser.py
python tools/check_campaign_browser.py
node --test tests/campaign_player.test.mjs
python tools/probe_campaign.py --count 300
python tools/explore_campaign.py
python -m pip wheel --no-deps --wheel-dir dist .
```

JavaScript 测试中的真实轨迹来自 `check_campaign_browser.py`；没有轨迹时相关测试明确跳过，不用合成数据冒充浏览器证据。建议使用维护中的 Python 3.13/3.14 补丁版本。本机旧解释器的异常及独立复核情况见本轮验证记录，不把一次成功重跑写成已查明根因。

代码 MIT；SRD 派生资料 CC BY 4.0，见 [NOTICE](NOTICE) 与 [固定来源指纹](docs/srd-source.json)。世界、任务、地图与敌人策略原创，不宣称官方授权认证。
