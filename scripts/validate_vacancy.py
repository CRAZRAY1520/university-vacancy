# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""驗證 data/vacancy.csv。獨立重讀 raw/,不 import ETL 的任何邏輯。

執行:uv run scripts/validate_vacancy.py
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW = next((ROOT / "raw").glob("*.csv"))
failures: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("  ✅ " if ok else "  ❌ ") + msg)
    if not ok:
        failures.append(msg)


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# --- 原始檔:欄位用名稱前綴取,避免依賴 ETL ---
raw = read(RAW)
cols = list(raw[0].keys())
cA = next(c for c in cols if c.endswith("(A)"))
cB = next(c for c in cols if c.endswith("(B)"))
cC = next(c for c in cols if c.endswith("(C)"))
cE = next(c for c in cols if "(E)" in c)

vac = read(ROOT / "data" / "vacancy.csv")
smap = read(ROOT / "data" / "school_mapping.csv")
pmap = read(ROOT / "data" / "program_mapping.csv")
to_unified = {r["orig_code"]: r["unified_code"] for r in smap}

# 每年 raw 合計,以及被排除(A=0 且 C=0)的合計
raw_sum = defaultdict(lambda: [0, 0, 0, 0])      # rows, A, B, C
ex_sum = defaultdict(lambda: [0, 0, 0, 0])
raw_unified = defaultdict(lambda: [0, 0, 0])     # (year, 統一代碼) → A, B, C
for r in raw:
    a, b, c = int(r[cA]), int(r[cB]), int(r[cC])
    y = r["學年度"]
    tgt = ex_sum if (a == 0 and c == 0) else raw_sum
    tgt[y][0] += 1; tgt[y][1] += a; tgt[y][2] += b; tgt[y][3] += c
    if tgt is raw_sum:
        u = raw_unified[(y, to_unified[r["學校統計處代碼"]])]
        u[0] += a; u[1] += b; u[2] += c

out_sum = defaultdict(lambda: [0, 0, 0, 0])
out_unified = defaultdict(lambda: [0, 0, 0])
for r in vac:
    y = r["year_roc"]
    a, b, c = int(r["quota_A"]), int(r["reserved_B"]), int(r["enrolled_C"])
    o = out_sum[y]
    o[0] += 1; o[1] += a; o[2] += b; o[3] += c
    u = out_unified[(y, r["school_code"])]
    u[0] += a; u[1] += b; u[2] += c

years = sorted(raw_sum.keys() | ex_sum.keys())

print("1. 每學年 ΣA、ΣB、ΣC 與原始檔一致")
for y in years:
    ra = raw_sum[y]; ex = ex_sum[y]; o = out_sum[y]
    check(o[1:] == ra[1:], f"{y}: 輸出 A/B/C = {o[1:]},原始(扣排除列) = {ra[1:]},排除 {ex[0]} 列(其 A/B/C 合計 {ex[1:]})")
    # 排除列本身 A=0 且 C=0,因此原始全部合計 = 輸出合計
    check(ex[1] == 0 and ex[3] == 0, f"{y}: 被排除的列 ΣA=ΣC=0")

print("2. 學校合併前後人數總和一致")
keys = sorted(raw_unified.keys() | out_unified.keys())
bad = [k for k in keys if raw_unified.get(k) != out_unified.get(k)]
check(not bad, f"{len(keys)} 組 (學年, 統一代碼) 的 A/B/C 全部相同" + (f";不符: {bad[:3]}" if bad else ""))
merged_targets = {r["unified_code"] for r in smap if r["orig_code"] != r["unified_code"]}
out_codes = {r["school_code"] for r in vac}
check(out_codes <= {r["unified_code"] for r in smap}, "輸出的 school_code 都在 school_mapping 的統一代碼內")
check(not (out_codes & {r["orig_code"] for r in smap if r["orig_code"] != r["unified_code"]}),
      "已被併入的原代碼不再出現在輸出")
for t in sorted(merged_targets):
    members = [r["orig_code"] for r in smap if r["unified_code"] == t]
    for y in years:
        exp = [0, 0, 0]
        for r in raw:
            if r["學年度"] == y and r["學校統計處代碼"] in members and not (int(r[cA]) == 0 and int(r[cC]) == 0):
                exp[0] += int(r[cA]); exp[1] += int(r[cB]); exp[2] += int(r[cC])
        if exp != out_unified.get((y, t), [0, 0, 0]):
            check(False, f"{t} {y}: 合併成員總和 {exp} ≠ 輸出 {out_unified.get((y, t))}")
check(True, f"合併目標 {sorted(merged_targets)} 逐年核對完成")

print("3. 主鍵、欄位與值域")
pk = [(r["year_roc"], r["school_code"], r["dept"], r["day_night"], r["program"]) for r in vac]
check(len(pk) == len(set(pk)), f"{len(pk):,} 列沒有重複主鍵 (year_roc, school_code, dept, day_night, program)")
check(all(int(r["vacancy"]) >= 0 for r in vac), "vacancy 沒有負數")
check(all(int(r["gap"]) == int(r["quota_A"]) - int(r["reserved_B"]) - int(r["enrolled_C"]) for r in vac), "gap = A − B − C")
check(all(int(r["vacancy"]) == max(int(r["gap"]), 0) for r in vac), "vacancy = max(gap, 0)")
check(any(int(r["gap"]) < 0 for r in vac), "gap 有負數(超收)被保留")
check(all(int(r["year"]) == int(r["year_roc"]) + 1911 for r in vac), "year = year_roc + 1911")
check(sorted({r["year_roc"] for r in vac}) == [str(y) for y in range(106, 115)], "9 個學年(106–114)齊全")
check({r["ownership"] for r in vac} <= {"公立", "私立"}, "ownership 只有公立/私立")
check(not any(r["school"] == "" or "學校財團法人" in r["school"] for r in vac), "school 簡稱非空且不含「學校財團法人」")
check(not any(int(r["quota_A"]) == 0 and int(r["enrolled_C"]) == 0 for r in vac), "輸出沒有 A=0 且 C=0 的列")
check({r["program"] for r in vac} <= {r["program_raw"] for r in pmap}, "輸出的學制班別都在 program_mapping 內")
grp = {r["program_raw"]: r["program_group"] for r in pmap}
check(all(r["program_group"] != "" for r in vac), "program_group 沒有空值")
check({r["program_group"] for r in vac} <= {"學士", "碩士", "博士", "專科"}, "program_group 只有學士/碩士/博士/專科")
check(all(r["program_group"] == grp[r["program"]] for r in vac), "program_group 與 program_mapping 一致")
check(list(vac[0].keys()).index("program_group") == list(vac[0].keys()).index("program") + 1, "program_group 緊接在 program 後面")
check({r["foreign_E"] for r in vac if int(r["year_roc"]) <= 108} == {""}, "106–108 學年 foreign_E 全為空")
check(all(r["foreign_E"] != "" for r in vac if int(r["year_roc"]) >= 109), "109 學年起 foreign_E 皆有數字")

print("4. 每學年統計(vacancy.csv)")
fmt = "{:>5} {:>6} {:>9} {:>9} {:>8} {:>9}"
head = fmt.format("學年", "學校數", "ΣA", "ΣC", "總缺額", "註冊率")
for title, sel in (("全部", lambda r: True),
                   ("日間學士班(program=學士班(含四技), day_night=日間)",
                    lambda r: r["day_night"] == "日間" and r["program"] == "學士班(含四技)")):
    print(f"  [{title}]")
    print("  " + head)
    for y in years:
        rs = [r for r in vac if r["year_roc"] == y and sel(r)]
        sa = sum(int(r["quota_A"]) for r in rs); sb = sum(int(r["reserved_B"]) for r in rs)
        sc = sum(int(r["enrolled_C"]) for r in rs); sv = sum(int(r["vacancy"]) for r in rs)
        n = len({r["school_code"] for r in rs})
        print("  " + fmt.format(y, n, f"{sa:,}", f"{sc:,}", f"{sv:,}", f"{sc / (sa - sb) * 100:.2f}%"))
print("  註冊率 = ΣC / Σ(A−B),未封頂;總缺額 = Σ vacancy(逐列 max(gap,0))")

print()
if failures:
    print(f"❌ {len(failures)} 項未通過")
    sys.exit(1)
print("🎉 全部通過")
