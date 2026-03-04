# -*- coding: utf-8 -*-
"""应用设置"""

import os

APP_CONFIG = {
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB max upload
    'HOST': '0.0.0.0',
    'PORT': int(os.getenv('WO_PORT', '5003')),
    'DEBUG': False
}
