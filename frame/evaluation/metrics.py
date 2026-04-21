from __future__ import annotations

from math import comb
from typing import Iterable, Sequence

# 计算在前K次尝试中至少成功一次的概率，基于二项分布的封闭形式概率计算
def pass_at_k(successes: Sequence[bool], k: int) -> float:
    n = len(successes)      # 结果总数
    if n == 0 or k <= 0:
        return 0.0

    k = min(k, n)
    c = sum(1 for item in successes if item)    # 成功的数量
    if c <= 0:
        return 0.0

    failures = n - c
    if failures < k:
        return 1.0

    return 1.0 - (comb(failures, k) / comb(n, k))

# 从 n 次尝试中选 k 个，全部都是成功的概率
def pass_hat_k(successes: Sequence[bool], k: int) -> float:
    n = len(successes)
    if n == 0 or k <= 0 or k > n:
        return 0.0

    c = sum(1 for item in successes if item)
    if c < k:
        return 0.0

    return comb(c, k) / comb(n, k)

# 在前 k 个结果中，找回了多少“应该找到的东西” 即覆盖率
def recall_at_k(expected: Sequence[str], recalled: Sequence[str], k: int) -> float:
    if not expected:
        return 1.0

    if k <= 0:
        return 0.0

    top_k = recalled[:k]
    hit = sum(1 for item in expected if item in top_k)
    return hit / len(expected)

def precision_at_k(expected: Sequence[str], recalled: Sequence[str], k: int) -> float:
    # 前 k 个结果中，有多少是“正确的”
    if k <= 0:
        return 0.0

    top_k = recalled[:k]
    if not top_k:
        return 0.0

    hit = sum(1 for item in top_k if item in expected)
    return hit / len(top_k)


def mean(values: Iterable[float]) -> float:
    values_list = list(values)
    if not values_list:
        return 0.0
    return sum(values_list) / len(values_list)


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator
