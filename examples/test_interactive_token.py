#!/usr/bin/env python3
"""
测试interactive token是否免费
使用方法: python test_interactive_token.py
"""

import asyncio
import logging
from decimal import Decimal

from paradex_py.account.subkey_account import SubkeyAccount
from paradex_py.api.api_client import ParadexApiClient
from paradex_py.common.order import Order, OrderSide, OrderType

# 配置你的账户信息
L2_ADDRESS = "0x28a3d30a3c03124258d5e86ff58757f901311767a08ffa49c9468ee7bf0793"
L2_PRIVATE_KEY = "0x07ad5c1e7d962d345a2cc970f2106518bc023ad0b7b3786b0934ed84b576fb31"
MARKET = "BTC-USD-PERP"
TRADE_SIZE = "0.001"  # 0.001 BTC


async def main():
    # 设置日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Interactive Token 免费交易测试")
    logger.info("=" * 60)

    # 创建 ParadexApiClient，使用 interactive token
    api_client = ParadexApiClient(
        env="prod",
        logger=logger,
        use_interactive_token=True,  # 启用免费interactive token
    )

    # 获取系统配置
    config = api_client.fetch_system_config()

    # 创建 subkey 账户
    account = SubkeyAccount(
        config=config,
        l2_private_key=L2_PRIVATE_KEY,
        l2_address=L2_ADDRESS,
    )

    # 初始化账户（会使用interactive token获取JWT）
    api_client.init_account(account)

    logger.info(f"账户L2地址: {hex(account.l2_address)}")
    logger.info(f"使用Interactive Token: {api_client.use_interactive_token}")

    # 获取账户信息
    summary = api_client.fetch_account_summary()
    logger.info(f"账户余额: {summary.free_collateral} {summary.settlement_asset}")

    # 下一个市价单测试
    logger.info(f"\n在 {MARKET} 下一个测试买单，大小: {TRADE_SIZE}")

    order = Order(
        market=MARKET,
        order_type=OrderType.Market,
        order_side=OrderSide.Buy,
        size=Decimal(TRADE_SIZE),
    )

    # 提交订单
    result = api_client.submit_order(order)
    order_id = result.get('id', 'unknown')
    logger.info(f"订单提交成功! Order ID: {order_id}")

    # 等待成交
    logger.info("等待订单成交...")
    await asyncio.sleep(3)

    # 查询成交记录
    fills = api_client.fetch_fills({
        "market": MARKET,
        "page_size": 10,
    })

    logger.info("\n" + "=" * 60)
    logger.info("成交记录 (Fills):")
    logger.info("=" * 60)

    if fills.get('results'):
        for fill in fills['results']:
            fee = fill.get('fee', '0')
            fee_token = fill.get('fee_token', 'USDC')
            price = fill.get('price', '0')
            size = fill.get('size', '0')
            side = fill.get('side', '')

            logger.info(f"方向: {side}")
            logger.info(f"  成交价格: {price}")
            logger.info(f"  成交数量: {size}")
            logger.info(f"  手续费: {fee} {fee_token}")
            logger.info("-" * 40)
    else:
        logger.info("暂无成交记录")

    # 查询订单状态
    logger.info(f"\n查询订单状态: {order_id}")
    order_status = api_client.fetch_order(order_id)
    logger.info(f"订单状态: {order_status.get('status', 'unknown')}")

    logger.info("\n" + "=" * 60)
    logger.info("测试完成!")
    logger.info("如果手续费为0，则说明interactive token免费功能生效")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
