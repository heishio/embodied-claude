"""Sleep-like replay and consolidation routines."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .graph import MemoryGraph
    from .memory import MemoryStore
    from .types import Memory

# ── Bias Update Constants ──────────────────────
BIAS_ACCUMULATION_RATE = 0.01    # バイアス蓄積レート（控えめ）
BIAS_MAX_CAP = 0.15              # 単一バイアスの上限
BIAS_DECAY_FACTOR = 0.90         # コンソリデーション毎の減衰率
BIAS_PRUNE_THRESHOLD = 0.001    # この値以下のバイアスを刈り取り
BIAS_APPLY_COEFFICIENT = 0.05   # recall時のノイズ適用係数


@dataclass(frozen=True)
class ConsolidationStats:
    """Summary statistics for replay execution."""

    replay_events: int
    coactivation_updates: int
    link_updates: int
    refreshed_memories: int

    def to_dict(self) -> dict[str, int]:
        return {
            "replay_events": self.replay_events,
            "coactivation_updates": self.coactivation_updates,
            "link_updates": self.link_updates,
            "refreshed_memories": self.refreshed_memories,
        }


class ConsolidationEngine:
    """Replay memories and update association strengths."""

    async def run(
        self,
        store: "MemoryStore",
        window_hours: int = 24,
        max_replay_events: int = 200,
        link_update_strength: float = 0.2,
    ) -> ConsolidationStats:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, window_hours))
        recent = await store.list_recent(limit=max(max_replay_events * 2, 50))
        recent = [m for m in recent if self._is_after(m, cutoff)]

        if len(recent) < 2:
            return ConsolidationStats(0, 0, 0, len(recent))

        replay_events = 0
        coactivation_updates = 0
        link_updates = 0
        refreshed_ids: set[str] = set()

        for idx in range(len(recent) - 1):
            if replay_events >= max_replay_events:
                break

            left = recent[idx]
            right = recent[idx + 1]

            delta = max(0.05, min(1.0, link_update_strength))
            await store.bump_coactivation(left.id, right.id, delta=delta)
            coactivation_updates += 2

            left_error = max(0.0, left.prediction_error * 0.9)
            right_error = max(0.0, right.prediction_error * 0.9)
            await store.record_activation(left.id, prediction_error=left_error)
            await store.record_activation(right.id, prediction_error=right_error)
            refreshed_ids.add(left.id)
            refreshed_ids.add(right.id)

            if await store.maybe_add_related_link(left.id, right.id, threshold=0.6):
                link_updates += 1

            replay_events += 1

        # Consolidate freshness — sleep creates temporal distance
        await store.consolidate_freshness()

        return ConsolidationStats(
            replay_events=replay_events,
            coactivation_updates=coactivation_updates,
            link_updates=link_updates,
            refreshed_memories=len(refreshed_ids),
        )

    async def synthesize_composites(
        self,
        store: "MemoryStore",
        similarity_threshold: float = 0.75,
        min_group_size: int = 2,
        max_group_size: int = 8,
    ) -> dict[str, int]:
        """類似した level=0 記憶をグループ化し、合成記憶（level=1）を生成する。"""
        # 1. 対象取得
        mem_vecs = await store.fetch_level0_memories_with_vectors(min_freshness=0.1)
        if len(mem_vecs) < min_group_size:
            return {"composites_created": 0, "composites_skipped": 0}

        memories = [mv[0] for mv in mem_vecs]
        vectors = np.array([mv[1] for mv in mem_vecs])

        # 2. 類似度計算（コサイン類似度行列）
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-10
        normalized = vectors / norms
        sim_matrix = normalized @ normalized.T

        # 3. Union-Find でグループ化
        n = len(memories)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= similarity_threshold:
                    union(i, j)

        # グループ収集
        groups: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in groups:
                groups[root] = []
            groups[root].append(i)

        # min_group_size 未満を除外
        groups = {k: v for k, v in groups.items() if len(v) >= min_group_size}

        # max_group_size を超えたら最も相互類似度が高いサブセットに絞る
        for root, indices in list(groups.items()):
            if len(indices) > max_group_size:
                # 各ペアの類似度合計でスコアを計算し、上位を残す
                scores: list[tuple[float, int]] = []
                for idx in indices:
                    s = sum(sim_matrix[idx, j] for j in indices if j != idx)
                    scores.append((s, idx))
                scores.sort(reverse=True)
                groups[root] = [idx for _, idx in scores[:max_group_size]]

        # 4. 既存チェック
        existing = await store.get_existing_composite_members()
        composites_created = 0
        composites_skipped = 0

        for indices in groups.values():
            member_ids = frozenset(memories[i].id for i in indices)
            if member_ids in existing:
                composites_skipped += 1
                continue

            # 5. 合成ベクトル生成（importance で重み付けた加重平均 → 正規化）
            weights = np.array([float(memories[i].importance) for i in indices])
            member_vectors = np.array([vectors[i] for i in indices])
            weighted_sum = (member_vectors.T @ weights).T
            norm = np.linalg.norm(weighted_sum) + 1e-10
            composite_vector = weighted_sum / norm

            # 6. メタ情報の集約
            emotions = [memories[i].emotion for i in indices]
            emotion_counter = Counter(emotions)
            composite_emotion = emotion_counter.most_common(1)[0][0]

            importances = [memories[i].importance for i in indices]
            composite_importance = min(5, ceil(sum(importances) / len(importances)))

            freshnesses = [memories[i].freshness for i in indices]
            composite_freshness = max(freshnesses)

            categories = [memories[i].category for i in indices]
            category_counter = Counter(categories)
            composite_category = category_counter.most_common(1)[0][0]

            # 7. 保存
            await store.save_composite(
                member_ids=list(member_ids),
                vector=composite_vector,
                emotion=composite_emotion,
                importance=composite_importance,
                freshness=composite_freshness,
                category=composite_category,
            )
            composites_created += 1

        return {
            "composites_created": composites_created,
            "composites_skipped": composites_skipped,
        }

    async def compute_boundary_layers(
        self,
        store: "MemoryStore",
        graph: "MemoryGraph | None" = None,
        n_layers: int = 3,
        noise_scale: float = 0.1,
        max_template_strength: float = 0.3,
    ) -> dict[str, int]:
        """外縁検出 + ノイズレイヤー生成 + バイアス蓄積。

        各 composite について:
        - Layer 0: ノイズなしで edge/core を分類
        - Layer 1..n_layers: 体験チェーンベースのノイズで edge/core を再分類

        Returns:
            {"composites_processed": int, "total_layers": int,
             "biases_updated": int, "biases_decayed": int, "biases_pruned": int}
        """
        composite_ids = await store.fetch_all_composite_ids()
        if not composite_ids:
            return {
                "composites_processed": 0, "total_layers": 0,
                "biases_updated": 0, "biases_decayed": 0, "biases_pruned": 0,
            }

        # 1. バイアス減衰（蓄積より先に行う）
        decay_stats = await self._decay_biases(store)

        # 2. 既存バイアスを取得
        existing_biases = await store.fetch_template_biases()

        # テンプレート生成（全composite共通） — 3-tuple: (vec, transient_strength, bias_weight)
        templates: list[tuple[np.ndarray, float, float, str]] = []  # (vec, transient, bias, chain_id)
        if graph is not None:
            raw_templates = await store.fetch_verb_chain_templates()
            for chain_id, vec, verbs, nouns in raw_templates:
                raw_strength = await graph.get_path_strength(verbs, nouns)
                strength = min(raw_strength, max_template_strength)
                if strength > 0:
                    bias = existing_biases.get(chain_id, 0.0)
                    templates.append((vec, strength, bias, chain_id))

        await store.clear_boundary_layers()

        composites_processed = 0
        total_layers = 0
        # 各compositeのlayer0分類を記録（バイアス更新用）
        composite_layer0_map: dict[str, list[int]] = {}

        for cid in composite_ids:
            members = await store.fetch_composite_with_vectors(cid)
            if len(members) < 2:
                continue

            centroid = await store.fetch_composite_centroid(cid)
            if centroid is None:
                continue

            member_ids = [m[0] for m in members]
            member_vecs = np.array([m[1] for m in members])

            # ── Layer 0: ノイズなし ──
            layer0 = self._classify_edge_core(member_vecs, centroid)
            composite_layer0_map[cid] = layer0
            all_layers: list[tuple[str, int, int]] = []
            for i, mid in enumerate(member_ids):
                all_layers.append((mid, 0, layer0[i]))

            # ── Layer 1..n_layers: ノイズ適用 ──
            layer_classifications: list[list[int]] = []
            for layer_idx in range(1, n_layers + 1):
                noised_vecs = self._apply_noise(
                    member_vecs, templates, noise_scale, layer_idx,
                )
                # 新しい重心を計算
                noised_centroid = noised_vecs.mean(axis=0)
                norm = np.linalg.norm(noised_centroid) + 1e-10
                noised_centroid = noised_centroid / norm

                layer_classes = self._classify_edge_core(noised_vecs, noised_centroid)
                layer_classifications.append(layer_classes)
                for i, mid in enumerate(member_ids):
                    all_layers.append((mid, layer_idx, layer_classes[i]))

            await store.save_boundary_layers(cid, all_layers)
            composites_processed += 1
            total_layers += 1 + n_layers

        # 3. バイアス蓄積
        biases_updated = await self._update_biases(
            store, templates, composite_layer0_map, n_layers, existing_biases,
        )

        return {
            "composites_processed": composites_processed,
            "total_layers": total_layers,
            "biases_updated": biases_updated,
            "biases_decayed": decay_stats.get("biases_decayed", 0),
            "biases_pruned": decay_stats.get("biases_pruned", 0),
        }

    def _classify_edge_core(
        self, member_vecs: np.ndarray, centroid: np.ndarray
    ) -> list[int]:
        """メンバーを重心からの距離で edge(1) / core(0) に分類。"""
        # コサイン距離: d = 1 - cos(v, centroid)
        c_norm = centroid / (np.linalg.norm(centroid) + 1e-10)
        m_norms = member_vecs / (np.linalg.norm(member_vecs, axis=1, keepdims=True) + 1e-10)
        similarities = m_norms @ c_norm
        distances = 1.0 - similarities
        d_mean = float(np.mean(distances))
        return [1 if float(d) > d_mean else 0 for d in distances]

    def _apply_noise(
        self,
        member_vecs: np.ndarray,
        templates: list[tuple[np.ndarray, float, float, str]],
        noise_scale: float,
        seed: int,
        max_template_strength: float = 0.3,
    ) -> np.ndarray:
        """テンプレートベースのノイズを適用。テンプレートがなければランダムノイズ。

        templates: list of (vec, transient_strength, bias_weight, chain_id)
        effective_strength = min(transient + BIAS_APPLY_COEFFICIENT * bias, max_template_strength)
        """
        rng = np.random.default_rng(seed)
        n_members = member_vecs.shape[0]
        dim = member_vecs.shape[1]

        if not templates:
            # フォールバック: ランダムノイズ
            noise = rng.normal(0, noise_scale, size=(n_members, dim)).astype(np.float32)
            noised = member_vecs + noise
            norms = np.linalg.norm(noised, axis=1, keepdims=True) + 1e-10
            return noised / norms

        # テンプレートベースのノイズ
        noised = member_vecs.copy()
        m_norms = member_vecs / (np.linalg.norm(member_vecs, axis=1, keepdims=True) + 1e-10)

        for t_vec, transient_strength, bias_weight, _chain_id in templates:
            effective_strength = min(
                transient_strength + BIAS_APPLY_COEFFICIENT * bias_weight,
                max_template_strength,
            )
            alpha = rng.normal(0, 1)
            t_norm = t_vec / (np.linalg.norm(t_vec) + 1e-10)
            alignments = m_norms @ t_norm  # shape: (n_members,)
            for i in range(n_members):
                noised[i] += effective_strength * alpha * float(alignments[i]) * t_norm * noise_scale

        # 正規化
        norms = np.linalg.norm(noised, axis=1, keepdims=True) + 1e-10
        return noised / norms

    async def _decay_biases(self, store: "MemoryStore") -> dict[str, int]:
        """バイアスを減衰・刈り取り。"""
        return await store.decay_template_biases(BIAS_DECAY_FACTOR, BIAS_PRUNE_THRESHOLD)

    async def _update_biases(
        self,
        store: "MemoryStore",
        templates: list[tuple[np.ndarray, float, float, str]],
        composite_layer0_map: dict[str, list[int]],
        n_layers: int,
        existing_biases: dict[str, float],
    ) -> int:
        """各テンプレートのバイアスを蓄積する。

        composite毎にlayer 0 vs layer k の分類変化（ハミング距離 / メンバー数）を計算し、
        テンプレートのtransient_strengthの割合で按分して蓄積。
        """
        if not templates or not composite_layer0_map or n_layers == 0:
            return 0

        db = store._ensure_connected()

        # 全compositeの平均シフトを計算
        overall_shifts: list[float] = []
        for cid, layer0 in composite_layer0_map.items():
            n_members = len(layer0)
            if n_members == 0:
                continue
            # 各レイヤーのlayer0との分類差を取得
            for layer_idx in range(1, n_layers + 1):
                rows = db.execute(
                    """SELECT member_id, is_edge FROM boundary_layers
                       WHERE composite_id = ? AND layer_index = ?
                       ORDER BY member_id""",
                    (cid, layer_idx),
                ).fetchall()
                if len(rows) != n_members:
                    continue
                layer0_rows = db.execute(
                    """SELECT member_id, is_edge FROM boundary_layers
                       WHERE composite_id = ? AND layer_index = 0
                       ORDER BY member_id""",
                    (cid,),
                ).fetchall()
                # ハミング距離
                hamming = sum(
                    1 for l0, lk in zip(layer0_rows, rows)
                    if l0["is_edge"] != lk["is_edge"]
                )
                shift = hamming / n_members
                overall_shifts.append(shift)

        if not overall_shifts:
            return 0

        avg_shift = sum(overall_shifts) / len(overall_shifts)

        # テンプレート毎のバイアス更新
        sum_strengths = sum(t[1] for t in templates)
        if sum_strengths <= 0:
            return 0

        bias_updates: list[tuple[str, float, int]] = []
        for _vec, transient_strength, bias_weight, chain_id in templates:
            proportion = transient_strength / sum_strengths
            shift_contribution = proportion * avg_shift
            old_bias = existing_biases.get(chain_id, 0.0)
            new_bias = min(BIAS_MAX_CAP, old_bias + BIAS_ACCUMULATION_RATE * shift_contribution)
            # update_count を既存の値から取得
            row = db.execute(
                "SELECT update_count FROM template_biases WHERE chain_id = ?",
                (chain_id,),
            ).fetchone()
            old_count = row["update_count"] if row else 0
            bias_updates.append((chain_id, new_bias, old_count + 1))

        await store.save_template_biases(bias_updates)
        return len(bias_updates)

    def _is_after(self, memory: "Memory", cutoff: datetime) -> bool:
        try:
            timestamp = datetime.fromisoformat(memory.timestamp)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        return timestamp >= cutoff
