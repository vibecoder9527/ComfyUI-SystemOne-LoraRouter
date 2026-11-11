[English](README.md) | 繁體中文

# ComfyUI-SystemOne-LoraRouter

一組 ComfyUI 自訂節點：讓 SystemOne 判斷哪些主題選項符合你的提示詞，把選中的選項轉成標籤，再載入符合這些標籤的 LoRA。

每個 Theme 節點上，positive 輸入在 negative 之上。positive 必填；negative 為選填，未連接或空白時送出空字串。提示詞是輸入插槽，不會存進主題裡。

完整規格見 [SPEC.md](SPEC.md)。舊版工作流程（`enable_json`、`theme_result`、主題庫、序列）的升級方式見 [MIGRATION.md](MIGRATION.md)。

<img width="1420" height="717" alt="image" src="https://github.com/user-attachments/assets/da821ec8-0d73-497c-a8ec-5b7992bce843" />

## 安裝

放在 `custom_nodes` 裡的資料夾名稱必須是 `ComfyUI-SystemOne-LoraRouter`。

```bash
cd /path/to/ComfyUI/custom_nodes
git clone <repo-url> ComfyUI-SystemOne-LoraRouter
```

重新啟動 ComfyUI，再對瀏覽器強制重新整理，讓 `js/` 裡的前端檔案載入。不需要額外安裝 Python 套件；存圖節點使用 ComfyUI 本身附帶的 numpy 與 Pillow。

## 節點

所有節點都在 **SystemOne → LoraRouter** 分類下。

| 節點 | Class | 用途 | 輸出 |
| --- | --- | --- | --- |
| SystemOne Settings | `S1Settings` | API 金鑰、端點、模型、門檻與錯誤處理方式 | `S1_SETTINGS` |
| LoRA Library | `S1LoraLibrary` | 可供選用的 LoRA，含標籤與強度 | `S1_LORA_LIB` |
| Theme Root | `S1ThemeRoot` | 第一層判斷：一定會詢問 SystemOne | 32 個 `S1_DECISION` 選項插槽，最後是 `report_json` |
| Theme | `S1Theme` | 後續判斷：只有 `upstream` 接到的插槽被觸發時才執行 | 32 個 `S1_DECISION` 選項插槽，最後是 `report_json` |
| Theme Collect | `S1ThemeCollect` | 合併同層分支的判斷結果 | `S1_DECISION` |
| LoRA Aggregate | `S1LoraAggregate` | 把標籤對應到 LoRA Library 並載入 LoRA | `MODEL`、`CLIP`、`report_json` |
| S1 Save Image (Scrubbed) | `S1SaveImageScrubbed` | 像 Save Image 一樣存圖，但 PNG 內不含 SystemOne 金鑰與網址 | `IMAGE`（輸出節點） |

## 基本接法

```
SystemOne Settings ──► Theme Root.settings ──(選項插槽)──► Theme.upstream ──(選項插槽)──► LoRA Aggregate.decision
positive / negative ──► Theme Root、Theme                              LoRA Library ──► LoRA Aggregate.lora_lib
                                                                       MODEL / CLIP ──► LoRA Aggregate ──► 取樣器
```

1. **SystemOne Settings**：填入 `api_key`，或留空並設定環境變數 `SYSTEM_ONE_API_KEY`（欄位有值時以欄位為準）。`endpoint` 預設為 `https://system-one.dev/v1/systemone`。`api_model` 留空時送出 `unspecified`。`noul_threshold`（預設 0.5）與 `min_confidence`（預設 0）用來調整選取。`on_error`：`passthrough` 會記錄 API 失敗、該主題不加任何標籤，但仍從每個選項插槽輸出；`raise` 會中止整個流程。
2. **LoRA Library**：加入你的 LoRA 與標籤（見下文）。
3. **Theme Root**：把 Settings 接到 `settings`，提示詞接到 `positive`（`negative` 選填），再填寫選項表格。
4. **Theme**（選用，可多層）：接同一個 Settings、它自己的提示詞，以及上層主題的某個選項插槽到 `upstream`。只有該選項被選中時才會執行。
5. **LoRA Aggregate**：接上 `MODEL`、把 LoRA Library 接到 `lora_lib`，再把要套用標籤的選項插槽（或 Theme Collect）接到 `decision`。只有需要修改 CLIP 時才接 `CLIP`；沒接時 CLIP 輸出為 `None`。

沒被選中的選項插槽會輸出 `ExecutionBlocker`，ComfyUI 會略過只接在那個插槽後面的節點。None 選項被選中時仍會輸出，但不貢獻任何標籤。

## LoRA Library（節點上直接編輯）

直接在節點上編輯；`library_json` 欄位會隱藏，存檔時存的就是它。

- **＋ Add Lora** 會開啟 LoRA 選單（資料夾以子選單呈現，可打字篩選）。選好檔案後才會新增一列。新增的列預設開啟 Default On、強度 1.00。
- 點某一列的名稱可以改選其他檔案。
- **Default On**：開啟代表一律載入；關閉代表只有主題選中它的標籤時才載入。
- **Strength**：◀ / ▶ 每次調整 0.05，也可以左右拖曳或直接輸入。同一個值會同時寫入 `strength_model` 與 `strength_clip`。
- **S** 代表把這個項目標記為 slider LoRA，強度可設為 −5 到 5。取消標記時，負的強度會重設為 0。
- **Tags** 以標籤片（chip）呈現：輸入後按 Enter 或逗號新增，Backspace 刪除最後一個，× 刪除單一標籤，點一下標籤可以編輯。建議清單來自圖中已使用的標籤。LoRA Library 的標籤只能是純名稱（不帶權重）。
- 在列上按右鍵可使用 **Move up**、**Move down**、**Mark as Slider** / **Unmark Slider** 與 **Delete**。

## Theme Root / Theme（節點上直接編輯）

直接在節點上編輯；`theme_json` 欄位會隱藏。

- 最上方的文字框是給 SystemOne 的主題說明（instructions）。
- 選項表格有 **Option**（列號）、**Description**、**Tags (Comma)** 三欄。Description 是 SystemOne 判斷該選項時讀的內容；Tags 是該選項被選中時貢獻的標籤。
- **Add option** 會在 None 上方新增一列。
- **None** 永遠在最後一列，不能移動也不能刪除，有自己的輸出插槽，且不貢獻標籤。它的 id 存在 `theme_json` 的 `none_option_id`。
- **`option_N` 永遠等於第 N 列。** 選項 id 依表格順序重新編號，所以 `report_json` 與第 N 個輸出插槽永遠代表第 N 列（None 拿最後一號）。
- 在列上按右鍵可使用 **Move up**、**Move down** 或 **Delete**。移動時兩列連同 id 一起交換，接在那些輸出插槽上的線會跟著選項走。刪除時下方各列往前重新編號，它們的線也跟著往前移；被刪選項本身的線會斷開。
- 存檔時 id 順序不一致的工作流程（例如 None = `option_2`、dress = `option_3`），載入時會自動重新編號一次並重接線。以前產生的 `report_json` 保留當時的 id。
- 輸出插槽以選項文字標示，未使用的插槽會隱藏；送出的 prompt 中 `report_json` 永遠是輸出索引 32。一個主題最多 32 個選項。
- `select_mode` 存在 `theme_json` 裡：`single`（預設）會問一題單選；`multi` 會對每個選項各問一次是否符合，分數達到 `noul_threshold` 的選項都會被選中。節點上的編輯器會保留原本存的值。

## Slider LoRA：`tag:weight`

在主題選項的標籤中可以寫 `name:weight`，例如 `age:-2`、`age:0`、`age:1.5`（也可以寫 `+1.5`）。單純寫 `age` 的用法不變。

- 只比對名稱，且不分大小寫：選項標籤 `Age:-2` 會對應到 LoRA Library 標籤 `age`。
- 帶權重的命中會覆蓋該 LoRA 的兩個強度；不帶權重的命中則沿用 LoRA Library 設定的強度。
- 權重 `0` 會略過該 LoRA，即使開啟了 Default On 也一樣（列在 `skipped`，原因為 `weight_0`）。
- 多個被選中的選項對同一個 LoRA 給出不同權重時，取絕對值最大的；絕對值相同時取第一個。
- 超出 −5..5 的權重會被限制在範圍內，並記錄警告。
- 沒有標記為 slider 的 LoRA 收到負權重時仍會套用，並記錄警告。
- 標籤片顯示權重的格式為 `age −2`。

送給 SystemOne 的判斷請求不包含任何標籤。

## Theme Collect

當兩個同層分支要一起套用時使用 Collect：

```
Theme Root 插槽 ──► Theme A ──► Theme Collect ──► LoRA Aggregate
                └─► Theme B ──┘
```

輸入一開始是 `a` 與 `b`；接上一個就會再出現一個空的輸入（最多 16 個）。沒有執行到的分支會被忽略，所以只有一個分支觸發時 Collect 仍會執行。沒有任何可用輸入時會報錯。同一個主題的相同判斷只保留一份；同一個 `theme_id` 出現兩個不同的判斷時會報錯。

## report_json

- **Theme / Theme Root**：`theme_id`、`role`、`status`、`selected`（選中的選項 id）、此主題的 `tags`、所有上游的 `decisions`、`accumulated_tags`、`errors`、`slots`（每個選項的 `{option_id, emitted}`）、`api`（`called`、`endpoint`、`model`、`key_source`）以及 `notes`。不會包含 API 金鑰。
- **LoRA Aggregate**：`tags`、`themes`、`matched`（含 `weight_source` 與 `slider`）、`skipped`、`applied`、`errors`、`notes` 與 `warnings`。

## S1 Save Image (Scrubbed)

用法和內建的 **Save Image** 節點一樣：`filename_prefix`、ComfyUI 的輸出資料夾、`prefix_00001_.png` 的流水號檔名、UI 預覽，也支援 `--disable-metadata`。PNG 仍內嵌 `prompt` 與 `workflow`，可以直接拖回 ComfyUI 使用。

寫檔前會清除 SystemOne Settings 的 `api_key` 與 `endpoint`：

- prompt 與 workflow（包含子圖 subgraph）中的這兩個欄位會設為 `""`；重新載入後會使用 `SYSTEM_ONE_API_KEY` 與預設端點；
- 這兩個值在 metadata 其他地方出現時也會一併移除，包括透過連接的 Primitive 或 String 節點傳入的值（少於 6 個字元的值只會在 Settings 欄位中清除）。

存檔後會重新讀取 PNG。若仍找得到被清除的值，就刪除該檔案並報錯。metadata 的其他內容都不會更動。要分享圖片時，請改用這個節點取代 Save Image。

## 注意事項與限制

- Theme Collect 依賴對 ComfyUI 0.44 執行器的一個小 hook，讓被略過的同層分支不會連帶略過 Collect。若 hook 無法安裝，會顯示 `ThemeCollectHookWarning`，Collect 會維持保守行為（不執行）。
- `multi` 主題一個都沒選中時，所有選項插槽都會被阻擋。主題沒有任何選項則視為錯誤（依 `on_error` 處理）。
- 在 ComfyUI 之外（例如測試中）不會真的載入 LoRA 檔案，報告中會註明。

## 測試

```bash
python3 -m unittest
```

測試不會呼叫 SystemOne，也不需要 API 金鑰。安裝了 `node` 時會一併執行 JS 模型測試。這套測試不包含瀏覽器實際操作。

## AI 協作開發

本專案是與 AI 助理 Grok Bot 協作開發的。需求、設計與測試由維護者主導，大部分的程式碼與文件則由 Grok Bot 撰寫。每一項變更在合併前，都會經過維護者審查，並在 ComfyUI 中實際測試。
