# -*- coding: utf-8 -*-
"""
系统日志模块

功能：
- 系统运行日志（启动、错误、异常）
- 数据库操作日志（查询、插入、更新）
- 用户行为日志（登录、操作）
- API调用日志（请求、响应）

日志按日期存储到 logs/ 目录
轮转的旧日志自动压缩为 .gz 格式
"""

import os
import sys
import logging
import gzip
import shutil
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from functools import wraps
import json
import traceback

# 获取基础目录
# PyInstaller打包后，sys.executable指向exe文件，日志应放在exe同级目录
# 开发模式下，使用__file__定位到web_app目录
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后，获取 exe 所在目录
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    # 开发模式，utils/logger.py -> web_app/
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 日志目录
LOG_DIR = os.path.join(_BASE_DIR, 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)


# ============================================
#   日志压缩功能
# ============================================
def compress_log_file(source, dest):
    """压缩日志文件为 .gz 格式

    Args:
        source: 源文件路径
        dest: 目标文件路径（将自动添加 .gz 后缀）
    """
    try:
        gz_dest = dest + '.gz'
        with open(source, 'rb') as f_in:
            with gzip.open(gz_dest, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(source)  # 删除原文件
    except Exception as e:
        print(f"[LOG] 日志压缩失败: {e}")


def namer(name):
    """自定义轮转文件命名（添加 .gz 后缀）"""
    return name + '.gz'


def rotator(source, dest):
    """自定义轮转处理器（压缩旧日志）"""
    compress_log_file(source, dest)


# ============================================
#   日志格式化器
# ============================================
class JsonFormatter(logging.Formatter):
    """JSON格式日志（便于解析）"""
    def format(self, record):
        log_data = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'category': getattr(record, 'category', 'SYSTEM'),
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


class ReadableFormatter(logging.Formatter):
    """可读格式日志"""
    def format(self, record):
        category = getattr(record, 'category', 'SYSTEM')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        base = f"[{timestamp}] [{record.levelname}] [{category}] {record.getMessage()}"
        if hasattr(record, 'extra_data') and record.extra_data:
            base += f" | {record.extra_data}"
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
        return base


# ============================================
#   创建日志记录器
# ============================================
def create_logger(name, filename, use_json=False, compress=True):
    """创建日志记录器

    Args:
        name: 日志器名称
        filename: 日志文件名
        use_json: 是否使用JSON格式
        compress: 是否压缩轮转的旧日志（默认True）
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    # 文件处理器（按天轮转，保留30天）
    log_file = os.path.join(LOG_DIR, filename)
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.suffix = '%Y-%m-%d.log'

    # 启用日志压缩
    if compress:
        file_handler.rotator = rotator
        file_handler.namer = namer

    if use_json:
        file_handler.setFormatter(JsonFormatter())
    else:
        file_handler.setFormatter(ReadableFormatter())

    logger.addHandler(file_handler)

    # 控制台处理器（仅WARNING以上）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(ReadableFormatter())
    logger.addHandler(console_handler)

    return logger


# 创建各类日志记录器
system_logger = create_logger('system', 'system.log')      # 系统运行
db_logger = create_logger('database', 'database.log')       # 数据库操作
api_logger = create_logger('api', 'api.log')               # API调用
user_logger = create_logger('user', 'user.log')            # 用户行为


# ============================================
#   日志记录函数
# ============================================
def log_system(level, message, **kwargs):
    """记录系统日志"""
    record = system_logger.makeRecord(
        'system', getattr(logging, level.upper(), logging.INFO),
        '', 0, message, (), None
    )
    record.category = 'SYSTEM'
    record.extra_data = kwargs if kwargs else None
    system_logger.handle(record)


def log_db(operation, table, message, **kwargs):
    """记录数据库操作日志

    Args:
        operation: 操作类型 (SELECT/INSERT/UPDATE/DELETE/CONNECT)
        table: 表名
        message: 日志消息
        **kwargs: 额外数据（如affected_rows, sql等）
    """
    extra = {'operation': operation, 'table': table}
    extra.update(kwargs)

    record = db_logger.makeRecord(
        'database', logging.INFO,
        '', 0, message, (), None
    )
    record.category = f'DB:{operation}'
    record.extra_data = extra
    db_logger.handle(record)


def log_api(method, path, status_code, duration_ms, **kwargs):
    """记录API调用日志

    Args:
        method: HTTP方法
        path: 请求路径
        status_code: 响应状态码
        duration_ms: 耗时(毫秒)
        **kwargs: 额外数据（如operator, params等）
    """
    level = logging.INFO if status_code < 400 else logging.WARNING
    message = f"{method} {path} -> {status_code} ({duration_ms}ms)"

    extra = {'method': method, 'path': path, 'status': status_code, 'duration': duration_ms}
    extra.update(kwargs)

    record = api_logger.makeRecord(
        'api', level,
        '', 0, message, (), None
    )
    record.category = 'API'
    record.extra_data = extra
    api_logger.handle(record)


def log_user(action, operator, message, **kwargs):
    """记录用户行为日志

    Args:
        action: 操作类型 (LOGIN/LOGOUT/ADD_TO_WO/PACKING/SYNC等)
        operator: 操作人
        message: 日志消息
        **kwargs: 额外数据
    """
    extra = {'action': action, 'operator': operator}
    extra.update(kwargs)

    record = user_logger.makeRecord(
        'user', logging.INFO,
        '', 0, message, (), None
    )
    record.category = f'USER:{action}'
    record.extra_data = extra
    user_logger.handle(record)

    # 强制刷新确保日志立即写入文件
    for handler in user_logger.handlers:
        if hasattr(handler, 'flush'):
            handler.flush()


def log_error(message, exc_info=None, **kwargs):
    """记录错误日志"""
    record = system_logger.makeRecord(
        'system', logging.ERROR,
        '', 0, message, (), exc_info
    )
    record.category = 'ERROR'
    record.extra_data = kwargs if kwargs else None
    system_logger.handle(record)


# ============================================
#   装饰器：自动记录函数调用
# ============================================
def log_function_call(logger_func=None, action='FUNCTION'):
    """装饰器：记录函数调用"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = datetime.now()
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start).total_seconds() * 1000
                if logger_func:
                    logger_func(action, f"{func.__name__} 执行成功", duration_ms=round(duration))
                return result
            except Exception as e:
                duration = (datetime.now() - start).total_seconds() * 1000
                log_error(f"{func.__name__} 执行失败: {str(e)}", exc_info=True, duration_ms=round(duration))
                raise
        return wrapper
    return decorator


# ============================================
#   日志查询函数
# ============================================
def get_log_files():
    """获取所有日志文件列表"""
    files = []
    if os.path.exists(LOG_DIR):
        for f in os.listdir(LOG_DIR):
            if f.endswith('.log'):
                filepath = os.path.join(LOG_DIR, f)
                stat = os.stat(filepath)
                files.append({
                    'name': f,
                    'size': stat.st_size,
                    'size_str': format_size(stat.st_size),
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
    return sorted(files, key=lambda x: x['mtime'], reverse=True)


def read_log_file(filename, lines=500, search=None, level=None):
    """读取日志文件内容

    Args:
        filename: 文件名
        lines: 读取行数（从末尾开始）
        search: 搜索关键词
        level: 日志级别筛选

    Returns:
        list: 日志行列表
    """
    filepath = os.path.join(LOG_DIR, filename)
    if not os.path.exists(filepath):
        return []

    result = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            # 从末尾读取
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

            for line in reversed(recent_lines):  # 最新的在前
                line = line.strip()
                if not line:
                    continue
                # 筛选
                if search and search.lower() not in line.lower():
                    continue
                if level and f'[{level}]' not in line:
                    continue
                result.append(line)

    except Exception as e:
        result.append(f"读取日志失败: {str(e)}")

    return result


def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


# ============================================
#   启动日志
# ============================================
def log_startup():
    """记录系统启动"""
    log_system('INFO', '系统启动', version='V2.1')


def log_shutdown():
    """记录系统关闭"""
    log_system('INFO', '系统关闭')
