# Memory MCP - Boundary System

合成記憶の「領域」と「境界」を扱う仕組み。
核心: 点と点の類似度ではなく、領域と領域の近さで想起する。しかも「どこから来たか」で近さが変わる。

## 全体像

```
level=0 記憶群
  ↓ synthesize_composites (consolidation.py)
level=1 合成記憶 (centroid + members)
  ↓ compute_boundary_layers (consolidation.py)
boundary_layers テーブル (composite_id, member_id, layer_index, is_edge)
  ↓ recall 時に参照
recall_divergent → edge 展開 + fuzziness スコア
recall_experience → fuzziness ベースリランク
recall_by_verb → 経路依存レイヤー選択 + boundary スコアリランク
```

## 実装済み

### Step 1: 合成記憶 (level=1)
- **consolidation.py: `synthesize_composites()`**
  - level=0 記憶をベクトル類似度でクラスタリング
  - クラスタの重心ベクトル + メンバーリストを level=1 記憶として保存
  - `composite_members` テーブルでメンバー管理
- **store.py**: `fetch_level0_memories_with_vectors()`, `fetch_composite_with_vectors()`, `fetch_composite_centroid()`, `fetch_all_composite_ids()`

### Step 2: 外縁検出 + ノイズレイヤー
- **consolidation.py: `compute_boundary_layers()`**
  - Layer 0: ノイズなし。各メンバーの重心からの距離で edge/core を分類
  - Layer 1〜N: 体験チェーン（VerbChain）の経路パターンからバイアスベクトルを生成し、ノイズとして加えた上で edge/core を再分類
  - グラフなし時はランダムノイズにフォールバック
  - `max_template_strength` で反芻思考防止（太い経路がノイズを支配しないようキャップ）
- **store.py**: `save_boundary_layers()`, `clear_boundary_layers()`, `fetch_verb_chain_templates()`
- **boundary_layers テーブル**: `(composite_id, member_id, layer_index, is_edge)`
- `consolidate_memories` ツール実行時に自動で `compute_boundary_layers` も呼ばれる

### Step 3a: recall / recall_divergent の boundary-aware 化
- **store.py: `get_member_boundary_scores(memory_ids)`**
  - fuzziness = 全レイヤーで edge に分類された回数 / 全レイヤー数 (0.0〜1.0)
- **store.py: `find_adjacent_composites(composite_id, query_vec)`**
  - edge メンバーの平均ベクトルから隣接 composite を発見
- **store.py: `expand_composite_edges(composite_ids, query_vec)`**
  - composite の edge メンバー + 隣接 composite の edge メンバーを展開
- **recall_divergent (store.py)**
  - spread 結果から level=1 composite を抽出 → `expand_composite_edges` で edge メンバーを追加候補に
  - workspace selection 時に `boundary_score` (fuzziness) を diversity boost として加味

### Step 3b: 経路依存レイヤー選択 (recall_experience / recall_by_verb)
- **store.py: `select_active_boundary_layer(path_vec)`**
  - 経路ベクトル（辿った verbs/nouns を結合して embedding したもの）に最も aligned な boundary layer を選択
  - 各レイヤーの edge メンバー平均ベクトルと path_vec の cosine similarity → argmax
- **store.py: `get_chain_boundary_scores(chain_ids, layer_index)`**
  - verb chain と edge メンバーの cosine similarity → boundary 近接スコア (0.0〜1.0)
  - layer_index 指定時: そのレイヤーの edge メンバーとの類似度
  - layer_index=None: fuzziness ベース（全レイヤー横断、fuzziness > 0.5 のメンバーを edge 扱い）
- **verb_chain.py: `expand_from_fragment()` 返り値拡張**
  - `(chains, visited_verbs, visited_nouns)` を返すように変更
  - グラフ展開で辿ったノードが「経路」として使える
- **server.py: recall_experience ハンドラ**
  - fuzziness ベース boundary bonus (WEIGHT=0.05) でリランク（lower is better なので減算）
- **server.py: recall_by_verb ハンドラ**
  - visited_verbs/nouns → path embedding → `select_active_boundary_layer` → そのレイヤーの boundary scores
  - 元の順位スコア + 0.1 * boundary_score でリランク

## 未実装 / 構想段階

### コンソリデート時の boundary 更新最適化
- 現在: `consolidate_memories` のたびに全 composite の boundary layers を再計算
- 構想: 変更のあった composite だけ差分更新

### 領域間距離の直接計算
- 現在: edge メンバーのベクトルを介して間接的に隣接関係を計算
- 構想: composite 同士の「距離」を boundary の重なりで直接定義
  - 2つの composite の edge メンバーが似ている = 近い領域
  - 経路依存で「どこから来たかで距離が変わる」

### テンプレート強度の動的調整
- 現在: `max_template_strength` は固定値
- 構想: 使われすぎた経路の減衰、新しい経路が入ると古いのが相対的に薄まる仕組み
- グラフの重み減衰・刈り取りと同じ思想

### 階層的合成 (level=2+)
- 構想: level=1 composite 同士をさらにクラスタリングして level=2 合成記憶を作る
- より大きな「意味の領域」を形成

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `consolidation.py` | 合成記憶生成 + boundary layer 計算 |
| `store.py` | boundary 関連のDB操作 + recall 時のスコアリング |
| `verb_chain.py` | 動詞チェーン展開（経路情報を返す） |
| `server.py` | MCPハンドラ（recall_experience / recall_by_verb のリランク） |
| `graph.py` | 動詞/名詞の重み付きグラフ（テンプレート生成の元データ） |

## DB テーブル

```sql
-- 合成記憶のメンバー
composite_members (composite_id, member_id, contribution_weight)

-- 境界レイヤー
boundary_layers (composite_id, member_id, layer_index, is_edge)
-- layer_index=0: ノイズなし基準レイヤー
-- layer_index=1+: ノイズ付きレイヤー
-- is_edge=1: 外縁, is_edge=0: 中心
```
