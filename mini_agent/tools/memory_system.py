"""
自进化记忆沉淀系统

三类记忆：
- procedural: Agent 解决问题的步骤经验
- episodic:   发生了什么事
- profile:    用户偏好和画像

流程：任务结束 → LLM提炼 → 分类存储 → 下次启动注入
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from sentence_transformers import SentenceTransformer
import numpy as np

if TYPE_CHECKING:
    from ..schema import Message
    from ..llm import LLMClient


MEMORY_FILE = Path.home() / ".mini-agent" / "memory" / "memories.json"

DISTILL_PROMPT = """请从以下对话中提炼值得记住的信息，分三类输出，每类最多3条，每条不超过50字。

对话内容：
{conversation}

输出格式（严格JSON，不要加任何其他内容）：
{{
  "procedural": ["Agent解决问题的步骤经验，如安装了什么包、用了什么方法"],
  "episodic": ["发生了什么事，完成了什么任务"],
  "profile": ["用户偏好、习惯、背景信息"]
}}

注意：
- 没有值得记录的内容时，对应类别返回空数组
- 只记录有复用价值的信息，不记录无意义闲聊"""


class MemorySystem:

    def __init__(self, memory_file: Path = MEMORY_FILE):
        self.memory_file = memory_file
        self.memories: dict = {"procedural": [], "episodic": [], "profile": []}
        self._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        self._load()

    def _load(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    self.memories = json.load(f)
            except Exception:
                pass

    def _save(self):
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.memories, f, ensure_ascii=False, indent=2)

    async def distill_and_save(self, messages: List["Message"], llm: "LLMClient"):
        """任务结束后调用，提炼记忆并存储"""
        from ..schema import Message as Msg

        # 拼对话内容（跳过 system prompt）
        conversation = ""
        for msg in messages:
            if msg.role == "system":
                continue
            if msg.role == "user":
                conversation += f"用户: {msg.content}\n"
            elif msg.role == "assistant" and msg.content:
                conversation += f"Assistant: {msg.content}\n"

        if not conversation.strip():
            return

        try:
            response = await llm.generate(messages=[
                Msg(role="user", content=DISTILL_PROMPT.format(conversation=conversation))
            ])

            text = response.content.strip()
            # 去掉可能的 markdown 代码块
            text = text.replace("```json", "").replace("```", "").strip()
            extracted = json.loads(text)

            changed = False
            for memory_type in ["procedural", "episodic", "profile"]:
                items = extracted.get(memory_type, [])
                for item in items:
                    if item and not self._is_duplicate(item, memory_type):
                        self.memories[memory_type].append({
                            "id": str(uuid.uuid4())[:8],
                            "content": item,
                            "created_at": datetime.now().isoformat(),
                        })
                        changed = True

                # 每类最多保留20条，超出时淘汰最旧的
                if len(self.memories[memory_type]) > 20:
                    self.memories[memory_type] = self.memories[memory_type][-20:]

            if changed:
                self._save()
                print(f"✅ 记忆已更新")

        except Exception as e:
            print(f"⚠️  记忆提炼失败: {e}")

    def _is_duplicate(self, new_content: str, memory_type: str) -> bool:
        """用 BGE 语义相似度判断是否重复"""
        items = self.memories[memory_type]
        if not items:
            return False

        new_emb = self._model.encode([new_content], normalize_embeddings=True)[0]
        existing_texts = [m["content"] for m in items]
        existing_embs = self._model.encode(existing_texts, normalize_embeddings=True)
        scores = existing_embs @ new_emb

        max_idx = scores.argmax()
        if scores[max_idx] > 0.7:  # 语义相似度超过0.7认为是同一类信息
            items[max_idx]["content"] = new_content  # 替换为最新版本
            return True
        return False

    def retrieve(self, query: str, top_k: int = 5) -> dict:
        """按查询语义召回相关记忆"""
        query_emb = self._model.encode([query], normalize_embeddings=True)[0]

        result = {"procedural": [], "episodic": [], "profile": []}

        for memory_type in ["procedural", "episodic", "profile"]:
            items = self.memories[memory_type]
            if not items:
                continue

            texts = [m["content"] for m in items]
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            scores = embeddings @ query_emb  # 余弦相似度

            # 取 Top-K
            top_indices = scores.argsort()[::-1][:top_k]
            result[memory_type] = [items[i] for i in top_indices if scores[i] > 0.3]

        return result

    def build_prompt_for_query(self, query: str) -> str:
        """按查询动态召回记忆生成 prompt（替代全量注入）"""
        recalled = self.retrieve(query)

        lines = []
        if recalled["profile"]:
            lines.append("## 用户画像")
            for m in recalled["profile"]:
                lines.append(f"- {m['content']}")

        if recalled["procedural"]:
            lines.append("\n## 经验记忆")
            for m in recalled["procedural"]:
                lines.append(f"- {m['content']}")

        if recalled["episodic"]:
            lines.append("\n## 历史任务")
            for m in recalled["episodic"]:
                lines.append(f"- {m['content']}")

        if not lines:
            return ""

        return "## 长期记忆\n" + "\n".join(lines)

    def build_prompt(self) -> str:
        """生成全量记忆 prompt，启动时注入"""
        lines = []

        if self.memories["profile"]:
            lines.append("## 用户画像")
            for m in self.memories["profile"]:
                lines.append(f"- {m['content']}")

        if self.memories["procedural"]:
            lines.append("\n## 经验记忆")
            for m in self.memories["procedural"]:
                lines.append(f"- {m['content']}")

        if self.memories["episodic"]:
            lines.append("\n## 历史任务")
            for m in self.memories["episodic"][-5:]:
                lines.append(f"- {m['content']}")

        if not lines:
            return ""

        return "## 长期记忆\n" + "\n".join(lines)