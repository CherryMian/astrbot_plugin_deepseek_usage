"""
AstrBot 插件：DeepSeek 余额与用量查询

指令（仅管理员私聊）：
  /balance  查询账户余额（需 API Key）
  /cost     近七天花费图表（需平台 Token）

LLM 函数工具（Function Calling）：
  query_deepseek_balance  查询 DeepSeek 余额（仅限管理员，非管理员拒绝）
  query_deepseek_cost     查询 DeepSeek 近期花费明细（仅限管理员，非管理员拒绝）

可视化视图 (Plugin View)：
  views/dashboard  提供一键复制控制台提取脚本、凭据在线修改与验证、实时数据看板

配置项：deepseek_api_key 和 platform_token。
"""

import os
from datetime import datetime, timezone, timedelta

import aiohttp
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp

try:
    from astrbot.api.web import error_response, json_response, request
except ImportError:
    error_response = None
    json_response = None
    request = None

PLUGIN_NAME = "astrbot_plugin_deepseek_usage"


class DeepSeekUsagePlugin(Star):
    """DeepSeek 余额与用量查询插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._chart_dir = os.path.join("data", "deepseek_usage_charts")
        os.makedirs(self._chart_dir, exist_ok=True)

        # 注册 Web API 用于可视化控制台
        if hasattr(self.context, "register_web_api") and json_response is not None:
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/status",
                self.web_get_status,
                ["GET"],
                "获取当前配置、余额与花费概览",
            )
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/config/save",
                self.web_save_config,
                ["POST"],
                "保存并更新插件配置",
            )
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/test",
                self.web_test_connection,
                ["POST"],
                "测试 API Key 和 Token 连接",
            )

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """检查发送者是否具有管理员权限"""
        if event.is_admin():
            return True
        sender_id = str(event.get_sender_id()).strip()
        admins = [
            str(x).strip()
            for x in self.context.astrbot_config.get("admins_id", [])
        ]
        return sender_id in admins

    # ━━━━━━━━━━━━━ /balance ━━━━━━━━━━━━━

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @filter.command("balance")
    async def cmd_balance(self, event: AstrMessageEvent):
        """查询 DeepSeek 账户余额"""
        api_key = self.config.get("deepseek_api_key", "").strip()
        if not api_key:
            yield event.plain_result("⚠️ 请先在 WebUI 插件配置中填写 deepseek_api_key")
            return

        try:
            data = await self._api_get(
                "https://api.deepseek.com/user/balance",
                bearer=api_key,
            )
        except Exception as e:
            yield event.plain_result(f"❌ 查询余额失败: {e}")
            return

        is_available = data.get("is_available", False)
        lines = [
            "💰 DeepSeek 账户余额",
            f"状态: {'✅ 可用' if is_available else '❌ 不可用'}",
        ]
        for info in data.get("balance_infos", []):
            cur = info.get("currency", "?")
            sym = "¥" if cur == "CNY" else "$"
            lines.append(
                f"\n  [{cur}]"
                f"\n  总可用: {sym}{float(info.get('total_balance', 0)):.2f}"
                f"\n  赠金:   {sym}{float(info.get('granted_balance', 0)):.2f}"
                f"\n  充值:   {sym}{float(info.get('topped_up_balance', 0)):.2f}"
            )
        yield event.plain_result("\n".join(lines))

    # ━━━━━━━━━━━━━ /cost ━━━━━━━━━━━━━

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @filter.command("cost")
    async def cmd_cost(self, event: AstrMessageEvent):
        """查看近七天花费图表"""
        token = self.config.get("platform_token", "").strip()
        if not token:
            yield event.plain_result(
                "⚠️ 请先在 WebUI 插件配置中填写 platform_token，"
                "配置项旁有提取方法说明。"
            )
            return

        bj = timezone(timedelta(hours=8))
        now = datetime.now(bj)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = today - timedelta(days=6)
        end = today + timedelta(days=1)
        start_ts, end_ts = int(start.timestamp()), int(end.timestamp())

        try:
            raw = await self._api_get(
                "https://platform.deepseek.com/api/v0/usage/by_api_key/cost",
                bearer=token,
                params={"start": start_ts, "end": end_ts, "tz": 28800},
                platform=True,
            )
        except TokenExpiredError:
            yield event.plain_result(
                "🔑 Token 已过期，请在 WebUI 插件配置中重新粘贴 platform_token，"
                "配置项旁有提取方法说明。"
            )
            return
        except Exception as e:
            yield event.plain_result(f"❌ 查询花费失败: {e}")
            return

        daily = self._parse_costs(raw, start_ts, end_ts, bj)
        if not any(daily.values()):
            yield event.plain_result("📊 近七天没有花费记录。")
            return

        chart_path = self._draw_chart(daily)
        total = sum(daily.values())
        avg = total / len(daily)
        peak = max(daily, key=daily.get)
        summary = (
            f"📊 近 7 天花费统计\n\n"
            f"总花费: ¥{total:.4f}\n"
            f"日均:   ¥{avg:.4f}\n"
            f"最高:   {peak} ¥{daily[peak]:.4f}"
        )
        yield event.chain_result([
            Comp.Plain(summary),
            Comp.Image.fromFileSystem(chart_path),
        ])

    # ━━━━━━━━━━━━━ LLM Tools ━━━━━━━━━━━━━

    @filter.llm_tool(name="query_deepseek_balance")
    async def query_deepseek_balance(self, event: AstrMessageEvent):
        """查询当前 DeepSeek API 账号的可用余额、充值余额和赠金余额。此操作涉及隐私与资产信息，仅限管理员查询。非管理员请求将被拒绝。"""
        if not self._is_admin(event):
            return (
                f"权限拒绝：当前请求者 (用户ID: {event.get_sender_id()}) 不是机器人管理员。"
                "出于账户与资产安全考虑，只有管理员有权查询 DeepSeek 余额。"
                "请直接告知用户权限不足，拒绝提供余额信息。"
            )

        api_key = self.config.get("deepseek_api_key", "").strip()
        if not api_key:
            return "错误：插件未配置 deepseek_api_key，请提示管理员在 WebUI 中配置。"

        try:
            data = await self._api_get(
                "https://api.deepseek.com/user/balance",
                bearer=api_key,
            )
        except Exception as e:
            return f"查询 DeepSeek 余额失败：{e}"

        is_available = data.get("is_available", False)
        status_desc = "正常可用" if is_available else "不可用/欠费"
        res_lines = [f"DeepSeek 账户状态: {status_desc}"]
        for info in data.get("balance_infos", []):
            cur = info.get("currency", "CNY")
            total = float(info.get("total_balance", 0))
            granted = float(info.get("granted_balance", 0))
            topped_up = float(info.get("topped_up_balance", 0))
            res_lines.append(
                f"- [{cur}] 总可用余额: {total:.2f} {cur}（充值余额: {topped_up:.2f} {cur}，赠金余额: {granted:.2f} {cur}）"
            )
        return "\n".join(res_lines)

    @filter.llm_tool(name="query_deepseek_cost")
    async def query_deepseek_cost(self, event: AstrMessageEvent, days: int = 7):
        """查询 DeepSeek API 账号近期的每日花费金额、用量明细与花费统计。此操作涉及隐私与账单数据，仅限管理员查询。非管理员请求将被拒绝。

        Args:
            days(number): 查询的天数范围，默认为 7 天（即近一周），范围 1 到 30
        """
        if not self._is_admin(event):
            return (
                f"权限拒绝：当前请求者 (用户ID: {event.get_sender_id()}) 不是机器人管理员。"
                "出于账户与账单安全考虑，只有管理员有权查询 DeepSeek 花费明细。"
                "请直接告知用户权限不足，拒绝提供花费信息。"
            )

        token = self.config.get("platform_token", "").strip()
        if not token:
            return "错误：插件未配置 platform_token，请提示管理员在 WebUI 中配置。"

        days = max(1, min(30, int(days)))
        bj = timezone(timedelta(hours=8))
        now = datetime.now(bj)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = today - timedelta(days=days - 1)
        end = today + timedelta(days=1)
        start_ts, end_ts = int(start.timestamp()), int(end.timestamp())

        try:
            raw = await self._api_get(
                "https://platform.deepseek.com/api/v0/usage/by_api_key/cost",
                bearer=token,
                params={"start": start_ts, "end": end_ts, "tz": 28800},
                platform=True,
            )
        except TokenExpiredError:
            return "错误：平台 Token 已过期，请提示管理员在 WebUI 插件配置中重新更新 platform_token。"
        except Exception as e:
            return f"查询 DeepSeek 花费数据失败：{e}"

        daily = self._parse_costs(raw, start_ts, end_ts, bj)
        total = sum(daily.values())
        avg = total / len(daily) if daily else 0
        peak = max(daily, key=daily.get) if daily else ""

        res_lines = [
            f"DeepSeek 近 {len(daily)} 天花费统计（货币: CNY）：",
            f"- 总花费: ¥{total:.4f}",
            f"- 日均花费: ¥{avg:.4f}",
            f"- 最高单日: {peak} (¥{daily.get(peak, 0):.4f})",
            "每日明细:",
        ]
        for d, c in daily.items():
            res_lines.append(f"  * {d}: ¥{c:.4f}")
        return "\n".join(res_lines)

    # ━━━━━━━━━━━━━ Web API (用于 Dashboard 视图) ━━━━━━━━━━━━━

    async def web_get_status(self):
        """Web API: 获取当前配置、余额与近七天花费统计"""
        api_key = self.config.get("deepseek_api_key", "").strip()
        token = self.config.get("platform_token", "").strip()

        balance_data = None
        if api_key:
            try:
                raw_b = await self._api_get(
                    "https://api.deepseek.com/user/balance",
                    bearer=api_key,
                )
                balance_data = {
                    "is_available": raw_b.get("is_available", False),
                    "info": raw_b.get("balance_infos", []),
                }
            except Exception as e:
                logger.warning(f"[DeepSeek] Web API 查询余额失败: {e}")

        cost_data = None
        if token:
            try:
                bj = timezone(timedelta(hours=8))
                now = datetime.now(bj)
                today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_ts = int((today - timedelta(days=6)).timestamp())
                end_ts = int((today + timedelta(days=1)).timestamp())
                raw_c = await self._api_get(
                    "https://platform.deepseek.com/api/v0/usage/by_api_key/cost",
                    bearer=token,
                    params={"start": start_ts, "end": end_ts, "tz": 28800},
                    platform=True,
                )
                daily = self._parse_costs(raw_c, start_ts, end_ts, bj)
                total = sum(daily.values())
                avg = total / len(daily) if daily else 0
                peak = max(daily, key=daily.get) if daily else "-"
                cost_data = {
                    "total": total,
                    "avg": avg,
                    "peak": peak,
                    "peak_val": daily.get(peak, 0) if peak != "-" else 0,
                    "daily": daily,
                }
            except Exception as e:
                logger.warning(f"[DeepSeek] Web API 查询花费失败: {e}")

        return json_response({
            "config": {
                "deepseek_api_key": api_key,
                "platform_token": token,
            },
            "balance": balance_data,
            "cost": cost_data,
        })

    async def web_save_config(self):
        """Web API: 保存并更新插件配置"""
        try:
            payload = await request.json(default={})
        except Exception:
            payload = {}
        if not payload and hasattr(request, "get_json"):
            payload = await request.get_json() or {}

        if "deepseek_api_key" in payload:
            self.config["deepseek_api_key"] = str(payload["deepseek_api_key"]).strip()
        if "platform_token" in payload:
            self.config["platform_token"] = str(payload["platform_token"]).strip()

        if hasattr(self.config, "save_config"):
            try:
                self.config.save_config()
            except Exception as e:
                logger.warning(f"[DeepSeek] 保存配置失败: {e}")

        return json_response({"status": "ok", "saved": True})

    async def web_test_connection(self):
        """Web API: 验证凭据有效性"""
        try:
            payload = await request.json(default={})
        except Exception:
            payload = {}
        if not payload and hasattr(request, "get_json"):
            payload = await request.get_json() or {}

        api_key = str(payload.get("deepseek_api_key", "")).strip() or self.config.get("deepseek_api_key", "").strip()
        token = str(payload.get("platform_token", "")).strip() or self.config.get("platform_token", "").strip()

        balance_ok = False
        balance_err = ""
        if api_key:
            try:
                await self._api_get("https://api.deepseek.com/user/balance", bearer=api_key)
                balance_ok = True
            except Exception as e:
                balance_err = str(e)
        else:
            balance_err = "未填写 API Key"

        cost_ok = False
        cost_err = ""
        if token:
            try:
                bj = timezone(timedelta(hours=8))
                now = int(datetime.now(bj).timestamp())
                await self._api_get(
                    "https://platform.deepseek.com/api/v0/usage/by_api_key/cost",
                    bearer=token,
                    params={"start": now - 86400, "end": now, "tz": 28800},
                    platform=True,
                )
                cost_ok = True
            except Exception as e:
                cost_err = str(e)
        else:
            cost_err = "未填写 Platform Token"

        return json_response({
            "balance_ok": balance_ok,
            "balance_error": balance_err,
            "cost_ok": cost_ok,
            "cost_error": cost_err,
        })

    # ━━━━━━━━━━━━━ HTTP ━━━━━━━━━━━━━

    async def _api_get(
        self,
        url: str,
        bearer: str,
        params: dict | None = None,
        platform: bool = False,
    ) -> dict:
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Accept": "application/json",
        }
        if platform:
            headers["x-client-platform"] = "web"
            headers["User-Agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    raise TokenExpiredError()
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")
                return await resp.json()

    # ━━━━━━━━━━━━━ 解析 ━━━━━━━━━━━━━

    def _parse_costs(
        self, raw: dict, start_ts: int, end_ts: int, tz
    ) -> dict[str, float]:
        daily: dict[str, float] = {}
        data_list = raw.get("data", {}).get("biz_data", {}).get("data", [])
        if data_list:
            for series in data_list[0].get("series", []):
                for b in series.get("buckets", []):
                    ts = b.get("time", 0)
                    if ts < start_ts or ts >= end_ts:
                        continue
                    try:
                        cost = float(b.get("cost", "0"))
                    except (ValueError, TypeError):
                        cost = 0.0
                    key = datetime.fromtimestamp(ts, tz=tz).strftime("%m-%d")
                    daily[key] = daily.get(key, 0.0) + cost

        base = datetime.fromtimestamp(start_ts, tz=tz)
        days_count = max(1, (end_ts - start_ts) // 86400)
        for i in range(days_count):
            k = (base + timedelta(days=i)).strftime("%m-%d")
            daily.setdefault(k, 0.0)
        return dict(sorted(daily.items()))

    # ━━━━━━━━━━━━━ 图表 ━━━━━━━━━━━━━

    def _draw_chart(self, daily: dict[str, float]) -> str:
        plt.rcParams["font.sans-serif"] = [
            "Noto Sans CJK SC", "Noto Serif CJK SC", "SimHei", "Microsoft YaHei", "DejaVu Sans",
        ]
        plt.rcParams["axes.unicode_minus"] = False

        dates, costs = list(daily.keys()), list(daily.values())
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
        mx = max(costs) if costs else 1

        colors = []
        for c in costs:
            r = c / mx if mx > 0 else 0
            colors.append((0.2 + 0.3 * (1 - r), 0.4 + 0.3 * (1 - r),
                           0.95 - 0.3 * (1 - r), 0.85))

        bars = ax.bar(dates, costs, color=colors, edgecolor="#4a7ccc",
                      linewidth=0.8, width=0.6)
        for bar, c in zip(bars, costs):
            if c > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + mx * 0.02,
                        f"¥{c:.2f}", ha="center", va="bottom",
                        fontsize=9, fontweight="bold", color="#333")

        ax.set_title("DeepSeek API 近 7 天花费",
                      fontsize=14, fontweight="bold", pad=15)
        ax.set_xlabel("日期", fontsize=11)
        ax.set_ylabel("花费 (CNY ¥)", fontsize=11)
        ax.set_ylim(0, mx * 1.25 if mx > 0 else 1)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#ccc")
        ax.tick_params(colors="#666")
        ax.yaxis.grid(True, alpha=0.3, linestyle="--")
        ax.set_axisbelow(True)

        ax.text(0.98, 0.95, f"总计: ¥{sum(costs):.2f}",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=11, fontweight="bold", color="#4a7ccc",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#e8f0fe",
                          edgecolor="#4a7ccc", alpha=0.8))
        plt.tight_layout()

        path = os.path.join(self._chart_dir, "cost_7days.png")
        fig.savefig(path, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path

    async def terminate(self):
        pass


class TokenExpiredError(Exception):
    """平台 Token 过期"""
    pass
