# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""把 data/vacancy.csv 整理成網頁可直接載入的 docs/data.js。

index.html 以 <script src="data.js"> 載入,取得全域變數 VACANCY_DATA。
資料以代碼陣列存放以縮小檔案;每一列是系所 × 日間/進修 × 學制班別,六個整數:
    [dept_idx, day_night_idx, program_idx, quota_A, reserved_B, enrolled_C]
gap 與 vacancy 由網頁逐列計算:gap = A − B − C,vacancy = max(gap, 0)。

執行:uv run work/build_data.py
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "vacancy.csv"
OUT = ROOT / "docs" / "data.js"
PREFIX = "const VACANCY_DATA = "
SIZE_LIMIT = 3 * 1024 * 1024


def download_date() -> str:
    m = re.search(r"下載日期:(\d{4}-\d{2}-\d{2})", (ROOT / "raw" / "SOURCES.md").read_text(encoding="utf-8"))
    assert m, "raw/SOURCES.md 找不到下載日期"
    return m.group(1)


def main() -> None:
    with open(SRC, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    years = sorted({int(r["year_roc"]) for r in rows})
    day_night = sorted({r["day_night"] for r in rows}, key=["日間", "進修", "在職"].index)
    programs = sorted({(r["program"], r["program_group"]) for r in rows},
                      key=lambda p: (["學士", "碩士", "博士", "專科"].index(p[1]), p[0]))
    schools = sorted({(r["school_code"], r["school"], r["ownership"], r["school_type"]) for r in rows})
    school_idx = {s[0]: i for i, s in enumerate(schools)}
    dept_keys = sorted({(school_idx[r["school_code"]], r["dept"]) for r in rows})
    dept_idx = {k: i for i, k in enumerate(dept_keys)}
    dn_idx = {v: i for i, v in enumerate(day_night)}
    prog_idx = {p[0]: i for i, p in enumerate(programs)}

    by_year: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        by_year[r["year_roc"]].extend([
            dept_idx[(school_idx[r["school_code"]], r["dept"])],
            dn_idx[r["day_night"]], prog_idx[r["program"]],
            int(r["quota_A"]), int(r["reserved_B"]), int(r["enrolled_C"]),
        ])

    with open(ROOT / "data" / "school_mapping.csv", encoding="utf-8-sig", newline="") as f:
        smap = list(csv.DictReader(f))
    merges = [{"fromCode": m["orig_code"], "fromName": m["orig_name"], "toCode": m["unified_code"],
               "toName": m["short_name"], "note": m["note"]}
              for m in smap if m["orig_code"] != m["unified_code"]]

    data = {
        "meta": {
            "title": "全台大學招生缺額",
            "source": {
                "name": "大專校院校務資訊公開平臺 學12-1 新生(含境外生)註冊率-以「系(所)」統計",
                "agency": "教育部高等教育司",
                "datasetUrl": "https://data.gov.tw/dataset/26228",
                "fileUrl": "https://udb.moe.edu.tw/download/udata/static_file/114/學12-1.新生(含境外生)註冊率-以「系(所)」統計.csv",
                "downloaded": download_date(),
                "license": "政府資料開放授權條款-第 1 版",
                "baseDate": "每年 10 月 15 日",
            },
            "period": {"from": years[0], "to": years[-1], "years": years,
                       "yearsCE": [y + 1911 for y in years],
                       "note": "學年度為民國年;西元年 = 學年度 + 1911(學年起始年,例如 114 學年 = 2025)"},
            "fields": {
                "rows": "dept_idx, day_night_idx, program_idx, quota_A, reserved_B, enrolled_C",
                "quota_A": "核定新生招生名額", "reserved_B": "新生保留入學資格人數",
                "enrolled_C": "總量內實際註冊人數",
            },
            "schools": [{"code": s[0], "name": s[1], "ownership": s[2], "type": s[3]} for s in schools],
            "merges": merges,
            "depts": "頂層 depts:[school_idx, 系所名稱],與 rows 的 dept_idx 對應",
            "programs": [{"raw": p[0], "group": p[1]} for p in programs],
            "dayNight": day_night,
            "formulas": {
                "gap": "gap = A − B − C(可為負,負數代表超收)",
                "vacancy": "vacancy = max(gap, 0),逐列計算後再加總",
                "rate": "註冊率 = ΣC ÷ Σ(A − B),不含境外生,不封頂",
                "officialRate": "教育部官方註冊率 = (C + E) ÷ (A − B + E),單列上限 100%",
            },
            "limitations": [
                "缺額為推算值(A − B − C),資料集本身沒有缺額欄位。",
                "缺額加總是逐列 max(gap, 0) 再相加,某系所超收不會抵銷其他系所的缺額,所以總缺額會大於 ΣA − ΣB − ΣC。",
                "註冊率不含境外生(E),也不對單列封頂,和教育部公布的官方數字略有差異。",
                "國立陽明交通大學在 106–109 學年為陽明、交通兩校合計(原始資料中陽明大學為獨立代碼,已併入)。",
                "校名為現行名稱:國立高雄科技大學 106 學年為高雄第一、高雄應用、高雄海洋三校合計;亞東科技大學含前身亞東技術學院;馬偕醫學大學含前身馬偕醫學院;原始資料中部分學校的歷史校名已被回填為現行名稱。",
                "已排除核定名額與註冊人數皆為 0 的列(941 列,皆在 109 學年之後)。",
                "停招或停辦的學校只出現在有資料的學年。",
            ],
        },
        "depts": [[i, n] for i, n in dept_keys],
        "rows": {str(y): by_year[str(y)] for y in years},
    }
    OUT.parent.mkdir(exist_ok=True)
    text = PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(text, encoding="utf-8", newline="")
    size = OUT.stat().st_size
    print(f"寫出 {OUT}:{size:,} bytes ({size / 1024 / 1024:.2f} MB),"
          f"{len(rows):,} 列、{len(dept_keys):,} 個系所、{len(schools)} 所學校")
    if size > SIZE_LIMIT:
        print("⚠️ 超過 3 MB,請決定是否改用學校層級")

    verify(rows)


def verify(csv_rows: list[dict]) -> None:
    """從 docs/data.js 還原,與 vacancy.csv 逐學年比對 ΣA、ΣB、ΣC、總缺額與列數。"""
    text = OUT.read_text(encoding="utf-8")
    assert text.startswith(PREFIX) and text.endswith(";\n")
    d = json.loads(text[len(PREFIX):-2])
    ok = True
    print("核對(data.js 還原 vs vacancy.csv):")
    print(f"  {'學年':>4} {'列數':>7} {'ΣA':>9} {'ΣC':>9} {'總缺額':>8}  結果")
    for y in d["meta"]["period"]["years"]:
        flat = d["rows"][str(y)]
        assert len(flat) % 6 == 0
        n = len(flat) // 6
        a = b = c = v = 0
        for i in range(0, len(flat), 6):
            ra, rb, rc = flat[i + 3], flat[i + 4], flat[i + 5]
            a += ra; b += rb; c += rc; v += max(ra - rb - rc, 0)
        cr = [r for r in csv_rows if r["year_roc"] == str(y)]
        ca = sum(int(r["quota_A"]) for r in cr); cb = sum(int(r["reserved_B"]) for r in cr)
        cc = sum(int(r["enrolled_C"]) for r in cr); cv = sum(int(r["vacancy"]) for r in cr)
        same = (n, a, b, c, v) == (len(cr), ca, cb, cc, cv)
        ok &= same
        print(f"  {y:>4} {n:>7,} {a:>9,} {c:>9,} {v:>8,}  {'✅' if same else '❌ csv=' + str((len(cr), ca, cb, cc, cv))}")
    assert ok, "data.js 與 vacancy.csv 不一致"
    print("🎉 核對通過")


if __name__ == "__main__":
    main()
