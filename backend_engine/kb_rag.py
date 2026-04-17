from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


WORD_RE = re.compile(r"[a-zA-Z0-9_\-\+\.]+")


@dataclass
class Chunk:
    chunk_id: str
    text: str
    source: str
    section: str
    topic_tags: List[str]


class _HashEmbedding:
    """Deterministic local embedding to avoid model downloads in early phase.

    This keeps RAG runnable in constrained/offline environments while still
    allowing ChromaDB vector similarity retrieval.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        tokens = WORD_RE.findall(text.lower())
        if not tokens:
            return vec
        for token in tokens:
            h = int(hashlib.sha1(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = -1.0 if ((h >> 8) & 1) else 1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class DFTKnowledgeBase:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.kb_root = project_root / "knowledge_base"
        self.vector_dir = self.kb_root / "vector_store"
        self.meta_dir = self.kb_root / "metadata"
        self.chunks_dir = self.kb_root / "chunks"
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self._embedding = _HashEmbedding(dim=256)

        self._client = None
        self._collection = None

    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection

        try:
            import chromadb  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "chromadb is required for RAG. Install with: pip install chromadb"
            ) from exc

        self._client = chromadb.PersistentClient(path=str(self.vector_dir))
        self._collection = self._client.get_or_create_collection(
            name="dft_octopus_kb",
            metadata={"description": "DFT + Octopus knowledge base"},
        )
        return self._collection

    @staticmethod
    def chunk_markdown(text: str, source: str, topic_tags: Optional[List[str]] = None) -> List[Chunk]:
        tags = topic_tags or []
        lines = text.splitlines()

        chunks: List[Chunk] = []
        current_section = "root"
        buffer: List[str] = []
        section_idx = 0

        def flush():
            nonlocal section_idx, buffer
            body = "\n".join(buffer).strip()
            if not body:
                return
            section_idx += 1
            chunk_id = f"{source}:{section_idx}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=body,
                    source=source,
                    section=current_section,
                    topic_tags=tags,
                )
            )
            buffer = []

        for line in lines:
            if line.startswith("#"):
                flush()
                current_section = line.lstrip("#").strip() or "untitled"
                continue
            buffer.append(line)
            if len("\n".join(buffer)) > 1400:
                flush()

        flush()
        return chunks

    def ingest_markdown(self, source: str, text: str, topic_tags: Optional[List[str]] = None) -> Dict[str, int]:
        collection = self._ensure_collection()
        chunks = self.chunk_markdown(text=text, source=source, topic_tags=topic_tags)
        if not chunks:
            return {"chunks": 0}

        ids = [c.chunk_id for c in chunks]
        docs = [c.text for c in chunks]
        metadatas = [
            {
                "source": c.source,
                "section": c.section,
                "topic_tags": json.dumps(c.topic_tags, ensure_ascii=True),
            }
            for c in chunks
        ]
        embeddings = [self._embedding.embed(c.text) for c in chunks]

        existing = collection.get(ids=ids)
        existing_ids = set(existing.get("ids", [])) if existing else set()
        if existing_ids:
            keep = [i for i, cid in enumerate(ids) if cid not in existing_ids]
            ids = [ids[i] for i in keep]
            docs = [docs[i] for i in keep]
            metadatas = [metadatas[i] for i in keep]
            embeddings = [embeddings[i] for i in keep]

        if ids:
            collection.add(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)

        log_path = self.meta_dir / "ingestion_log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "source": source,
                        "added_chunks": len(ids),
                        "total_chunks_prepared": len(chunks),
                        "topic_tags": topic_tags or [],
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )

        return {"chunks": len(ids)}

    def query(self, query: str, top_k: int = 5, topic_tag: Optional[str] = None) -> Dict[str, object]:
        collection = self._ensure_collection()
        q_embedding = self._embedding.embed(query)

        where = None
        if topic_tag:
            where = {"topic_tags": {"$contains": topic_tag}}

        result = collection.query(
            query_embeddings=[q_embedding],
            n_results=max(1, min(top_k, 20)),
            where=where,
        )

        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        hits = []
        for doc, meta, dist in zip(docs, metas, dists):
            hits.append(
                {
                    "text": doc,
                    "source": (meta or {}).get("source", "unknown"),
                    "section": (meta or {}).get("section", "unknown"),
                    "distance": dist,
                }
            )

        return {"query": query, "top_k": top_k, "hits": hits}


def default_kb(project_root: Optional[Path] = None) -> DFTKnowledgeBase:
    root = project_root or Path(__file__).resolve().parents[1]
    return DFTKnowledgeBase(project_root=root)
