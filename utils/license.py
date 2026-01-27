# -*- coding: utf-8 -*-
"""License授权验证模块

功能：
- 验证License文件有效性
- 检查授权是否过期
- 提供授权信息查询
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import redirect, url_for, request

# 密钥（用于签名验证，请勿泄露）
_SECRET_KEY = "TechTeam@ACC2026!Lic#Key"

# License文件路径
# PyInstaller打包后，sys.executable指向exe文件，license.lic应放在exe同级目录
# 开发模式下，使用__file__定位到web_app目录
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后，获取 exe 所在目录
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    # 开发模式，utils/license.py -> web_app/
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LICENSE_FILE = os.path.join(_BASE_DIR, 'license.lic')


def _generate_signature(data: dict) -> str:
    """生成License签名"""
    # 按固定顺序拼接关键字段
    sign_str = f"{data.get('product', '')}" \
               f"{data.get('customer', '')}" \
               f"{data.get('expire_date', '')}" \
               f"{_SECRET_KEY}"
    return hashlib.sha256(sign_str.encode('utf-8')).hexdigest()


def _verify_signature(data: dict, signature: str) -> bool:
    """验证License签名"""
    expected = _generate_signature(data)
    return expected == signature


def load_license() -> dict:
    """加载License文件

    Returns:
        dict: License信息，包含 valid, message, data 字段
    """
    if not os.path.exists(LICENSE_FILE):
        return {
            'valid': False,
            'message': '未找到授权文件',
            'data': None
        }

    try:
        with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        # 解码License内容
        import base64
        try:
            decoded = base64.b64decode(content).decode('utf-8')
            lic_data = json.loads(decoded)
        except:
            return {
                'valid': False,
                'message': '授权文件格式无效',
                'data': None
            }

        # 验证签名
        signature = lic_data.pop('signature', '')
        if not _verify_signature(lic_data, signature):
            return {
                'valid': False,
                'message': '授权文件签名无效',
                'data': None
            }

        # 还原签名字段
        lic_data['signature'] = signature

        return {
            'valid': True,
            'message': 'OK',
            'data': lic_data
        }

    except Exception as e:
        return {
            'valid': False,
            'message': f'读取授权文件失败: {str(e)}',
            'data': None
        }


def check_license() -> dict:
    """检查License是否有效且未过期

    Returns:
        dict: 检查结果，包含 valid, expired, message, license_info 字段
    """
    result = load_license()

    if not result['valid']:
        return {
            'valid': False,
            'expired': False,
            'message': result['message'],
            'license_info': None
        }

    lic_data = result['data']

    # 检查过期时间
    try:
        expire_date = datetime.strptime(lic_data['expire_date'], '%Y-%m-%d')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # 过期日期当天仍然有效，第二天才算过期
        expire_date_end = expire_date.replace(hour=23, minute=59, second=59)

        if today > expire_date_end:
            days_expired = (today - expire_date).days
            return {
                'valid': False,
                'expired': True,
                'message': f'授权已过期 {days_expired} 天',
                'license_info': {
                    'product': lic_data.get('product', '-'),
                    'customer': lic_data.get('customer', '-'),
                    'expire_date': lic_data.get('expire_date', '-'),
                    'days_remaining': -days_expired
                }
            }

        days_remaining = (expire_date - today).days

        return {
            'valid': True,
            'expired': False,
            'message': 'OK',
            'license_info': {
                'product': lic_data.get('product', '-'),
                'customer': lic_data.get('customer', '-'),
                'expire_date': lic_data.get('expire_date', '-'),
                'days_remaining': days_remaining
            }
        }

    except Exception as e:
        return {
            'valid': False,
            'expired': False,
            'message': f'授权日期格式错误: {str(e)}',
            'license_info': None
        }


def get_license_info() -> dict:
    """获取License详细信息（用于显示）

    Returns:
        dict: License信息
    """
    result = check_license()

    if result['license_info']:
        info = result['license_info']
        info['status'] = 'Active' if result['valid'] else ('Expired' if result['expired'] else 'Invalid')
        info['status_class'] = 'success' if result['valid'] else 'danger'

        # 计算剩余天数提示（精确到天）
        if result['valid']:
            if info['days_remaining'] == 0:
                info['warning'] = "License expires today"
            elif info['days_remaining'] <= 30:
                info['warning'] = f"License expiring soon, {info['days_remaining']} days remaining"
            else:
                info['warning'] = None
        else:
            info['warning'] = None

        return info
    else:
        return {
            'product': '-',
            'customer': '-',
            'expire_date': '-',
            'days_remaining': 0,
            'status': 'Invalid',
            'status_class': 'danger',
            'warning': None
        }


def generate_license(product: str, customer: str, expire_date: str) -> str:
    """生成License文件内容

    Args:
        product: 产品名称
        customer: 客户名称
        expire_date: 过期日期 (YYYY-MM-DD)

    Returns:
        str: Base64编码的License内容
    """
    import base64

    lic_data = {
        'product': product,
        'customer': customer,
        'expire_date': expire_date,
        'issue_date': datetime.now().strftime('%Y-%m-%d')
    }

    # 生成签名
    signature = _generate_signature(lic_data)
    lic_data['signature'] = signature

    # 编码
    json_str = json.dumps(lic_data, ensure_ascii=False)
    encoded = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

    return encoded


# 全局缓存，避免每次请求都读取文件
_license_cache = None
_cache_time = None
_CACHE_DURATION = 10  # 缓存10秒（缩短缓存时间以提高安全性）


def get_cached_license_status() -> dict:
    """获取缓存的License状态（减少文件IO）

    安全机制：
    1. 如果license文件不存在，立即返回无效状态（不使用缓存）
    2. 缓存有效期为10秒，超过后重新检查
    """
    global _license_cache, _cache_time

    # 安全检查：如果license文件不存在，立即返回无效（不使用缓存）
    if not os.path.exists(LICENSE_FILE):
        _license_cache = None
        _cache_time = None
        return {
            'valid': False,
            'expired': False,
            'message': '未找到授权文件',
            'license_info': None
        }

    now = datetime.now()
    # 修复bug: 使用total_seconds()获取正确的秒数差值
    if _license_cache is None or _cache_time is None or (now - _cache_time).total_seconds() > _CACHE_DURATION:
        _license_cache = check_license()
        _cache_time = now

    return _license_cache


def clear_license_cache():
    """清除License缓存（更新License后调用）"""
    global _license_cache, _cache_time
    _license_cache = None
    _cache_time = None
