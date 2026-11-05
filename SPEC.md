# ComfyUI SystemOne LoRA Router — 資料結構與接線規格

> 狀態：規格草案（尚未實作）  
> 目標：三節點畫布接線 → SystemOne 決策 → 彙總 LoRA 表 → 套用後輸出 MODEL  
> 語言：繁體中文規格說明

---

## 0. 設計總覽

畫布上三個節點：

| 節點 | 角色 | 輸出型別 |
|------|------|----------|
| **LoRA Library** | 定義可被選用的 LoRA 實體庫 | `S1_LORA_LIB` |
| **Theme Library** | 定義主題（問題／選項／選項→LoRA 對應） | `S1_THEME_LIB` |
| **Theme Sequence** | 主執行器：依序跑主題、打 SystemOne、套 LoRA | `MODEL`（+ 可選 `CLIP`、除錯字串） |

接線方向（固定）：

```
[LoRA Library] ──S1_LORA_LIB──┐
                              ├──► [Theme Sequence] ──MODEL──► 下游
[Theme Library] ─S1_THEME_LIB─┘         ▲
                                         │ MODEL / CLIP / prompt…
```

Theme Sequence 另吃：`model`、可選 `clip`、`positive_prompt`、可選 `negative_prompt`、API 設定。

---

## 1. 自訂型別名稱與承載物件

ComfyUI 慣例：自訂型別 = 大寫字串；前後端只比對字串相同即可接線；實際傳遞任意 Python 物件。輸入端一律 `forceInput: True`。

| 型別字串 | Python 承載 | 說明 |
|----------|-------------|------|
| `S1_LORA_LIB` | `LoraLibrary`（dict-backed dataclass / TypedDict） | LoRA 實體表；以 `lora_id` 為鍵 |
| `S1_THEME_LIB` | `ThemeLibrary` | 主題定義表；以 `theme_id` 為鍵 |
| `S1_THEME_SEQ` | *不對外暴露*（序列定義嵌在 Theme Sequence 節點 widget／JSON） | 預設：序列步驟寫在主節點上，不另開第四個節點 |
| `S1_DECISION_REPORT` | `str`（JSON 字串） | 可選除錯輸出；非正式自訂型別，用 `STRING` 即可 |

**預設（標為 defaults）**：不另做 `S1_THEME_SEQ` 接線型別；主題順序與依賴直接寫在 Theme Sequence 的 `sequence_json` 欄位。若之後要「序列可重用」，再加第四個 Sequence Library 節點輸出 `S1_THEME_SEQ`。

前綴 `S1_` 避免與其他自訂節點撞名。

---

## 2. 三節點 INPUT / RETURN / CATEGORY / FUNCTION

套件目錄建議：`ComfyUI-SystemOne-LoraRouter`  
CATEGORY 統一：`SystemOne/LoraRouter`

### 2.1 LoRA Library — `S1LoraLibrary`

```text
CLASS: S1LoraLibrary
CATEGORY: SystemOne/LoraRouter
FUNCTION: build

INPUT_TYPES:
  required:
    library_json: ("STRING", {
      "multiline": True,
      "default": "{ \"loras\": [] }"
    })
  optional: {}   # 後期可加「從檔案載入」路徑

RETURN_TYPES: ("S1_LORA_LIB",)
RETURN_NAMES: ("lora_lib",)
```

行為：解析／驗證 JSON → 回傳 `LoraLibrary` 物件。不碰 disk 上的 `.safetensors` 本體（只存相對 `loras/` 的 name 與預設強度）。

### 2.2 Theme Library — `S1ThemeLibrary`

```text
CLASS: S1ThemeLibrary
CATEGORY: SystemOne/LoraRouter
FUNCTION: build

INPUT_TYPES:
  required:
    library_json: ("STRING", {
      "multiline": True,
      "default": "{ \"themes\": [] }"
    })

RETURN_TYPES: ("S1_THEME_LIB",)
RETURN_NAMES: ("theme_lib",)
```

行為：解析主題定義（問題文案、單選／複選、選項、選項→`lora_id` 列表）。**不**內嵌完整 LoRA 路徑；只引用 `lora_id`。

### 2.3 Theme Sequence — `S1ThemeSequence`（主執行器）

```text
CLASS: S1ThemeSequence
CATEGORY: SystemOne/LoraRouter
FUNCTION: apply

INPUT_TYPES:
  required:
    model:      ("MODEL",)
    theme_lib:  ("S1_THEME_LIB", {"forceInput": True})
    lora_lib:   ("S1_LORA_LIB",  {"forceInput": True})
    positive:   ("STRING", {"multiline": True, "default": ""})
    sequence_json: ("STRING", {
      "multiline": True,
      "default": "{ \"steps\": [] }"
    })
    api_key:    ("STRING", {"default": "", "multiline": False})
      # 預設：空字串時改讀環境變數 SYSTEM_ONE_API_KEY
    api_model:  ("STRING", {"default": ""})
      # 預設：空則用 GET /v1/models 的預設／節點內建 fallback 字串（實作時再鎖）
  optional:
    clip:       ("CLIP",)
    negative:   ("STRING", {"multiline": True, "default": ""})
    endpoint:   ("STRING", {"default": "https://system-one.dev/v1/systemone"})
    noul_threshold: ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01})
    on_error:   (["passthrough", "raise"], {"default": "passthrough"})
      # passthrough：API 失敗則原 model/clip 原樣輸出
    strength_conflict: (["max", "sum_clamp_1", "last_wins"], {"default": "max"})
    min_confidence: ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01})
      # choice 低於門檻時改用該主題的 fallback_option_id（若有）

RETURN_TYPES: ("MODEL", "CLIP", "STRING")
RETURN_NAMES: ("model", "clip", "report_json")
```

說明：
- 若未接 `clip`：只套 MODEL 側 LoRA（`load_lora_for_models(model, None, …)` 慣例），`CLIP` 輸出回傳輸入的 `clip` 或 `None`（Comfy 端：optional 未接時不輸出有效 CLIP；**預設**：未接 clip 時第二輸出仍回傳 `None`，下游勿硬接）。
- `report_json`：逐步決策、啟用的 LoRA 表、錯誤訊息，方便除錯。

---

## 3. JSON Schema / Dataclass

### 3.1 LoRA 條目 — `LoraEntry`

```json
{
  "lora_id": "style_anime_v3",
  "name": "anime_style_v3.safetensors",
  "strength_model": 0.8,
  "strength_clip": 0.8,
  "tags": ["style", "anime"],
  "enabled_default": true,
  "meta": {}
}
```

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `lora_id` | string | ✓ | 庫內唯一 ID；主題只引用這個 |
| `name` | string | ✓ | 相對 ComfyUI `loras/` 的檔名（與 Lora Loader 相同） |
| `strength_model` | float | ✓ | 預設 model 強度；可被對應覆寫 |
| `strength_clip` | float | ✓ | 預設 clip 強度 |
| `tags` | string[] | | 僅供人讀／日後篩選 |
| `enabled_default` | bool | | 預設 `true`；`false` 表示除非被選中否則永不載入 |
| `meta` | object | | 擴充用 |

`LoraLibrary`：

```json
{
  "version": 1,
  "loras": [ /* LoraEntry[] */ ]
}
```

### 3.2 選項 — `ThemeOption`

```json
{
  "option_id": "anime",
  "label": "動漫風格",
  "description": "平面賽璐璐、清晰線稿、二次元審美",
  "lora_bindings": [
    { "lora_id": "style_anime_v3", "strength_model": 0.85, "strength_clip": null },
    { "lora_id": "detail_eyes", "strength_model": 0.5, "strength_clip": 0.5 }
  ]
}
```

| 欄位 | 說明 |
|------|------|
| `option_id` | 主題內唯一；送進 SystemOne `criteria` 的 **key**（短、穩定、無空白） |
| `label` | 人讀名稱 |
| `description` | 送進 `criteria[option_id]` 的說明文字（決策依據） |
| `lora_bindings` | 此選項啟用的 LoRA 列表；可 0..N（支援一選多 LoRA） |
| `lora_bindings[].strength_*` | `null`／省略 = 用庫內預設；有值則覆寫 |

**對應關係（已鎖定 ABC）**：
- 1:1 → 一個 option 一個 binding  
- 一選多 → 一個 option 多個 binding  
- 一 LoRA 多選 → 同一 `lora_id` 出現在多個 option 的 bindings（彙總時去重）

### 3.3 主題定義 — `ThemeDefinition`

```json
{
  "theme_id": "art_style",
  "title": "畫風",
  "instructions": "依提示詞判斷最適合的主要畫風。",
  "select_mode": "single",
  "options": [ /* ThemeOption[] */ ],
  "fallback_option_id": "realistic",
  "none_option_id": null
}
```

| 欄位 | 說明 |
|------|------|
| `theme_id` | 庫內唯一；序列步驟引用 |
| `select_mode` | `"single"` \| `"multi"` |
| `instructions` | SystemOne `questions.*.instructions` |
| `fallback_option_id` | single：低信心或無效答案時使用；multi：可為 `null`（表示全不選） |
| `none_option_id` | **預設**：single 且至少 2 個選項時，可設一個「都不套」的虛擬選項（無 bindings）；未設則必須選一個有意義的選項 |

`ThemeLibrary`：

```json
{
  "version": 1,
  "themes": [ /* ThemeDefinition[] */ ]
}
```

### 3.4 序列步驟與依賴 — `SequenceStep` / `DependencyRule`

```json
{
  "version": 1,
  "steps": [
    {
      "step_id": "s1",
      "theme_id": "art_style",
      "enabled_by_default": true,
      "dependencies": []
    },
    {
      "step_id": "s2",
      "theme_id": "character_pack",
      "enabled_by_default": false,
      "dependencies": [
        {
          "when": {
            "step_id": "s1",
            "op": "includes_any",
            "option_ids": ["anime"]
          },
          "actions": [
            { "type": "enable_step" },
            {
              "type": "rewrite_options",
              "keep_option_ids": ["waifu_a", "waifu_b"],
              "add_options": [],
              "remove_option_ids": [],
              "patch_bindings": {
                "waifu_a": [
                  { "lora_id": "char_a", "strength_model": 0.9, "strength_clip": 0.9 }
                ]
              }
            },
            {
              "type": "rewrite_instructions",
              "instructions": "在動漫畫風前提下，選擇要套用的角色包（可複選）。"
            }
          ]
        }
      ]
    }
  ]
}
```

**`when` 條件（預設支援這組）**：

| `op` | 語意 |
|------|------|
| `eq` | single：選中 == 唯一 `option_ids[0]` |
| `neq` | 相反 |
| `includes_any` | multi／single：選中集合與 `option_ids` 有交集 |
| `includes_all` | 選中集合包含全部 `option_ids` |
| `skipped` | 前步驟被跳過（未啟用或依賴不成立） |
| `answered` | 前步驟有實際問過並得到答案 |

多條 `dependencies`：**預設 OR**（任一 `when` 成立就執行其 `actions`）。同一 dependency 內 `actions` 依陣列順序套用。

**`actions` 類型（兩種依賴都涵蓋）**：

| `type` | 效果 |
|--------|------|
| `enable_step` | 本步改為啟用（覆蓋 `enabled_by_default: false`） |
| `disable_step` | 強制跳過 |
| `rewrite_options` | 改後題選項集合／bindings（`keep` / `add` / `remove` / `patch_bindings`） |
| `rewrite_instructions` | 改後題 `instructions` |
| `set_select_mode` | 改 `"single"` / `"multi"`（少用；預設允許） |

若某步最終為 disabled → 不呼叫 SystemOne、答案記為 `skipped`，供後步 `when.op: skipped` 使用。

---

## 4. Theme Sequence 執行期演算法

### 4.1 前置

1. 驗證 `lora_lib`、`theme_lib`、`sequence_json` schema（`version`、唯一 ID、所有 `theme_id`／`lora_id` 可解析）。
2. 解析 API key：widget > `SYSTEM_ONE_API_KEY` 環境變數。
3. 建立 `state`（送 SystemOne）：

```json
{
  "positive": "<positive prompt>",
  "negative": "<negative or empty>"
}
```

**預設**：`state` 用物件而非純字串，方便之後擴充；`negative` 空則仍帶 `""`。

4. 初始化：
   - `answers: dict[step_id, Answer]`
   - `pending_lora: dict[lora_id, {strength_model, strength_clip, sources[]}]`
   - `step_enabled: dict[step_id, bool]` ← 先填各步 `enabled_by_default`

### 4.2 依 `steps` 陣列順序走訪

對每個 `step`：

1. **套用依賴（只看「已完成」的前步）**  
   掃描 `dependencies`；`when` 成立則依序執行 `actions`（enable/disable/rewrite…）。  
   rewrite 作用在「本步主題的**執行期副本**」，不改 Theme Library 原件。

2. **若最終 disabled** → 記 `answers[step_id] = {status:"skipped"}`，continue。

3. **組 SystemOne 問題（每個啟用步驟一次 HTTP；預設）**  
   - 原因：後步 options／instructions 可能被前步 rewrite；無法把全部主題塞進單次 request 的固定 `questions`。  
   - 單次 request 仍遵守官方上限：`questions` 1–32（本設計每步通常 1 題；multi 用多個 noul 時見下）。

#### 4.2.1 `select_mode: "single"` → `choice`

```json
{
  "model": "<api_model>",
  "state": { "positive": "...", "negative": "..." },
  "questions": {
    "<step_id>": {
      "type": "choice",
      "instructions": "<theme.instructions 經 rewrite 後>",
      "criteria": {
        "<option_id>": "<description>",
        "...": "..."
      }
    }
  }
}
```

- `POST https://system-one.dev/v1/systemone`  
- Header：`Authorization: Bearer …`，建議 `Idempotency-Key: <uuid4>`  
- 讀 `answers[<step_id>].choice` → 選中的 `option_id`  
- 若有 `confidence` 且 `< min_confidence` → 改用 `fallback_option_id`  
- Choice 至少需要模型允許的最少選項數（文件：多數 ≥2；以模型 `minChoiceOptions` 為準）。**預設**：若 rewrite 後只剩 1 個 option，自動補一個 `__none__`（無 binding）以滿足 API，或直接不呼叫、視為選中唯一選項（實作選：**只剩 1 個則跳過 API、直接採用**）。

#### 4.2.2 `select_mode: "multi"` → 每個 option 一個 `noul`

官方無原生 multi-choice；**預設模式**：

```json
"questions": {
  "<step_id>__<option_id>": {
    "type": "noul",
    "instructions": "<theme.instructions>\n具體選項：<label> — <description>\n是否應啟用此選項？",
    "criteria": {
      "true": "提示詞明確需要或強烈暗示此選項",
      "false": "提示詞不需要此選項"
    }
  }
}
```

- 對每個 question：若 `noul >= noul_threshold` → 選中該 `option_id`  
- 同一 request 可放多個 noul（上限 32）。若選項 > 32：**預設**分批 request，state 相同。  
- **備選（未預設啟用）**：先用一個 `choice` 選「主類」，再對細項 noul——留待日後。

4. **依選中 options 展開 `lora_bindings`**，寫入 `pending_lora`：
   - 同一 `lora_id` 多次命中 → 依 `strength_conflict` 合併：
     - `max`（預設）：取較大 strength_model／strength_clip  
     - `sum_clamp_1`：相加後 clamp 到 1.0  
     - `last_wins`：後寫覆蓋  
   - `sources` 記錄 `(step_id, option_id)` 供 report。

5. 記 `answers[step_id] = {status:"ok", selected:[...], raw:...}`。

### 4.3 套用 LoRA

1. 將 `pending_lora` 轉成有序列表（**預設排序**：`lora_id` 字典序，保證可重現；日後可加 `priority` 欄位）。  
2. 對每一筆呼叫 ComfyUI 核心慣用路徑：

```python
from comfy.sd import load_lora_for_models
# 或 folder_paths + comfy.utils.load_torch_file 取得 lora 後：
model, clip = load_lora_for_models(
    model, clip,  # clip 可為 None
    lora_object,
    strength_model,
    strength_clip,
)
```

3. 找不到檔案：依 `on_error` — `passthrough` 跳過該筆並寫入 report；`raise` 則中斷。  
4. API／網路錯誤：同樣依 `on_error`；`passthrough` 時回傳原始 model/clip。

### 4.4 輸出

- `model`：套用後 MODEL  
- `clip`：套用後 CLIP 或 None  
- `report_json`：壓縮 JSON，例如：

```json
{
  "answers": { "s1": { "status": "ok", "selected": ["anime"] }, "s2": { "status": "ok", "selected": ["waifu_a"] } },
  "applied": [
    { "lora_id": "style_anime_v3", "name": "anime_style_v3.safetensors", "strength_model": 0.85, "strength_clip": 0.8, "sources": [["s1","anime"]] }
  ],
  "errors": []
}
```

---

## 5. 最小範例設定（2 主題 + 依賴 + 3 LoRA）

### LoRA Library

```json
{
  "version": 1,
  "loras": [
    {
      "lora_id": "style_anime_v3",
      "name": "anime_style_v3.safetensors",
      "strength_model": 0.8,
      "strength_clip": 0.8
    },
    {
      "lora_id": "style_realistic",
      "name": "realistic_skin_v2.safetensors",
      "strength_model": 0.7,
      "strength_clip": 0.7
    },
    {
      "lora_id": "char_a",
      "name": "character_a.safetensors",
      "strength_model": 0.9,
      "strength_clip": 0.9
    }
  ]
}
```

### Theme Library

```json
{
  "version": 1,
  "themes": [
    {
      "theme_id": "art_style",
      "title": "畫風",
      "instructions": "判斷提示詞的主要畫風。",
      "select_mode": "single",
      "fallback_option_id": "realistic",
      "options": [
        {
          "option_id": "anime",
          "label": "動漫",
          "description": "二次元、賽璐璐、動漫角色",
          "lora_bindings": [
            { "lora_id": "style_anime_v3", "strength_model": 0.85 }
          ]
        },
        {
          "option_id": "realistic",
          "label": "寫實",
          "description": "真實光影、照片感、寫實皮膚",
          "lora_bindings": [
            { "lora_id": "style_realistic" }
          ]
        }
      ]
    },
    {
      "theme_id": "character_pack",
      "title": "角色包",
      "instructions": "是否套用角色 LoRA（可複選）。",
      "select_mode": "multi",
      "fallback_option_id": null,
      "options": [
        {
          "option_id": "waifu_a",
          "label": "角色 A",
          "description": "提到角色 A 的名字或特徵",
          "lora_bindings": [
            { "lora_id": "char_a", "strength_model": 0.9, "strength_clip": 0.9 }
          ]
        },
        {
          "option_id": "waifu_b",
          "label": "角色 B（示範無檔）",
          "description": "提到角色 B",
          "lora_bindings": []
        }
      ]
    }
  ]
}
```

### Theme Sequence（`sequence_json`）

```json
{
  "version": 1,
  "steps": [
    {
      "step_id": "s1",
      "theme_id": "art_style",
      "enabled_by_default": true,
      "dependencies": []
    },
    {
      "step_id": "s2",
      "theme_id": "character_pack",
      "enabled_by_default": false,
      "dependencies": [
        {
          "when": {
            "step_id": "s1",
            "op": "includes_any",
            "option_ids": ["anime"]
          },
          "actions": [
            { "type": "enable_step" },
            {
              "type": "rewrite_instructions",
              "instructions": "在動漫畫風下，選擇要啟用的角色包（可複選）。"
            },
            {
              "type": "rewrite_options",
              "keep_option_ids": ["waifu_a"],
              "remove_option_ids": ["waifu_b"],
              "add_options": [],
              "patch_bindings": {}
            }
          ]
        }
      ]
    }
  ]
}
```

**走讀**：提示詞偏動漫 → s1 選 `anime` → 啟用 s2、只留 `waifu_a` → 若 noul 過門檻 → 套用 `style_anime_v3` + `char_a`。若 s1 選 `realistic` → s2 維持 disabled → 只套 `style_realistic`。

---

## 6. 已選定的預設（非阻塞）與僅存開放項

### 已選定 defaults（可直接依此 scaffold）

| 項目 | 預設 |
|------|------|
| 序列存放處 | 寫在 Theme Sequence 的 `sequence_json`，不做第四節點 |
| 多主題 API | **每啟用步驟一次** POST（因依賴 rewrite） |
| 單選 | `type: "choice"` |
| 複選 | 每 option 一個 `type: "noul"`，`>= noul_threshold` 視為選中 |
| 強度衝突 | `max` |
| API 失敗 | `passthrough` 原 model |
| state 形狀 | `{positive, negative}` 物件 |
| 套用順序 | `lora_id` 字典序 |
| 型別前綴 | `S1_LORA_LIB` / `S1_THEME_LIB` |
| Schema 版本 | `version: 1` |
| API 端點 | `https://system-one.dev/v1/systemone` |
| Key | widget 優先，否則 `SYSTEM_ONE_API_KEY` |

### 開放項（不阻塞 scaffold；實作前可再問使用者）

1. **`api_model` 預設字串**：需使用者提供常用 model `name`（來自 `GET /v1/models`），規格不硬編碼易過期的 ID。  
2. **UI 舒適度**：第一版用 multiline JSON widget；側邊欄視覺編輯器列為 v2。  
3. **是否輸出「純 LoRA 表」第三除錯腳**：目前用 `report_json` 即可。

---

## 7. Scaffold 建議檔案樹（僅指引，本規格不含實作碼）

```text
ComfyUI-SystemOne-LoraRouter/
  __init__.py
  nodes/
    lora_library.py
    theme_library.py
    theme_sequence.py
  schema/
    types.py          # dataclasses + validate_*
  systemone/
    client.py         # POST wrapper
  requirements.txt    # requests 或 httpx
  README.md
```

NODE_CLASS_MAPPINGS：`S1LoraLibrary` / `S1ThemeLibrary` / `S1ThemeSequence`。

---

## 8. SystemOne 契約摘要（實作必遵）

- `POST https://system-one.dev/v1/systemone`  
- Auth：`Authorization: Bearer <key>`  
- Body：`model`, `state`, `questions`（1–32）  
- 問題類型：`choice` | `score` | `noul`（本套件用 choice + noul）  
- Choice 回覆：`answers[qid].choice` + `probabilities` + `confidence`  
- Noul 回覆：`answers[qid].noul` ∈ [0,1]  
- 建議帶 `Idempotency-Key`  
- 參考：[System One API docs](https://docs.system-one.dev/en/docs/api)

---

**成功標準**：使用者確認本規格後，即可依第 2–5 節 scaffold 空殼節點與 schema 驗證，再填 client 與 `load_lora_for_models` 迴圈。
