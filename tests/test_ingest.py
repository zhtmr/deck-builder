import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "system-deck" / "scripts"))
import ingest  # noqa: E402

NS = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'


def p(text):
    return f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>'


def tbl(rows):
    trs = "".join(
        "<hp:tr>" + "".join(f"<hp:tc><hp:subList>{c}</hp:subList></hp:tc>" for c in r) + "</hp:tr>" for r in rows)
    return f'<hp:p><hp:run><hp:tbl>{trs}</hp:tbl></hp:run></hp:p>'


def make_hwpx(path: Path, sections: list[str]):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        for i, body in enumerate(sections):
            z.writestr(f"Contents/section{i}.xml", f'<?xml version="1.0"?><hs:sec {NS} xmlns:hs="x">{body}</hs:sec>')


class HwpxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_paragraphs_tables_and_order(self):
        f = self.tmp / "기획서.hwpx"
        make_hwpx(f, [
            p("제목 문단") + tbl([[p("구분"), p("값")], [p("지연"), p("42ms")], [p("처리량"), p("1,200 req/s")]]) + p("표 뒤 문단"),
            p("두 번째 섹션"),
        ])
        md = ingest.parse_hwpx(f)
        self.assertLess(md.index("제목 문단"), md.index("| 구분 | 값 |"))
        self.assertLess(md.index("| 처리량 | 1,200 req/s |"), md.index("표 뒤 문단"))
        self.assertLess(md.index("표 뒤 문단"), md.index("두 번째 섹션"))
        # 표 셀 문단이 본문에 중복 출력되지 않는다
        self.assertEqual(md.count("42ms"), 1)

    def test_nested_table_flattened_in_cell(self):
        f = self.tmp / "n.hwpx"
        inner = tbl([[p("a"), p("b")]])
        make_hwpx(f, [tbl([[p("바깥"), inner]])])
        md = ingest.parse_hwpx(f)
        self.assertIn("a b", md)

    def test_pipe_in_cell_is_escaped(self):
        f = self.tmp / "e.hwpx"
        make_hwpx(f, [tbl([[p("h1"), p("h2")], [p("x|y"), p("z")]])])
        md, tables = ingest.extract_tables(ingest.parse_hwpx(f), "e.hwpx")
        self.assertEqual(tables[0]["rows"][0], ["x|y", "z"])

    def test_not_a_zip(self):
        f = self.tmp / "bad.hwpx"
        f.write_bytes(b"not a zip")
        with self.assertRaises(ingest.IngestError):
            ingest.parse_hwpx(f)

    def test_missing_sections(self):
        f = self.tmp / "empty.hwpx"
        with zipfile.ZipFile(f, "w") as z:
            z.writestr("mimetype", "x")
        with self.assertRaises(ingest.IngestError):
            ingest.parse_hwpx(f)


class TableSuggestTest(unittest.TestCase):
    def tables(self, md):
        return ingest.extract_tables(md, "t.md")[1]

    def test_stats(self):
        t = self.tables("| 지표 | 값 |\n|---|---|\n| 지연 | 42ms |\n| 처리량 | 1,200 |\n")
        self.assertEqual(t[0]["suggest"], "stats")
        self.assertEqual(t[0]["numeric_cols"], [1])

    def test_timeline(self):
        t = self.tables("| 시기 | 내용 |\n|---|---|\n| 2026.08 | 설계 |\n| 2026.09 | 구현 |\n| 2026.10 | 배포 |\n")
        self.assertEqual(t[0]["suggest"], "timeline")

    def test_marker_and_numbering(self):
        md, t = ingest.extract_tables("본문\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n| c | d |\n|---|---|\n| x | y |\n", "f.md")
        self.assertIn("> [표 1 · f.md]", md)
        self.assertIn("> [표 2 · f.md]", md)
        self.assertEqual([x["no"] for x in t], [1, 2])


class RunTest(unittest.TestCase):
    def test_run_writes_outputs_and_skips_failures(self):
        tmp = Path(tempfile.mkdtemp())
        make_hwpx(tmp / "a.hwpx", [p("안녕") + tbl([[p("k"), p("v")], [p("n"), p("10%")]])])
        (tmp / "b.md").write_text("# 제목\n본문", encoding="utf-8")
        (tmp / "c.hwpx").write_bytes(b"broken")
        out = tmp / "out"
        rc = ingest.run([tmp / "a.hwpx", tmp / "b.md", tmp / "c.hwpx"], out)
        self.assertEqual(rc, 0)
        src = (out / "source.md").read_text(encoding="utf-8")
        self.assertIn("📄 a.hwpx", src)
        self.assertIn("📄 b.md", src)
        self.assertNotIn("c.hwpx", src)

    def test_directory_skips_deck_and_node_modules(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "docs").mkdir()
        (tmp / "docs" / "a.md").write_text("x", encoding="utf-8")
        (tmp / "node_modules").mkdir()
        (tmp / "node_modules" / "b.md").write_text("y", encoding="utf-8")
        (tmp / ".deck").mkdir()
        (tmp / ".deck" / "source.md").write_text("z", encoding="utf-8")
        names = [f.name for f in ingest.collect([tmp])]
        self.assertEqual(names, ["a.md"])


if __name__ == "__main__":
    unittest.main()
