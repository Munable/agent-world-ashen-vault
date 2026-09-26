# 灰烬地城 · Ashen Vault

当前代码：0.3.0a1 / G2 Phase A，复核基线 `e9d345b3`。

灰烬地城是 Agent World Runtime 的规则与恢复验证世界，保留现有六区域单人冒险、三职业成长和共享状态合作预览。**它不是 Runtime 的通用模板，也不再把完整 RPG 作为验证底座的先决条件。** 当前方向见[实验定位](docs/GAME_DESIGN.md)和[后续范围](docs/ROADMAP.md)。

## 已有范围与证据边界

Fighter / Rogue / Wizard 可沿现有主链从 1 级升级到 3 级。状态、资源、随机结果、回执、待决反应和观察使用服务器规则；模型与玩家决策在外部。

当前主链在守印考验后结束，再应用三级升级；不提供后续三级冒险。三级特性的处理器／夹具测试不等于正常主链已经使用过这些特性。Champion / Thief / Evoker 与法术实现均有边界，见 [G2_RULES](docs/G2_RULES.md)。

`party.*` 是 1–3 独立身份共享状态的战斗／休息预览，不是完整多人六区域战役。最终浏览器主链为 Fighter；三职业交叉探测是固定脚本，不能当成三职业全部浏览器体验或自主 Agent 验证。详见 [G2_VALIDATION](docs/G2_VALIDATION.md)。

## 运行

```sh
python -m venv .venv
# 激活虚拟环境后：
python -m pip install .
python -m ashen_vault.provision --campaign --db private/ember.sqlite3 --out private/my-key.json --name Traveler
python -m ashen_vault.server --campaign --db private/ember.sqlite3 --port 8851
```

打开 `http://127.0.0.1:8851/watch`，使用私密身份文件中的 identity_token。令牌只用于请求鉴权，不进入 URL 或浏览器持久存储。单人 universe 为 `ashen-vault-ember`；不带 --campaign 的 M1 为 `ashen-vault`，两种模式不能混用存档。

[统一产品目标](https://github.com/Munable/agent-world/blob/main/PRODUCT_POSITIONING.md)是用户持有跨世界通用令牌；此包当前固定依赖的 Runtime 0.14.0 仍验证 universe 绑定凭据，不能描述成目标已完成。

## 文档与维护

[架构](docs/ARCHITECTURE.md)只描述当前分层；[G2 规则](docs/G2_RULES.md)只列支持范围；[G2 验证](docs/G2_VALIDATION.md)只说明证据。历史 M1/G1 的规则与验证文件保留作基线，不成为新增内容的强制路线图。

维护现有回归并优先复现 Runtime 缺陷；默认不增加职业、地图或法术。日常测试使用本地或可控机器，纯文档更新不重复运行计费 CI。

代码 MIT；SRD 派生资料 CC BY 4.0，见 [NOTICE](NOTICE) 与 [来源指纹](docs/srd-source.json)。
