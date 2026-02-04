"""Tests for memory/graph_store.py edge cases - Coverage additions.

This file tests edge cases not covered in test_memory_graph_store.py:
- traverse() with max_depth=0 (should return only seed node)
- traverse() with disconnected nodes
- find_path() when no path exists (already covered but extended here)
- store_embedding / delete_embedding / is_embedding_stale basics
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create isolated data directory for play_db."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    # Close any existing connection before test
    import reos.play_db as play_db
    play_db.close_connection()

    yield data_dir

    # Cleanup after test
    play_db.close_connection()


@pytest.fixture
def initialized_db(temp_data_dir: Path):
    """Initialize the database and return the play_db module."""
    import reos.play_db as play_db

    play_db.init_db()
    return play_db


@pytest.fixture
def graph_store(initialized_db):
    """Create a MemoryGraphStore with initialized database."""
    from reos.memory.graph_store import MemoryGraphStore

    return MemoryGraphStore()


@pytest.fixture
def test_act(initialized_db) -> str:
    """Create a test act and return its ID."""
    _, act_id = initialized_db.create_act(title="Test Act")
    return act_id


@pytest.fixture
def test_blocks(test_act: str, initialized_db) -> list[str]:
    """Create test blocks and return their IDs."""
    from reos.play.blocks_db import create_block

    block_ids = []
    for i in range(5):
        block = create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": f"Test block {i}"}],
        )
        block_ids.append(block.id)

    return block_ids


# =============================================================================
# Graph Traversal Edge Cases
# =============================================================================


class TestTraverseEdgeCases:
    """Test edge cases for graph traversal."""

    def test_traverse_max_depth_zero(self, graph_store, test_blocks) -> None:
        """traverse() with max_depth=0 returns only the seed node."""
        from reos.memory.relationships import RelationshipType

        # Create a chain: block_0 -> block_1 -> block_2
        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )
        graph_store.create_relationship(
            test_blocks[1], test_blocks[2], RelationshipType.REFERENCES
        )

        # Traverse with max_depth=0
        result = graph_store.traverse(test_blocks[0], max_depth=0)

        # Should only contain the starting node
        assert result.start_block_id == test_blocks[0]
        assert len(result.visited_blocks) == 1
        assert test_blocks[0] in result.visited_blocks
        assert test_blocks[1] not in result.visited_blocks
        assert test_blocks[2] not in result.visited_blocks

        # Should have the seed node at depth 0
        assert result.blocks_by_depth[0] == [test_blocks[0]]
        assert 1 not in result.blocks_by_depth

        # Should have no edges (didn't traverse beyond start)
        assert len(result.edges) == 0

    def test_traverse_disconnected_nodes(self, graph_store, test_blocks) -> None:
        """traverse() doesn't find disconnected nodes."""
        from reos.memory.relationships import RelationshipType

        # Create two separate components:
        # Component 1: block_0 -> block_1
        # Component 2: block_2 -> block_3
        # block_4 is isolated

        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )
        graph_store.create_relationship(
            test_blocks[2], test_blocks[3], RelationshipType.REFERENCES
        )

        # Traverse from block_0
        result = graph_store.traverse(test_blocks[0], max_depth=5)

        # Should only find connected component
        assert test_blocks[0] in result.visited_blocks
        assert test_blocks[1] in result.visited_blocks

        # Should not find disconnected nodes
        assert test_blocks[2] not in result.visited_blocks
        assert test_blocks[3] not in result.visited_blocks
        assert test_blocks[4] not in result.visited_blocks

    def test_traverse_disconnected_graph_from_isolated_node(
        self, graph_store, test_blocks
    ) -> None:
        """traverse() from isolated node returns only that node."""
        from reos.memory.relationships import RelationshipType

        # Create relationships between other blocks
        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )

        # Traverse from isolated block_4
        result = graph_store.traverse(test_blocks[4], max_depth=5)

        # Should only contain the starting node
        assert len(result.visited_blocks) == 1
        assert test_blocks[4] in result.visited_blocks
        assert len(result.edges) == 0

    def test_find_path_no_connection(self, graph_store, test_blocks) -> None:
        """find_path() returns None when nodes are in different components."""
        from reos.memory.relationships import RelationshipType

        # Create two disconnected components
        # Component 1: block_0 -> block_1
        # Component 2: block_2 -> block_3
        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )
        graph_store.create_relationship(
            test_blocks[2], test_blocks[3], RelationshipType.REFERENCES
        )

        # Try to find path between disconnected components
        path = graph_store.find_path(test_blocks[0], test_blocks[2], max_depth=10)

        assert path is None

    def test_find_path_from_isolated_node(self, graph_store, test_blocks) -> None:
        """find_path() returns None from an isolated node."""
        from reos.memory.relationships import RelationshipType

        # Create a connection not involving block_4
        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )

        # Try to find path from isolated node
        path = graph_store.find_path(test_blocks[4], test_blocks[0], max_depth=10)

        assert path is None

    def test_find_path_to_isolated_node(self, graph_store, test_blocks) -> None:
        """find_path() returns None to an isolated node."""
        from reos.memory.relationships import RelationshipType

        # Create a connection not involving block_4
        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )

        # Try to find path to isolated node
        path = graph_store.find_path(test_blocks[0], test_blocks[4], max_depth=10)

        assert path is None


# =============================================================================
# Embedding Storage Edge Cases
# =============================================================================


class TestEmbeddingStorageBasics:
    """Test basic embedding storage functionality (complementing existing tests)."""

    def test_store_embedding_basic(self, graph_store, test_blocks) -> None:
        """store_embedding stores embedding with correct parameters."""
        embedding_vec = np.random.randn(384).astype(np.float32)
        embedding_bytes = embedding_vec.tobytes()

        result = graph_store.store_embedding(
            block_id=test_blocks[0],
            embedding=embedding_bytes,
            content_hash="test_hash_123",
            model_name="test-model-v1",
        )

        assert result is True

        # Verify stored
        retrieved = graph_store.get_embedding(test_blocks[0])
        assert retrieved is not None
        retrieved_embedding, retrieved_hash = retrieved
        assert retrieved_embedding == embedding_bytes
        assert retrieved_hash == "test_hash_123"

    def test_store_embedding_default_model(self, graph_store, test_blocks) -> None:
        """store_embedding uses default model name when not specified."""
        embedding_bytes = np.random.randn(384).astype(np.float32).tobytes()

        result = graph_store.store_embedding(
            block_id=test_blocks[0],
            embedding=embedding_bytes,
            content_hash="hash",
        )

        assert result is True
        # The embedding should be stored (model name is internal)

    def test_delete_embedding_basic(self, graph_store, test_blocks) -> None:
        """delete_embedding removes the embedding."""
        embedding_bytes = np.random.randn(384).astype(np.float32).tobytes()

        # Store
        graph_store.store_embedding(test_blocks[0], embedding_bytes, "hash1")

        # Verify it exists
        assert graph_store.get_embedding(test_blocks[0]) is not None

        # Delete
        result = graph_store.delete_embedding(test_blocks[0])
        assert result is True

        # Verify it's gone
        assert graph_store.get_embedding(test_blocks[0]) is None

    def test_delete_embedding_nonexistent(self, graph_store, test_blocks) -> None:
        """delete_embedding returns False for nonexistent embedding."""
        result = graph_store.delete_embedding(test_blocks[0])
        assert result is False

    def test_is_embedding_stale_missing_embedding(self, graph_store, test_blocks) -> None:
        """is_embedding_stale returns True when embedding doesn't exist."""
        result = graph_store.is_embedding_stale(test_blocks[0], "any_hash")
        assert result is True

    def test_is_embedding_stale_hash_match(self, graph_store, test_blocks) -> None:
        """is_embedding_stale returns False when hash matches."""
        embedding_bytes = np.random.randn(384).astype(np.float32).tobytes()

        graph_store.store_embedding(test_blocks[0], embedding_bytes, "matching_hash")

        result = graph_store.is_embedding_stale(test_blocks[0], "matching_hash")
        assert result is False

    def test_is_embedding_stale_hash_mismatch(self, graph_store, test_blocks) -> None:
        """is_embedding_stale returns True when hash differs."""
        embedding_bytes = np.random.randn(384).astype(np.float32).tobytes()

        graph_store.store_embedding(test_blocks[0], embedding_bytes, "old_hash")

        result = graph_store.is_embedding_stale(test_blocks[0], "new_hash")
        assert result is True

    def test_store_and_retrieve_multiple_embeddings(
        self, graph_store, test_blocks
    ) -> None:
        """Can store and retrieve embeddings for multiple blocks."""
        embeddings = {}

        # Store embeddings for first 3 blocks
        for i in range(3):
            embedding = np.random.randn(384).astype(np.float32).tobytes()
            embeddings[test_blocks[i]] = embedding
            graph_store.store_embedding(
                test_blocks[i], embedding, f"hash_{i}"
            )

        # Retrieve and verify
        for i in range(3):
            retrieved = graph_store.get_embedding(test_blocks[i])
            assert retrieved is not None
            retrieved_embedding, retrieved_hash = retrieved
            assert retrieved_embedding == embeddings[test_blocks[i]]
            assert retrieved_hash == f"hash_{i}"

    def test_embedding_update_changes_hash(self, graph_store, test_blocks) -> None:
        """Updating an embedding changes its content hash."""
        embedding1 = np.random.randn(384).astype(np.float32).tobytes()
        embedding2 = np.random.randn(384).astype(np.float32).tobytes()

        # Store first version
        graph_store.store_embedding(test_blocks[0], embedding1, "hash_v1")
        result1 = graph_store.get_embedding(test_blocks[0])
        assert result1[1] == "hash_v1"

        # Update with new version
        graph_store.store_embedding(test_blocks[0], embedding2, "hash_v2")
        result2 = graph_store.get_embedding(test_blocks[0])
        assert result2[1] == "hash_v2"
        assert result2[0] == embedding2


# =============================================================================
# Combined Edge Cases
# =============================================================================


class TestCombinedEdgeCases:
    """Test combinations of graph operations and embeddings."""

    def test_traverse_and_check_embeddings(self, graph_store, test_blocks) -> None:
        """Can traverse graph and check which nodes have embeddings."""
        from reos.memory.relationships import RelationshipType

        # Create relationships
        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )
        graph_store.create_relationship(
            test_blocks[1], test_blocks[2], RelationshipType.REFERENCES
        )

        # Store embeddings for some blocks
        embedding = np.random.randn(384).astype(np.float32).tobytes()
        graph_store.store_embedding(test_blocks[0], embedding, "hash0")
        graph_store.store_embedding(test_blocks[2], embedding, "hash2")
        # test_blocks[1] has no embedding

        # Traverse
        result = graph_store.traverse(test_blocks[0], max_depth=2)

        # Check embeddings for visited blocks
        blocks_with_embeddings = []
        for block_id in result.visited_blocks:
            if graph_store.get_embedding(block_id) is not None:
                blocks_with_embeddings.append(block_id)

        assert test_blocks[0] in blocks_with_embeddings
        assert test_blocks[2] in blocks_with_embeddings
        assert test_blocks[1] not in blocks_with_embeddings

    def test_delete_block_relationships_and_embedding(
        self, graph_store, test_blocks
    ) -> None:
        """Can delete both relationships and embedding for a block."""
        from reos.memory.relationships import RelationshipType

        # Create relationships
        graph_store.create_relationship(
            test_blocks[0], test_blocks[1], RelationshipType.REFERENCES
        )
        graph_store.create_relationship(
            test_blocks[1], test_blocks[2], RelationshipType.REFERENCES
        )

        # Store embedding
        embedding = np.random.randn(384).astype(np.float32).tobytes()
        graph_store.store_embedding(test_blocks[1], embedding, "hash")

        # Delete relationships for block 1
        rel_count = graph_store.delete_relationships_for_block(test_blocks[1])
        assert rel_count == 2

        # Delete embedding for block 1
        emb_deleted = graph_store.delete_embedding(test_blocks[1])
        assert emb_deleted is True

        # Verify cleanup
        assert len(graph_store.get_relationships(test_blocks[1])) == 0
        assert graph_store.get_embedding(test_blocks[1]) is None

    def test_traverse_with_no_edges_at_all(self, graph_store, test_blocks) -> None:
        """traverse() works correctly when there are no edges in the graph."""
        # Don't create any relationships

        result = graph_store.traverse(test_blocks[0], max_depth=3)

        # Should only contain the start node
        assert len(result.visited_blocks) == 1
        assert test_blocks[0] in result.visited_blocks
        assert len(result.edges) == 0
        assert result.blocks_by_depth == {0: [test_blocks[0]]}
