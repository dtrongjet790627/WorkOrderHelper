# -*- coding: utf-8 -*-
"""
用户权限验证路由
"""

from flask import Blueprint, request, jsonify
from utils.permission import check_user_permission, validate_user_login
from utils.logger import log_user

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/check_permission', methods=['GET', 'POST'])
def api_check_permission():
    """
    检查用户是否有数据修改权限

    请求参数:
        username: 用户工号（GET参数或POST JSON）

    返回:
        {
            'has_permission': bool,  # 是否有权限
            'username': str,         # 用户名
            'job': str,              # 职位
            'reason': str            # 权限原因说明
        }
    """
    if request.method == 'GET':
        username = request.args.get('username', '')
    else:
        data = request.json or {}
        username = data.get('username', '')

    result = check_user_permission(username)
    return jsonify(result)


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    """
    用户登录验证（工号+密码）

    请求参数:
        username: 用户工号
        password: 用户密码（明文）

    返回:
        {
            'valid': bool,           # 登录是否成功
            'username': str,         # 用户名
            'job': str,              # 职位
            'has_permission': bool,  # 是否有数据修改权限
            'reason': str            # 说明
        }
    """
    data = request.json or {}
    username = data.get('username', '')
    password = data.get('password', '')

    result = validate_user_login(username, password)

    # 记录登录日志
    if result.get('valid'):
        log_user('LOGIN', username, f"用户登录成功",
                 job=result.get('job', ''),
                 has_permission=result.get('has_permission', False))
    else:
        log_user('LOGIN_FAIL', username or '未知', f"登录失败: {result.get('reason', '未知原因')}")

    return jsonify(result)


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    """
    用户登出（记录日志）

    请求参数:
        username: 用户工号

    返回:
        {'success': bool, 'message': str}
    """
    data = request.json or {}
    username = data.get('username', '')

    if username:
        log_user('LOGOUT', username, f"用户登出")
        return jsonify({'success': True, 'message': '登出成功'})
    else:
        return jsonify({'success': False, 'message': '未提供用户名'})


@auth_bp.route('/api/validate_user', methods=['POST'])
def api_validate_user():
    """
    验证用户是否存在（仅检查用户名，不验证密码）
    用于快速检查用户是否存在

    请求参数:
        username: 用户工号

    返回:
        {
            'valid': bool,           # 用户是否存在
            'username': str,         # 用户名
            'job': str,              # 职位
            'has_permission': bool,  # 是否有数据修改权限
            'reason': str            # 权限原因说明
        }
    """
    data = request.json or {}
    username = data.get('username', '')

    if not username:
        return jsonify({
            'valid': False,
            'username': '',
            'job': '',
            'has_permission': False,
            'reason': '请输入工号'
        })

    result = check_user_permission(username)

    # 用户存在的条件：不是"用户不存在"
    valid = result['reason'] != '用户不存在'

    return jsonify({
        'valid': valid,
        'username': result['username'],
        'job': result['job'],
        'has_permission': result['has_permission'],
        'reason': result['reason']
    })
