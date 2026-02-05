# Paradex Python SDK & BTC-USDT 套利策略

[![Release](https://img.shields.io/github/v/release/tradeparadex/paradex-py)](https://img.shields.io/github/v/release/tradeparadex/paradex-py)
[![Build status](https://img.shields.io/github/actions/workflow/status/tradeparadex/paradex-py/main.yml?branch=main)](https://github.com/tradeparadex/paradex-py/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tradeparadex/paradex-py/branch/main/graph/badge.svg)](https://codecov.io/gh/tradeparadex/paradex-py)
[![Commit activity](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)](https://img.shields.io/github/commit-activity/m/tradeparadex/paradex-py)
[![License](https://img.shields.io/github/license/tradeparadex/paradex-py)](https://img.shields.io/github/license/tradeparadex/paradex-py)

Paradex Python SDK 提供了一个简单易用的接口来与 Paradex REST 和 WebSocket API 进行交互。本项目还包含一个完整的 **BTC-USDT 套利策略机器人**，用于自动化跨账户套利交易。

## 目录

- [快速开始](#快速开始)
- [SDK 认证方式](#sdk-认证方式)
  - [L1 + L2 认证（传统模式）](#l1--l2-认证传统模式)
  - [L2-Only 认证（Subkey 模式）](#l2-only-认证-subkey-模式)
- [WebSocket 使用](#websocket-使用)
- [REST API 示例](#rest-api-示例)
- [BTC-USDT 套利策略](#btc-usdt-套利策略)
  - [策略概述](#策略概述-1)
  - [前置条件](#前置条件)
  - [环境配置](#环境配置)
  - [快速开始-套利](#快速开始-套利)
  - [配置参数详解](#配置参数详解)
  - [策略原理](#策略原理)
  - [API 速率限制与收费机制](#api-速率限制与收费机制)
  - [风险提示](#风险提示)
  - [故障排查](#故障排查)
- [开发指南](#开发指南)
- [相关资源](#相关资源)

---

## 快速开始

### 安装

```bash
# 使用 pip 安装
pip install -e /path/to/paradex-py

# 或使用 uv
uv pip install -e /path/to/paradex-py
```

### 基本使用

```python
from paradex_py import ParadexSubkey
from paradex_py.environment import Environment

# 使用 Subkey 模式（推荐）
paradex = ParadexSubkey(
    env=Environment.PROD,
    l2_private_key="0x...",
    l2_address="0x..."
)

# 获取账户信息
print(hex(paradex.account.l2_address))

# 查询市场
markets = paradex.api_client.fetch_markets()
print(markets)
```

---

## SDK 认证方式

### L1 + L2 认证（传统模式）

传统模式需要 Ethereum（L1）地址和私钥，用于账户初始化和链上操作。

```python
from paradex_py import Paradex
from paradex_py.environment import Environment

paradex = Paradex(
    env=Environment.TESTNET,  # 或 Environment.PROD
    l1_address="0x...",       # Ethereum 地址
    l1_private_key="0x..."    # Ethereum 私钥
)

print(hex(paradex.account.l2_address))      # L2 地址
print(hex(paradex.account.l2_public_key))   # L2 公钥
print(hex(paradex.account.l2_private_key))  # L2 私钥（可用于 Subkey 模式）
```

### L2-Only 认证（Subkey 模式）

轻量级认证模式，仅需 Starknet（L2）私钥和地址，适用于已完成 onboarding 的账户进行链下操作。

```python
from paradex_py import ParadexSubkey
from paradex_py.environment import Environment

paradex = ParadexSubkey(
    env=Environment.PROD,  # 或 Environment.TESTNET
    l2_private_key="0x...",   # L2 私钥
    l2_address="0x..."        # L2 地址
)

print(hex(paradex.account.l2_address))      # L2 地址
print(hex(paradex.account.l2_public_key))   # L2 公钥
```

> **推荐**：优先使用 Subkey 模式，性能更优且无需每次都进行 L1 签名验证。

---

## WebSocket 使用

WebSocket API 用于实时数据订阅，如行情、订单状态等。

```python
import asyncio
from paradex_py import ParadexSubkey
from paradex_py.environment import Environment
from paradex_py.api.ws_client import ParadexWebsocketChannel

async def on_message(ws_channel, message):
    print(f"频道: {ws_channel}")
    print(f"数据: {message}")

async def main():
    paradex = ParadexSubkey(
        env=Environment.PROD,
        l2_private_key="0x...",
        l2_address="0x..."
    )

    # 连接 WebSocket
    await paradex.ws_client.connect()

    # 订阅行情数据（BBO - 最佳买一卖一价）
    await paradex.ws_client.subscribe(
        ParadexWebsocketChannel.BBO.format(market="BTC-USD-PERP"),
        callback=on_message
    )

    # 保持连接
    await asyncio.sleep(60)

    # 断开连接
    await paradex.ws_client.close()

asyncio.run(main())
```

### 可订阅的频道

| 频道 | 说明 |
|------|------|
| `MARKETS_SUMMARY` | 所有市场汇总数据 |
| `BBO.{market}` | 指定市场最佳买一卖一价 |
| `ORDERS` | 订单状态更新 |
| `ACCOUNT` | 账户资金更新 |

---

## REST API 示例

### 查询市场列表

```python
from paradex_py import ParadexSubkey
from paradex_py.environment import Environment

paradex = ParadexSubkey(
    env=Environment.PROD,
    l2_private_key="0x...",
    l2_address="0x..."
)

# 获取所有市场
markets = paradex.api_client.fetch_markets()
print(markets)
```

### 提交订单

```python
from decimal import Decimal
from paradex_py.common.order import Order, OrderSide, OrderType

# 创建市价买单
order = Order(
    market="BTC-USD-PERP",
    order_type=OrderType.Market,
    order_side=OrderSide.Buy,
    size=Decimal("0.01"),  # 0.01 BTC
)

# 提交订单
result = paradex.api_client.submit_order(order=order)
print(result)
```

### 查询账户信息

```python
# 获取账户汇总
summary = paradex.api_client.fetch_account_summary()
print(f"账户价值: {summary.account_value}")
print(f"可用保证金: {summary.free_collateral}")

# 获取持仓
positions = paradex.api_client.fetch_positions()
print(positions)

# 获取成交记录
fills = paradex.api_client.fetch_fills(params={"market": "BTC-USD-PERP"})
print(fills)
```

---

## BTC-USDT 套利策略

### 策略概述

本策略是一个**BTC-USDT 跨账户套利机器人**，用于检测并执行套利交易。

#### 核心逻辑

```
当检测到某个交易对（如 BTC-USD-PERP）的买一价和卖一价价差满足条件时：
  1. 账户1 → 做多（买入）
  2. 账户2 → 做空（卖出）
  3. 检测到反向机会时 → 反向开仓（合并平仓+开仓为一个订单）
  4. 停掉程序时 → 平掉所有持仓
```

#### 策略特点

- **首次开仓**：两个账户同时下单，建立对冲仓位
- **反向开仓**：合并平仓+开仓为一个订单，减少手续费
- **动态仓位**：根据账户总价值自动计算开仓数量
- **优雅停止**：停掉程序时自动平仓

---

### 前置条件

#### 1. 账户要求

你需要准备**两个 Paradex 账户**：

| 账户 | 用途 | 需要的凭证 |
|------|------|-----------|
| 账户1 | 做多方 | L1 地址 + 私钥 **或** L2 私钥 + 地址 |
| 账户2 | 做空方 | L1 地址 + 私钥 **或** L2 私钥 + 地址 |

#### 2. 资金要求

- 两个账户都需要有足够的保证金
- 建议使用 **40-50x 杠杆**
- 账户需要有交易权限

#### 3. 环境要求

```bash
# 确保已安装 paradex-py
pip install -e /Users/patrick/Desktop/paradex-py
```

---

### 环境配置

#### 认证模式选择

脚本支持两种认证模式：

| 模式 | 环境变量 | 说明 |
|------|----------|------|
| 传统模式 | `AUTH_MODE=l1` | 使用 L1 Ethereum 地址和私钥 |
| Subkey 模式 | `AUTH_MODE=subkey` | 仅使用 L2 私钥和地址（推荐） |

#### 环境变量配置

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
export TARGET_LEVERAGE="40"
export MIN_TRADE_INTERVAL="3"
export TRADE_SIZE="0.01"

# 日志配置（可选）
export LOG_FILE="FALSE"
```

---

### 快速开始-套利

#### 步骤 1：准备账户

**使用 Subkey 模式（推荐，更轻量）**

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

**使用传统 L1 模式**

```bash
export AUTH_MODE="l1"
export ACCOUNT1_L1_ADDRESS="你的账户1 Ethereum 地址"
export ACCOUNT1_L1_PRIVATE_KEY="你的账户1 Ethereum 私钥"
export ACCOUNT2_L1_ADDRESS="你的账户2 Ethereum 地址"
export ACCOUNT2_L1_PRIVATE_KEY="你的账户2 Ethereum 私钥"
```

#### 步骤 2：运行策略

```bash
# 使用快速启动脚本（推荐）
cd /Users/patrick/Desktop/paradex-py/examples
./快速开始.sh

# 或直接运行
python arbitrage_btc_usdt.py
```

#### 步骤 3：停止策略

**按 `Ctrl+C` 停止**，程序会自动平掉所有持仓后退出。

---

### 配置参数详解

#### 认证配置

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `AUTH_MODE` | 认证模式：`l1` 或 `subkey` | `subkey` |
| `ACCOUNT1_L1_ADDRESS` | 账户1 Ethereum 地址（l1模式） | `0x1234...` |
| `ACCOUNT1_L1_PRIVATE_KEY` | 账户1 Ethereum 私钥（l1模式） | `0xabcd...` |
| `ACCOUNT1_L2_ADDRESS` | 账户1 L2 地址（subkey模式） | `0x5678...` |
| `ACCOUNT1_L2_PRIVATE_KEY` | 账户1 L2 私钥（subkey模式） | `0xefgh...` |
| `ACCOUNT2_L1_ADDRESS` | 账户2 Ethereum 地址（l1模式） | `0x...` |
| `ACCOUNT2_L1_PRIVATE_KEY` | 账户2 Ethereum 私钥（l1模式） | `0x...` |
| `ACCOUNT2_L2_ADDRESS` | 账户2 L2 地址（subkey模式） | `0x...` |
| `ACCOUNT2_L2_PRIVATE_KEY` | 账户2 L2 私钥（subkey模式） | `0x...` |

#### 交易配置

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `MARKET` | 交易市场 | `BTC-USD-PERP` |
| `MIN_SPREAD_THRESHOLD` | 最小价差阈值（百分比） | `0` |
| `USE_DYNAMIC_SIZE` | 是否动态计算下单数量 | `true` |
| `FUNDS_RATIO` | 使用账户总价值的比例（0~1） | `0.9` |
| `TARGET_LEVERAGE` | 目标杠杆倍数 | `40` |
| `MIN_TRADE_INTERVAL` | 最小交易间隔（秒） | `3` |
| `TRADE_SIZE` | 固定下单数量（仅动态模式关闭时使用） | `0.01` |

#### 日志配置

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `LOG_FILE` | 是否输出到文件 | `FALSE` 或 `true` |

---

### 策略原理

#### 交易流程

```
┌─────────────────────────────────────────────────────────────┐
│                      套利策略流程                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 连接 WebSocket，订阅 BBO 频道                             │
│            ↓                                                │
│  2. 实时获取买一价 (Bid) 和卖一价 (Ask)                       │
│            ↓                                                │
│  3. 计算价差 = Ask - Bid                                    │
│            ↓                                                │
│  4. 检查价差是否 ≤ 阈值                                      │
│     ├─ 否 → 继续监控                                       │
│     └─ 是 → 执行套利                                        │
│            ↓                                                │
│  5. 首次开仓：                                               │
│     ├─ 账户1：市价买入 (Market Buy)                         │
│     └─ 账户2：市价卖出 (Market Sell)                        │
│            ↓                                                │
│  6. 检测到反向机会：                                          │
│     ├─ 计算反向开仓数量 = abs(持仓) + 新开仓数量              │
│     └─ 合并为一个订单，减少手续费                             │
│            ↓                                                │
│  7. 按 Ctrl+C 停止：                                         │
│     ├─ 账户1：市价平仓 (Reduce Only)                        │
│     └─ 账户2：市价平仓 (Reduce Only)                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 下单数量计算

**动态模式（默认）**

```
1. 获取两个账户的账户总价值 (account_value)
2. 取较小值 × FUNDS_RATIO → 实际使用保证金
3. 名义仓位 = 保证金 × 目标杠杆
4. 下单数量 = 名义仓位 / 当前价格
5. 舍入到 0.00001 的倍数（Paradex 要求）
```

**示例**：
- 账户总价值：1000 USDT
- FUNDS_RATIO：0.9
- 杠杆：40x
- BTC 价格：100000 USDT
- 名义价值：1000 × 0.9 × 40 = 36000 USDT
- 开仓数量：36000 / 100000 = **0.36 BTC**

**反向开仓计算**：
- 当前持仓：+0.36 BTC（多）
- 新开仓数量：0.36 BTC
- 合并订单数量：0.36 + 0.36 = **0.72 BTC**
- 最终持仓：-0.36 BTC（空）

---

### API 速率限制与收费机制

#### 费率限制

Paradex 对 API 请求有严格的速率限制，超出限制将产生费用：

| 时间窗口 | 限制数量 | 说明 |
|---------|---------|------|
| 每秒 | **3 次** | 单秒内最多 3 个订单请求 |
| 每分钟 | **30 次** | 1 分钟内最多 30 个订单请求 |
| 每小时 | **300 次** | 1 小时内最多 300 个订单请求 |
| 24小时 | **1000 次** | 24小时内最多 1000 个订单请求 |

> ⚠️ **重要**：超过上述限制将产生额外费用！

#### 对本策略的影响

本套利策略的执行会产生以下 API 请求：

```
首次开仓：
├─ 账户1：1 个买入订单
└─ 账户2：1 个卖出订单
    总计：2 个订单请求

反向开仓（合并订单）：
├─ 账户1：1 个合并订单（平仓+开仓）
└─ 账户2：1 个合并订单（平仓+开仓）
    总计：2 个订单请求
```

#### 频率计算示例

| 交易间隔 | 每秒循环次数 | 每分钟循环次数 | 24小时循环次数 | 24小时订单数 |
|---------|-------------|---------------|---------------|-------------|
| `MIN_TRADE_INTERVAL=2` | 0.5 次/秒 | 15 次/分 | 360 次/分 | **720 单** ✅ |
| `MIN_TRADE_INTERVAL=3` | 0.33 次/秒 | 10 次/分 | 240 次/分 | **480 单** ✅ |
| `MIN_TRADE_INTERVAL=5` | 0.2 次/秒 | 6 次/分 | 144 次/分 | **288 单** ✅ |

#### 安全配置建议

为了避免产生额外费用，建议：

```
┌─────────────────────────────────────────────────────────────┐
│                    推荐配置参数                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  MIN_SPREAD_THRESHOLD = 0   # 仅在价差为 0 时触发           │
│  MIN_TRADE_INTERVAL = 1.5+   # 交易间隔至少 1.5 秒              │
│                                                             │
│  计算公式：                                                 │
│  24小时最大订单数 = (86400 / MIN_TRADE_INTERVAL) × 2        │
│                                                             │
│  目标：24小时订单数 < 1000                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 风险提示

#### ⚠️ 重要安全提醒

1. **实盘风险**：此策略为示例代码，不构成投资建议
2. **价格风险**：开仓和平仓期间可能出现滑点
3. **保证金风险**：杠杆交易会放大收益和损失
4. **技术风险**：网络延迟可能导致执行失败
5. **费率风险**：超过 API 速率限制会产生额外费用

#### 建议的安全措施

1. **从小额开始测试**
2. **设置合理的交易间隔**
3. **监控账户余额和订单状态**
4. **定期检查日志**

#### 不适合使用的情况

- 账户资金不足
- 网络不稳定
- 不了解套利原理
- 无法承受潜在损失

---

### 故障排查

#### 问题 1：连接 WebSocket 失败

```
错误信息：WebSocket connection failed
```

**解决方案**：
- 检查网络连接
- 验证账户凭证是否正确
- 确认账户是否有交易权限

#### 问题 2：订单提交被拒绝

```
错误信息：Order rejected: insufficient margin
```

**解决方案**：
- 增加账户保证金
- 降低下单数量（减小 FUNDS_RATIO）
- 减少杠杆倍数（减小 TARGET_LEVERAGE）

#### 问题 3：价差始终不满足条件

```
状态：等待套利机会...
```

**解决方案**：
- 降低 `MIN_SPREAD_THRESHOLD`（设置为 `0` 表示价差为 0 时触发）
- 检查市场是否有足够的流动性

#### 问题 4：平仓失败

```
错误信息：Close position failed
```

**解决方案**：
- 检查是否有足够的持仓
- 确认网络连接正常
- 手动检查账户持仓状态

#### 问题 5：私钥格式错误

```
错误信息：私钥长度不正确
```

**解决方案**：
- 确保私钥是 64 位十六进制字符（可带 0x 前缀）
- 例如：`0xabc123...def`（共 64 个字符，不含 0x）

---

## 开发指南

### 常用命令

```bash
# 安装依赖
make install

# 代码检查
make check

# 运行测试
make test

# 构建项目
make build

# 清理构建文件
make clean-build

# 发布到 PyPI
make publish

# 构建并发布
make build-and-publish

# 文档测试
make docs-test

# 生成文档
make docs
```

### 使用 uv 管理依赖

本项目使用 `uv` 作为 Python 包管理器：

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依赖
uv sync

# 运行测试
uv run pytest

# 构建项目
uv build
```

---

## 相关资源

- [Paradex API 文档](https://docs.api.testfound.paradex.trade)
- [paradex-py GitHub](https://github.com/tradeparadex/paradex-py)
- [SDK 详细文档](./docs/README.md)
- [套利策略详细说明](./examples/ARBITRAGE_README.md)

---

> ⚠️ **注意**：本项目包含示例代码和实盘交易策略，使用前请确保充分理解其原理和风险。
