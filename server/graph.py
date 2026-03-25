from langgraph.graph import END, START, StateGraph

from server.nodes.application import (
    compile_cover_pdfs_node,
    compile_resume_pdfs_node,
    generate_cover_texes_node,
    generate_resume_texes_node,
    load_application_sources_node,
)
from server.nodes.browser_render import browser_render_node
from server.nodes.job_details_json import job_details_json_node
from server.nodes.parse_job_links import parse_job_links_node
from server.state import GraphState
from server.tracing import configure_langsmith


def build_graph(
    *,
    with_job_details: bool = False,
    with_application: bool = False,
    checkpointer: object | None = None,
):
    configure_langsmith()
    g = StateGraph(GraphState)
    g.add_node("browser_render", browser_render_node)
    g.add_edge(START, "browser_render")

    if not with_job_details:
        g.add_edge("browser_render", END)
        return g.compile(checkpointer=checkpointer)

    g.add_node("parse_job_links", parse_job_links_node)
    g.add_node("job_details_json", job_details_json_node)
    g.add_edge("browser_render", "parse_job_links")
    g.add_edge("parse_job_links", "job_details_json")

    if not with_application:
        g.add_edge("job_details_json", END)
        return g.compile(checkpointer=checkpointer)

    g.add_node("load_application_sources", load_application_sources_node)
    g.add_node("generate_resume_texes", generate_resume_texes_node)
    g.add_node("compile_resume_pdfs", compile_resume_pdfs_node)
    g.add_node("generate_cover_texes", generate_cover_texes_node)
    g.add_node("compile_cover_pdfs", compile_cover_pdfs_node)

    g.add_edge("job_details_json", "load_application_sources")
    g.add_edge("load_application_sources", "generate_resume_texes")
    g.add_edge("generate_resume_texes", "compile_resume_pdfs")
    g.add_edge("compile_resume_pdfs", "generate_cover_texes")
    g.add_edge("generate_cover_texes", "compile_cover_pdfs")
    g.add_edge("compile_cover_pdfs", END)

    return g.compile(checkpointer=checkpointer)
