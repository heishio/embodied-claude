"""Core memory compaction - extract and write memory essence to MEMORY.md."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Section marker in MEMORY.md (記憶の核セクションは常に末尾扱い)
SECTION_START = "## 記憶の核"

# Compaction parameters
# Fresh group: freshness-weighted scoring
FRESH_FULL = 3
FRESH_FRAGMENTS = 12
# Legacy group: traditional scoring with light freshness
LEGACY_FULL = 2
LEGACY_FRAGMENTS = 6
TOP_GRAPH_NODES = 15  # Number of top graph noun nodes


def _extract_first_sentence(content: str, max_chars: int = 80) -> str:
    first_line = content.split("\n")[0]
    idx = first_line.find("。")
    if idx >= 0:
        return first_line[: idx + 1]
    if len(first_line) > max_chars:
        return first_line[:max_chars] + "..."
    return first_line


def _extract_last_sentence(content: str, max_chars: int = 80) -> str:
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    if not lines:
        return ""
    last_line = lines[-1]
    sentences = [s for s in last_line.split("。") if s.strip()]
    if not sentences:
        return last_line[:max_chars]
    result = sentences[-1].strip()
    if not result.endswith("。"):
        result += "。"
    if len(result) > max_chars:
        return result[:max_chars] + "..."
    return result


def _extract_first_last(content: str, max_chars: int = 80) -> str:
    first = _extract_first_sentence(content, max_chars)
    last = _extract_last_sentence(content, max_chars)
    if first == last or not last or last == "。":
        return first
    return f"{first} ... {last}"


def compact_core_memories(db_path: str, memory_md_path: str) -> dict:
    """Extract core memories and write to MEMORY.md.

    Two groups:
    - Fresh: freshness-weighted (recent important memories)
    - Legacy: traditional scoring with light freshness boost (long-term core)

    Returns stats about the compaction.
    """
    if not memory_md_path:
        return {"skipped": True, "reason": "no MEMORY_MD_PATH configured"}

    md_path = Path(memory_md_path)
    if not md_path.parent.exists():
        return {"skipped": True, "reason": f"directory not found: {md_path.parent}"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        rows = _fetch_memories(conn)
        fresh_ranked = _score_fresh(rows)
        legacy_ranked = _score_legacy(rows)
        graph_nodes = _get_graph_top_nodes(conn, TOP_GRAPH_NODES)

        # Deduplicate: remove fresh picks from legacy
        fresh_ids = {m["id"] for m in fresh_ranked[: FRESH_FULL + FRESH_FRAGMENTS]}
        legacy_ranked = [m for m in legacy_ranked if m["id"] not in fresh_ids]

        section_text = _format_section(fresh_ranked, legacy_ranked, graph_nodes)
        _update_memory_md(md_path, section_text)

        return {
            "compacted": True,
            "total_memories": len(rows),
            "fresh_full": min(FRESH_FULL, len(fresh_ranked)),
            "fresh_fragments": min(FRESH_FRAGMENTS, max(0, len(fresh_ranked) - FRESH_FULL)),
            "legacy_full": min(LEGACY_FULL, len(legacy_ranked)),
            "legacy_fragments": min(LEGACY_FRAGMENTS, max(0, len(legacy_ranked) - LEGACY_FULL)),
            "graph_nodes": len(graph_nodes),
        }
    except Exception as e:
        logger.error(f"Compaction failed: {e}")
        return {"compacted": False, "error": str(e)}
    finally:
        conn.close()


def _fetch_memories(conn: sqlite3.Connection) -> list[dict]:
    """Fetch all level-0 memories with scoring data."""
    cur = conn.cursor()

    cur.execute("""
        SELECT
            m.id,
            m.content,
            m.importance,
            m.freshness,
            m.category,
            m.access_count,
            m.activation_count,
            COALESCE(bf.fuzziness, 0.0) as boundary_fuzziness
        FROM memories m
        LEFT JOIN (
            SELECT member_id,
                   CAST(SUM(is_edge) AS REAL) / COUNT(*) as fuzziness
            FROM boundary_layers GROUP BY member_id
        ) bf ON bf.member_id = m.id
        WHERE m.level = 0
        GROUP BY m.id
    """)

    # Template biases: composite_id → bias_weight → memory_id にマッピング
    cur2 = conn.cursor()
    cur2.execute(
        """SELECT cm.member_id, tb.bias_weight
           FROM template_biases tb
           JOIN composite_members cm ON cm.composite_id = tb.template_id
           WHERE tb.bias_weight > 0.0001"""
    )
    bias_map: dict[str, float] = {}
    for r in cur2.fetchall():
        mid, bw = r[0], r[1]
        # 同じmemory_idが複数compositeに属する場合はmax
        if mid not in bias_map or bw > bias_map[mid]:
            bias_map[mid] = bw

    rows = []
    for row in cur.fetchall():
        rows.append({
            "id": row["id"],
            "content": row["content"],
            "importance": row["importance"],
            "freshness": row["freshness"],
            "category": row["category"],
            "access_count": row["access_count"],
            "activation_count": row["activation_count"],
            "boundary_fuzziness": row["boundary_fuzziness"],
            "bias_weight": bias_map.get(row["id"], 0.0),
        })

    return rows


def _score_fresh(rows: list[dict]) -> list[dict]:
    """Score with freshness as dominant factor."""
    scored = []
    for m in rows:
        importance_score = (m["importance"] - 1) * 0.1
        freshness = m["freshness"]

        # freshness * importance dominates
        composite = (
            freshness * 1.0
            + importance_score * 0.5
        )

        scored.append({**m, "composite_score": composite})

    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    return scored


def _score_legacy(rows: list[dict]) -> list[dict]:
    """Traditional scoring with light freshness boost."""
    scored = []
    for m in rows:
        importance_score = (m["importance"] - 1) * 0.1
        access_score = min(
            (m["access_count"] + m["activation_count"]) / 20.0, 1.0
        )
        fuzziness = m["boundary_fuzziness"]
        bias_score = m["bias_weight"] / 0.15
        freshness = m["freshness"]

        composite = (
            importance_score * 1.0
            + access_score * 0.3
            + fuzziness * 0.2
            + bias_score * 0.3
            + freshness * 0.15
        )

        scored.append({**m, "composite_score": composite})

    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    return scored


def _get_graph_top_nodes(conn: sqlite3.Connection, limit: int) -> list[tuple[str, float]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT gn.surface_form, SUM(ge.weight) as total_weight
        FROM graph_nodes gn
        JOIN graph_edges ge ON gn.id = ge.from_id OR gn.id = ge.to_id
        WHERE gn.type = 'noun'
        GROUP BY gn.id
        ORDER BY total_weight DESC
        LIMIT ?
    """,
        (limit,),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def _format_section(
    fresh: list[dict],
    legacy: list[dict],
    graph_nodes: list[tuple[str, float]],
) -> str:
    lines = [SECTION_START, ""]

    # Graph nodes as keyword cloud
    if graph_nodes:
        node_strs = [n[0] for n in graph_nodes]
        lines.append(f"核語: {', '.join(node_strs)}")
        lines.append("")

    # Fresh full memories
    for i, m in enumerate(fresh[:FRESH_FULL]):
        content = m["content"]
        content_lines = content.split("\n")
        if len(content_lines) > 8:
            content = "\n".join(content_lines[:8]) + "\n..."
        lines.append(f"**[{i+1}]** {content}")
        lines.append("")

    # Fresh fragments
    if len(fresh) > FRESH_FULL:
        for m in fresh[FRESH_FULL : FRESH_FULL + FRESH_FRAGMENTS]:
            fragment = _extract_first_last(m["content"])
            lines.append(f"- {fragment}")
        lines.append("")

    # Legacy full memories
    offset = FRESH_FULL
    for i, m in enumerate(legacy[:LEGACY_FULL]):
        content = m["content"]
        content_lines = content.split("\n")
        if len(content_lines) > 8:
            content = "\n".join(content_lines[:8]) + "\n..."
        lines.append(f"**[{offset + i + 1}]** {content}")
        lines.append("")

    # Legacy fragments
    if len(legacy) > LEGACY_FULL:
        for m in legacy[LEGACY_FULL : LEGACY_FULL + LEGACY_FRAGMENTS]:
            fragment = _extract_first_last(m["content"])
            lines.append(f"- {fragment}")
        lines.append("")

    return "\n".join(lines)


def _update_memory_md(md_path: Path, section_text: str) -> None:
    if md_path.exists():
        content = md_path.read_text(encoding="utf-8")
    else:
        content = "# Embodied Claude - Memory\n\n"

    section_start_idx = content.find(SECTION_START)

    if section_start_idx >= 0:
        # 記憶の核セクションは常に MEMORY.md の末尾扱い.
        # 本文中に下位 "## 流れ" 等のヘッダがあると以前は途中で切っていたため
        # 古い核の続きが堆積するバグがあった. SECTION_START 以降は全置換する.
        content = content[:section_start_idx] + section_text
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += "\n" + section_text

    md_path.write_text(content, encoding="utf-8")
    logger.info(f"Updated MEMORY.md core section at {md_path}")
