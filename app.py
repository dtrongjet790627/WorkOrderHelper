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

from flask import Flask, render_template
from config.settings import APP_CONFIG
from config.database import LINE_CONFIG
from routes import register_blueprints


def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = APP_CONFIG['MAX_CONTENT_LENGTH']

    # 注册蓝图
    register_blueprints(app)

    # 首页路由
    @app.route('/')
    def index():
        return render_template('index_hulu.html', lines=LINE_CONFIG)

    return app


# 创建应用实例
app = create_app()


if __name__ == '__main__':
    app.run(
        host=APP_CONFIG['HOST'],
        port=APP_CONFIG['PORT'],
        debug=APP_CONFIG['DEBUG']
    )
