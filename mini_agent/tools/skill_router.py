"""
SkillRouter - 两阶段 Skill 召回路由

原项目问题：15 个 Skill 元信息全量注入 system prompt，Token 浪费。
改造目标：用 TF-IDF embedding 做相似度召回，只把最相关的 Top-K 注入 prompt。
"""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    from .skill_loader import Skill, SkillLoader


@dataclass
class SkillMeta:
    name: str
    description: str
    task_types: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    example_queries: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    return re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]', text)


def _tf_idf_vector(text: str, vocab: Dict[str, int], idf: Dict[str, float]) -> List[float]:
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * len(vocab)
    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    total = len(tokens)
    for t in tf:
        tf[t] /= total
    vec = [0.0] * len(vocab)
    for t, idx in vocab.items():
        if t in tf:
            vec[idx] = tf[t] * idf.get(t, 1.0)
    return vec


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SkillRouter:
    def __init__(self, skill_loader: "SkillLoader", top_n: int = 5, top_k: int = 3, index_cache: Optional[str] = None):
        self.skill_loader = skill_loader
        self.top_n = top_n
        self.top_k = top_k
        self.index_cache = Path(index_cache) if index_cache else None
        self.metas: List[SkillMeta] = []
        self.metas: List[SkillMeta] = []
        self._index_built = False
        self._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        self.keyword_map = {
            "word": ["docx", "document", "editing"],
            "文档": ["docx", "document", "word", "editing"],
            "doc": ["docx", "document"],
            "ppt": ["pptx", "presentation", "slides"],
            "幻灯片": ["pptx", "slides", "presentation"],
            "演示": ["pptx", "slides", "presentation"],
            "表格": ["xlsx", "excel", "spreadsheet"],
            "excel": ["xlsx", "spreadsheet"],
            "pdf": ["pdf", "document", "reportlab"],
            "图片": ["image", "canvas", "design"],
            "设计": ["canvas", "design", "brand"],
            "测试": ["testing", "webapp", "automation"],
            "网页": ["webapp", "testing", "html"],
            "gif": ["slack", "gif", "animation"],
            "动图": ["slack", "gif", "animation"],
        }

    def build_index(self) -> None:
        skills = list(self.skill_loader.loaded_skills.values())
        if not skills:
            return
        if self.index_cache and self.index_cache.exists():
            self._load_cache()
            if self.metas:
                self._index_built = True
                return
        self.metas = [self._build_meta(s) for s in skills]
        texts = [self._meta_to_text(m) for m in self.metas]
        embeddings = self._model.encode(texts, normalize_embeddings=True).tolist()
        for meta, emb in zip(self.metas, embeddings):
            meta.embedding = emb
        self._index_built = True
        if self.index_cache:
            self._save_cache()
        print(f"✅ SkillRouter: indexed {len(self.metas)} skills (bge embedding)")

    def _build_meta(self, skill: "Skill") -> SkillMeta:
        task_types, domains, keywords, examples = [], [], [], []
        if skill.metadata:
            task_types = [t.strip() for t in skill.metadata.get("task_types", "").split(",") if t.strip()]
            domains = [d.strip() for d in skill.metadata.get("domains", "").split(",") if d.strip()]
            keywords = [k.strip() for k in skill.metadata.get("keywords", "").split(",") if k.strip()]
            raw = skill.metadata.get("example_queries", "")
            examples = [e.strip() for e in raw.split("|") if e.strip()]
        if not keywords:
            keywords = _tokenize(skill.name + " " + skill.description)[:10]
        return SkillMeta(name=skill.name, description=skill.description,
                         task_types=task_types, domains=domains,
                         keywords=keywords, example_queries=examples)

    def _meta_to_text(self, meta: SkillMeta) -> str:
        parts = [meta.name, meta.description, " ".join(meta.task_types),
                 " ".join(meta.domains), " ".join(meta.keywords), " ".join(meta.example_queries)]
        return " ".join(p for p in parts if p)

    def _build_vocab_and_idf(self, docs: List[str]) -> None:
        n = len(docs)
        df: Dict[str, int] = {}
        for doc in docs:
            for t in set(_tokenize(doc)):
                df[t] = df.get(t, 0) + 1
        self.vocab = {term: idx for idx, (term, _) in enumerate(sorted(df.items(), key=lambda x: -x[1]))}
        self.idf = {term: math.log(n / freq + 1e-9) for term, freq in df.items()}

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Tuple[SkillMeta, float]]:
        if not self._index_built:
            self.build_index()
        if not self.metas:
            return []
        k = top_k or self.top_k
        query_emb = self._model.encode([query], normalize_embeddings=True)[0].tolist()
        scores = [(meta, _cosine(query_emb, meta.embedding)) for meta in self.metas if meta.embedding]
        scores.sort(key=lambda x: -x[1])
        return scores[:k]

    def _expand_query(self, query: str) -> str:
        """关键词扩展：把中文/缩写映射到 Skill 元信息里的英文词"""
        tokens = _tokenize(query)
        extra = []
        for t in tokens:
            if t in self.keyword_map:
                extra.extend(self.keyword_map[t])
        return query + " " + " ".join(extra)

    def retrieve_names(self, query: str, top_k: Optional[int] = None) -> List[str]:
        return [meta.name for meta, _ in self.retrieve(query, top_k)]

    def build_prompt(self, results: List[Tuple[SkillMeta, float]]) -> str:
        if not results:
            return ""
        lines = ["## Available Skills (top matches for current task)\n",
                 "Load full content using `get_skill` when needed.\n"]
        for meta, score in results:
            lines.append(f"- `{meta.name}`: {meta.description}  _(relevance: {score:.2f})_")
        return "\n".join(lines)

    def build_full_prompt(self) -> str:
        if not self.metas:
            return ""
        lines = ["## Available Skills\n", "Load full content using `get_skill` when needed.\n"]
        for meta in self.metas:
            lines.append(f"- `{meta.name}`: {meta.description}")
        return "\n".join(lines)

    def _save_cache(self) -> None:
        try:
            data = {"vocab": self.vocab, "idf": self.idf,
                    "metas": [{"name": m.name, "description": m.description,
                               "task_types": m.task_types, "domains": m.domains,
                               "keywords": m.keywords, "example_queries": m.example_queries,
                               "embedding": m.embedding} for m in self.metas]}
            self.index_cache.parent.mkdir(parents=True, exist_ok=True)
            self.index_cache.write_text(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            print(f"⚠️  SkillRouter cache save failed: {e}")

    def _load_cache(self) -> None:
        try:
            data = json.loads(self.index_cache.read_text())
            self.vocab = data["vocab"]
            self.idf = data["idf"]
            self.metas = [SkillMeta(**{k: v for k, v in m.items()}) for m in data["metas"]]
            print(f"✅ SkillRouter: loaded from cache ({len(self.metas)} skills)")
        except Exception as e:
            print(f"⚠️  SkillRouter cache load failed: {e}")
            self.metas = []