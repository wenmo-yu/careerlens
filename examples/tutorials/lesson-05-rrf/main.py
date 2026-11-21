"""练习 05：手算排名融合（RRF），理解「榜首不一定支持结论」。

对应课程：tutorials/04-retrieval-agent.md（样板课）。
不需要安装、不需要服务、不需要第三方依赖——只用 Python 标准库。
运行：python3 examples/tutorials/lesson-05-rrf/main.py
"""
from __future__ import annotations

from itertools import zip_longest

# 教学用的两张玩具榜单：值是按相关性排序的证据 ID，名次从 0 开始。
# 这不是任何真实用户数据，也不是 CareerLens 的服务响应。
LIST_A = ["A", "B"]        # A 第 0 名，B 第 1 名，C 缺席
LIST_B = ["C", "B"]        # C 第 0 名，B 第 1 名，A 缺席
K = 2                      # 教学用的平滑常数；真实服务由 Qdrant 内部决定，源码未显式指定


def rrf_score(rank: int | None, k: int = K) -> float:
    """命中则 1/(k+rank)，缺席则 0。名次从 0 数起。"""
    return 0.0 if rank is None else 1.0 / (k + rank)


def fuse(*lists: list[str], k: int = K) -> dict[str, float]:
    """对每张榜单算名次，对所有证据累加 RRF 分数。"""
    scores: dict[str, float] = {}
    for ranking in lists:
        for rank, doc in enumerate(ranking):          # enumerate 默认从 0 开始
            scores[doc] = scores.get(doc, 0.0) + rrf_score(rank, k)
    return scores


def rank_interleave(*lists: list[str]) -> list[str]:
    """按名次交错两路结果（hybrid 模式用的方式，不是分数相加）。"""
    out: list[str] = []
    for pair in zip_longest(*lists):
        for doc in pair:
            if doc is not None and doc not in out:
                out.append(doc)
    return out


def approx(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def main() -> None:
    # 环节一：先手算。B 两榜都命中，A/C 各只在一榜榜首。
    scores = fuse(LIST_A, LIST_B)
    print("融合分数：", {d: round(s, 4) for d, s in sorted(scores.items())})
    assert approx(scores["B"], 2 / 3), scores          # 1/(2+1)+1/(2+1)
    assert approx(scores["A"], 1 / 2), scores          # 1/(2+0)
    assert approx(scores["C"], 1 / 2), scores          # 1/(2+0)
    order = sorted(scores, key=lambda d: (-scores[d], d))
    assert order[0] == "B", order                      # 两榜都命中的 B 排第一
    print("排名第一：", order[0], "（两榜都命中，高于只中一榜的榜首）")

    # 环节二：改一个变量——把 B 从榜单 A 移除，看顺序怎么变。
    scores_no_b = fuse(["A"], LIST_B)
    order_no_b = sorted(scores_no_b, key=lambda d: (-scores_no_b[d], d))
    # B 只中一榜后掉到 1/3；A、C 各中一榜榜首（0.5），按字母序 A 在前。
    assert order_no_b[0] == "A", order_no_b
    print("移除 B 在榜单 A 的命中后，B 掉到 1/3，不再第一：",
          [(d, round(s, 4)) for d, s in sorted(scores_no_b.items(), key=lambda kv: -kv[1])])

    # 环节三：名次交错（hybrid 的 knowledge_fusion）和分数融合是两回事。
    inter = rank_interleave(LIST_A, LIST_B)
    assert inter[:3] == ["A", "C", "B"], inter
    print("名次交错结果：", inter, "（与分数融合的排名依据不同）")

    # 环节四：榜首 ≠ 支持。分数最高的 B 也可能是「收藏了教程」这类兴趣线索。
    # 检索只回答「排第几」，不回答「能不能作为结论依据」。
    evidence_support = {"A": True, "B": False, "C": True}   # 假设 B 是兴趣线索
    top = order[0]
    assert evidence_support[top] is False, "本练习特意让榜首是不支持的证据"
    print(f"结论：{top} 虽然排第一，却不能支持「做过上线」；应写「证据不足」。")

    print("OK：手算、改变量、名次交错、榜首判错四步都通过。")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        raise SystemExit(f"失败：断言未通过 {exc!r}") from None
