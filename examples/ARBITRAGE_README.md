# BTC-USDT 套利策略使用说明

## 目录

- [策略概述](#策略概述)
- [前置条件](#前置条件)
- [环境配置](#环境配置)
- [快速开始](#快速开始)
- [配置参数详解](#配置参数详解)
- [使用示例](#使用示例)
- [策略原理](#策略原理)
- [API 速率限制与收费机制](#api-速率限制与收费机制)
- [风险提示](#风险提示)
- [故障排查](#故障排查)

---

## 策略概述

本策略是一个**BTC-USDT 套利机器人**，用于检测并执行跨账户套利交易。

### 核心逻辑

```
当检测到某个交易对（如 BTC-USD-PERP）的买一价和卖一价价差满足条件时：
  1. 账户1 → 做多（买入）
  2. 账户2 → 做空（卖出）
  3. 等待指定时间后 → 同时平仓
```

### 适用场景

- **交易所内部套利**：利用同一交易所同一交易对的买卖价差
- **双账户对冲**：一个账户做多，另一个账户做空，实现对冲套利
- **高频交易**：自动监控价格，自动执行交易

---

## 前置条件

### 1. 账户要求

你需要准备**两个 Paradex 账户**：

| 账户 | 用途 | 需要的凭证 |
|------|------|-----------|
| 账户1 | 做多方 | L1 地址 + 私钥 **或** L2 私钥 + 地址 |
| 账户2 | 做空方 | L1 地址 + 私钥 **或** L2 私钥 + 地址 |

### 2. 账户要求

- 两个账户都需要有足够的保证金
- 建议使用 **50x 杠杆**
- 账户需要有交易权限

### 3. 环境要求

```bash
# 安装 paradex-py（如果尚未安装）
pip install -e /path/to/paradex-py

# 或者使用 uv
uv pip install -e /path/to/paradex-py
```

---

## 环境配置

### 认证模式选择

脚本支持两种认证模式：

| 模式 | 环境变量 | 说明 |
|------|----------|------|
| 传统模式 | `AUTH_MODE=l1` | 使用 L1 Ethereum 地址和私钥 |
| Subkey 模式 | `AUTH_MODE=subkey` | 仅使用 L2 私钥和地址（轻量级） |

### 环境变量配置

#### 方式一：设置环境变量（推荐）

```bash
# 认证模式
export AUTH_MODE="subkey"  # 或 "l1"

# 账户1配置（做多方）
export ACCOUNT1_L2_ADDRESS="0x..."
export ACCOUNT1_L2_PRIVATE_KEY="0x..."
# 或使用 L1 认证
# export ACCOUNT1_L1_ADDRESS="0x..."
# export ACCOUNT1_L1_PRIVATE_KEY="0x..."

# 账户2配置（做空方）
export ACCOUNT2_L2_ADDRESS="0x..."
export ACCOUNT2_L2_PRIVATE_KEY="0x..."
# 或使用 L1 认证
# export ACCOUNT2_L1_ADDRESS="0x..."
# export ACCOUNT2_L1_PRIVATE_KEY="0x..."

# 交易配置
export MARKET="BTC-USD-PERP"
export MIN_SPREAD_THRESHOLD="0"
export USE_DYNAMIC_SIZE="true"
export FUNDS_RATIO="0.9"
export TARGET_LEVERAGE="50"
export CLOSE_AFTER_SECONDS="1"

# 日志配置（可选）
export LOG_FILE="FALSE"
```

#### 方式二：直接运行（会使用默认值）

```bash
# 使用内置的测试账户配置运行
python examples/arbitrage_btc_usdt.py
```

> ⚠️ **注意**：实际运行前必须设置有效的账户凭证！

---

## 快速开始

### 步骤 1：准备账户

#### 使用 Subkey 模式（推荐，更轻量）

```bash
# 设置账户1的 L2 凭证
export ACCOUNT1_L2_ADDRESS="你的账户1 L2 地址"
export ACCOUNT1_L2_PRIVATE_KEY="你的账户1 L2 私钥"

# 设置账户2的 L2 凭证
export ACCOUNT2_L2_ADDRESS="你的账户2 L2 地址"
export ACCOUNT2_L2_PRIVATE_KEY="你的账户2 L2 私钥"

# 设置认证模式
export AUTH_MODE="subkey"
```

#### 使用传统 L1 模式

```bash
# 设置账户1的 L1 凭证
export ACCOUNT1_L1_ADDRESS="你的账户1 以太坊地址"
export ACCOUNT1_L1_PRIVATE_KEY="你的账户1 以太坊私钥"

# 设置账户2的 L1 凭证
export ACCOUNT2_L1_ADDRESS="你的账户2 以太坊地址"
export ACCOUNT2_L1_PRIVATE_KEY="你的账户2 以太坊私钥"

# 设置认证模式
export AUTH_MODE="l1"
```

### 步骤 2：运行策略

```bash
# 基本运行
python examples/arbitrage_btc_usdt.py

# 或指定配置文件
python examples/arbitrage_btc_usdt.py --config config.env
```

### 步骤 3：监控运行

启动后，你会看到类似以下输出：

```
============================================================
BTC-USDT 套利策略启动
市场: BTC-USD-PERP
价差阈值: 0
动态下单: True (FUNDS_RATIO=0.9, TARGET_LEVERAGE=50x)
自动平仓: 1.0s 后市价 reduce_only 平仓
固定数量(仅当USE_DYNAMIC_SIZE=false时使用): 0.01
============================================================
...
```

---

## 配置参数详解

### 认证配置

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `AUTH_MODE` | 认证模式：`l1` 或 `subkey` | `subkey` |
| `ACCOUNT1_L1_ADDRESS` | 账户1 以太坊地址（l1模式） | `0x1234...` |
| `ACCOUNT1_L1_PRIVATE_KEY` | 账户1 以太坊私钥（l1模式） | `0xabcd...` |
| `ACCOUNT1_L2_ADDRESS` | 账户1 L2 地址（subkey模式） | `0x5678...` |
| `ACCOUNT1_L2_PRIVATE_KEY` | 账户1 L2 私钥（subkey模式） | `0xefgh...` |
| `ACCOUNT2_L1_ADDRESS` | 账户2 以太坊地址（l1模式） | `0x...` |
| `ACCOUNT2_L1_PRIVATE_KEY` | 账户2 以太坊私钥（l1模式） | `0x...` |
| `ACCOUNT2_L2_ADDRESS` | 账户2 L2 地址（subkey模式） | `0x...` |
| `ACCOUNT2_L2_PRIVATE_KEY` | 账户2 L2 私钥（subkey模式） | `0x...` |

### 交易配置

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `MARKET` | 交易市场 | `BTC-USD-PERP` |
| `MIN_SPREAD_THRESHOLD` | 最小价差阈值（百分比） | `0` |
| `USE_DYNAMIC_SIZE` | 是否动态计算下单数量 | `true` |
| `FUNDS_RATIO` | 使用较少账户保证金的比例（0~1） | `0.9` |
| `TARGET_LEVERAGE` | 目标杠杆倍数 | `50` |
| `CLOSE_AFTER_SECONDS` | 开仓后自动平仓的等待时间（秒） | `1` |
| `TRADE_SIZE` | 固定下单数量（仅动态模式关闭时使用） | `0.01` |

### 日志配置

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `LOG_FILE` | 是否输出到文件 | `FALSE` 或 `true` |

---

## 使用示例

### 示例 1：基本使用（Subkey 模式）

```bash
# 设置环境变量
export AUTH_MODE="subkey"
export ACCOUNT1_L2_ADDRESS="0x742d35Cc6634C0532925a3b844Bc9e7595f2bE60"
export ACCOUNT1_L2_PRIVATE_KEY="0xabc123def456..."
export ACCOUNT2_L2_ADDRESS="0x853d35Cc6634C0532925a3b844Bc9e7595f2bE61"
export ACCOUNT2_L2_PRIVATE_KEY="0xxyz789abc..."

# 运行
python examples/arbitrage_btc_usdt.py
```

### 示例 2：使用 L1 传统认证

```bash
export AUTH_MODE="l1"
export ACCOUNT1_L1_ADDRESS="0x742d35Cc6634C0532925a3b844Bc9e7595f2bE60"
export ACCOUNT1_L1_PRIVATE_KEY="0xabc123def456..."
export ACCOUNT2_L1_ADDRESS="0x853d35Cc6634C0532925a3b844Bc9e7595f2bE61"
export ACCOUNT2_L1_PRIVATE_KEY="0xxyz789abc..."

python examples/arbitrage_btc_usdt.py
```

### 示例 3：自定义交易参数

```bash
export AUTH_MODE="subkey"
export ACCOUNT1_L2_ADDRESS="0x..."
export ACCOUNT1_L2_PRIVATE_KEY="0x..."
export ACCOUNT2_L2_ADDRESS="0x..."
export ACCOUNT2_L2_PRIVATE_KEY="0x..."

# 使用固定下单数量
export USE_DYNAMIC_SIZE="false"
export TRADE_SIZE="0.05"

# 设置更长的平仓等待时间
export CLOSE_AFTER_SECONDS="5"

# 打印日志到文件
export LOG_FILE="true"

python examples/arbitrage_btc_usdt.py
```

### 示例 4：使用配置文件

创建配置文件 `arbitrage_config.sh`：

```bash
#!/bin/bash
# arbitrage_config.sh - 套利策略配置文件

export AUTH_MODE="subkey"
export ACCOUNT1_L2_ADDRESS="0x742d35Cc6634C0532925a3b844Bc9e7595f2bE60"
export ACCOUNT1_L2_PRIVATE_KEY="0xabc123def456..."
export ACCOUNT2_L2_ADDRESS="0x853d35Cc6634C0532925a3b844Bc9e7595f2bE61"
export ACCOUNT2_L2_PRIVATE_KEY="0xxyz789abc..."

export MARKET="BTC-USD-PERP"
export MIN_SPREAD_THRESHOLD="0"
export USE_DYNAMIC_SIZE="true"
export FUNDS_RATIO="0.9"
export TARGET_LEVERAGE="50"
export CLOSE_AFTER_SECONDS="1"
export LOG_FILE="FALSE"
```

运行：

```bash
source arbitrage_config.sh
python examples/arbitrage_btc_usdt.py
```

---

## 策略原理

### 交易流程

```
┌─────────────────────────────────────────────────────────────┐
│                      套利策略流程                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 连接 WebSocket，订阅 BBO 频道                             │
│            ↓                                                │
│  2. 实时获取买一价 (Bid) 和卖一价 (Ask)                         │
│            ↓                                                │
│  3. 计算价差 = Ask - Bid                                    │
│            ↓                                                │
│  4. 检查价差是否 ≤ 阈值                                      │
│     ├─ 否 → 继续监控                                       │
│     └─ 是 → 执行套利                                        │
│            ↓                                                │
│  5. 账户1：市价买入 (Market Buy)                            │
│  6. 账户2：市价卖出 (Market Sell)                           │
│            ↓                                                │
│  7. 等待 N 秒 (CLOSE_AFTER_SECONDS)                         │
│            ↓                                                │
│  8. 账户1：市价卖出平多仓 (Reduce Only Sell)                 │
│  9. 账户2：市价买入平空仓 (Reduce Only Buy)                  │
│            ↓                                                │
│  10. 完成一次套利循环，继续监控                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 下单数量计算

#### 动态模式（默认）

```
1. 获取两个账户的可用保证金 (free_collateral)
2. 取较小值 × FUNDS_RATIO → 实际使用保证金
3. 名义仓位 = 保证金 × 目标杠杆
4. 下单数量 = 名义仓位 / 当前价格
5. 舍入到 0.00001 的倍数（Paradex 要求）
```

#### 固定模式

```
直接使用 TRADE_SIZE 作为下单数量
```

### 关键配置说明

#### 杠杆倍数 (`TARGET_LEVERAGE`)

- Parade 的最大杠杆通常为 **50x**
- 杠杆越高，名义仓位越大，风险也越高
- 建议根据账户风险承受能力设置

#### 保证金比例 (`FUNDS_RATIO`)

- 设置为 0.9 表示使用较少账户 **90%** 的可用保证金
- 建议保留一定缓冲，避免因保证金不足导致订单被拒

#### 平仓时间 (`CLOSE_AFTER_SECONDS`)

- 设置为 1 秒表示开仓后 **1 秒** 自动平仓
- 时间太短可能无法成交
- 时间太长会暴露于价格波动风险

---

## API 速率限制与收费机制

### 费率限制

Paradex 对 API 请求有严格的速率限制，超出限制将产生费用：

| 时间窗口 | 限制数量 | 说明 |
|---------|---------|------|
| 每秒 | **3 次** | 单秒内最多 3 个订单请求 |
| 每分钟 | **30 次** | 1 分钟内最多 30 个订单请求 |
| 每小时 | **300 次** | 1 小时内最多 300 个订单请求 |
| 24小时 | **1000 次** | 24小时内最多 1000 个订单请求 |

> ⚠️ **重要**：超过上述限制将产生额外费用！

### 对本策略的影响

本套利策略的执行会产生以下 API 请求：

```
每次套利循环（开仓 + 平仓）：
├─ 账户1：1 个买入订单
├─ 账户2：1 个卖出订单
├─ 账户1：1 个平仓卖出订单（Reduce Only）
└─ 账户2：1 个平仓买入订单（Reduce Only）

总计：4 个订单请求 / 每次套利循环
```

### 频率计算示例

| 策略配置 | 每秒循环次数 | 每分钟循环次数 | 24小时循环次数 | 24小时订单数 |
|---------|-------------|---------------|---------------|-------------|
| `CLOSE_AFTER_SECONDS=1` | 0.5 次/秒 | 15 次/分 | 360 次/分 | **1440 单** ❌ |
| `CLOSE_AFTER_SECONDS=2` | 0.33 次/秒 | 10 次/分 | 240 次/分 | **960 单** ✅ |
| `CLOSE_AFTER_SECONDS=3` | 0.25 次/秒 | 7.5 次/分 | 180 次/分 | **720 单** ✅ |
| `CLOSE_AFTER_SECONDS=5` | 0.17 次/秒 | 5 次/分 | 120 次/分 | **480 单** ✅ |
| `CLOSE_AFTER_SECONDS=10` | 0.1 次/秒 | 3 次/分 | 72 次/分 | **288 单** ✅ |

### 安全配置建议

为了避免产生额外费用，建议：

```
┌─────────────────────────────────────────────────────────────┐
│                    推荐配置参数                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  MIN_SPREAD_THRESHOLD = 0   # 仅在价差为 0 时触发           │
│  CLOSE_AFTER_SECONDS = 3+   # 平仓间隔至少 3 秒              │
│                                                             │
│  计算公式：                                                 │
│  24小时最大订单数 = (86400 / CLOSE_AFTER_SECONDS) × 4        │
│                                                             │
│  目标：24小时订单数 < 1000                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 监控 API 使用量

```bash
# 查看当前账户的订单使用情况（需要 API 支持）
# 可以通过日志统计订单数量

# 日志中会显示：
# 交易统计 - 总计: X, 成功: Y, 失败: Z

# 推算 24 小时订单数：
# 24小时预估 = 当前订单数 / 已运行小时数 × 24
```

---

## 风险提示

### ⚠️ 重要安全提醒

1. **实盘风险**：此策略为示例代码，不构成投资建议
2. **价格风险**：开仓和平仓期间可能出现滑点
3. **保证金风险**：杠杆交易会放大收益和损失
4. **技术风险**：网络延迟可能导致执行失败

### 建议的安全措施

1. **从小额开始测试**
2. **设置止损机制**
3. **监控账户余额**
4. **定期检查日志**

### 不适合使用的情况

- 账户资金不足
- 网络不稳定
- 不了解套利原理
- 无法承受潜在损失

---

## 故障排查

### 问题 1：连接 WebSocket 失败

```
错误信息：WebSocket connection failed
```

**解决方案**：
- 检查网络连接
- 验证账户凭证是否正确
- 确认账户是否有交易权限

### 问题 2：订单提交被拒绝

```
错误信息：Order rejected: insufficient margin
```

**解决方案**：
- 增加账户保证金
- 降低下单数量
- 减少杠杆倍数

### 问题 3：价差始终不满足条件

```
状态：等待套利机会...
```

**解决方案**：
- 降低 `MIN_SPREAD_THRESHOLD`（设置为 `0` 表示价差为 0 时触发）
- 检查市场是否有足够的流动性

### 问题 4：平仓失败

```
错误信息：Close position failed
```

**解决方案**：
- 检查是否有足够的持仓
- 确认网络连接正常
- 手动检查账户持仓状态

### 问题 5：私钥格式错误

```
错误信息：私钥长度不正确
```

**解决方案**：
- 确保私钥是 64 位十六进制字符（可带 0x 前缀）
- 例如：`0xabc123...def`（共 64 个字符，不含 0x）

---

## 日志输出说明

运行时，程序会输出以下信息：

| 日志类型 | 说明 |
|---------|------|
| `📊 BBO` | 实时价格和价差信息 |
| `✅ 套利交易成功` | 套利执行成功 |
| `❌ 套利交易失败` | 套利执行失败 |
| `⏱️ 到达平仓时间` | 开始自动平仓 |
| `交易统计` | 总计/成功/失败次数 |

### 日志示例

```
📊 BBO | 买一: 65000.00 | 卖一: 65000.00 | 价差: 0.00 (0.0000%) | 阈值: 0%
============================================================
检测到套利机会！
买一价: 65000, 卖一价: 65000, 价差: 0
下单数量: 0.01 (动态size=0.01...)
============================================================
账户1提交买单: <Order ...>
账户2提交卖单: <Order ...>
✅ 套利交易成功执行！
...
⏱️ 到达平仓时间（1.0s），开始同时市价平仓（reduce_only）
...
交易统计 - 总计: 1, 成功: 1, 失败: 0
============================================================
```

---

## 进阶配置

### 使用自定义回调

如果需要自定义交易逻辑，可以修改代码中的 `on_bbo_update` 方法：

```python
async def on_bbo_update(self, ws_channel: ParadexWebsocketChannel, message: dict) -> None:
    """自定义 BBO 更新处理"""
    # 添加自定义逻辑
    # 例如：发送通知、记录到数据库等
    await super().on_bbo_update(ws_channel, message)
```

### 集成到其他系统

```python
from arbitrage_btc_usdt import ArbitrageBot

# 自定义初始化
bot = ArbitrageBot(
    account1=account1,
    account2=account2,
    market="BTC-USD-PERP",
    min_spread=Decimal("0"),
    # ... 其他参数
)

# 连接到你的监控系统
await bot.start_monitoring()
```

---

## 相关资源

- [Paradex API 文档](https://docs.api.testnet.paradex.trade)
- [paradex-py GitHub](https://github.com/tradeparadex/paradex-py)
- [示例代码目录](../)

---

## 联系与支持

如有问题或建议，请：

1. 查看 [故障排查](#故障排查) 部分
2. 检查日志输出中的错误信息
3. 在 GitHub 仓库中提交 Issue
