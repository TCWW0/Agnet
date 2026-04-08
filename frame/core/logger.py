"""frame.core.logger

实现说明（简要）
- 基础日志目录由环境变量 ``LOG_DIR`` 决定，若未设置则使用 ``bin/logs``；初始化后不再修改。
- 支持按 workflow_id 绑定日志，可在多个 Agent 中复用同一实例并通过 ``set_workflow_id`` 更新。
- 日志格式：``[WorkFlowID] [timestamp] [classname:function:line] [level]: {message}``
- 暴露简单 API：``debug/info/warning/error/critical``。
- 使用双缓冲（两个内存缓冲区）和后台写线程定期/触发式将日志写磁盘，并在退出时刷新。
"""

from __future__ import annotations

import os
import time
import threading
import inspect
import atexit
from enum import Enum
from typing import List, Optional


class Level(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Logger:
    """轻量线程安全的双缓冲文件日志实现。

    初始化后会在后台启动写线程并在进程退出时自动关闭（通过 ``atexit`` 注册）。
    """

    def __init__(
        self,
        file_name: str,
        workflow_id: Optional[str] = None,
        min_level: Level = Level.INFO,
        buffer_size: int = 1024,
        flush_interval: float = 1.0,
    ) -> None:
        # 基础目录由环境变量决定，初始化后不可更改
        storage_dir = os.getenv("LOG_DIR")
        if not storage_dir:
            storage_dir = "bin/logs"
        self._base_dir = storage_dir

        # 只保留 basename，防止传入相对/绝对路径覆盖 base dir
        safe_name = os.path.basename(file_name) or "app.log"
        self.file_name_ = safe_name

        # 支持按日期与序号轮替：分离文件名 stem 和扩展名
        stem, ext = os.path.splitext(safe_name)
        self._file_stem = stem
        self._file_ext = ext or ".log"

        # 日期格式与大小阈值（大小阈值只能通过环境变量控制）
        self._date_format = "%Y%m%d"
        # 解析环境变量 LOG_FILE_SIZE（支持简单算术表达式，如 "10 * 1024 * 1024 # 10 MB"）
        raw_size = os.getenv("LOG_FILE_SIZE")
        self.max_bytes_: Optional[int] = self._parse_size_env(raw_size) if raw_size else None

        # 如果未配置 LOG_FILE_SIZE，则保持向后兼容：使用原始文件名
        if not self.max_bytes_:
            self.storage_path_ = os.path.join(self._base_dir, self.file_name_)
            self._current_date = None
        else:
            # 当前活跃文件的日期与索引（index=0 表示无序号）
            import time as _time
            self._current_date = _time.strftime(self._date_format, _time.gmtime())
            # 选择初始 storage path（若目录中已有文件则按策略选择）
            self.storage_path_ = self._select_path_for_date(self._current_date, 0)

        self.min_level_ = min_level
        self.workflow_id = workflow_id or "-"

        # 缓冲区阈值（按字节计），默认 1KB
        self._buffer_size = max(1, int(buffer_size))
        self._flush_interval = float(flush_interval)

        # 双缓冲结构（两个 list），active 指示当前写入缓冲区
        self._buffers: List[List[str]] = [[], []]
        # 每个缓冲区当前已占用字节数（用于判断是否满）
        self._buffer_bytes = [0, 0]
        self._active = 0

        # 线程同步/控制
        self._lock = threading.Lock()
        self._flush_event = threading.Event()
        self._stop_event = threading.Event()

        # 确保目录存在
        try:
            os.makedirs(self._base_dir, exist_ok=True)
        except Exception:
            # 若目录创建失败，后续写入会抛出错误，暂不在此处中断
            pass

        # 后台写线程
        self._thread = threading.Thread(
            target=self._writer_loop,
            name=f"LoggerWriter-{self.file_name_}",
            daemon=True,
        )
        self._thread.start()

        # 在进程退出时尽量刷新并关闭
        atexit.register(self.close)

    def set_workflow_id(self, workflow_id: Optional[str]) -> None:
        """设置或更新绑定的 workflow id。"""
        with self._lock:
            self.workflow_id = workflow_id or "-"

    # ----- 简单 API -----
    def debug(self, msg: str, *args, **kwargs) -> None:
        self._log(Level.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        self._log(Level.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._log(Level.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._log(Level.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        self._log(Level.CRITICAL, msg, *args, **kwargs)

    # ----- 内部实现 -----
    def _should_log(self, level: Level) -> bool:
        levels = [Level.DEBUG, Level.INFO, Level.WARNING, Level.ERROR, Level.CRITICAL]
        return levels.index(level) >= levels.index(self.min_level_)

    # ----- 辅助方法：解析环境变量中的文件大小表达式 -----
    def _parse_size_env(self, raw: str) -> Optional[int]:
        """解析环境变量字符串，支持简单的算术表达式并移除注释。返回 int bytes 或 None。"""
        if not raw:
            return None
        v = raw.split("#", 1)[0].strip()
        if not v:
            return None
        try:
            # 使用 ast 安全地求值简单算术表达式
            import ast
            import operator as _op

            allowed_ops = {
                ast.Add: _op.add,
                ast.Sub: _op.sub,
                ast.Mult: _op.mul,
                ast.Div: _op.truediv,
                ast.FloorDiv: _op.floordiv,
                ast.Mod: _op.mod,
                ast.Pow: _op.pow,
            }

            def _eval(node):
                if isinstance(node, ast.Expression):
                    return _eval(node.body)
                if isinstance(node, ast.Constant):
                    if isinstance(node.value, (int, float)):
                        return node.value
                    raise ValueError("invalid constant")
                if isinstance(node, ast.BinOp):
                    left = _eval(node.left)
                    right = _eval(node.right)
                    op = type(node.op)
                    if op in allowed_ops:
                        return allowed_ops[op](left, right)
                    raise ValueError("unsupported operator")
                if isinstance(node, ast.UnaryOp):
                    if isinstance(node.op, ast.UAdd):
                        return +_eval(node.operand)
                    if isinstance(node.op, ast.USub):
                        return -_eval(node.operand)
                    raise ValueError("unsupported unary op")
                raise ValueError("unsupported expression")

            tree = ast.parse(v, mode="eval")
            val = _eval(tree)
            return int(val)
        except Exception:
            try:
                return int(v)
            except Exception:
                return None

    # ----- 辅助方法：按日期/索引选择或创建文件路径 -----
    def _path_for_index(self, date_str: str, index: int) -> str:
        if index <= 0:
            name = f"{self._file_stem}_{date_str}{self._file_ext}"
        else:
            name = f"{self._file_stem}_{date_str}_{index}{self._file_ext}"
        return os.path.join(self._base_dir, name)

    def _next_index_for_date(self, date_str: str) -> int:
        """扫描日志目录，返回下一个可用索引（如果没有文件返回 0）。"""
        max_idx = -1
        try:
            for fn in os.listdir(self._base_dir):
                if not fn.startswith(self._file_stem + "_" + date_str):
                    continue
                stem_fn, ext = os.path.splitext(fn)
                if ext != self._file_ext:
                    continue
                suffix = stem_fn[len(self._file_stem) + 1 + len(date_str) :]
                if not suffix:
                    idx = 0
                elif suffix.startswith("_") and suffix[1:].isdigit():
                    idx = int(suffix[1:])
                else:
                    continue
                if idx > max_idx:
                    max_idx = idx
        except Exception:
            return 0
        return max_idx + 1

    def _select_path_for_date(self, date_str: str, new_bytes: int) -> str:
        """基于当前目录和大小阈值选择一个合适的日志文件路径（可能为无序号文件或带序号文件）。

        new_bytes: 即将写入的字节数（用于判断是否会触发大小轮替）。
        """
        # 首先尝试无序号的基础文件
        candidate0 = self._path_for_index(date_str, 0)
        try:
            if not os.path.exists(candidate0):
                return candidate0
            # 如果未设置大小阈值，直接复用
            if not self.max_bytes_:
                return candidate0
            cur_size = os.path.getsize(candidate0)
            if cur_size + new_bytes <= self.max_bytes_:
                return candidate0
            # 否则，需要使用下一个索引
            next_idx = self._next_index_for_date(date_str)
            return self._path_for_index(date_str, next_idx)
        except Exception:
            # 出错时回退到基础文件名
            return candidate0

    def _log(self, level: Level, msg: str, *args, **kwargs) -> None:
        if not self._should_log(level):
            return
        # 支持多种格式化风格（兼容旧代码中既有的 %-format 与新的 {}.format）
        if args or kwargs:
            # 检测消息中是否包含花括号或百分号，决定优先使用哪种格式化
            has_brace = ("{" in msg and "}" in msg)
            has_percent = "%" in msg

            formatted = None
            # 当字符串明显使用 {} 风格且不包含 % 时，优先使用 str.format
            if has_brace and not has_percent:
                try:
                    formatted = msg.format(*args, **kwargs)
                except Exception:
                    formatted = None
                if formatted is None:
                    try:
                        # 回退到 %-format（若 args/kwargs 适配）
                        if kwargs and not args:
                            formatted = msg % kwargs
                        else:
                            formatted = msg % args
                    except Exception:
                        formatted = None
            else:
                # 否则（默认）优先尝试 %-format，这修复了之前 msg.format 无异常但未替换 % 占位符的问题
                if has_percent:
                    try:
                        if kwargs and not args:
                            formatted = msg % kwargs
                        else:
                            formatted = msg % args
                    except Exception:
                        formatted = None
                    if formatted is None:
                        try:
                            formatted = msg.format(*args, **kwargs)
                        except Exception:
                            formatted = None
                else:
                    # 不包含 % 且也不明显是 %-format，尝试 str.format
                    try:
                        formatted = msg.format(*args, **kwargs)
                    except Exception:
                        formatted = None
                    if formatted is None:
                        try:
                            if kwargs and not args:
                                formatted = msg % kwargs
                            else:
                                formatted = msg % args
                        except Exception:
                            formatted = None

            if formatted is not None:
                msg = formatted

        entry = self._format_entry(level, msg)
        self._enqueue(entry)

    def _format_entry(self, level: Level, msg: str) -> str:
        # 确保单行日志：把消息中的真实换行替换为转义序列 "\\n"，
        # 以便每条日志条目写入文件时始终为单行，便于后续行级解析。
        if isinstance(msg, str):
            # 先把 Windows 风格 CRLF 统一替换，再处理单独的 CR/LF
            msg = msg.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")

        # UTC 时间，包含毫秒
        ts = time.gmtime()
        timestr = time.strftime("%Y-%m-%dT%H:%M:%S", ts)
        ms = int((time.time() - int(time.time())) * 1000)
        timestamp = f"{timestr}.{ms:03d}Z"

        caller = self._get_caller_info()
        wf = self.workflow_id or "-"
        return f"[{wf}] [{timestamp}] [{caller}] [{level.value}]: {msg}\n"

    def _get_caller_info(self) -> str:
        # 查找第一个非本模块的调用帧
        stack = inspect.stack()
        try:
            for frame_info in stack[2:]:
                module = inspect.getmodule(frame_info.frame)
                if module and module.__name__ == __name__:
                    continue
                self_obj = frame_info.frame.f_locals.get("self")
                if self_obj is not None:
                    classname = type(self_obj).__name__
                else:
                    classname = os.path.splitext(os.path.basename(frame_info.filename))[0]
                func = frame_info.function
                lineno = frame_info.lineno
                return f"{classname}:{func}:{lineno}"
        finally:
            # 删除对帧的引用，避免循环引用
            for f in stack:
                del f
        return "unknown:?:0"

    def _enqueue(self, entry: str) -> None:
        with self._lock:
            buf = self._buffers[self._active]
            buf.append(entry)
            # 以字节为单位计数（准确反映占用），utf-8 编码长度
            added = len(entry.encode("utf-8"))
            self._buffer_bytes[self._active] += added
            if self._buffer_bytes[self._active] >= self._buffer_size:
                # 切换活跃缓冲区并唤醒写线程
                self._active ^= 1
                self._flush_event.set()

    def _swap_and_take(self) -> List[str]:
        # 交换 active 并返回之前活跃缓冲区的内容
        with self._lock:
            prev = self._active
            # 切换到另一个缓冲区，让生产者继续写入
            self._active ^= 1
            buf = self._buffers[prev]
            self._buffers[prev] = []
            # 清空对应的字节计数
            self._buffer_bytes[prev] = 0
            return buf

    def _take_inactive(self) -> List[str]:
        # 直接取非活跃缓冲区（用于生产者已在enqueue时切换 active 的场景）
        with self._lock:
            idx = self._active ^ 1
            buf = self._buffers[idx]
            self._buffers[idx] = []
            self._buffer_bytes[idx] = 0
            return buf

    def _writer_loop(self) -> None:
        # 后台线程：等待 flush_event 或定期 flush
        while not self._stop_event.is_set():
            triggered = self._flush_event.wait(timeout=self._flush_interval)
            # 清除事件标志，准备下一轮
            self._flush_event.clear()

            if triggered:
                # 生产者已在 enqueue 时切换 active，直接取非活跃缓冲区
                buf = self._take_inactive()
            else:
                # 定期触发：交换 active 并获取之前活跃缓冲区
                buf = self._swap_and_take()

            if buf:
                self._write_lines(buf)

        # 退出前再写剩余两缓冲区内容
        with self._lock:
            remaining = self._buffers[self._active][:]
            other = self._buffers[self._active ^ 1][:]
            # 清空缓冲与字节计数，写线程之后会把内容刷到磁盘
            self._buffers[self._active] = []
            self._buffers[self._active ^ 1] = []
            self._buffer_bytes[self._active] = 0
            self._buffer_bytes[self._active ^ 1] = 0

        if remaining:
            self._write_lines(remaining)
        if other:
            self._write_lines(other)

    def _write_lines(self, lines: List[str]) -> None:
        try:
            # 计算即将写入的字节数
            new_bytes = sum(len(line.encode("utf-8")) for line in lines)

            # 轮替逻辑：仅当启用按大小轮替（通过 LOG_FILE_SIZE 设置）时生效
            if getattr(self, "_current_date", None) is not None and self.max_bytes_:
                import time as _time

                date_str = _time.strftime(self._date_format, _time.gmtime())
                # 若跨日期，重置为当天的基础文件或新文件
                if date_str != self._current_date:
                    self._current_date = date_str
                    self.storage_path_ = self._select_path_for_date(date_str, new_bytes)
                else:
                    # 同一天，优先检查当前文件是否会超过阈值
                    try:
                        if os.path.exists(self.storage_path_):
                            cur_size = os.path.getsize(self.storage_path_)
                        else:
                            # 若当前文件不存在（首次写入），选择合适的路径
                            self.storage_path_ = self._select_path_for_date(date_str, new_bytes)
                            cur_size = os.path.getsize(self.storage_path_) if os.path.exists(self.storage_path_) else 0

                        if cur_size + new_bytes > self.max_bytes_:
                            # 需要创建一个新的序号文件
                            next_idx = self._next_index_for_date(date_str)
                            self.storage_path_ = self._path_for_index(date_str, next_idx)
                    except Exception:
                        # 轮替检测失败时回退并尝试写当前路径
                        pass

            # 最终写入当前 storage_path_
            with open(self.storage_path_, "a", encoding="utf-8") as f:
                f.writelines(lines)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    # 在某些环境下 fsync 可能失败（例如虚拟文件系统），忽略但继续
                    pass
        except Exception:
            # 写失败时尽量把信息输出到 stderr，不抛出异常以免影响主流程
            try:
                import sys

                sys.stderr.write("Logger: write failed\n")
            except Exception:
                pass

    def flush(self, timeout: float = 5.0) -> None:
        """请求刷新并在最多 `timeout` 秒内等待缓冲区清空。"""
        self._flush_event.set()
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                # 以字节计数为准，确保真正写入磁盘后返回
                if self._buffer_bytes[0] == 0 and self._buffer_bytes[1] == 0:
                    return
            time.sleep(0.01)

    def close(self) -> None:
        """停止后台线程并刷新所有剩余日志（幂等）。"""
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        self._flush_event.set()
        self._thread.join(timeout=3.0)
        # 最后确保所有缓冲区已写入
        try:
            self.flush(timeout=2.0)
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"<Logger file={self.storage_path_} min_level={self.min_level_.name} workflow={self.workflow_id}>"


global_logger: Logger = Logger(file_name="app.log", min_level=Level.DEBUG)