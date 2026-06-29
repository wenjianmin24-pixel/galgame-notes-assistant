"""全量 transcript 向量索引 — 文本分块 + embedding + 余弦检索。

增量同步：只在有新行时对新文本做 embedding，不重复索引旧内容。
"""
import math
from typing import Optional


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """纯 Python 余弦相似度，无外部依赖。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class TranscriptIndex:
    """全量台词的内存向量索引。

    - 分块：每 CHUNK_LINES 条台词一组，重叠 OVERLAP_LINES 条
    - 增量：只对上次索引之后的新行做 embedding
    - 检索：余弦相似度 top-k
    """

    CHUNK_LINES = 8
    OVERLAP_LINES = 2

    def __init__(self, llm_client, embed_model: str):
        self.llm = llm_client
        self.embed_model = embed_model
        self._chunks: list[str] = []         # 文本块
        self._vectors: list[list[float]] = [] # 对应向量
        self._indexed_line_count = 0

    def reconfigure(self, llm_client, embed_model):
        """热更新 embedding 客户端和模型。模型变了需 force 重建索引。"""
        model_changed = embed_model != self.embed_model
        self.llm = llm_client
        self.embed_model = embed_model
        if model_changed:
            # 模型变了，旧向量失效，标记需重建
            self._chunks.clear()
            self._vectors.clear()
            self._indexed_line_count = 0

    # ── 索引构建 ────────────────────────────────────────

    def ensure_synced(self, transcript: str, force: bool = False):
        """增量同步：为新行做分块和 embedding。

        支持 force=True 强制全量重建（测试 / 模型切换后）。
        """
        lines = [l.strip() for l in transcript.splitlines() if l.strip()]
        if force:
            self._chunks.clear()
            self._vectors.clear()
            self._indexed_line_count = 0

        if len(lines) <= self._indexed_line_count:
            return

        new_lines = lines[self._indexed_line_count:]
        new_chunks = self._chunkify(new_lines)

        if not new_chunks:
            self._indexed_line_count = len(lines)
            return

        # 批量 embedding
        vectors = self.llm.embed_batch(new_chunks, self.embed_model)
        self._chunks.extend(new_chunks)
        self._vectors.extend(vectors)
        self._indexed_line_count = len(lines)

    def _chunkify(self, lines: list[str]) -> list[str]:
        """将台词行列表按固定大小 + 重叠分割为文本块。"""
        chunks = []
        step = max(self.CHUNK_LINES - self.OVERLAP_LINES, 1)
        pos = 0
        while pos < len(lines):
            chunk_lines = lines[pos:pos + self.CHUNK_LINES]
            chunks.append("\n".join(chunk_lines))
            pos += step
        return chunks

    # ── 检索 ────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> list[str]:
        """返回与 query 最相似的 top_k 个文本块（按相似度降序）。"""
        if not self._chunks:
            return []

        q_vec = self.llm.embed(query, self.embed_model)
        scored = [
            (_cosine_sim(q_vec, v), c)
            for v, c in zip(self._vectors, self._chunks)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for s, c in scored[:top_k] if s > 0.15]

    def is_empty(self) -> bool:
        return len(self._chunks) == 0
