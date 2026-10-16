"""Sinh docs/huong-dan-su-dung.md từ apps/web/src/lib/guide.json (nguồn duy nhất, cũng dùng cho trang Hướng dẫn).

python infra/scripts/build_guide.py           # ghi file
python infra/scripts/build_guide.py --check   # thoát mã 1 nếu file đang lệch với guide.json (dùng trong CI)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "apps/web/src/lib/guide.json"
TARGET = ROOT / "docs/huong-dan-su-dung.md"
IMAGES = "../apps/web/public/guide"


def render() -> str:
    g = json.loads(SOURCE.read_text(encoding="utf-8"))
    out = [
        f"# {g['title']}",
        "",
        "<!-- File sinh tự động từ apps/web/src/lib/guide.json bằng infra/scripts/build_guide.py. Sửa ở guide.json. -->",
        "",
        g["intro"],
        "",
        "Trong ứng dụng, cùng nội dung này có ở menu **Hướng dẫn sử dụng** (đường dẫn `/help`), kèm nút mở đúng màn hình.",
        "",
        "## Mục lục",
        "",
    ]
    groups: list[str] = []
    for s in g["sections"]:
        if s["group"] not in groups:
            groups.append(s["group"])
    n = 0
    for grp in groups:
        out.append(f"- **{grp}**")
        for s in g["sections"]:
            if s["group"] == grp:
                n += 1
                out.append(f"  - [{n}. {s['title']}](#{s['id']})")
    out += ["- [Hỏi đáp](#hoi-dap)", ""]
    n = 0
    for grp in groups:
        out += [f"## {grp}", ""]
        for s in g["sections"]:
            if s["group"] != grp:
                continue
            n += 1
            out += [
                f'<a id="{s["id"]}"></a>',
                "",
                f"### {n}. {s['title']}",
                "",
                f"_{s['summary']}_",
                "",
            ]
            if s.get("route") and s["route"] != "/login":
                out += [f"Màn hình: `{s['route']}`", ""]
            out += [f"{i}. {step}" for i, step in enumerate(s["steps"], 1)]
            out.append("")
            if s.get("image"):
                out += [f"![Màn hình: {s['title']}]({IMAGES}/{s['image']})", ""]
            if s.get("tips"):
                out += ["> **Lưu ý**", ">"] + [f"> - {t}" for t in s["tips"]] + [""]
    out += ['<a id="hoi-dap"></a>', "", "## Hỏi đáp", ""]
    for f in g["faq"]:
        out += [f"**{f['q']}**", "", f["a"], ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
            print(
                f"{TARGET.relative_to(ROOT)} lệch với guide.json: chạy python infra/scripts/build_guide.py"
            )
            return 1
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"Đã ghi {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
