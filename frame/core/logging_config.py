"""统一日志配置：提供一次性初始化函数，保证格式一致且可复用。"""
import logging
from typing import Optional


def setup_logging(level: int = logging.INFO, fmt: Optional[str] = None) -> None:
    """Configure root logging if not already configured.

    This is idempotent: if the root logger already has handlers, it does nothing.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    if fmt is None:
        fmt = "[%(asctime)s.%(msecs)03d] %(name)s %(levelname)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S")


__all__ = ["setup_logging"]
