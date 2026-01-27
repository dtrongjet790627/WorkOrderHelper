# -*- coding: utf-8 -*-
"""
权限控制模块
检查用户是否有权限执行数据修改操作
"""

import cx_Oracle
import hashlib
from config.database import DB_CONFIG

# iplant_web用户配置（用于权限验证）
IPLANT_WEB_CONFIG = {
    'user': 'iplant_web',
    'password': 'iplant',
}

# 有权限的职位关键词
PERMISSION_JOB_KEYWORDS = ['线长', '生产主管', '制造总监', '制造经理']

# 特殊用户（直接有权限）
PERMISSION_SPECIAL_USERS = ['8888']


def get_iplant_web_connection():
    """获取iplant_web数据库连接"""
    dsn = cx_Oracle.makedsn(
        DB_CONFIG['host'],
        DB_CONFIG['port'],
        service_name=DB_CONFIG['service_name']
    )
    conn = cx_Oracle.connect(
        user=IPLANT_WEB_CONFIG['user'],
        password=IPLANT_WEB_CONFIG['password'],
        dsn=dsn
    )
    return conn


def check_user_permission(username):
    """
    检查用户是否有数据修改权限

    Args:
        username: 用户工号

    Returns:
        dict: {
            'has_permission': bool,  # 是否有权限
            'username': str,         # 用户名
            'job': str,              # 职位
            'reason': str            # 权限原因说明
        }
    """
    if not username:
        return {
            'has_permission': False,
            'username': '',
            'job': '',
            'reason': '未提供用户工号'
        }

    username = str(username).strip()

    # 检查特殊用户
    if username in PERMISSION_SPECIAL_USERS:
        return {
            'has_permission': True,
            'username': username,
            'job': '系统管理员',
            'reason': '特殊授权用户'
        }

    try:
        conn = get_iplant_web_connection()
        cursor = conn.cursor()

        # 查询用户信息
        cursor.execute("""
            SELECT USERNAME, JOB FROM IPLANT_USER
            WHERE USERNAME = :username
        """, {'username': username})

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {
                'has_permission': False,
                'username': username,
                'job': '',
                'reason': '用户不存在'
            }

        db_username = row[0] or ''
        job = row[1] or ''

        # 检查职位是否包含授权关键词
        for keyword in PERMISSION_JOB_KEYWORDS:
            if keyword in job:
                return {
                    'has_permission': True,
                    'username': db_username,
                    'job': job,
                    'reason': f'职位包含"{keyword}"'
                }

        return {
            'has_permission': False,
            'username': db_username,
            'job': job,
            'reason': '职位无数据修改权限'
        }

    except Exception as e:
        return {
            'has_permission': False,
            'username': username,
            'job': '',
            'reason': f'权限验证失败: {str(e)}'
        }


def validate_user_login(username, password):
    """
    验证用户登录（工号+MD5密码）

    Args:
        username: 用户工号
        password: 用户密码（明文，会进行MD5加密后比对）

    Returns:
        dict: {
            'valid': bool,           # 登录是否成功
            'username': str,         # 用户名
            'job': str,              # 职位
            'has_permission': bool,  # 是否有数据修改权限
            'reason': str            # 说明
        }
    """
    if not username or not password:
        return {
            'valid': False,
            'username': username or '',
            'job': '',
            'has_permission': False,
            'reason': '请输入用户名和密码'
        }

    username = str(username).strip()
    password = str(password).strip()

    # 计算密码的MD5值
    password_md5 = hashlib.md5(password.encode('utf-8')).hexdigest().upper()

    try:
        conn = get_iplant_web_connection()
        cursor = conn.cursor()

        # 查询用户信息和密码
        cursor.execute("""
            SELECT USERNAME, PASSWORD, JOB FROM IPLANT_USER
            WHERE USERNAME = :username
        """, {'username': username})

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {
                'valid': False,
                'username': username,
                'job': '',
                'has_permission': False,
                'reason': '用户名不存在，请检查输入'
            }

        db_username = row[0] or ''
        db_password = (row[1] or '').upper()  # 数据库中的MD5密码
        job = row[2] or ''

        # 验证密码（所有用户都需要验证密码，包括8888）
        if db_password != password_md5:
            return {
                'valid': False,
                'username': db_username,
                'job': '',
                'has_permission': False,
                'reason': '密码错误，请重新输入'
            }

        # 检查职位权限
        has_permission = False
        permission_reason = '职位无数据修改权限'

        # 特殊用户8888直接有权限
        if username in PERMISSION_SPECIAL_USERS:
            has_permission = True
            permission_reason = '特殊授权用户'
        else:
            # 检查职位是否包含授权关键词
            for keyword in PERMISSION_JOB_KEYWORDS:
                if keyword in job:
                    has_permission = True
                    permission_reason = f'职位包含"{keyword}"'
                    break

        return {
            'valid': True,
            'username': db_username,
            'job': job,
            'has_permission': has_permission,
            'reason': permission_reason
        }

    except Exception as e:
        return {
            'valid': False,
            'username': username,
            'job': '',
            'has_permission': False,
            'reason': f'登录验证失败: {str(e)}'
        }


def require_permission(func):
    """
    权限验证装饰器
    用于API路由函数，自动检查请求中的用户权限

    使用方式:
        @require_permission
        def my_api():
            ...
    """
    from functools import wraps
    from flask import request, jsonify

    @wraps(func)
    def wrapper(*args, **kwargs):
        # 从请求中获取用户名
        data = request.json or {}
        username = data.get('operator_id') or data.get('username') or ''

        # 检查权限
        permission = check_user_permission(username)

        if not permission['has_permission']:
            return jsonify({
                'error': '无操作权限',
                'permission_error': True,
                'reason': permission['reason'],
                'username': permission['username']
            }), 403

        return func(*args, **kwargs)

    return wrapper
