#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ACC工单管理系统 - ERP收货处理

项目结构:
    config/         配置模块
    models/         数据库连接模块
    utils/          工具函数
    routes/         路由蓝图
    templates/      HTML模板
    static/         静态资源
"""

import sys
import os

# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 启用 oracledb thick mode（支持 Oracle 11g）
import oracledb
try:
    oracledb.init_oracle_client()  # 服务器环境：自动从系统PATH检测Oracle客户端
except Exception:
    try:
        oracledb.init_oracle_client(lib_dir=r"D:\Software_Space\instantclient_23_0")  # 本地开发环境回退
    except Exception as e:
        print(f"[WARNING] Oracle thick mode init failed: {e}")

from flask import Flask, render_template, request, redirect, url_for, jsonify
from config.settings import APP_CONFIG
from config.database import LINE_CONFIG
from routes import register_blueprints
from utils.license import get_cached_license_status, get_license_info, clear_license_cache, LICENSE_FILE

# 不需要License检查的路径
LICENSE_EXEMPT_PATHS = [
    '/license',
    '/api/activate_license',
    '/api/license_info',
    '/static/',
    '/favicon.ico'
]


def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = APP_CONFIG['MAX_CONTENT_LENGTH']

    # 注册蓝图
    register_blueprints(app)

    @app.before_request
    def check_license():
        """请求前检查License授权"""
        for path in LICENSE_EXEMPT_PATHS:
            if request.path.startswith(path):
                return None
        status = get_cached_license_status()
        if not status['valid']:
            return redirect(url_for('license_page'))
        return None

    # 首页路由
    @app.route('/')
    def index():
        return render_template('index_hulu.html', lines=LINE_CONFIG)

    @app.route('/license')
    def license_page():
        """授权验证页面"""
        status = get_cached_license_status()
        return render_template('license_expired.html',
                               license_info=status.get('license_info'),
                               message=status.get('message'))

    @app.route('/api/activate_license', methods=['POST'])
    def activate_license():
        """激活License"""
        try:
            import base64
            import json as json_lib
            data = request.json
            license_code = data.get('license_code', '').strip()

            if not license_code:
                return jsonify({'success': False, 'message': '请输入授权码'})

            try:
                decoded = base64.b64decode(license_code).decode('utf-8')
                lic_data = json_lib.loads(decoded)

                if 'expire_date' not in lic_data or 'signature' not in lic_data:
                    return jsonify({'success': False, 'message': '授权码格式无效'})

                from datetime import datetime
                expire_date = datetime.strptime(lic_data['expire_date'], '%Y-%m-%d')
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                expire_date_end = expire_date.replace(hour=23, minute=59, second=59)
                if today > expire_date_end:
                    return jsonify({'success': False, 'message': f"授权码已过期 ({lic_data['expire_date']})"})
            except Exception:
                return jsonify({'success': False, 'message': '授权码无效，无法解析'})

            with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
                f.write(license_code)

            clear_license_cache()

            from utils.license import check_license as verify_license
            result = verify_license()
            if result['valid']:
                info = result['license_info']
                return jsonify({
                    'success': True,
                    'message': f"授权成功！有效期至 {info['expire_date']}，剩余 {info['days_remaining']} 天"
                })
            else:
                return jsonify({'success': False, 'message': result['message']})

        except Exception as e:
            return jsonify({'success': False, 'message': f'激活失败: {str(e)}'})

    @app.route('/api/license_info')
    def api_license_info():
        """获取License信息API"""
        return jsonify(get_license_info())

    return app


# 创建应用实例
app = create_app()


if __name__ == '__main__':
    app.run(
        host=APP_CONFIG['HOST'],
        port=APP_CONFIG['PORT'],
        debug=APP_CONFIG['DEBUG']
    )
