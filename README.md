# 全台大專校院招生缺額 106–114 學年

BI 作業。用教育部公開的系所層級資料，看全台大專校院各學年的核定名額、註冊人數和缺額。

網站：https://crazray1520.github.io/university-vacancy/

可以依學年區間、公私立、學校類別、學制、日間／進修和學校篩選，所有圖表連動。

## 資料來源

- 資料集：大學、技專校院各系所註冊率（大專校院校務資訊公開平臺 學12-1）
- 提供機關：教育部高等教育司
- 資料集頁面：https://data.gov.tw/dataset/26228
- 下載網址：`https://udb.moe.edu.tw/download/udata/static_file/114/學12-1.新生(含境外生)註冊率-以「系(所)」統計.csv`
- 授權：政府資料開放授權條款第 1 版
- 下載日期：2026-10-12
- 統計基準日：每年 10 月 15 日
- 涵蓋學年度：106–114（共 9 年）
- 原檔 SHA-256 記在 `raw/SOURCES.md`

## 資料夾結構

```
raw/        原始資料，不修改
  學12-1.新生(含境外生)註冊率-以「系(所)」統計.csv
  SOURCES.md              來源網址、下載日期、SHA-256
  download_headers.txt    下載時的 HTTP 標頭
work/
  etl_vacancy.py          raw → data
  build_data.py           data → docs/data.js
data/
  vacancy.csv             整理後的資料，每列一個系所班別
  school_mapping.csv      學校代碼對照（含合併）
  program_mapping.csv     學制班別歸類
scripts/
  validate_vacancy.py     驗證 data/vacancy.csv
docs/
  data.js                 網頁用的資料
  index.html              BI 網頁（GitHub Pages 發佈此資料夾）
prompts/                  課程提示
```

## 流程

```
raw/*.csv → work/etl_vacancy.py → data/*.csv → work/build_data.py → docs/data.js → docs/index.html
```

`data/vacancy.csv` 欄位：`year_roc, year, school_code, school, ownership, school_type, dept, day_night, program, program_group, quota_A, reserved_B, enrolled_C, foreign_E, gap, vacancy`。

ETL 做的事：

- 106–108 學年的境外生人數（E）原檔寫 `...`，轉成空值。
- 核定名額與註冊人數都是 0 的列排除，共 941 列（都在 109 學年之後）。
- 依學校對照表統一學校代碼和簡稱。合併後主鍵相同的 17 列加總成一列。
- 學年度保留民國年，另加西元年（學年度 + 1911）。
- 輸出 74,493 列、163 所學校。

## 重跑與驗證

需要 [uv](https://docs.astral.sh/uv/)，不需要另外安裝套件。

```
uv run work/etl_vacancy.py
uv run scripts/validate_vacancy.py
uv run work/build_data.py
```

- `validate_vacancy.py` 重新讀原始檔比對：每學年 ΣA、ΣB、ΣC，學校合併前後人數，主鍵不重複，vacancy 沒有負數，9 個學年齊全，`program_group` 沒有空值。
- `build_data.py` 寫出 `docs/data.js` 後，會從檔案還原並比對每學年的列數、ΣA、ΣB、ΣC 和總缺額。

本機預覽：直接用瀏覽器開 `docs/index.html`。圖表元件 ECharts 從 cdnjs 載入，需要網路。

## 名額、缺額與註冊率

- 核定名額（A）：教育部核定的招生名額。
- 保留入學（B）：已取得保留入學資格的人數。
- 可招名額 = A − B。
- 註冊人數（C）：總量內實際註冊人數。
- gap = A − B − C。負數代表超收。
- 缺額（vacancy）= max(gap, 0)。每個系所班別各算一列，再加總。
- 註冊率 = ΣC ÷ Σ(A − B)。

教育部公布的註冊率是 (C + E) ÷ (A − B + E)，E 為境外生註冊人數，單列上限 100%。本專案的註冊率不含 E，也不封頂，和官方數字略有差異。

網頁上「核定名額」是 A，「可招名額」是 A − B。圖表 1 的長條用可招名額，KPI 的名額增減用核定名額。

## 學校合併對照

| 原代碼 | 原校名 | 統一代碼 | 統一後簡稱 |
|---|---|---|---|
| 0016 | 國立陽明大學 | 0007 | 國立陽明交通大學 |
| 0026 | 國立高雄第一科技大學 | 0053 | 國立高雄科技大學 |
| 0027 | 國立高雄應用科技大學 | 0053 | 國立高雄科技大學 |
| 0034 | 國立高雄海洋科技大學 | 0053 | 國立高雄科技大學 |
| 1166 | 亞東技術學院 | 1084 | 亞東科技大學 |
| 1195 | 馬偕學校財團法人馬偕醫學院 | 1085 | 馬偕醫學大學 |
| 1290 | 崇仁醫護管理專科學校 | 1293 | 崇仁醫護管理專科學校 |

完整對照在 `data/school_mapping.csv`。簡稱去掉「學校財團法人」及重複的校名。

學制歸類在 `data/program_mapping.csv`：學士班、二技、4+X、附設進院歸學士；碩士班歸碩士；博士班歸博士；五專、二專、附設進專歸專科。

## 限制

- 缺額是推算值（A − B − C），資料集沒有缺額欄位。
- 缺額加總是逐列 max(gap, 0) 再相加，超收的系所不會抵銷其他系所的缺額。
- 註冊率不含境外生，也不對單列封頂，和教育部官方數字略有差異。
- 國立陽明交通大學 106–109 學年為陽明、交通兩校合計。原始資料中陽明大學是獨立代碼，已併入。
- 校名為現行名稱。國立高雄科技大學 106 學年為三校合計；亞東科技大學含前身亞東技術學院；馬偕醫學大學含前身馬偕醫學院。原始資料中部分學校的歷史校名已被回填為現行名稱。
- 停招或停辦的學校只出現在有資料的學年。
- 沒有錄取人數，資料集只有核定名額、保留入學和註冊人數。
- 只有 9 個學年（106–114），不是 10 年。
