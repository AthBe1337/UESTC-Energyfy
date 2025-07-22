import logging
import os
from logging.handlers import TimedRotatingFileHandler
import threading


class Logger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # 使用双重检查锁定确保线程安全
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(Logger, cls).__new__(cls)
                    # 只在首次实例化时初始化
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, name="app", log_level=logging.INFO,
                 log_to_console=True, log_to_file=True, log_file="app.log",
                 backup_count=7, when='midnight', fmt=None, datefmt=None):
        # 防止重复初始化
        if self._initialized:
            return

        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)

        # 清除可能存在的旧处理器
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # 设置日志格式
        fmt = fmt or '%(asctime)s | %(levelname)-8s | %(message)s'
        datefmt = datefmt or '%Y-%m-%d %H:%M:%S'
        formatter = logging.Formatter(fmt, datefmt)

        # 控制台处理器
        if log_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        # 文件处理器（带轮转）
        if log_to_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = TimedRotatingFileHandler(
                filename=log_file,
                when=when,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        # 防止重复初始化
        self._initialized = True

    # 日志方法
    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs, exc_info=True)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs, exc_info=True)

    def exception(self, msg, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)


# 全局访问点
def get_logger():
    """获取全局日志实例"""
    if Logger._instance is None:
        # 默认配置初始化
        Logger(
            name="Energyfy",
            log_level=logging.INFO,
            log_to_console=True,
            log_to_file=True,
            log_file="logs/Energyfy.log",
            backup_count=7
        )
    return Logger._instance
