from langgraph.graph import END, START, StateGraph

from server.nodes.browser_render import browser_render_node
from server.nodes.job_details_json import job_details_json_node

from server.nodes.parse_job_links import parse_job_links_node
from server.state import GraphState
from server.tracing import configure_langsmith


def build_graph(*, with_job_details: bool = False):
    configure_langsmith()
    g = StateGraph(GraphState)
    g.add_node("browser_render", browser_render_node)
    g.add_edge(START, "browser_render")

    if with_job_details:
        g.add_node("parse_job_links", parse_job_links_node)
        g.add_node("job_details_json", job_details_json_node)
        g.add_edge("browser_render", "parse_job_links")
        g.add_edge("parse_job_links", "job_details_json")
        g.add_edge("job_details_json", END)
    else:
        g.add_edge("browser_render", END)

    return g.compile()
