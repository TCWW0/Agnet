import time
import unittest
import os
from frame.core.logger import Logger, Level

# 测试 Logger 的基本功能和日志文件生成
class TestLoggerBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.log_file = "test_basic.log"
        # 确保测试前日志文件不存在
        log_path = os.path.join("bin/logs", self.log_file)
        if os.path.exists(log_path):
            os.remove(log_path)
        self.logger = Logger(file_name=self.log_file, min_level=Level.DEBUG, flush_interval=1.0,buffer_size=128)

    def test_log_creation(self):
        self.logger.debug("Debug message")  # 应该被记录
        self.logger.info("Info message")    # 应该被记录
        self.logger.warning("Warning message")  # 应该被记录
        self.logger.error("Error message")  # 应该被记录
        self.logger.critical("Critical message")  # 应该被记录
        # 等待日志写入
        time.sleep(1.5)
        log_path = os.path.join("bin/logs", self.log_file)
        self.assertTrue(os.path.exists(log_path), "Log file should be created")
        with open(log_path, "r") as f:
            content = f.read()
            self.assertIn("Debug message", content, "Debug message should be in log")
            self.assertIn("Info message", content, "Info message should be in log")
            self.assertIn("Warning message", content, "Warning message should be in log")
            self.assertIn("Error message", content, "Error message should be in log")
            self.assertIn("Critical message", content, "Critical message should be in log")

    def test_level_filter(self):
        self.logger.min_level_ = Level.WARNING
        self.logger.debug("Debug message")  # 不应该被记录
        self.logger.info("Info message")    # 不应该被记录
        self.logger.warning("Warning message")  # 应该被记录
        self.logger.error("Error message")  # 应该被记录
        self.logger.critical("Critical message")  # 应该被记录
        # 等待日志写入
        time.sleep(1.5)
        log_path = os.path.join("bin/logs", self.log_file)
        with open(log_path, "r") as f:
            content = f.read()
            self.assertNotIn("Debug message", content, "Debug message should NOT be in log")
            self.assertNotIn("Info message", content, "Info message should NOT be in log")
            self.assertIn("Warning message", content, "Warning message should be in log")
            self.assertIn("Error message", content, "Error message should be in log")
            self.assertIn("Critical message", content, "Critical message should be in log")

