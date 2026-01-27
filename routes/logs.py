# -*- coding: utf-8 -*-
"""
系统日志查看路由
"""

import os
from flask import Blueprint, jsonify, request

# 导入日志工具
from utils.logger import get_log_files, read_log_file, LOG_DIR

logs_bp = Blueprint('logs', __name__, url_prefix='/api/logs')


@logs_bp.route('/files')
def get_logs_files():
    """获取日志文件列表"""
    try:
        files = get_log_files()
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@logs_bp.route('/read')
def read_logs():
    """读取日志内容"""
    try:
        # 支持file和filename两个参数名
        filename = request.args.get('filename') or request.args.get('file', 'system.log')
        lines = int(request.args.get('lines', 500))
        search = request.args.get('search', '')
        level = request.args.get('level', '')

        # 安全检查：防止路径遍历
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': '非法文件名'})

        content = read_log_file(filename, lines, search if search else None, level if level else None)

        # 获取文件大小信息
        filepath = os.path.join(LOG_DIR, filename)
        size_str = '-'
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    size_str = f"{size:.1f}{unit}"
                    break
                size /= 1024

        return jsonify({
            'lines': content,
            'count': len(content),
            'size_str': size_str,
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)})
