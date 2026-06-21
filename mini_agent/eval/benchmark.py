"""
Benchmark 评测模块

自动跑任务集，统计：
- pass_rate: 完成率
- tool_rounds: 平均工具调用轮数
- avg_latency: 平均耗时
- category_stats: 按类别统计
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import Agent
    from ..llm import LLMClient
    from ..schema import Message

JUDGE_PROMPT = """你是一个评测 AI Agent 任务完成质量的评判员。

任务要求：
{task}

Agent 的回复：
{response}

判断标准：
- Agent 执行了工具操作且操作结果符合任务要求 → PASS
- Agent 给出了任务要求的具体信息或数据 → PASS
- 以下情况判 FAIL：
  - Agent 报错且没有恢复
  - Agent 只描述了计划但没有实际执行工具
  - Agent 执行了操作但结果明显不符合任务要求
  - Agent 的回复与任务要求完全无关

输出严格 JSON 格式，不要任何其他内容：
{{
  "verdict": "PASS" 或 "FAIL",
  "verifier_reason": "判断理由，一句话",
  "failure_category": "若PASS则填null，若FAIL则从以下选一个：tool_error/llm_misunderstanding/timeout/incomplete"
}}"""


@dataclass
class TaskResult:
    task_id: str
    category: str
    task: str
    passed: bool
    tool_rounds: int
    latency: float
    response: str
    tool_trace: List[str] = field(default_factory=list)      # 新增
    verifier_reason: str = ""                                  # 新增
    failure_category: Optional[str] = None                    # 新增
    error: Optional[str] = None


@dataclass
class BenchmarkReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    avg_latency: float = 0.0
    avg_tool_rounds: float = 0.0
    pass_rate: float = 0.0
    category_stats: dict = field(default_factory=dict)
    results: List[TaskResult] = field(default_factory=list)


class Benchmark:

    def __init__(
            self,
            tasks_file: str = None,
            output_dir: str = "./eval_results",
    ):
        if tasks_file is None:
            tasks_file = str(Path(__file__).parent / "tasks.json")

        self.tasks = json.loads(Path(tasks_file).read_text(encoding="utf-8"))
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def _judge(self, task: str, response: str, llm: "LLMClient") -> tuple[bool, str, Optional[str]]:
        """LLM-as-Judge，返回 (passed, verifier_reason, failure_category)"""
        from ..schema import Message
        try:
            prompt = JUDGE_PROMPT.format(task=task, response=response)
            result = await llm.generate(messages=[
                Message(role="user", content=prompt)
            ])
            text = result.content.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            passed = data.get("verdict", "FAIL").upper() == "PASS"
            reason = data.get("verifier_reason", "")
            fail_cat = data.get("failure_category", None)
            return passed, reason, fail_cat
        except Exception as e:
            return False, f"Judge解析失败: {e}", "tool_error"

    async def run(self, agent: "Agent", llm: "LLMClient", task_ids: List[str] = None) -> BenchmarkReport:
        """
        运行评测

        Args:
            agent: Agent 实例
            llm: LLM 客户端（用于 Judge）
            task_ids: 指定运行哪些任务，None 表示全部
        """
        tasks = self.tasks
        if task_ids:
            tasks = [t for t in tasks if t["id"] in task_ids]

        results = []
        print(f"\n{'=' * 60}")
        print(f"🧪 开始评测，共 {len(tasks)} 个任务")
        print(f"{'=' * 60}\n")

        for i, task_def in enumerate(tasks):
            task_id = task_def["id"]
            task_text = task_def["task"]
            category = task_def["category"]

            print(f"[{i + 1}/{len(tasks)}] {task_id}: {task_text[:40]}...")

            # 重置 agent 消息历史（保留 system prompt）
            agent.messages = [agent.messages[0]]
            # 关闭安全审批（评测时自动放行）
            agent.safety_guard.auto_approve = True

            start = time.time()
            tool_rounds = 0

            try:
                agent.add_user_message(task_text)
                response = await agent.run()
                latency = time.time() - start

                # 统计工具调用轮数和 tool_trace
                tool_rounds = sum(1 for m in agent.messages if m.role == "tool")
                tool_trace = [
                    m.name for m in agent.messages
                    if m.role == "tool" and hasattr(m, 'name') and m.name
                ]

                # LLM-as-Judge
                passed, reason, fail_cat = await self._judge(task_text, response, llm)

                result = TaskResult(
                    task_id=task_id,
                    category=category,
                    task=task_text,
                    passed=passed,
                    tool_rounds=tool_rounds,
                    latency=latency,
                    response=response[:500],
                    tool_trace=tool_trace,
                    verifier_reason=reason,
                    failure_category=fail_cat,
                )

                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"  {status} | {latency:.1f}s | {tool_rounds}轮 | {reason[:40]}")

            except Exception as e:
                latency = time.time() - start
                result = TaskResult(
                    task_id=task_id,
                    category=category,
                    task=task_text,
                    passed=False,
                    tool_rounds=tool_rounds,
                    latency=latency,
                    response="",
                    error=str(e),
                )
                print(f"  💥 ERROR: {e}")

            results.append(result)
            # 任务间稍作等待，避免 API 限流
            await asyncio.sleep(1)

        # 关闭自动审批
        agent.safety_guard.auto_approve = False

        return self._generate_report(results)

    def _generate_report(self, results: List[TaskResult]) -> BenchmarkReport:
        """生成评测报告"""
        report = BenchmarkReport()
        report.total = len(results)
        report.results = results
        report.passed = sum(1 for r in results if r.passed)
        report.failed = report.total - report.passed
        report.pass_rate = report.passed / report.total if report.total else 0
        report.avg_latency = sum(r.latency for r in results) / len(results) if results else 0
        report.avg_tool_rounds = sum(r.tool_rounds for r in results) / len(results) if results else 0

        # 按类别统计
        categories = {}
        for r in results:
            if r.category not in categories:
                categories[r.category] = {"total": 0, "passed": 0}
            categories[r.category]["total"] += 1
            if r.passed:
                categories[r.category]["passed"] += 1

        for cat, stats in categories.items():
            stats["pass_rate"] = stats["passed"] / stats["total"]
        report.category_stats = categories

        # 打印报告
        self._print_report(report)

        # 保存报告
        self._save_report(report)

        return report

    def _print_report(self, report: BenchmarkReport):
        print(f"\n{'=' * 60}")
        print(f"📊 评测报告")
        print(f"{'=' * 60}")
        print(f"总任务数:     {report.total}")
        print(f"通过:         {report.passed}")
        print(f"失败:         {report.failed}")
        print(f"完成率:       {report.pass_rate:.1%}")
        print(f"平均耗时:     {report.avg_latency:.1f}s")
        print(f"平均工具轮数: {report.avg_tool_rounds:.1f}")
        print(f"\n按类别统计:")
        for cat, stats in report.category_stats.items():
            print(f"  {cat}: {stats['passed']}/{stats['total']} ({stats['pass_rate']:.1%})")
        print(f"{'=' * 60}\n")

    def _save_report(self, report: BenchmarkReport):
        data = {
            "summary": {
                "total": report.total,
                "passed": report.passed,
                "failed": report.failed,
                "pass_rate": report.pass_rate,
                "avg_latency": report.avg_latency,
                "avg_tool_rounds": report.avg_tool_rounds,
            },
            "category_stats": report.category_stats,
            "results": [
                {
                    "task_id": r.task_id,
                    "category": r.category,
                    "task": r.task,
                    "passed": r.passed,
                    "tool_rounds": r.tool_rounds,
                    "latency": r.latency,
                    "tool_trace": r.tool_trace,
                    "verifier_reason": r.verifier_reason,
                    "failure_category": r.failure_category,
                    "error": r.error,
                }
                for r in report.results
            ]
        }

        # 版本回归对比
        existing = sorted(self.output_dir.glob("benchmark_*.json"))
        if existing:
            try:
                prev = json.loads(existing[-1].read_text(encoding="utf-8"))
                prev_rate = prev["summary"]["pass_rate"]
                delta = report.pass_rate - prev_rate
                symbol = "📈" if delta >= 0 else "📉"
                print(f"{symbol} 版本对比: {prev_rate:.1%} → {report.pass_rate:.1%} ({delta:+.1%})")
                data["regression"] = {
                    "prev_pass_rate": prev_rate,
                    "delta": delta,
                }
            except Exception:
                pass

        output_file = self.output_dir / f"benchmark_{int(time.time())}.json"
        output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📁 报告已保存: {output_file}")