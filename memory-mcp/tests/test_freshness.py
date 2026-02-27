"""Tests for freshness (心理的時間距離) feature."""

import pytest

from memory_mcp.memory import MemoryStore
from memory_mcp.server import _freshness_filter


class TestFreshnessFilter:
    """Tests for _freshness_filter helper."""

    def test_no_bounds(self):
        assert _freshness_filter(0.5, None, None) is True

    def test_min_only(self):
        assert _freshness_filter(0.5, 0.3, None) is True
        assert _freshness_filter(0.2, 0.3, None) is False

    def test_max_only(self):
        assert _freshness_filter(0.5, None, 0.7) is True
        assert _freshness_filter(0.8, None, 0.7) is False

    def test_range(self):
        assert _freshness_filter(0.5, 0.3, 0.7) is True
        assert _freshness_filter(0.2, 0.3, 0.7) is False
        assert _freshness_filter(0.8, 0.3, 0.7) is False

    def test_exact_boundary(self):
        assert _freshness_filter(0.3, 0.3, 0.7) is True
        assert _freshness_filter(0.7, 0.3, 0.7) is True


class TestFreshnessSave:
    """Tests for freshness on save."""

    @pytest.mark.asyncio
    async def test_new_memory_has_freshness_1(self, memory_store: MemoryStore):
        """New memory should have freshness = 1.0."""
        memory = await memory_store.save(content="テスト記憶")
        assert memory.freshness == 1.0

    @pytest.mark.asyncio
    async def test_existing_memories_decay_on_save(self, memory_store: MemoryStore):
        """Existing memories should lose freshness when a new memory is saved."""
        m1 = await memory_store.save(content="最初の記憶")
        assert m1.freshness == 1.0

        # Save another memory -> m1 should decay
        await memory_store.save(content="二番目の記憶")

        m1_after = await memory_store.get_by_id(m1.id)
        assert m1_after is not None
        assert m1_after.freshness < 1.0
        assert m1_after.freshness == pytest.approx(1.0 - 0.003, abs=0.001)

    @pytest.mark.asyncio
    async def test_multiple_saves_accumulate_decay(self, memory_store: MemoryStore):
        """Multiple saves should accumulate freshness decay."""
        m1 = await memory_store.save(content="最初の記憶")

        for i in range(10):
            await memory_store.save(content=f"記憶 {i+2}")

        m1_after = await memory_store.get_by_id(m1.id)
        assert m1_after is not None
        # 10 saves -> freshness should be ~1.0 - 0.003*10 = 0.97
        expected = 1.0 - 0.003 * 10
        assert m1_after.freshness == pytest.approx(expected, abs=0.005)

    @pytest.mark.asyncio
    async def test_freshness_floor(self, memory_store: MemoryStore):
        """Freshness should never go below 0.01."""
        m1 = await memory_store.save(content="古い記憶")

        # Force freshness very low
        db = memory_store._ensure_connected()
        db.execute("UPDATE memories SET freshness = 0.02 WHERE id = ?", (m1.id,))
        db.commit()

        # Save new memory -> decay should not go below 0.01
        await memory_store.save(content="新しい記憶")

        m1_after = await memory_store.get_by_id(m1.id)
        assert m1_after is not None
        assert m1_after.freshness >= 0.01


class TestFreshnessConsolidate:
    """Tests for consolidate_freshness."""

    @pytest.mark.asyncio
    async def test_consolidate_freshness(self, memory_store: MemoryStore):
        """consolidate_freshness should multiply all freshness by factor."""
        m1 = await memory_store.save(content="テスト記憶1")
        m2 = await memory_store.save(content="テスト記憶2")

        await memory_store.consolidate_freshness(factor=0.85)

        m1_after = await memory_store.get_by_id(m1.id)
        m2_after = await memory_store.get_by_id(m2.id)
        assert m1_after is not None
        assert m2_after is not None

        # m1 was decayed once (when m2 was saved): 1.0 - 0.003 = 0.997
        # Then consolidated: 0.997 * 0.85 = 0.847
        assert m1_after.freshness < 0.997
        assert m1_after.freshness == pytest.approx((1.0 - 0.003) * 0.85, abs=0.01)

        # m2 was fresh (1.0), consolidated: 1.0 * 0.85 = 0.85
        assert m2_after.freshness == pytest.approx(1.0 * 0.85, abs=0.01)

    @pytest.mark.asyncio
    async def test_consolidate_freshness_floor(self, memory_store: MemoryStore):
        """consolidate_freshness should not go below 0.01."""
        m1 = await memory_store.save(content="テスト記憶")

        # Force freshness very low
        db = memory_store._ensure_connected()
        db.execute("UPDATE memories SET freshness = 0.02 WHERE id = ?", (m1.id,))
        db.commit()

        await memory_store.consolidate_freshness(factor=0.1)

        m1_after = await memory_store.get_by_id(m1.id)
        assert m1_after is not None
        assert m1_after.freshness >= 0.01


class TestFreshnessConsolidateCutoff:
    """Tests for post-consolidation decay scope."""

    @pytest.mark.asyncio
    async def test_old_memories_not_decayed_after_consolidate(self, memory_store: MemoryStore):
        """After consolidation, old memories should not get fixed decay on new saves."""
        m_old = await memory_store.save(content="コンソリデート前の記憶")

        # Consolidate — this records last_consolidated_at
        await memory_store.consolidate_freshness(factor=0.85)
        old_freshness = (await memory_store.get_by_id(m_old.id)).freshness

        # Save a new memory after consolidation
        await memory_store.save(content="コンソリデート後の新しい記憶")

        # Old memory should NOT have decayed further (its timestamp is before cutoff)
        m_old_after = await memory_store.get_by_id(m_old.id)
        assert m_old_after.freshness == old_freshness

    @pytest.mark.asyncio
    async def test_new_memories_still_decay_after_consolidate(self, memory_store: MemoryStore):
        """New memories (after consolidation) should still get fixed decay."""
        await memory_store.save(content="種")
        await memory_store.consolidate_freshness(factor=0.85)

        m_new = await memory_store.save(content="コンソリデート後の記憶A")
        # Save another — m_new should decay
        await memory_store.save(content="コンソリデート後の記憶B")

        m_new_after = await memory_store.get_by_id(m_new.id)
        assert m_new_after.freshness < 1.0
        assert m_new_after.freshness == pytest.approx(1.0 - 0.003, abs=0.001)


class TestFreshnessDecayAll:
    """Tests for decay_all_freshness."""

    @pytest.mark.asyncio
    async def test_decay_all_freshness(self, memory_store: MemoryStore):
        """decay_all_freshness should subtract amount from all memories."""
        m1 = await memory_store.save(content="テスト記憶")

        await memory_store.decay_all_freshness(amount=0.1)

        m1_after = await memory_store.get_by_id(m1.id)
        assert m1_after is not None
        assert m1_after.freshness == pytest.approx(1.0 - 0.1, abs=0.01)
