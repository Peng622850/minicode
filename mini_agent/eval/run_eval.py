"""评测入口脚本"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mini_agent.config import Config
from mini_agent import LLMClient
from mini_agent.agent import Agent
from mini_agent.schema import LLMProvider
from mini_agent.tools.bash_tool import BashOutputTool, BashKillTool, BashTool
from mini_agent.tools.file_tools import ReadTool, WriteTool, EditTool
from mini_agent.tools.note_tool import SessionNoteTool
from mini_agent.eval.benchmark import Benchmark


async def main():
    # 加载配置
    config = Config.load()

    # 初始化 LLM
    provider = LLMProvider.ANTHROPIC if config.llm.provider.lower() == "anthropic" else LLMProvider.OPENAI
    llm = LLMClient(
        api_key=config.llm.api_key,
        provider=provider,
        api_base=config.llm.api_base,
        model=config.llm.model,
    )

    # 初始化工具
    workspace = Path("./eval_workspace")
    workspace.mkdir(exist_ok=True)
    tools = [
        BashOutputTool(),
        BashKillTool(),
        BashTool(workspace_dir=str(workspace)),
        ReadTool(workspace_dir=str(workspace)),
        WriteTool(workspace_dir=str(workspace)),
        EditTool(workspace_dir=str(workspace)),
        SessionNoteTool(memory_file=str(workspace / ".agent_memory.json")),
    ]

    # 初始化 Agent
    agent = Agent(
        llm_client=llm,
        system_prompt="You are a helpful AI assistant that can complete coding and file tasks.",
        tools=tools,
        max_steps=20,
        workspace_dir=str(workspace),
    )

    # 运行评测
    benchmark = Benchmark()
    await benchmark.run(agent, llm)


if __name__ == "__main__":
    asyncio.run(main())