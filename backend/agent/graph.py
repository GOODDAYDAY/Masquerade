"""LangGraph workflow definition for player decision-making.

The graph orchestrates three nodes:
  Thinker → Evaluator → (retry?) → Optimizer → END

Each node is an async function that reads/writes to the shared AgentState.
"""

from functools import partial

from langgraph.graph import END, StateGraph

from backend.agent.llm_client import LLMClient
from backend.agent.nodes.evaluator import evaluator_node, should_retry
from backend.agent.nodes.optimizer import optimizer_node
from backend.agent.nodes.thinker import thinker_node
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.graph")


def build_player_graph(llm_client: LLMClient) -> StateGraph:
    """Build and compile the player decision LangGraph.

    Nodes receive the llm_client via functools.partial so the graph
    definition stays clean and testable.
    """
    graph = StateGraph(AgentState)

    # Bind llm_client to each node function
    graph.add_node("thinker", partial(thinker_node, llm_client=llm_client))
    graph.add_node("evaluator", partial(evaluator_node, llm_client=llm_client))
    graph.add_node("optimizer", partial(optimizer_node, llm_client=llm_client))

    # Entry point
    graph.set_entry_point("thinker")

    # Thinker → Evaluator (always)
    graph.add_edge("thinker", "evaluator")

    # Evaluator → conditional: retry thinker or proceed to optimizer
    graph.add_conditional_edges(
        "evaluator",
        should_retry,
        {
            "retry": "thinker",
            "proceed": "optimizer",
        },
    )

    # Optimizer → END
    graph.add_edge("optimizer", END)

    logger.info("Player decision graph built successfully")
    return graph.compile()
