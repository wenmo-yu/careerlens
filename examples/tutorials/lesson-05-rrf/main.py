"""练习 05：手算排名融合（RRF），理解「榜首不一定支持结论」。

对应课程：tutorials/04-检索Agent.md（样板课）。
使用 Python 标准库。在装好 Python 的终端运行即可。

内置算例：
  python3 examples/tutorials/lesson-05-rrf/main.py          # 默认：四环节回归断言
  python3 examples/tutorials/lesson-05-rrf/main.py --k 10   # 变体一：只改 k
  python3 examples/tutorials/lesson-05-rrf/main.py --drop-b # 变体二：从榜 A 移除 B

自定义榜单通过 --rankings 传入，格式为两组用逗号分隔的证据 ID。
内置算例核对固定分数。自定义榜单交由读者按公式核对。
"""
from __future__ import annotations

import argparse
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


def show(label: str, scores: dict[str, float]) -> list[str]:
    """打印一组分数与排序，返回排序后的 ID 列表供调用方核对。"""
    order = sorted(scores, key=lambda d: (-scores[d], d))   # 同分按 ID 字母序，规则固定
    print(f"{label}分数：", {d: round(s, 4) for d, s in sorted(scores.items())})
    print(f"{label}排序：", [(d, round(scores[d], 4)) for d in order])
    return order


def run_default() -> None:
    """默认入口：四环节回归断言，用的是写死的初始分数。"""
    scores = fuse(LIST_A, LIST_B)
    print("=== 默认入口：四环节回归 ===")
    show("原始两榜 ", scores)
    assert approx(scores["B"], 2 / 3), scores          # 1/(2+1)+1/(2+1)
    assert approx(scores["A"], 1 / 2), scores          # 1/(2+0)
    assert approx(scores["C"], 1 / 2), scores          # 1/(2+0)
    order = sorted(scores, key=lambda d: (-scores[d], d))
    assert order[0] == "B", order                      # 两榜都命中的 B 排第一
    print("排名第一：", order[0], "（两榜都命中，高于只中一榜的榜首）")

    scores_no_b = fuse(["A"], LIST_B)
    order_no_b = show("移除B命中", scores_no_b)
    assert order_no_b[0] == "A", order_no_b
    print("移除 B 在榜单 A 的命中后：A、C 并列 1/2，B 掉到 1/3，不再第一。")

    inter = rank_interleave(LIST_A, LIST_B)
    assert inter[:3] == ["A", "C", "B"], inter
    print("名次交错结果：", inter, "（与分数融合的排名依据不同）")

    evidence_support = {"A": True, "B": False, "C": True}   # 假设 B 是兴趣线索
    top = order[0]
    assert evidence_support[top] is False, "本练习特意让榜首是不支持的证据"
    print(f"结论：{top} 虽然排第一，却不能支持「做过上线」；应写「证据不足」。")
    print("OK：默认四环节（手算、改变量、名次交错、榜首判错）都通过。")


def run_variant(k: int, drop_b: bool) -> None:
    """可调入口：只改一个变量，输出可复算分数，不跑默认断言。"""
    list_a = [d for d in LIST_A if not (drop_b and d == "B")]
    print(f"=== 变体入口：k={k}" + ("，从榜 A 移除 B" if drop_b else "，两榜原样") + " ===")
    print("榜 A：", list_a, " 榜 B：", LIST_B)
    scores = fuse(list_a, LIST_B, k=k)
    order = show("融合后", scores)

    a, b, c = scores.get("A", 0.0), scores.get("B", 0.0), scores.get("C", 0.0)
    if not drop_b and k == 2:
        assert approx(a, 1 / 2) and approx(b, 2 / 3) and approx(c, 1 / 2)
        assert order[0] == "B"
    elif not drop_b and k == 10:
        assert approx(a, 1 / 10) and approx(b, 2 / 11) and approx(c, 1 / 10)
        assert order[0] == "B"
        gap = b - a
        print(f"B 与 A 分差：{gap:.4f}；倍率：{b / a:.2f}")
    elif drop_b and k == 2:
        assert approx(a, 1 / 2) and approx(b, 1 / 3) and approx(c, 1 / 2)
        assert order[0] == "A" and order[1] == "C"
    print("按脚本排序规则排第一：", order[0])
    print("OK：变体入口执行完成。")


def parse_ranking(value: str) -> list[str]:
    ids = [doc.strip() for doc in value.split(",")]
    if not all(ids) or len(ids) != len(set(ids)):
        raise argparse.ArgumentTypeError("榜内 ID 用逗号分隔，每一项非空且只出现一次")
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="RRF 手算练习：默认回归 + 可调变体")
    parser.add_argument("--k", type=int, default=None, help="替换教学常数 k，例如 --k 10")
    rankings = parser.add_mutually_exclusive_group()
    rankings.add_argument("--drop-b", action="store_true", help="从内置榜单 A 移除 B")
    rankings.add_argument(
        "--rankings", nargs=2, type=parse_ranking, metavar=("榜单A", "榜单B"),
        help='自定义两张榜，例如 --rankings "A,X,Y,B" "C,U,V,B"',
    )
    args = parser.parse_args()
    k = args.k if args.k is not None else K
    if k < 1:
        parser.error("--k 必须为正整数")

    if args.rankings is not None:
        print(f"自定义榜单，k={k}：", *args.rankings)
        show("融合后", fuse(*args.rankings, k=k))
        print("OK：自定义榜单计算完成。")
    elif args.k is not None or args.drop_b:
        run_variant(k, args.drop_b)
    else:
        run_default()


if __name__ == "__main__":
    main()
