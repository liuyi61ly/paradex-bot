"""
BTC-USDT 套利策略示例
当检测到买一价和卖一价价差为0时，直接反向开仓（利润最大化）
- 检测到价差 → 反向开仓（不做等待平仓）
- 停掉程序时 → 自动平掉所有持仓

费率限制：
  - 每秒: 3 次订单
  - 每分钟: 30 次订单
  - 每小时: 300 次订单
  - 24小时: 1000 次订单

每次反向开仓会产生 2 个订单请求（账户1和账户2各一个订单）
"""
import asyncio
import os
import logging
from collections import deque
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional

# 抑制 httpx 的 HTTP 请求日志（太冗长）
logging.getLogger("httpx").setLevel(logging.WARNING)

from paradex_py import Paradex, ParadexSubkey
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py.common.order import Order, OrderSide, OrderType
from paradex_py.environment import PROD

# 环境变量配置
# 认证模式：l1（传统） 或 subkey（L2-only）
AUTH_MODE = os.getenv("AUTH_MODE", "subkey").lower()

# 账户1配置
ACCOUNT1_L1_ADDRESS = os.getenv("ACCOUNT1_L1_ADDRESS", "")
ACCOUNT1_L1_PRIVATE_KEY = os.getenv("ACCOUNT1_L1_PRIVATE_KEY", "")
ACCOUNT1_L2_ADDRESS = os.getenv("ACCOUNT1_L2_ADDRESS", "")
ACCOUNT1_L2_PRIVATE_KEY = os.getenv("ACCOUNT1_L2_PRIVATE_KEY", "")

# 账户2配置
ACCOUNT2_L1_ADDRESS = os.getenv("ACCOUNT2_L1_ADDRESS", "")
ACCOUNT2_L1_PRIVATE_KEY = os.getenv("ACCOUNT2_L1_PRIVATE_KEY", "")
ACCOUNT2_L2_ADDRESS = os.getenv("ACCOUNT2_L2_ADDRESS", "")
ACCOUNT2_L2_PRIVATE_KEY = os.getenv("ACCOUNT2_L2_PRIVATE_KEY", "")

# 交易配置
MARKET = os.getenv("MARKET", "BTC-USD-PERP")  # 交易市场
MIN_SPREAD_THRESHOLD = Decimal(os.getenv("MIN_SPREAD_THRESHOLD", "0"))  # 最小价差阈值（0表示价差为0）

# 交易频率控制
MIN_TRADE_INTERVAL = float(os.getenv("MIN_TRADE_INTERVAL", "0"))  # 最小交易间隔（秒），0表示无限制

# 资金与杠杆配置
USE_DYNAMIC_SIZE = os.getenv("USE_DYNAMIC_SIZE", "true").lower() == "true"
FUNDS_RATIO = Decimal(os.getenv("FUNDS_RATIO", "0.9"))  # 使用较少账户可用资金的比例（0~1）
TARGET_LEVERAGE = int(os.getenv("TARGET_LEVERAGE", "50"))  # 目标杠杆

# 若不使用动态 sizing，可用固定数量（单位：BTC）
TRADE_SIZE = Decimal(os.getenv("TRADE_SIZE", "0.01"))

# 日志配置
LOG_FILE = os.getenv("LOG_FILE", "FALSE").lower() == "true"

if LOG_FILE:
    from paradex_py.common.file_logging import file_logger
    logger = file_logger
else:
    from paradex_py.common.console_logging import console_logger
    logger = console_logger


# ============================================================
# 速率限制器
# ============================================================

class RateLimiter:
    """API 速率限制器 - 确保不超出 Paradex 的费率限制"""

    # 费率限制配置
    LIMITS = {
        "second": (3, timedelta(seconds=1)),
        "minute": (30, timedelta(minutes=1)),
        "hour": (300, timedelta(hours=1)),
        "day": (1000, timedelta(days=1)),
    }

    def __init__(self):
        self._requests_second: deque[datetime] = deque()
        self._requests_minute: deque[datetime] = deque()
        self._requests_hour: deque[datetime] = deque()
        self._requests_day: deque[datetime] = deque()
        self._total_requests = 0
        self._blocked_requests = 0

    def _cleanup_old_requests(self, deque_: deque[datetime], delta: timedelta) -> None:
        now = datetime.now()
        while deque_ and deque_[0] < now - delta:
            deque_.popleft()

    def _cleanup_all(self) -> None:
        self._cleanup_old_requests(self._requests_second, self.LIMITS["second"][1])
        self._cleanup_old_requests(self._requests_minute, self.LIMITS["minute"][1])
        self._cleanup_old_requests(self._requests_hour, self.LIMITS["hour"][1])
        self._cleanup_old_requests(self._requests_day, self.LIMITS["day"][1])

    def _add_request(self, deque_: deque[datetime]) -> None:
        deque_.append(datetime.now())

    def can_proceed(self) -> tuple[bool, str]:
        self._cleanup_all()
        now = datetime.now()
        for name, (limit, delta) in self.LIMITS.items():
            deque_ = getattr(self, f"_requests_{name}")
            current_count = len(deque_)
            if current_count >= limit:
                if deque_:
                    oldest = deque_[0]
                    wait_time = (oldest + delta) - now
                    if wait_time.total_seconds() > 0:
                        return False, f"{name} 窗口已满 ({current_count}/{limit}), 需等待 {wait_time.seconds + 1} 秒"
        return True, "OK"

    async def acquire(self, timeout: float = 60.0) -> tuple[bool, str, float]:
        can_proceed, reason = self.can_proceed()
        if can_proceed:
            self._add_request(self._requests_second)
            self._add_request(self._requests_minute)
            self._add_request(self._requests_hour)
            self._add_request(self._requests_day)
            self._total_requests += 1
            return True, "OK", 0.0

        wait_seconds = 1.0
        try:
            import re
            numbers = re.findall(r'\d+', reason)
            if numbers:
                wait_seconds = max(1.0, float(numbers[0]))
        except Exception:
            pass

        waited = 0.0
        while waited < timeout:
            await asyncio.sleep(min(wait_seconds, timeout - waited))
            waited += wait_seconds
            can_proceed, reason = self.can_proceed()
            if can_proceed:
                self._add_request(self._requests_second)
                self._add_request(self._requests_minute)
                self._add_request(self._requests_hour)
                self._add_request(self._requests_day)
                self._total_requests += 1
                return True, "OK", waited

        self._blocked_requests += 1
        return False, f"等待超时 ({timeout}秒)", waited

    def get_stats(self) -> dict:
        self._cleanup_all()
        return {
            "second": len(self._requests_second),
            "minute": len(self._requests_minute),
            "hour": len(self._requests_hour),
            "day": len(self._requests_day),
            "total_requests": self._total_requests,
            "blocked_requests": self._blocked_requests,
        }

    def get_usage_percentage(self) -> dict:
        stats = self.get_stats()
        return {
            "second": f"{stats['second']}/{self.LIMITS['second'][0]} ({stats['second'] / self.LIMITS['second'][0] * 100:.1f}%)",
            "minute": f"{stats['minute']}/{self.LIMITS['minute'][0]} ({stats['minute'] / self.LIMITS['minute'][0] * 100:.1f}%)",
            "hour": f"{stats['hour']}/{self.LIMITS['hour'][0]} ({stats['hour'] / self.LIMITS['hour'][0] * 100:.1f}%)",
            "day": f"{stats['day']}/{self.LIMITS['day'][0]} ({stats['day'] / self.LIMITS['day'][0] * 100:.1f}%)",
        }


# 全局速率限制器
rate_limiter = RateLimiter()


def _is_hex(s: str) -> bool:
    s2 = s[2:] if s.startswith("0x") else s
    if not s2:
        return False
    try:
        int(s2, 16)
        return True
    except Exception:
        return False


def _require_eth_address(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} 为空")
    if not _is_hex(value):
        raise ValueError(f"{name} 不是合法十六进制")
    v = value[2:] if value.startswith("0x") else value
    if len(v) != 40:
        raise ValueError(f"{name} 长度不正确：期望40个hex字符(20字节)，实际{len(v)}个")


def _require_eth_private_key(name: str, value: str) -> None:
    if not value:
        raise ValueError(f"{name} 为空")
    if not _is_hex(value):
        raise ValueError(f"{name} 不是合法十六进制")
    v = value[2:] if value.startswith("0x") else value
    if len(v) != 64:
        raise ValueError(f"{name} 长度不正确：期望64个hex字符(32字节)，实际{len(v)}个")


class ArbitrageBot:
    """套利机器人类 - 反向开仓模式"""

    def __init__(
        self,
        account1: Paradex,
        account2: Paradex,
        market: str,
        min_spread: Decimal = Decimal("0"),
        use_dynamic_size: bool = True,
        funds_ratio: Decimal = Decimal("0.9"),
        target_leverage: int = 50,
        fixed_trade_size: Decimal = Decimal("0.01"),
        min_trade_interval: float = 0.0,
    ):
        self.account1 = account1  # 账户1
        self.account2 = account2  # 账户2
        self.market = market
        self.min_spread = min_spread
        self.use_dynamic_size = use_dynamic_size
        self.funds_ratio = funds_ratio
        self.target_leverage = target_leverage
        self.fixed_trade_size = fixed_trade_size

        # 当前价格状态
        self.current_bid: Optional[Decimal] = None
        self.current_ask: Optional[Decimal] = None
        self.last_price_update = None

        # 持仓方向控制
        # None = 无持仓, "LONG" = 账户1多/账户2空, "SHORT" = 账户1空/账户2多
        self.current_position: Optional[str] = None
        self.current_trade_size: Optional[Decimal] = None

        # API 响应缓存（避免每次 BBO 更新都查询）
        self._cached_account_info: Optional[dict] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 2.0  # 缓存2秒

        # 交易状态
        self.trading_enabled = True
        self.last_trade_time = None
        self.min_trade_interval = min_trade_interval  # 最小交易间隔（秒）

        # 统计信息
        self.total_trades = 0
        self.successful_trades = 0
        self.failed_trades = 0

        # 打印配置信息
        usage = rate_limiter.get_usage_percentage()
        logger.info("=" * 60)
        logger.info("BTC-USDT 套利策略启动（反向开仓模式）")
        logger.info("策略说明：检测到价差时直接反向开仓，停机时自动平仓")
        logger.info(f"市场: {market}")
        logger.info(f"价差阈值: {min_spread}")
        logger.info(f"下单方式: {'动态' if use_dynamic_size else '固定'} (FUNDS_RATIO={funds_ratio}, LEVERAGE={target_leverage}x)")
        if min_trade_interval > 0:
            logger.info(f"最小交易间隔: {min_trade_interval}秒")
        else:
            logger.info(f"最小交易间隔: 无限制")
        logger.info("API 速率限制:")
        logger.info(f"  每秒: {usage['second']}")
        logger.info(f"  每分钟: {usage['minute']}")
        logger.info(f"  每小时: {usage['hour']}")
        logger.info(f"  24小时: {usage['day']}")
        logger.info("=" * 60)

    @staticmethod
    def _to_decimal(value: str | int | float | Decimal | None, default: Decimal = Decimal("0")) -> Decimal:
        if value is None:
            return default
        try:
            return Decimal(str(value))
        except Exception:
            return default

    def _fetch_free_collateral(self, paradex: Paradex) -> Decimal:
        """读取账户可用保证金"""
        try:
            summary = paradex.api_client.fetch_account_summary()
            return self._to_decimal(getattr(summary, "free_collateral", 0) or 0)
        except KeyboardInterrupt:
            raise  # 重新抛出，让上层处理
        except Exception as e:
            logger.error(f"获取可用保证金失败: {e}")
            return Decimal("0")

    def _fetch_account_value(self, paradex: Paradex) -> Decimal:
        """读取账户总价值（用于计算开仓数量）"""
        try:
            summary = paradex.api_client.fetch_account_summary()
            return self._to_decimal(getattr(summary, "account_value", 0) or 0)
        except KeyboardInterrupt:
            raise  # 重新抛出，让上层处理
        except Exception as e:
            logger.error(f"获取账户总价值失败: {e}")
            return Decimal("0")

    def _fetch_positions(self, paradex: Paradex) -> dict:
        """获取账户持仓"""
        try:
            positions = paradex.api_client.fetch_positions()
            return positions
        except KeyboardInterrupt:
            raise  # 重新抛出，让上层处理
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return {"results": []}

    def _get_cached_account_info(self) -> dict:
        """
        获取缓存的账户信息（避免频繁查询 API）

        返回: {
            'free1': Decimal,
            'free2': Decimal,
            'min_free': Decimal,
            'account_value1': Decimal,
            'account_value2': Decimal,
            'min_account_value': Decimal,
            'positions1': dict,
            'positions2': dict,
            'pos1_size': float,
            'pos2_size': float,
            'current_direction': str or None,
        }
        """
        try:
            now = datetime.now()

            # 检查缓存是否有效
            if (self._cached_account_info is not None and
                self._cache_timestamp is not None and
                (now - self._cache_timestamp).total_seconds() < self._cache_ttl):
                return self._cached_account_info

            # 缓存过期，重新查询
            free1 = self._fetch_free_collateral(self.account1)
            free2 = self._fetch_free_collateral(self.account2)
            min_free = min(free1, free2)

            # 获取账户总价值（用于计算名义价值）
            account_value1 = self._fetch_account_value(self.account1)
            account_value2 = self._fetch_account_value(self.account2)
            min_account_value = min(account_value1, account_value2)

            positions1 = self._fetch_positions(self.account1)
            positions2 = self._fetch_positions(self.account2)

            pos1 = None
            pos2 = None
            for p in positions1.get("results", []):
                if p.get("market") == self.market:
                    pos1 = p
                    break

            for p in positions2.get("results", []):
                if p.get("market") == self.market:
                    pos2 = p
                    break

            pos1_size = float(pos1.get("size", 0)) if pos1 else 0
            pos2_size = float(pos2.get("size", 0)) if pos2 else 0

            # 判断当前持仓方向
            current_direction = None
            if pos1_size > 0 and pos2_size < 0:
                current_direction = "LONG"
            elif pos1_size < 0 and pos2_size > 0:
                current_direction = "SHORT"

            # 保存到缓存
            self._cached_account_info = {
                'free1': free1,
                'free2': free2,
                'min_free': min_free,
                'account_value1': account_value1,
                'account_value2': account_value2,
                'min_account_value': min_account_value,
                'positions1': positions1,
                'positions2': positions2,
                'pos1': pos1,
                'pos2': pos2,
                'pos1_size': pos1_size,
                'pos2_size': pos2_size,
                'current_direction': current_direction,
            }
            self._cache_timestamp = now

            return self._cached_account_info

        except KeyboardInterrupt:
            raise  # 重新抛出，让上层处理
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}", exc_info=True)
            return {
                'free1': Decimal("0"),
                'free2': Decimal("0"),
                'min_free': Decimal("0"),
                'account_value1': Decimal("0"),
                'account_value2': Decimal("0"),
                'min_account_value': Decimal("0"),
                'positions1': {"results": []},
                'positions2': {"results": []},
                'pos1': None,
                'pos2': None,
                'pos1_size': 0,
                'pos2_size': 0,
                'current_direction': None,
            }

    def _compute_trade_size_from_funds(self, price: Decimal, target_side: str) -> tuple[Decimal, Decimal, Decimal, dict]:
        """
        计算反向开仓的订单数量

        策略逻辑：
        - 始终以较少账户的账户总价值（account_value）× FUNDS_RATIO × LEVERAGE 计算名义价值
        - 首次开仓：用计算出的名义价值开仓
        - 反向开仓：合并平仓+开仓为一个订单，数量 = abs(持仓) + 新开仓数量
        - 这样无论盈亏，反向开仓的名义价值都保持一致

        返回: (close_size, open_size, total_size, info_dict)
        - close_size: 平仓数量（需要平掉的数量）
        - open_size: 反向开仓数量
        - total_size: 订单总数量（用于日志）
        - info_dict: 包含账户1和账户2的订单详情
        """
        # 使用缓存获取账户信息
        info = self._get_cached_account_info()

        free1 = info['free1']
        free2 = info['free2']
        min_free = info['min_free']
        account_value1 = info['account_value1']
        account_value2 = info['account_value2']
        min_account_value = info['min_account_value']
        pos1 = info['pos1']
        pos2 = info['pos2']
        pos1_size = info['pos1_size']
        pos2_size = info['pos2_size']
        current_direction = info['current_direction']

        # 计算价格（用于估算）
        if price <= 0:
            raise ValueError(f"价格无效: price={price}")

        # 始终使用账户总价值计算名义价值
        # margin = min_account_value × FUNDS_RATIO
        # notional = margin × LEVERAGE
        margin = min_account_value * self.funds_ratio
        notional = margin * self.target_leverage
        size = (notional / price).quantize(Decimal("0.00001"))

        if current_direction is None:
            # ========== 首次开仓 ==========
            logger.info(f"📊 首次开仓计算:")
            logger.info(f"  账户总价值: {float(min_account_value):.4f} USDT")
            logger.info(f"  使用比例: {self.funds_ratio} × 杠杆: {self.target_leverage}x")
            logger.info(f"  名义价值: {float(notional):.4f} USDT")
            logger.info(f"  开仓数量: {float(size):.5f} BTC")

            if target_side == "LONG":
                # 账户1做多，账户2做空
                order1 = {
                    "side": "BUY",
                    "size": float(size),
                    "reduce_only": False,
                    "description": "首次开多"
                }
                order2 = {
                    "side": "SELL",
                    "size": float(size),
                    "reduce_only": False,
                    "description": "首次开空"
                }
            else:
                # 账户1做空，账户2做多
                order1 = {
                    "side": "SELL",
                    "size": float(size),
                    "reduce_only": False,
                    "description": "首次开空"
                }
                order2 = {
                    "side": "BUY",
                    "size": float(size),
                    "reduce_only": False,
                    "description": "首次开多"
                }

            info = {
                "is_first_trade": True,
                "current_direction": None,
                "account1": order1,
                "account2": order2,
                "close_size": 0,
                "open_size": float(size),
                "total_size": float(size),  # 首次开仓的订单数量
                "margin": float(margin),
                "notional": float(notional),
                "free1": float(free1),
                "free2": float(free2),
                "min_free": float(min_free),
                "account_value1": float(account_value1),
                "account_value2": float(account_value2),
                "min_account_value": float(min_account_value),
            }

            return size, Decimal("0"), size, info

        # ========== 反向开仓 ==========
        logger.info(f"📊 反向开仓计算:")
        logger.info(f"  当前持仓: {current_direction} | 账户1: {pos1_size:.5f} | 账户2: {pos2_size:.5f}")
        logger.info(f"  账户总价值: {float(min_account_value):.4f} USDT")
        logger.info(f"  使用比例: {self.funds_ratio} × 杠杆: {self.target_leverage}x")
        logger.info(f"  名义价值: {float(notional):.4f} USDT")
        logger.info(f"  新开仓数量: {float(size):.5f} BTC")

        abs_pos1_size = abs(pos1_size)
        abs_pos2_size = abs(pos2_size)

        # 计算平仓订单（reduce_only）
        if current_direction == "LONG":
            # 当前是多头，反向要做空
            # 账户1平多：卖出 | 账户2平空：买入
            close_order1 = {
                "side": "SELL",
                "size": abs_pos1_size,
                "reduce_only": True,
                "description": "平多"
            }
            close_order2 = {
                "side": "BUY",
                "size": abs_pos2_size,
                "reduce_only": True,
                "description": "平空"
            }
            # 反向开空
            open_order1 = {
                "side": "SELL",
                "size": float(size),
                "reduce_only": False,
                "description": f"反手开空 (margin={float(margin):.4f}×{self.target_leverage}x)"
            }
            open_order2 = {
                "side": "BUY",
                "size": float(size),
                "reduce_only": False,
                "description": f"反手开多 (margin={float(margin):.4f}×{self.target_leverage}x)"
            }
        else:
            # 当前是空头，反向要做多
            # 账户1平空：买入 | 账户2平多：卖出
            close_order1 = {
                "side": "BUY",
                "size": abs_pos1_size,
                "reduce_only": True,
                "description": "平空"
            }
            close_order2 = {
                "side": "SELL",
                "size": abs_pos2_size,
                "reduce_only": True,
                "description": "平多"
            }
            # 反向开多
            open_order1 = {
                "side": "BUY",
                "size": float(size),
                "reduce_only": False,
                "description": f"反手开多 (margin={float(margin):.4f}×{self.target_leverage}x)"
            }
            open_order2 = {
                "side": "SELL",
                "size": float(size),
                "reduce_only": False,
                "description": f"反手开空 (margin={float(margin):.4f}×{self.target_leverage}x)"
            }

        # 账户1的总订单 = 平仓数量 + 反向开仓数量（量化到0.00001避免浮点误差）
        total_size = (Decimal(str(abs_pos1_size)) + size).quantize(Decimal("0.00001"))

        info = {
            "is_first_trade": False,
            "current_direction": current_direction,
            "target_direction": target_side,
            "account1": {**close_order1, **open_order1},
            "account2": {**close_order2, **open_order2},
            "close_size": abs_pos1_size,
            "open_size": float(size),
            "total_size": float(total_size),  # 量化后的总订单数量
            "margin": float(margin),
            "notional": float(notional),
            "free1": float(free1),
            "free2": float(free2),
            "min_free": float(min_free),
            "account_value1": float(account_value1),
            "account_value2": float(account_value2),
            "min_account_value": float(min_account_value),
        }

        return Decimal(str(abs_pos1_size)), size, total_size, info

    def _compute_trade_size(self, bid: Decimal, ask: Decimal, target_side: str) -> tuple[Decimal, Decimal, str]:
        """计算本次开仓 size"""
        price = (bid + ask) / Decimal("2")
        if not self.use_dynamic_size:
            return self.fixed_trade_size, Decimal("0"), f"固定size={self.fixed_trade_size}"

        close_size, open_size, total_size, info = self._compute_trade_size_from_funds(price, target_side)

        if info["is_first_trade"]:
            desc = (
                f"首次开仓: {info['account1']['description']} | "
                f"size={total_size:.5f} (margin={info['margin']:.4f}, "
                f"notional={info['notional']:.4f})"
            )
        else:
            desc = (
                f"反向开仓: {info['current_direction']}→{info['target_direction']} | "
                f"平: {info['close_size']:.5f} + 开: {info['open_size']:.5f} = 总: {total_size:.5f} | "
                f"(保证金={info['min_free']:.4f}×{self.funds_ratio}×{self.target_leverage}x)"
            )

        return total_size, close_size, desc

    def _get_opposite_side(self) -> str:
        """获取当前应该开仓的方向"""
        if self.current_position is None:
            # 首次开仓，默认账户1做多，账户2做空
            return "LONG"
        elif self.current_position == "LONG":
            # 反向：账户1做空，账户2做多
            return "SHORT"
        else:
            # 反向：账户1做多，账户2做空
            return "LONG"

    async def _check_rate_limit(self) -> bool:
        """检查速率限制"""
        can_proceed, reason = rate_limiter.can_proceed()
        if not can_proceed:
            logger.warning(f"⚠️ 速率限制触发: {reason}")
            logger.info(f"当前使用情况: {rate_limiter.get_usage_percentage()}")
        return can_proceed

    async def _close_all_positions(self) -> bool:
        """
        平掉所有持仓（用于程序退出时）
        返回: 是否成功平掉所有仓位
        """
        logger.info("=" * 60)
        logger.info("🛑 正在平掉所有持仓...")

        success = True

        # 获取当前持仓
        positions1 = self._fetch_positions(self.account1)
        positions2 = self._fetch_positions(self.account2)

        # 查找当前市场的持仓
        pos1 = None
        pos2 = None
        for p in positions1.get("results", []):
            if p.get("market") == self.market:
                pos1 = p
                break

        for p in positions2.get("results", []):
            if p.get("market") == self.market:
                pos2 = p
                break

        # 平掉账户1的持仓
        if pos1 and float(pos1.get("size", 0)) != 0:
            size = Decimal(str(abs(float(pos1.get("size", 0)))))
            size = size.quantize(Decimal("0.00001"))

            if float(pos1.get("size", 0)) > 0:
                # 多头持仓，平仓需卖出
                close_order = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Sell,
                    size=size,
                    reduce_only=True,
                )
            else:
                # 空头持仓，平仓需买入
                close_order = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Buy,
                    size=size,
                    reduce_only=True,
                )

            logger.info(f"账户1平仓: {close_order}")
            try:
                await rate_limiter.acquire(timeout=30)
                result = self.account1.api_client.submit_order(order=close_order)
                logger.info(f"账户1平仓结果: {result}")
            except Exception as e:
                logger.error(f"账户1平仓失败: {e}")
                success = False

        # 平掉账户2的持仓
        if pos2 and float(pos2.get("size", 0)) != 0:
            size = Decimal(str(abs(float(pos2.get("size", 0)))))
            size = size.quantize(Decimal("0.00001"))

            if float(pos2.get("size", 0)) > 0:
                close_order = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Sell,
                    size=size,
                    reduce_only=True,
                )
            else:
                close_order = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Buy,
                    size=size,
                    reduce_only=True,
                )

            logger.info(f"账户2平仓: {close_order}")
            try:
                await rate_limiter.acquire(timeout=30)
                result = self.account2.api_client.submit_order(order=close_order)
                logger.info(f"账户2平仓结果: {result}")
            except Exception as e:
                logger.error(f"账户2平仓失败: {e}")
                success = False

        # 重置持仓状态
        self.current_position = None
        self.current_trade_size = None

        logger.info(f"🛑 平仓操作{'成功' if success else '部分失败'}")
        logger.info("=" * 60)
        return success

    async def on_bbo_update(self, ws_channel: ParadexWebsocketChannel, message: dict) -> None:
        """处理BBO更新"""
        try:
            params = message.get("params", {})
            data = params.get("data") or message.get("data", {})

            bid_str = data.get("bid")
            ask_str = data.get("ask")

            channel = params.get("channel", "")
            market = data.get("market") or (channel.split(".")[-1] if "." in channel else None)

            if not bid_str or not ask_str:
                logger.debug(f"BBO消息缺少价格数据")
                return

            if market != self.market:
                return

            bid = Decimal(str(bid_str))
            ask = Decimal(str(ask_str))

            self.current_bid = bid
            self.current_ask = ask
            self.last_price_update = datetime.now()

            spread = ask - bid
            spread_pct = (spread / ask) * 100

            # 检查是否满足交易条件
            if spread_pct <= self.min_spread and self.trading_enabled:
                await self.execute_arbitrage(bid, ask, spread)

        except KeyboardInterrupt:
            # 捕获 Ctrl+C，记录日志即可
            # 让主程序中的 KeyboardInterrupt 处理程序来执行 stop()
            logger.debug("WebSocket回调中收到中断信号")
            raise
        except Exception as e:
            logger.error(f"处理BBO更新时出错: {e}", exc_info=True)

    async def execute_arbitrage(self, bid: Decimal, ask: Decimal, spread: Decimal) -> None:
        """执行反向开仓

        策略逻辑：
        - 首次开仓：直接开多/空（2个订单）
        - 反向开仓：合并平仓+开仓为一个订单（2个订单）
        """
        # 检查速率限制
        if not await self._check_rate_limit():
            logger.warning("⚠️ 因速率限制跳过本次机会")
            return

        # 检查交易间隔
        if self.last_trade_time:
            time_since_last = (datetime.now() - self.last_trade_time).total_seconds()
            if time_since_last < self.min_trade_interval:
                return

        # 获取应该开仓的方向
        target_side = self._get_opposite_side()

        # 获取开仓信息（包含平仓+开仓详情）
        _, _, _, info = self._compute_trade_size_from_funds((bid + ask) / 2, target_side)

        logger.info("=" * 60)
        logger.info(f"🔄 执行 {'首次开仓' if info['is_first_trade'] else '反向开仓'}: {target_side}")
        logger.info(f"  之前方向: {self.current_position or '无持仓'}")
        logger.info(f"  买一: {bid}, 卖一: {ask}")

        # 获取速率限制许可
        success, reason, waited = await rate_limiter.acquire(timeout=60.0)
        if not success:
            logger.error(f"❌ 无法获取速率限制许可: {reason}")
            logger.info("=" * 60)
            return

        if waited > 0:
            logger.info(f"⏳ 等待了 {waited:.1f} 秒")

        # 创建订单

        if info['is_first_trade']:
            # ========== 首次开仓 ==========
            logger.info(f"  首次开仓: {info['account1']['description']}")
            logger.info(f"  下单数量: {info['open_size']:.5f} BTC")

            if target_side == "LONG":
                # 账户1做多，账户2做空
                order1 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Buy,
                    size=Decimal(str(info['open_size'])),
                )
                order2 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Sell,
                    size=Decimal(str(info['open_size'])),
                )
                desc1 = "账户1做多"
                desc2 = "账户2做空"
            else:
                # 账户1做空，账户2做多
                order1 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Sell,
                    size=Decimal(str(info['open_size'])),
                )
                order2 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Buy,
                    size=Decimal(str(info['open_size'])),
                )
                desc1 = "账户1做空"
                desc2 = "账户2做多"
        else:
            # ========== 反向开仓（合并平仓+开仓为一个订单） ==========
            reverse_size = info['total_size']
            logger.info(f"  反向: {info['current_direction']} → {info['target_direction']}")
            logger.info(f"  平仓: {info['close_size']:.5f} | 开仓: {info['open_size']:.5f} | 合并订单: {reverse_size:.5f} BTC")

            if info['current_direction'] == "LONG":
                # 当前是多头，反向要做空
                order1 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Sell,
                    size=Decimal(str(reverse_size)),
                )
                order2 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Buy,
                    size=Decimal(str(reverse_size)),
                )
            else:
                # 当前是空头，反向要做多
                order1 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Buy,
                    size=Decimal(str(reverse_size)),
                )
                order2 = Order(
                    market=self.market,
                    order_type=OrderType.Market,
                    order_side=OrderSide.Sell,
                    size=Decimal(str(reverse_size)),
                )

            desc1 = f"账户1反向({info['target_direction']})"
            desc2 = f"账户2反向({info['target_direction']})"

        # 提交订单（并行提交两个账户的订单）
        self.total_trades += 1
        self.trading_enabled = False
        try:
            logger.info(f"  {desc1}: {order1}")
            logger.info(f"  {desc2}: {order2}")

            # 并行提交订单（与 test_open_position.py 方式一致）
            result1, result2 = await asyncio.gather(
                self._submit_order(self.account1, order1),
                self._submit_order(self.account2, order2),
                return_exceptions=True
            )

            success1 = not isinstance(result1, Exception) and result1 is not None
            success2 = not isinstance(result2, Exception) and result2 is not None

            if success1 and success2:
                self.successful_trades += 1
                logger.info(f"✅ {'首次开仓' if info['is_first_trade'] else '反向开仓'}成功！")
                self.current_position = target_side
                self.current_trade_size = Decimal(str(info['open_size']))
                # 清空缓存，确保下次获取最新数据
                self._cached_account_info = None
                self._cache_timestamp = None

                # 等待 1 秒后查询成交记录（与 test_open_position.py 一致）
                await asyncio.sleep(1)
                logger.info("查询成交记录...")

                fills1 = await self._fetch_fills(self.account1, self.market)
                fills2 = await self._fetch_fills(self.account2, self.market)

                # 账户1成交记录
                if fills1.get("results"):
                    fill = fills1["results"][0]
                    logger.info(f"  📊 账户1成交:")
                    logger.info(f"    成交ID: {fill.get('id', 'N/A')}")
                    logger.info(f"    价格: {fill.get('price', 'N/A')}")
                    logger.info(f"    数量: {fill.get('size', 'N/A')}")
                    logger.info(f"    手续费: {fill.get('fee', 'N/A')} {fill.get('fee_token', 'N/A')}")

                # 账户2成交记录
                if fills2.get("results"):
                    fill = fills2["results"][0]
                    logger.info(f"  📊 账户2成交:")
                    logger.info(f"    成交ID: {fill.get('id', 'N/A')}")
                    logger.info(f"    价格: {fill.get('price', 'N/A')}")
                    logger.info(f"    数量: {fill.get('size', 'N/A')}")
                    logger.info(f"    手续费: {fill.get('fee', 'N/A')} {fill.get('fee_token', 'N/A')}")
            else:
                self.failed_trades += 1
                logger.error("❌ 开仓部分失败")
                if isinstance(result1, Exception):
                    logger.error(f"  账户1失败: {result1}")
                if isinstance(result2, Exception):
                    logger.error(f"  账户2失败: {result2}")

        except KeyboardInterrupt:
            self.failed_trades += 1
            logger.info("\n🛑 执行交易时收到中断信号")
            raise
        except Exception as e:
            self.failed_trades += 1
            logger.error(f"执行交易时出错: {e}", exc_info=True)
        finally:
            self.trading_enabled = True
            self.last_trade_time = datetime.now()

        # 打印统计
        stats = rate_limiter.get_stats()
        usage = rate_limiter.get_usage_percentage()
        logger.info(
            f"📈 统计 | 总: {self.total_trades} | 成功: {self.successful_trades} | 失败: {self.failed_trades} | "
            f"API: 秒{usage['second']} 分{usage['minute']}"
        )
        logger.info("=" * 60)

    async def _submit_order(self, paradex: Paradex, order: Order) -> dict:
        """提交订单（与 test_open_position.py 保持一致）"""
        return paradex.api_client.submit_order(order=order)

    async def _fetch_fills(self, paradex: Paradex, market: str) -> dict:
        """查询成交记录"""
        try:
            fills = paradex.api_client.fetch_fills(params={"market": market})
            return fills
        except KeyboardInterrupt:
            raise  # 重新抛出，让上层处理
        except Exception as e:
            logger.error(f"查询成交记录失败: {e}")
            return {"results": []}

    async def get_account_info(self) -> None:
        """获取账户信息"""
        try:
            logger.info("获取账户信息...")

            # 账户1
            acc1 = self.account1.api_client.fetch_account_info()
            acc1_summary = self.account1.api_client.fetch_account_summary()
            acc1_positions = self.account1.api_client.fetch_positions()
            pos1_size = 0
            for p in acc1_positions.get("results", []):
                if p.get("market") == self.market:
                    pos1_size = float(p.get("size", 0))
                    break

            # 账户2
            acc2 = self.account2.api_client.fetch_account_info()
            acc2_summary = self.account2.api_client.fetch_account_summary()
            acc2_positions = self.account2.api_client.fetch_positions()
            pos2_size = 0
            for p in acc2_positions.get("results", []):
                if p.get("market") == self.market:
                    pos2_size = float(p.get("size", 0))
                    break

            logger.info("=" * 60)
            logger.info("账户1:")
            logger.info(f"  L2地址: {hex(self.account1.account.l2_address)}")
            logger.info(f"  可用保证金: {getattr(acc1_summary, 'free_collateral', 'N/A')}")
            logger.info(f"  {self.market}持仓: {pos1_size}")

            logger.info("账户2:")
            logger.info(f"  L2地址: {hex(self.account2.account.l2_address)}")
            logger.info(f"  可用保证金: {getattr(acc2_summary, 'free_collateral', 'N/A')}")
            logger.info(f"  {self.market}持仓: {pos2_size}")
            logger.info("=" * 60)

        except KeyboardInterrupt:
            raise  # 重新抛出，让上层处理
        except Exception as e:
            logger.error(f"获取账户信息时出错: {e}", exc_info=True)

    async def start_monitoring(self) -> None:
        """启动监控（只用一个账户连接 WebSocket 监控价格即可）"""
        logger.info("启动监控...")

        # 获取初始持仓状态（只需要查询一次）
        await self._sync_position_status()
        await self.get_account_info()

        # 只用账户1连接 WebSocket（BBO 是公共数据，所有账户看到的价格一样）
        logger.info("连接 WebSocket (账户1)...")
        is_connected = False
        while not is_connected:
            is_connected = await self.account1.ws_client.connect()
            if not is_connected:
                logger.warning("WebSocket 连接失败，1秒后重试...")
                await asyncio.sleep(1)

        logger.info("WebSocket 连接成功")

        # 订阅 BBO
        logger.info(f"订阅 {self.market} BBO...")
        await self.account1.ws_client.subscribe(
            ParadexWebsocketChannel.BBO,
            callback=self.on_bbo_update,
            params={"market": self.market},
        )

        logger.info("✅ 监控已启动，等待套利机会...")
        logger.info("💡 策略说明: 检测到价差时直接反向开仓，停机时自动平仓")
        logger.info("按 Ctrl+C 停止")

    async def _sync_position_status(self) -> None:
        """同步持仓状态"""
        try:
            positions1 = self._fetch_positions(self.account1)
            positions2 = self._fetch_positions(self.account2)

            pos1_size = 0
            pos2_size = 0

            for p in positions1.get("results", []):
                if p.get("market") == self.market:
                    pos1_size = float(p.get("size", 0))
                    break

            for p in positions2.get("results", []):
                if p.get("market") == self.market:
                    pos2_size = float(p.get("size", 0))
                    break

            # 判断当前持仓方向
            if pos1_size > 0 and pos2_size < 0:
                self.current_position = "LONG"
            elif pos1_size < 0 and pos2_size > 0:
                self.current_position = "SHORT"
            elif pos1_size == 0 and pos2_size == 0:
                self.current_position = None
            else:
                # 持仓不一致，记录警告
                logger.warning(f"⚠️ 持仓不一致: 账户1={pos1_size}, 账户2={pos2_size}")
                self.current_position = None

            logger.info(f"📋 初始持仓状态: {self.current_position}")

        except Exception as e:
            logger.error(f"同步持仓状态失败: {e}")

    async def stop(self) -> None:
        """停止监控并平仓"""
        logger.info("=" * 60)
        logger.info("🛑 正在停止策略...")

        self.trading_enabled = False

        # 先平掉所有持仓
        await self._close_all_positions()

        # 关闭WebSocket
        if self.account1.ws_client:
            await self.account1.ws_client.close()

        # 打印最终统计
        stats = rate_limiter.get_stats()
        usage = rate_limiter.get_usage_percentage()
        logger.info("=" * 60)
        logger.info("最终统计")
        logger.info(f"  交易次数: {self.total_trades} (成功: {self.successful_trades}, 失败: {self.failed_trades})")
        logger.info(f"  API请求: 总{stats['total_requests']}, 被阻{stats['blocked_requests']}")
        logger.info(f"  最终费率使用:")
        logger.info(f"    每秒: {usage['second']}")
        logger.info(f"    每分钟: {usage['minute']}")
        logger.info(f"    每小时: {usage['hour']}")
        logger.info(f"    24小时: {usage['day']}")
        logger.info("=" * 60)


async def main():
    """主函数"""
    if AUTH_MODE not in {"l1", "subkey"}:
        logger.error("错误: AUTH_MODE 只能是 'l1' 或 'subkey'")
        return

    if AUTH_MODE == "l1":
        if not ACCOUNT1_L1_ADDRESS or not ACCOUNT1_L1_PRIVATE_KEY:
            logger.error("错误: 请设置 ACCOUNT1_L1_ADDRESS 和 ACCOUNT1_L1_PRIVATE_KEY")
            return
        if not ACCOUNT2_L1_ADDRESS or not ACCOUNT2_L1_PRIVATE_KEY:
            logger.error("错误: 请设置 ACCOUNT2_L1_ADDRESS 和 ACCOUNT2_L1_PRIVATE_KEY")
            return

        try:
            _require_eth_address("ACCOUNT1_L1_ADDRESS", ACCOUNT1_L1_ADDRESS)
            _require_eth_address("ACCOUNT2_L1_ADDRESS", ACCOUNT2_L1_ADDRESS)
            _require_eth_private_key("ACCOUNT1_L1_PRIVATE_KEY", ACCOUNT1_L1_PRIVATE_KEY)
            _require_eth_private_key("ACCOUNT2_L1_PRIVATE_KEY", ACCOUNT2_L1_PRIVATE_KEY)
        except Exception as e:
            logger.error(f"格式校验失败: {e}")
            return
    else:
        if not ACCOUNT1_L2_PRIVATE_KEY or not ACCOUNT1_L2_ADDRESS:
            logger.error("错误: subkey 模式需要 ACCOUNT1_L2_PRIVATE_KEY 与 ACCOUNT1_L2_ADDRESS")
            return
        if not ACCOUNT2_L2_PRIVATE_KEY or not ACCOUNT2_L2_ADDRESS:
            logger.error("错误: subkey 模式需要 ACCOUNT2_L2_PRIVATE_KEY 与 ACCOUNT2_L2_ADDRESS")
            return

    # 初始化账户1
    logger.info("初始化账户1...")
    if AUTH_MODE == "l1":
        account1 = Paradex(
            env=PROD,
            l1_address=ACCOUNT1_L1_ADDRESS,
            l1_private_key=ACCOUNT1_L1_PRIVATE_KEY,
            logger=logger,
        )
    else:
        account1 = ParadexSubkey(
            env=PROD,
            l2_private_key=ACCOUNT1_L2_PRIVATE_KEY,
            l2_address=ACCOUNT1_L2_ADDRESS,
            logger=logger,
        )

    # 初始化账户2
    logger.info("初始化账户2...")
    if AUTH_MODE == "l1":
        account2 = Paradex(
            env=PROD,
            l1_address=ACCOUNT2_L1_ADDRESS,
            l1_private_key=ACCOUNT2_L1_PRIVATE_KEY,
            logger=logger,
        )
    else:
        account2 = ParadexSubkey(
            env=PROD,
            l2_private_key=ACCOUNT2_L2_PRIVATE_KEY,
            l2_address=ACCOUNT2_L2_ADDRESS,
            logger=logger,
        )

    # 创建套利机器人
    bot = ArbitrageBot(
        account1=account1,
        account2=account2,
        market=MARKET,
        min_spread=MIN_SPREAD_THRESHOLD,
        use_dynamic_size=USE_DYNAMIC_SIZE,
        funds_ratio=FUNDS_RATIO,
        target_leverage=TARGET_LEVERAGE,
        fixed_trade_size=TRADE_SIZE,
        min_trade_interval=MIN_TRADE_INTERVAL,
    )

    try:
        await bot.start_monitoring()
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("\n🛑 收到 Ctrl+C 信号，正在停止...")
    except Exception as e:
        logger.error(f"运行时出错: {e}", exc_info=True)
    finally:
        await bot.stop()
        # 只关闭 account1 的 WebSocket（只有它连接了）
        if hasattr(account1, "close"):
            await account1.close()
        else:
            if hasattr(account1, "ws_client") and account1.ws_client:
                await account1.ws_client.close()
            account1.api_client.client.close()

        # account2 不需要关闭 WebSocket（从未连接）
        if hasattr(account2, "close"):
            await account2.close()
        else:
            account2.api_client.client.close()
        logger.info("程序已退出")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 静默退出，不显示 traceback
        pass
