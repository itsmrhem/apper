from langgraph.graph import END, START, StateGraph

from server.nodes.browser_render import browser_render_node
from server.state import GraphState


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("browser_render", browser_render_node)
    g.add_edge(START, "browser_render")
    g.add_edge("browser_render", END)
    return g.compile()
