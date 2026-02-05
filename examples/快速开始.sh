#!/bin/bash

# 套利策略快速启动脚本
# 使用方法：修改下面的配置，然后运行 ./快速开始.sh

echo "=========================================="
echo "套利策略快速配置脚本"
echo "=========================================="

# ============================================
# 配置区域 - 请修改下面的值
# ============================================

# 认证模式：subkey（推荐） 或 l1
AUTH_MODE="subkey"

# 账户1配置（做多账户）
# subkey 模式使用（推荐）：L2_PRIVATE_KEY（子键私钥） + L2_ADDRESS（主账户L2地址）
ACCOUNT1_L2_ADDRESS="0x你的账户1-L2地址"
ACCOUNT1_L2_PRIVATE_KEY="0x你的账户1-L2私钥"

# l1 模式使用（不推荐放这里）：L1地址 + L1私钥
ACCOUNT1_L1_ADDRESS="0x你的账户1-L1地址"
ACCOUNT1_L1_PRIVATE_KEY="0x你的账户1-L1私钥"

# 账户2配置（做空账户）
ACCOUNT2_L2_ADDRESS="0x你的账户2-L2地址"
ACCOUNT2_L2_PRIVATE_KEY="0x你的账户2-L2私钥"

ACCOUNT2_L1_ADDRESS="0x你的账户2L1地址"
ACCOUNT2_L1_PRIVATE_KEY="0x你的账户2L1私钥"

# 交易配置（可选）
MARKET="BTC-USD-PERP"          # 交易市场
MIN_SPREAD_THRESHOLD="0.001"   # 价差阈值（0.005表示0.005%，买一和卖一价差小于此值时套利）

# 动态下单（匹配你的需求：较少账户 free_collateral 的 90% 作为保证金，目标50x，1秒后平仓）
USE_DYNAMIC_SIZE="true"
FUNDS_RATIO="0.9"
TARGET_LEVERAGE="50"

# 固定下单数量（仅当 USE_DYNAMIC_SIZE=false 时生效）
TRADE_SIZE="0.01"

# 交易频率控制
MIN_TRADE_INTERVAL="2"  # 最小交易间隔（秒），0表示无限制，建议设置2秒以上避免触发费率限制

# 使用免费interactive token（替代收费API）- 免费但有500ms额外延迟
# 设置为 "true" 启用免费模式，"false" 使用标准收费API
USE_INTERACTIVE_TOKEN="true"

LOG_FILE="false"               # 是否使用文件日志

# ============================================
# 导出环境变量
# ============================================

export AUTH_MODE
export ACCOUNT1_L2_ADDRESS
export ACCOUNT1_L2_PRIVATE_KEY
export ACCOUNT2_L2_ADDRESS
export ACCOUNT2_L2_PRIVATE_KEY
export ACCOUNT1_L1_ADDRESS
export ACCOUNT1_L1_PRIVATE_KEY
export ACCOUNT2_L1_ADDRESS
export ACCOUNT2_L1_PRIVATE_KEY
export TRADE_SIZE
export MIN_TRADE_INTERVAL
export MIN_SPREAD_THRESHOLD
export MARKET
export USE_DYNAMIC_SIZE
export FUNDS_RATIO
export TARGET_LEVERAGE
export USE_INTERACTIVE_TOKEN
export LOG_FILE

# ============================================
# 验证配置
# ============================================

echo ""
echo "检查配置..."
echo ""

is_hex() {
    local s="$1"
    # remove optional 0x prefix
    s="${s#0x}"
    [[ "$s" =~ ^[0-9a-fA-F]+$ ]]
}

check_hex_len() {
    local name="$1"
    local value="$2"
    local expected_len="$3"
    local s="${value#0x}"

    if [ -z "$value" ]; then
        echo "❌ 错误: $name 为空"
        exit 1
    fi
    if ! is_hex "$value"; then
        echo "❌ 错误: $name 不是合法十六进制（应为0x开头或纯hex）"
        exit 1
    fi
    if [ "${#s}" -ne "$expected_len" ]; then
        echo "❌ 错误: $name 长度不正确：期望 ${expected_len} 个hex字符，但实际是 ${#s} 个"
        exit 1
    fi
}

if [ "$AUTH_MODE" != "subkey" ] && [ "$AUTH_MODE" != "l1" ]; then
    echo "❌ 错误: AUTH_MODE 必须是 subkey 或 l1"
    exit 1
fi

if [ "$AUTH_MODE" == "subkey" ]; then
    if [ "$ACCOUNT1_L2_ADDRESS" == "0x你的账户1主账户L2地址" ] || [ -z "$ACCOUNT1_L2_ADDRESS" ]; then
        echo "❌ 错误: 请设置 ACCOUNT1_L2_ADDRESS（主账户L2地址）"
        exit 1
    fi
    if [ "$ACCOUNT1_L2_PRIVATE_KEY" == "0x你的账户1子键L2私钥" ] || [ -z "$ACCOUNT1_L2_PRIVATE_KEY" ]; then
        echo "❌ 错误: 请设置 ACCOUNT1_L2_PRIVATE_KEY（子键L2私钥）"
        exit 1
    fi
    if [ "$ACCOUNT2_L2_ADDRESS" == "0x你的账户2主账户L2地址" ] || [ -z "$ACCOUNT2_L2_ADDRESS" ]; then
        echo "❌ 错误: 请设置 ACCOUNT2_L2_ADDRESS（主账户L2地址）"
        exit 1
    fi
    if [ "$ACCOUNT2_L2_PRIVATE_KEY" == "0x你的账户2子键L2私钥" ] || [ -z "$ACCOUNT2_L2_PRIVATE_KEY" ]; then
        echo "❌ 错误: 请设置 ACCOUNT2_L2_PRIVATE_KEY（子键L2私钥）"
        exit 1
    fi

    # L2字段都是felt，长度可能不同（前导0可省略），这里只校验hex合法
    if ! is_hex "$ACCOUNT1_L2_ADDRESS" || ! is_hex "$ACCOUNT2_L2_ADDRESS" || ! is_hex "$ACCOUNT1_L2_PRIVATE_KEY" || ! is_hex "$ACCOUNT2_L2_PRIVATE_KEY"; then
        echo "❌ 错误: L2 地址/私钥必须是合法十六进制（建议0x开头）"
        exit 1
    fi
else
    if [ "$ACCOUNT1_L1_ADDRESS" == "0x你的账户1L1地址" ] || [ -z "$ACCOUNT1_L1_ADDRESS" ]; then
        echo "❌ 错误: 请设置 ACCOUNT1_L1_ADDRESS"
        exit 1
    fi
    if [ "$ACCOUNT1_L1_PRIVATE_KEY" == "0x你的账户1L1私钥" ] || [ -z "$ACCOUNT1_L1_PRIVATE_KEY" ]; then
        echo "❌ 错误: 请设置 ACCOUNT1_L1_PRIVATE_KEY"
        exit 1
    fi
    if [ "$ACCOUNT2_L1_ADDRESS" == "0x你的账户2L1地址" ] || [ -z "$ACCOUNT2_L1_ADDRESS" ]; then
        echo "❌ 错误: 请设置 ACCOUNT2_L1_ADDRESS"
        exit 1
    fi
    if [ "$ACCOUNT2_L1_PRIVATE_KEY" == "0x你的账户2L1私钥" ] || [ -z "$ACCOUNT2_L1_PRIVATE_KEY" ]; then
        echo "❌ 错误: 请设置 ACCOUNT2_L1_PRIVATE_KEY"
        exit 1
    fi

    # 额外校验：以太坊地址=20字节(40 hex)，私钥=32字节(64 hex)
    check_hex_len "ACCOUNT1_L1_ADDRESS" "$ACCOUNT1_L1_ADDRESS" 40
    check_hex_len "ACCOUNT2_L1_ADDRESS" "$ACCOUNT2_L1_ADDRESS" 40
    check_hex_len "ACCOUNT1_L1_PRIVATE_KEY" "$ACCOUNT1_L1_PRIVATE_KEY" 64
    check_hex_len "ACCOUNT2_L1_PRIVATE_KEY" "$ACCOUNT2_L1_PRIVATE_KEY" 64
fi

echo "✅ 配置验证通过"
echo ""
echo "AUTH_MODE: $AUTH_MODE"
if [ "$AUTH_MODE" == "subkey" ]; then
    echo "账户1 L2地址: ${ACCOUNT1_L2_ADDRESS:0:20}..."
    echo "账户2 L2地址: ${ACCOUNT2_L2_ADDRESS:0:20}..."
else
    echo "账户1 L1地址: ${ACCOUNT1_L1_ADDRESS:0:20}..."
    echo "账户2 L1地址: ${ACCOUNT2_L1_ADDRESS:0:20}..."
fi
echo "交易市场: $MARKET"
echo "动态下单: $USE_DYNAMIC_SIZE (FUNDS_RATIO=$FUNDS_RATIO, TARGET_LEVERAGE=${TARGET_LEVERAGE}x)"
echo "交易间隔: ${MIN_TRADE_INTERVAL}s"
echo "固定数量(仅动态关闭时生效): $TRADE_SIZE"
echo "价差阈值: $MIN_SPREAD_THRESHOLD"
echo ""

# ============================================
# 运行脚本
# ============================================

PYTHON_BIN=""

# Prefer project virtualenv if present (recommended)
if [ -x "../.venv/bin/python" ]; then
    PYTHON_BIN="../.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    PYTHON_BIN="python"
fi

echo "启动套利策略..."
echo "按 Ctrl+C 停止"
echo "=========================================="
echo ""

$PYTHON_BIN arbitrage_btc_usdt.py

