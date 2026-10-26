# astrbot_plugin_deepseek_usage

DeepSeek API 余额与用量查询，适用于 AstrBot + NapCat (QQ)。

## 指令

| 指令 | 说明 | 需要 |
|------|------|------|
| `/balance` | 查询账户余额 | API Key |
| `/cost` | 近 7 天花费图表 | 平台 Token |

仅管理员私聊可用。

## LLM 函数工具 (Function Calling)

本插件提供 2 个供 AI 模型调用的函数工具，用户直接自然语言对话（如“帮我查下deepseek余额”或“最近花了多少token费用”）时，模型可自主调用工具并汇总回复：

| 工具名 | 说明 | 权限控制 |
|--------|------|----------|
| `query_deepseek_balance` | 查询当前 DeepSeek API 账号可用余额、充值余额与赠金 | **严格仅限管理员**，非管理员请求返回明确拒绝提示 |
| `query_deepseek_cost` | 查询 DeepSeek 账号近期的每日花费金额与统计（默认 7 天） | **严格仅限管理员**，非管理员请求返回明确拒绝提示 |

## 配置

WebUI → 插件 → DeepSeek 余额与用量查询 → 配置：

| 配置项 | 说明 |
|--------|------|
| `deepseek_api_key` | API Key，从 [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) 获取 |
| `platform_token` | 平台 Token，WebUI 配置项旁有提取脚本说明 |

## WebUI 控制台 (Plugin View)

插件提供了专属的 WebUI 管理视图（**扩展功能 → DeepSeek 控制台**）：
- **一键复制提取脚本**：点击按钮即可将控制台提取代码写入剪贴板，带有友好指引与 Toast 提示；
- **在线凭据管理与验证**：直接在线修改 API Key 与 Token，并支持单键测试连接；
- **实时看板**：直接查看当前总余额、充值/赠金明细以及近 7 天每日消费金额进度条。

## 安装

`astrbot_plugin_deepseek_usage` 放入 AstrBot 的 `data/plugins/`，重启或 WebUI 重载。

## 依赖

- `aiohttp`
- `matplotlib`
