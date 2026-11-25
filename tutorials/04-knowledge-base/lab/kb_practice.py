"""Rebuild CareerLens ingestion, retrieval, and Wiki in a separate practice copy."""

from pathlib import Path
from runpy import run_path

TUTORIALS = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE = TUTORIALS.parent / ".cache" / "knowledge-practice"
COMPILE_TESTS = "tests/test_wiki_compile.py"
KNOWLEDGE_TESTS = "tests/test_knowledge_mode.py"

LESSONS = {
    "parse": {
        "files": {"app/ingestion/files.py": ("_docx_blocks",)},
        "tests": ("tests/test_multiformat_parsing.py", "tests/test_xlsx_parsing.py"),
    },
    "sources": {
        "files": {
            "app/ingestion/contract.py": ("content_fingerprint",),
            "app/services/evidence.py": ("_append_source",),
        },
        "tests": (
            "tests/test_parsed_block_contract.py",
            "tests/test_source_dedup.py",
            "tests/test_chunking.py",
        ),
    },
    "retrieve": {
        "files": {
            "app/retrieval/hybrid.py": ("_cosine", "hybrid_search"),
            "app/retrieval/service.py": ("search_evidence",),
        },
        "tests": ("tests/test_qdrant_retrieval.py", KNOWLEDGE_TESTS),
    },
    "handles": {
        "files": {
            "app/wiki/handles.py": ("HandleTable.register", "HandleTable.resolve"),
            "app/wiki/compiler.py": ("resolve_citations", "prepare_page"),
        },
        "tests": (COMPILE_TESTS,),
    },
    "guard": {
        "files": {
            "app/wiki/tables.py": (
                "table_row_identities", "row_identity_loss_ratio", "assert_rows_preserved",
            ),
        },
        "tests": (COMPILE_TESTS,),
    },
    "versions": {
        "files": {"app/services/wiki_pages.py": ("_snapshot", "update_page")},
        "tests": ("tests/test_wiki_schema.py", COMPILE_TESTS),
    },
    "wiki-query": {
        "files": {"app/wiki/search.py": ("_wiki_hit", "search_wiki_pages")},
        "tests": (KNOWLEDGE_TESTS,),
    },
}

HINTS = {
    "_docx_blocks": (
        "按文档原来的顺序遍历 XML 元素，用标签区分段落 p 和表格 tbl。",
        "段落取文字和样式，忽略空段落。标题更新当前 section_path。",
        "普通段落与表格继承当前章节，按文档顺序追加三元组。",
    ),
    "content_fingerprint": (
        "先把 CRLF 和单独 CR 都换成 LF，再去掉首尾空白。",
        "把文字编码成 UTF-8 字节，交给 SHA-256，返回十六进制字符串。",
    ),
    "_append_source": (
        "取出 metadata 和已有来源列表，整条来源已经相等时返回 False。",
        "追加新来源，把完整 metadata 重新赋给字段，用列表长度更新 source_count。",
    ),
    "_cosine": (
        "用相同词的计数相乘求和。词不在另一份计数里时用 0。",
        "分别求计数向量的长度。任一长度为 0 时直接给 0 分。",
    ),
    "hybrid_search": (
        "用 Counter 得到问句词频，再用每篇文章的不同词统计文档频率。",
        "逐条求余弦、稀有词得分和完整短语加分，留下正分候选。",
        "让分数、正文和原记录一起排序，截断后再打包证据 ID 和原文。",
    ),
    "search_evidence": (
        "先按配置决定是否查 Qdrant，给实时过滤留多一点候选。",
        "按本轮可读证据 ID 过滤索引结果，正文以数据库记录为准。",
        "按模式处理空列表和异常。走本地时写明 weighted_score 和 fallback 原因。",
    ),
    "HandleTable.register": (
        "已经给过这个稳定 ID 句柄时复用。新 ID 从当前计数生成如 c000 的短名。",
        "递增计数，保存句柄到 ID 和 ID 到句柄的双向映射。",
    ),
    "HandleTable.resolve": (
        "从句柄查稳定 ID。找不到时记到 unknown_handles 的内部列表。",
        "返回找到的 ID，或查不到时的 None。",
    ),
    "resolve_citations": (
        "逐个用本轮的 HandleTable 翻译模型给出的句柄。",
        "忽略未知值，只保留第一次出现的稳定 ID，维持原次序。",
    ),
    "prepare_page": (
        "先拒绝空证据列表，再为本轮来源逐个登记短句柄。",
        "生成候选，翻译 citations，清正文里的标记。必要时用确定性页面。",
        "把源表和候选交给守卫，异常转成 WikiCompileError。",
        "返回页面字段、真实引用和诊断，供写入函数使用。",
    ),
    "table_row_identities": (
        "收集连续的竖线行，只有第二行是分隔线才把这一块当表格。",
        "跳过表头与分隔线，用未转义的竖线切开每一行。",
        "找到归一化后第一个非空单元格。遇到普通行和文件末尾都要结算。",
    ),
    "row_identity_loss_ratio": (
        "源表没有身份时返回 0。两边用 Counter 保留重复次数。",
        "求源表缺少的次数总和，除以源表行身份的总数。",
    ),
    "assert_rows_preserved": (
        "如果有 source_tables，按空行拼接各份表。否则使用原页面。",
        "损失超过允许比例时抛出 DroppedTableRowsError，附上百分比。",
    ),
    "_snapshot": (
        "复制会被换下来的当前版本和页面字段，引用列表单独复制。",
        "把 page.last_edit_source 记入快照，记录谁写了当时这一版。",
    ),
    "update_page": (
        "先核对传来的版本，再找可见字段或来源引用是否有变化。",
        "只在有相关变化时建旧快照并递增版本。",
        "更新 SQL 同时比对页面 ID 和读取时的版本。没命中则报告冲突。",
        "成功后写快照和裁剪历史，按调用约定提交并刷新页面。",
    ),
    "_wiki_hit": (
        "交还页面 ID、slug、标题和摘录，并保留两份证据引用。",
        "标记 source_kind 为 wiki，用 retrieval_method 说明评分来源。",
    ),
    "search_wiki_pages": (
        "先按用户和 published 状态查页面。没有页面就返回空。",
        "把标题与正文拼成候选，用已有的本地 hybrid_search 给页面评分。",
        "按候选中的页面 ID 找原页面，再调用 _wiki_hit 还原主题页字段。",
    ),
}


if __name__ == "__main__":
    launch = run_path(str(TUTORIALS / "01-agent-design" / "lab" / "practice.py"))["main"]
    raise SystemExit(
        launch(
            description=__doc__,
            default_workspace=DEFAULT_WORKSPACE,
            default_port=8031,
            lessons=LESSONS,
            hints=HINTS,
        )
    )
