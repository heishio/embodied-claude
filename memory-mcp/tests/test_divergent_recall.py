"""Tests for divergent recall and consolidation."""

import asyncio

import pytest

from memory_mcp.memory import MemoryStore


class TestDivergentRecall:
    """Divergent recall behavior tests."""

    @pytest.mark.asyncio
    async def test_recall_divergent_returns_results_with_diagnostics(
        self,
        memory_store: MemoryStore,
    ):
        await memory_store.save(
            content="朝の空をカメラで探した",
            emotion="5",
            category="observation",
            tags=("camera", "sky"),
        )
        await memory_store.save(
            content="窓の位置を変えて空を見つけた",
            emotion="1",
            category="observation",
            tags=("window", "sky"),
        )
        await memory_store.save(
            content="夕飯の献立を考えた",
            emotion="8",
            category="daily",
        )

        results, diagnostics = await memory_store.recall_divergent(
            context="空を探すカメラの話",
            n_results=3,
            max_branches=3,
            max_depth=3,
            include_diagnostics=True,
        )

        assert results
        assert "diversity_score" in diagnostics
        assert diagnostics["selected_count"] == len(results)

    @pytest.mark.asyncio
    async def test_get_association_diagnostics_has_core_metrics(
        self,
        memory_store: MemoryStore,
    ):
        await memory_store.save(content="カメラの向きと空の関係を覚えた")
        await memory_store.save(content="雲の色で天気を予測した")

        diagnostics = await memory_store.get_association_diagnostics(
            context="空とカメラ",
            sample_size=10,
        )

        assert "selected_count" in diagnostics
        assert "avg_prediction_error" in diagnostics


class TestConsolidation:
    """Consolidation replay tests."""

    @pytest.mark.asyncio
    async def test_consolidate_memories_updates_activation(
        self,
        memory_store: MemoryStore,
    ):
        first = await memory_store.save(content="朝の観察を記録した", category="observation")
        await asyncio.sleep(0.01)
        await memory_store.save(content="窓辺で空を見た", category="observation")

        stats = await memory_store.consolidate_memories(
            window_hours=1,
            max_replay_events=10,
            link_update_strength=0.3,
        )

        assert stats["replay_events"] > 0
        updated_first = await memory_store.get_by_id(first.id)
        assert updated_first is not None
        assert updated_first.activation_count >= 1
