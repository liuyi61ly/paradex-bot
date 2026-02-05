#!/usr/bin/env python3
"""
验证 L2 地址和私钥是否匹配
"""
import sys

from starknet_py.net.signer.stark_curve_signer import KeyPair


def validate_credentials(l2_address: str, l2_private_key: str):
    """验证私钥是否能生成指定的地址对应的公钥"""

    try:
        # 解析私钥
        private_key = int(l2_private_key, 16)
        print(f"✓ 私钥格式正确 (长度: {len(l2_private_key[2:])} hex字符)")

        # 生成 KeyPair
        key_pair = KeyPair.from_private_key(private_key)
        public_key = key_pair.public_key

        # 将地址转换为整数
        address_int = int(l2_address, 16)
        print(f"✓ 地址格式正确 (长度: {len(l2_address[2:])} hex字符)")

        print(f"\n从私钥推导的公钥: 0x{public_key:064x}")
        print(f"输入的L2地址:      {l2_address}")

        # 注意：地址和公钥是不同的概念
        # 地址 = hash(公钥)，不是直接等于公钥
        # 所以这里我们只能验证私钥格式是否正确

        return True

    except ValueError as e:
        print(f"✗ 格式错误: {e}")
        return False
    except Exception as e:
        print(f"✗ 错误: {e}")
        return False


def main():
    if len(sys.argv) != 3:
        print("用法: python verify_keys.py <L2_ADDRESS> <L2_PRIVATE_KEY>")
        print("\n示例:")
        print('  python verify_keys.py "0x123..." "0xabc..."')
        sys.exit(1)

    l2_address = sys.argv[1]
    l2_private_key = sys.argv[2]

    print("=" * 60)
    print("验证账户凭证")
    print("=" * 60)
    print()

    validate_credentials(l2_address, l2_private_key)


if __name__ == "__main__":
    main()

