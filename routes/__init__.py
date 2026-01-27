# -*- coding: utf-8 -*-
"""路由蓝图模块"""

from .workorder import workorder_bp
from .packing import packing_bp
from .erp import erp_bp
from .eai_logs import eai_logs_bp
from .hulu import hulu_bp
from .debug import debug_bp
from .detail_query import detail_query_bp
from .auth import auth_bp
from .logs import logs_bp


def register_blueprints(app):
    """注册所有蓝图

    Args:
        app: Flask应用实例
    """
    app.register_blueprint(workorder_bp)
    app.register_blueprint(packing_bp)
    app.register_blueprint(erp_bp)
    app.register_blueprint(eai_logs_bp)
    app.register_blueprint(hulu_bp)
    app.register_blueprint(debug_bp)
    app.register_blueprint(detail_query_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(logs_bp)
