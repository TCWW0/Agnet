from __future__ import annotations

from typing import Optional

from frame.memory.base import InMemoryMemoryKernel, MemoryKernel


class MemoryRegistry:
    def __init__(self, kernel: Optional[MemoryKernel] = None):
        self._kernel: MemoryKernel = kernel or InMemoryMemoryKernel()

    def set_kernel(self, kernel: MemoryKernel) -> None:
        self._kernel = kernel

    def get_kernel(self) -> MemoryKernel:
        return self._kernel


# Shared memory instance for multi-agent shared-session use cases.
global_memory_registry = MemoryRegistry()
