# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""大專校院各系所新生招生名額 / 註冊 / 缺額 ETL。

讀 raw/ 的「學12-1 新生(含境外生)註冊率-以「系(所)」統計.csv」,輸出:
- data/vacancy.csv          每列 = 學年度 × 學校 × 系所 × 日間/進修 × 學制班別
- data/school_mapping.csv   原學校代碼 → 統一代碼 / 簡稱
- data/program_mapping.csv  原學制班別 → 學士/碩士/博士/專科/其他

執行:uv run work/etl_vacancy.py
"""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "學12-1.新生(含境外生)註冊率-以「系(所)」統計.csv"
OUT_DIR = ROOT / "data"

# 原代碼 → (統一代碼, 說明)。合併、改制、更換代碼的學校都放這裡。
MERGES = {
    "0016": ("0007", "國立陽明大學與國立交通大學合併為國立陽明交通大學"),
    "0026": ("0053", "國立高雄第一科技大學併入國立高雄科技大學(107 學年起)"),
    "0027": ("0053", "國立高雄應用科技大學併入國立高雄科技大學(107 學年起)"),
    "0034": ("0053", "國立高雄海洋科技大學併入國立高雄科技大學(107 學年起)"),
    "1290": ("1293", "崇仁醫護管理專科學校更換統計處代碼"),
    "1195": ("1085", "馬偕醫學院改制為馬偕醫學大學(114 學年)"),
    "1166": ("1084", "亞東技術學院改制為亞東科技大學(110 學年);資料中 14 個系所名稱完全相同,待確認"),
}

# 原始學制班別 → (歸類, 說明)
PROGRAMS = {
    "學士班(含四技)": ("學士", ""),
    "二年制大學(二技)": ("學士", "二技為學士學位"),
    "學士後第二專長學士班(4+X)": ("學士", ""),
    "附設進院": ("學士", "附設進修學院,學士層級"),
    "碩士班": ("碩士", "含碩士在職專班(見 day_night=在職)"),
    "博士班": ("博士", ""),
    "五專": ("專科", ""),
    "二專": ("專科", ""),
    "附設進專": ("專科", "附設進修專校,專科層級"),
}

OUT_COLS = [
    "year_roc", "year", "school_code", "school", "ownership", "school_type",
    "dept", "day_night", "program", "program_group", "quota_A", "reserved_B", "enrolled_C",
    "foreign_E", "gap", "vacancy",
]


def short_name(name: str) -> str:
    """去掉「○○學校財團法人」「財團法人○○基金會」前綴,例:
    中華大學學校財團法人中華大學 → 中華大學。"""
    name = re.sub(r"^財團法人.*?基金會", "", name)
    name = re.sub(r"^.*?學校財團法人", "", name)
    return name


def to_int(v: str, col: str) -> int:
    if not re.fullmatch(r"\d+", v):
        raise ValueError(f"{col} 不是整數: {v!r}")
    return int(v)


def main() -> None:
    with open(RAW, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        raw_rows = list(reader)
    assert len(header) == 16, header
    # 以欄位位置讀取(名稱含全形符號,位置更穩);先確認順序沒變
    assert header[0] == "學年度" and header[3] == "學校統計處代碼" and header[8] == "學制班別"
    assert header[9].endswith("(A)") and header[10].endswith("(B)") and header[11].endswith("(C)")
    assert "(E)" in header[12]
    print(f"讀入 {len(raw_rows):,} 列")

    # --- 原始主鍵必須唯一 ---
    keys = Counter((r[0], r[3], r[5], r[6], r[7], r[8]) for r in raw_rows)
    dup = [k for k, n in keys.items() if n > 1]
    assert not dup, f"原始主鍵重複: {dup[:3]}"

    # --- 學校與學制對照 ---
    code_info: dict[str, dict] = {}
    for r in raw_rows:
        d = code_info.setdefault(r[3], {"name": set(), "own": set(), "typ": set(), "years": set()})
        d["name"].add(r[4]); d["own"].add(r[1]); d["typ"].add(r[2]); d["years"].add(int(r[0]))
    for c, d in code_info.items():
        assert len(d["name"]) == 1 and len(d["own"]) == 1 and len(d["typ"]) == 1, f"{c} 屬性不一致"
    for src, (dst, _) in MERGES.items():
        assert src in code_info and dst in code_info, (src, dst)
        assert dst not in MERGES, f"{dst} 不能再被合併"
    for r in {r[8] for r in raw_rows}:
        assert r in PROGRAMS, f"未歸類的學制班別: {r}"

    def unified(code: str) -> str:
        return MERGES[code][0] if code in MERGES else code

    short = {c: short_name(next(iter(d["name"]))) for c, d in code_info.items()}
    ukeys = [unified(c) for c in code_info]
    sn = Counter(short[u] for u in set(ukeys))
    assert all(n == 1 for n in sn.values()), f"簡稱重複: {[k for k, n in sn.items() if n > 1]}"
    for u in set(ukeys):  # 合併後設立別/類別要一致
        members = [c for c in code_info if unified(c) == u]
        assert len({next(iter(code_info[c]["own"])) for c in members}) == 1, u
        assert len({next(iter(code_info[c]["typ"])) for c in members}) == 1, u

    # --- 清理、排除、加總 ---
    excluded = Counter()
    agg: dict[tuple, dict] = {}
    order: list[tuple] = []
    for r in raw_rows:
        a = to_int(r[9], "A"); b = to_int(r[10], "B"); c = to_int(r[11], "C")
        if a == 0 and c == 0:
            assert b == 0
            excluded[r[0]] += 1
            continue
        e = None if r[12] == "..." else to_int(r[12], "E")
        u = unified(r[3])
        key = (r[0], u, r[6], r[7], r[8])
        if key not in agg:
            tgt = code_info[u]
            agg[key] = {
                "year_roc": int(r[0]), "year": int(r[0]) + 1911, "school_code": u,
                "school": short[u], "ownership": next(iter(tgt["own"])),
                "school_type": next(iter(tgt["typ"])), "dept": r[6], "day_night": r[7],
                "program": r[8], "program_group": PROGRAMS[r[8]][0], "quota_A": 0, "reserved_B": 0, "enrolled_C": 0,
                "foreign_E": None, "n": 0,
            }
            order.append(key)
        o = agg[key]
        o["n"] += 1
        o["quota_A"] += a; o["reserved_B"] += b; o["enrolled_C"] += c
        if e is not None:
            o["foreign_E"] = (o["foreign_E"] or 0) + e

    merged_rows = sum(o["n"] - 1 for o in agg.values())
    out = []
    for key in sorted(order, key=lambda k: (int(k[0]), k[1])):  # 穩定排序,同校保留原順序
        o = agg[key]
        o["gap"] = o["quota_A"] - o["reserved_B"] - o["enrolled_C"]
        o["vacancy"] = max(o["gap"], 0)
        out.append(o)

    OUT_DIR.mkdir(exist_ok=True)
    with open(OUT_DIR / "vacancy.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(OUT_COLS)
        for o in out:
            w.writerow(["" if o[c] is None else o[c] for c in OUT_COLS])

    with open(OUT_DIR / "school_mapping.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["orig_code", "orig_name", "unified_code", "short_name", "note"])
        for c in sorted(code_info):
            u = unified(c)
            w.writerow([c, next(iter(code_info[c]["name"])), u, short[u], MERGES[c][1] if c in MERGES else ""])

    with open(OUT_DIR / "program_mapping.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["program_raw", "program_group", "note"])
        for p, (g, note) in PROGRAMS.items():
            w.writerow([p, g, note])

    n_ex = sum(excluded.values())
    print(f"排除 A=0 且 C=0:{n_ex:,} 列;各學年:{dict(sorted(excluded.items()))}")
    print(f"合併後主鍵相同而加總的列:{merged_rows} 列")
    print(f"輸出 {len(out):,} 列 → {OUT_DIR / 'vacancy.csv'}")
    assert len(raw_rows) - n_ex - merged_rows == len(out)
    print(f"校名簡稱對照 {len(code_info)} 個原代碼 → {len(set(ukeys))} 個統一代碼")


if __name__ == "__main__":
    main()
