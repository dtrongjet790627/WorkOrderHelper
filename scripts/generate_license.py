# -*- coding: utf-8 -*-
"""
License生成工具

用法:
    python generate_license.py --days 365
    python generate_license.py --customer "CustomName" --expire 2027-01-23

参数:
    --customer: 客户名称 (默认: LEEKR)
    --days: 有效天数 (与--expire二选一)
    --expire: 过期日期 YYYY-MM-DD (与--days二选一)
    --output: 输出文件路径 (默认: license.lic)
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.license import generate_license


def main():
    parser = argparse.ArgumentParser(description='Generate License File')
    parser.add_argument('--customer', default='LEEKR', help='Customer name (default: LEEKR)')
    parser.add_argument('--days', type=int, help='Valid days')
    parser.add_argument('--expire', help='Expire date (YYYY-MM-DD)')
    parser.add_argument('--output', default='license.lic', help='Output file path')
    parser.add_argument('--product', default='工单小管家', help='Product name')

    args = parser.parse_args()

    # 计算过期日期
    if args.expire:
        try:
            expire_date = datetime.strptime(args.expire, '%Y-%m-%d')
        except ValueError:
            print(f"Error: Invalid date format, please use YYYY-MM-DD")
            sys.exit(1)
    elif args.days is not None:  # 支持 --days 0
        expire_date = datetime.now() + timedelta(days=args.days)
    else:
        print("Error: Please specify --days or --expire parameter")
        sys.exit(1)

    expire_str = expire_date.strftime('%Y-%m-%d')

    # 生成License
    license_content = generate_license(
        product=args.product,
        customer=args.customer,
        expire_date=expire_str
    )

    # 确定输出路径
    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(os.path.dirname(__file__), output_path)

    # 写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(license_content)

    print("=" * 50)
    print("License Generated Successfully!")
    print("=" * 50)
    print(f"Product:  {args.product}")
    print(f"Customer: {args.customer}")
    print(f"Expires:  {expire_str}")
    print(f"Created:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output:   {os.path.abspath(output_path)}")
    print("=" * 50)


if __name__ == '__main__':
    main()
