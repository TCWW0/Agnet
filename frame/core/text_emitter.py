from __future__ import annotations

import queue
import sys
import threading
from enum import Enum
from typing import Optional, Union
from queue import Queue

from frame.core.llm_types import TextDeltaCallback
from frame.core.logger import Logger, global_logger


class DispatchMode(str, Enum):
    """How to dispatch one queued chunk to callback calls."""

    CHUNK = "chunk"
    PER_CHAR = "per_char"


class QueueFullStrategy(str, Enum):
    """Behavior when the emitter queue is full."""

    DROP_OLDEST = "drop_oldest"
    DROP_NEW = "drop_new"
    BLOCK = "block"


def default_text_callback(text: str) -> None:
    """Default callback that writes text to stdout immediately."""

    if not text:
        return
    sys.stdout.write(text)
    sys.stdout.flush()


class TextEmitter:
    """Threaded callback dispatcher for streaming text chunks.

    Producer side (IO thread): call `emit(chunk)` quickly.
    Consumer side (worker thread): process queue and invoke callback.
    """

    _SENTINEL = object()

    def __init__(
        self,
        callback: Optional[TextDeltaCallback] = None,
        dispatch_mode: DispatchMode = DispatchMode.PER_CHAR,
        max_queue_size: int = 512,
        on_queue_full: QueueFullStrategy = QueueFullStrategy.DROP_OLDEST,
        logger: Optional[Logger] = None,
        worker_name: str = "TextEmitterWorker",
    ) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")

        self.callback_: TextDeltaCallback = callback or default_text_callback
        self.dispatch_mode_ = dispatch_mode
        self.on_queue_full_ = on_queue_full
        self.logger_ = logger or global_logger

        self._queue: Queue[Union[str, object]] = Queue(maxsize=max_queue_size)
        self._closed = threading.Event()

        self._worker = threading.Thread(target=self._worker_loop, name=worker_name, daemon=True)
        self._worker.start()

    def emit(self, chunk: str) -> None:
        """Accept one chunk from producer side."""

        if self._closed.is_set() or not chunk:
            return

        if self.on_queue_full_ == QueueFullStrategy.BLOCK:
            self._queue.put(chunk)
            return

        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            if self.on_queue_full_ == QueueFullStrategy.DROP_NEW:
                return
            self._drop_oldest_then_put(chunk)

    def close(self, timeout: Optional[float] = 1.0) -> None:
        """Stop worker and flush pending queue as much as possible."""

        if self._closed.is_set():
            return

        self._closed.set()
        self._enqueue_sentinel()
        self._worker.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._worker.is_alive()

    def __enter__(self) -> "TextEmitter":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def _drop_oldest_then_put(self, chunk: str) -> None:
        try:
            _ = self._queue.get_nowait()
            self._queue.task_done()
        except queue.Empty:
            pass

        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            # Worker might still be blocked. Keep producer non-blocking by dropping this chunk.
            return

    def _enqueue_sentinel(self) -> None:
        while True:
            try:
                self._queue.put_nowait(self._SENTINEL)
                return
            except queue.Full:
                try:
                    _ = self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    continue

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is self._SENTINEL:
                    return

                if not isinstance(item, str):
                    continue

                self._dispatch(item)
            finally:
                self._queue.task_done()

    def _dispatch(self, chunk: str) -> None:
        if self.dispatch_mode_ == DispatchMode.CHUNK:
            self._safe_callback(chunk)
            return

        for char in chunk:
            self._safe_callback(char)

    def _safe_callback(self, text: str) -> None:
        try:
            self.callback_(text)
        except Exception as err:  # pragma: no cover
            self.logger_.warning("TextEmitter callback failed err=%s", str(err))
