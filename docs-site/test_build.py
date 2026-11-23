import tempfile
import unittest
from pathlib import Path

from build import check_anchors, check_no_local_links, rewrite_links


class NavigationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.site = Path(folder.name)

    def page(self, path, content):
        file = self.site / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return file

    def test_shared_navigation_uses_site_root_from_either_home_route(self):
        home = self.page(
            "tutorials/从这里开始.md",
            "[开始](01.md#步骤-2)\n\n![主页](../docs/overview.png)\n",
        )
        self.page("docs/overview.png", "")
        sidebar = self.page("_sidebar.md", "[开始](tutorials/01.md)\n")
        lesson = self.page("tutorials/01.md", "## 步骤 2\n\n[返回](从这里开始.md)\n")

        self.assertEqual(rewrite_links(self.site, "test"), (0, []))
        self.assertEqual(
            home.read_text(encoding="utf-8"),
            '[开始](/tutorials/01.md#步骤-2)\n\n<img src="docs/overview.png" alt="主页">\n',
        )
        self.assertEqual(sidebar.read_text(encoding="utf-8"), "[开始](/tutorials/01.md)\n")
        self.assertIn("](从这里开始.md)", lesson.read_text(encoding="utf-8"))
        self.assertEqual(check_no_local_links(self.site), [])
        self.assertEqual(check_anchors(self.site), [])

    def test_invalid_same_page_anchor_is_reported(self):
        self.page("lesson.md", "## 开始\n\n[正确](#开始)\n[错误](#找不到)\n")

        self.assertEqual(check_anchors(self.site), ["lesson.md: #找不到 (anchor not found)"])

    def test_nested_relative_links_are_not_resolved_from_both_bases(self):
        self.page("tutorials/01.md", "# 第一课\n")
        self.page("tutorials/02.md", "[第二层路径](tutorials/01.md)\n")

        self.assertEqual(
            check_no_local_links(self.site),
            [f"{Path('tutorials/02.md')}: tutorials/01.md"],
        )
