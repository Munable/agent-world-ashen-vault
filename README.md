# 灰烬地城 · Ashen Vault

**状态：0.1.0a1 / M1 近战规则验收场。不是完整 D&D 游戏，不宣称已实现整个 SRD。**

这是 Agent World 的第二个独立世界包。基于 SRD 5.2.1 的有限规则实现，用于验证服务器裁决、回合、反应窗口、事务随机数、同身份续接和只读前端。没有修改通用内核，也没有复用灯溪镇的任务、地图或 NPC 逻辑。

目标仍是三个 3 级预设职业与一座原创地城；目前只开放两个固定的近战 NPC 数据配置，避免把缺少职业特性的角色伪装成合法职业。计划和验收门槛见 [ROADMAP](docs/ROADMAP.md)。

## 安装和运行

```sh
python -m venv .venv
# 激活虚拟环境后：
python -m pip install .
python -m ashen_vault.provision --db private/ashen.sqlite3 --out private/warden-key.json --name Warden
python -m ashen_vault.provision --db private/ashen.sqlite3 --out private/sentinel-key.json --name Sentinel
python -m ashen_vault.server --db private/ashen.sqlite3 --port 8850
```

浏览器打开 `http://127.0.0.1:8850/watch`，只读查看场景与裁决。身份文件属于用户，必须自行私密保存。配置工具只输出完成提示，不打印身份令牌，不覆盖已有文件。当前没有网站注册、找回、完整角色创建器或自动控制 NPC 的后台模型。

给两个可信 Agent 各自提供一份私密身份文件和 `/agent` 地址。它们各自验证 `/v1/whoami`，读取 `/v1/bootstrap` 和 discovery，自行选择一个空位 `vault.join`。只有两个身份都加入后才可 `vault.begin`。MCP 地址是 `/mcp`，HTTP 接口由同一个已安装内核提供。

当前提供：`join`、`look`、`begin`、`move`、`attack`、`dash`、`dodge`、`disengage`、`drop_prone`、`stand`、`react`、`end_turn`。只有 `look` 是读取；所有写入都使用唯一 operation_id，重试使用原 ID 和参数。`turn_id` 是新操作的回合前置条件，不能用上轮指令操作新回合。

## 最重要的行为边界

Agent 提交行动目标，不提交命中、伤害、骰点或自行声明的优势。服务器生成并记录骰点。普通行动受当前回合约束，但机会攻击通过显式反应窗口允许在本人回合之外发生。移动会在离开触及范围之前暂停；“等待反应”不是“已经移动完成”。

没有现实时间超时自动跳过回合，也没有默认自动放弃反应。断线后原身份可以继续处理原窗口。当前是两个用户控制的 NPC 近战配置，不是两个自主 LLM，也不是已完成的多职业冒险。

## 文档与验收

- [规则范围与逐条来源](docs/RULES_SCOPE.md)：已暴露、仅基础函数、未实现、场景裁定分开说明。
- [架构与身份边界](docs/ARCHITECTURE.md)：世界、内核、HTTP/MCP、公开前端的职责。
- [分阶段计划](docs/ROADMAP.md)：原始目标与后续职业、法术、完整地城验收。
- [验证记录](docs/VALIDATION.md)：真实执行结果，不把脚本测试包装成模型实测。

```sh
python -m unittest discover -s tests -q
python -m pip install playwright
python -m playwright install chromium
python tools/check_browser.py
python -m pip wheel --no-deps --wheel-dir dist .
```

代码使用 MIT 许可；SRD 派生规则资料适用 CC BY 4.0，见 [NOTICE](NOTICE) 与 [来源记录](docs/srd-source.json)。这是独立原创场景，不代表官方产品、授权认证或完整规则兼容认证。
