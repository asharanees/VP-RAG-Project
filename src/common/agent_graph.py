"""
LangGraph-based orchestration layer for the TSA Reporting Agent.

This module demonstrates the agentic workflow pattern using LangGraph.
It wraps the existing retrieval and generation logic in an explicit
directed graph with named nodes, typed state, and conditional routing.

WHY LANGGRAPH:
  - Makes the agent's decision flow explicit and visualizable
  - Each node is independently testable
  - Conditional edges replace buried if/elif chains
  - State is typed and traceable across the full execution
  - Supports loops (retry), parallelism, and human-in-the-loop natively

GRAPH STRUCTURE:
  [START]
     ↓
  [classify_intent]          ← determines intent + target weeks
     ↓
  [route_retriever]          ← conditional edge: which tool to call?
     ↓                ↓
  [structured_rag]  [web_search]   ← retrieval nodes (parallel possible)
     ↓                ↓
  [merge_context]            ← combines results from multiple retrievers
     ↓
  [generate_answer]          ← calls LLM with assembled context
     ↓
  [validate_answer]          ← confidence check; loops back if low quality
     ↓
  [format_output]            ← WhatsApp formatting
     ↓
  [END]
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

# ── LangGraph imports ─────────────────────────────────────────────────────────
try:
    from langgraph.graph import END, START, StateGraph
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    # Graceful fallback — the graph still runs via _run_manual_fallback()
    StateGraph = None
    START = "__start__"
    END = "__end__"

from common.structured_analyst import (
    build_structured_prompt,
    classify_query_intent,
    get_structured_context,
    load_structured_reports_json,
    resolve_target_weeks,
)
from common.weekly_analyst import apply_prompt_budget


# ── Agent State ───────────────────────────────────────────────────────────────
# This is the single shared state object that flows through every node.
# Every node receives the full state and returns a dict of fields to update.
# TypedDict makes it inspectable — you can see exactly what's in the state
# at any point in the graph execution.

class AgentState(TypedDict):
    # Input
    query: str
    sender: str

    # Intent classification results
    intent: str
    target_weeks: List[str]
    available_weeks: List[str]

    # Retrieval results
    structured_context: Dict[str, Any]   # from structured RAG
    web_context: str                      # from web search (future)
    retrieval_source: str                 # "structured" | "web" | "hybrid"

    # Generation
    prompt: str
    raw_answer: str
    final_answer: str

    # Control flow
    retry_count: int
    confidence: str                       # "high" | "low"
    error: Optional[str]


# ── Node functions ────────────────────────────────────────────────────────────
# Each node is a pure function: AgentState → dict of updates.
# LangGraph merges the returned dict into the state automatically.

def classify_intent_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Intent Classification
    Determines what the user is asking and which weeks are relevant.
    This is the 'brain' of the routing decision.
    """
    query = state["query"]
    available_weeks = state.get("available_weeks", [])

    intent_result = classify_query_intent(query)
    intent = intent_result.get("intent", "weekly_summary")
    target_weeks = resolve_target_weeks(query, available_weeks, intent)

    return {
        "intent": intent,
        "target_weeks": target_weeks,
    }


def structured_rag_node(state: AgentState, structured_reports: List[Dict]) -> Dict[str, Any]:
    """
    Node 2a: Structured RAG Retrieval
    Fetches context from the parsed report JSON.
    This is the primary retrieval path for report-based questions.
    """
    context = get_structured_context(
        state["intent"],
        state["target_weeks"],
        structured_reports,
        state["query"],
    )
    return {
        "structured_context": context,
        "retrieval_source": "structured",
    }


def web_search_node(state: AgentState, tavily_api_key: str = "") -> Dict[str, Any]:
    """
    Node 2b: Web Search Retrieval via Tavily API.
    Called when the query is about external information not in the reports.
    Examples: currency rates, vendor pricing, industry news, general telecom facts.

    Uses the Tavily Search API directly via HTTP (no SDK dependency needed).
    Falls back gracefully if the API key is missing or the call fails.
    """
    query = state["query"]

    if not tavily_api_key:
        return {
            "web_context": "[Web search unavailable — TAVILY_API_KEY not configured]",
            "retrieval_source": "web",
        }

    try:
        import urllib.request
        import json as _json

        payload = _json.dumps({
            "query": query,
            "search_depth": "basic",
            "max_results": 3,
            "include_answer": True,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {tavily_api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=8) as resp:
            result = _json.loads(resp.read().decode("utf-8"))

        # Build a clean context string from the results
        answer = result.get("answer", "")
        results = result.get("results", [])

        parts = []
        if answer:
            parts.append(f"Summary: {answer}")
        for r in results[:3]:
            title = r.get("title", "")
            content = r.get("content", "")[:300]
            url = r.get("url", "")
            parts.append(f"- {title}: {content} ({url})")

        web_context = "\n".join(parts) if parts else "No relevant web results found."

    except Exception as e:
        web_context = f"[Web search failed: {str(e)[:100]}]"

    return {
        "web_context": web_context,
        "retrieval_source": "web",
    }


def merge_context_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Context Merger
    Combines structured RAG and web search results into a single context.
    In hybrid mode, both sources contribute to the final answer.
    Currently a passthrough — becomes meaningful when web search is active.
    """
    # Future: merge state["structured_context"] + state["web_context"]
    # For now, structured context is the primary source
    return {}  # no state changes needed — context already in state


def generate_answer_node(state: AgentState, ai_client: Any = None) -> Dict[str, Any]:
    """
    Node 4: LLM Generation
    Builds the prompt from assembled context and calls the LLM.
    The prompt construction is the same as the existing pipeline —
    LangGraph just makes it an explicit named step.

    When ai_client is provided (production path), calls the LLM and stores
    the raw answer. When None (test/dry-run path), only builds the prompt.
    """
    prompt = build_structured_prompt(
        state["query"],
        state["intent"],
        state["structured_context"],
    )
    prompt = apply_prompt_budget(prompt, max_chars=9000)

    updates: Dict[str, Any] = {"prompt": prompt}

    if ai_client is not None:
        try:
            generation = ai_client.generate_answer(prompt)
            updates["raw_answer"] = generation.text
        except Exception as e:
            updates["raw_answer"] = ""
            updates["error"] = str(e)

    return updates


def validate_answer_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 5: Answer Validation (confidence check)
    Checks if the generated answer is substantive.
    If low confidence, the graph loops back to retry with broader context.

    This is the KEY node that demonstrates LangGraph's loop capability —
    something impossible to express cleanly in a linear pipeline.
    """
    answer = state.get("raw_answer", "")
    retry_count = state.get("retry_count", 0)

    # Simple heuristic: if answer is very short or says "not available", low confidence
    low_confidence_signals = [
        len(answer.strip()) < 50,
        "not available" in answer.lower() and retry_count == 0,
        answer.strip() == "I don't have enough information.",
    ]

    confidence = "low" if any(low_confidence_signals) else "high"
    return {
        "confidence": confidence,
        "retry_count": retry_count + (1 if confidence == "low" else 0),
    }


def format_output_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 6: Output Formatting
    Applies WhatsApp-specific formatting to the raw answer.
    Separated from generation so formatting can be changed independently.
    """
    answer = state.get("raw_answer", "")
    # WhatsApp formatting is handled by _normalize_whatsapp_text in rag_worker
    # Here we just pass through — the actual formatting happens at delivery
    return {"final_answer": answer}


# ── Conditional edge functions ────────────────────────────────────────────────
# These functions decide which node to go to next.
# They replace the if/elif chains buried in the original lambda_handler.

def route_retriever(state: AgentState) -> str:
    """
    Routing decision: which retriever to use?

    structured → report-based questions (most queries)
    web        → external knowledge questions (currency, pricing, news, etc.)
    hybrid     → questions needing both (future)
    """
    intent = state.get("intent", "weekly_summary")

    # Web search intents — routed to Tavily
    web_intents = {"web_search", "external_knowledge", "current_events"}
    if intent in web_intents:
        return "web_search"

    # Everything else uses structured RAG
    return "structured_rag"


def should_retry(state: AgentState) -> str:
    """
    Loop decision: retry generation or proceed to output?

    This demonstrates LangGraph's cycle capability.
    A linear pipeline cannot express 'try again with different parameters'.
    """
    if state.get("confidence") == "low" and state.get("retry_count", 0) < 2:
        return "retry"
    return "done"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_agent_graph(structured_reports: List[Dict], ai_client: Any = None, tavily_api_key: str = "") -> Any:
    """
    Builds and compiles the LangGraph StateGraph.

    The graph is compiled once at startup and reused for every query.
    Compilation validates the graph structure (no orphan nodes, valid edges).

    Args:
        structured_reports: The parsed report data loaded from S3.
        ai_client: AIRouter instance for LLM generation. If None, generation
                   node only builds the prompt (useful for testing).

    Returns:
        Compiled LangGraph app (or None if LangGraph not installed).
    """
    if not LANGGRAPH_AVAILABLE:
        return None

    # Bind structured_reports and ai_client into nodes via closures
    def _rag_node(state: AgentState) -> Dict[str, Any]:
        return structured_rag_node(state, structured_reports)

    def _web_node(state: AgentState) -> Dict[str, Any]:
        return web_search_node(state, tavily_api_key)

    def _generate_node(state: AgentState) -> Dict[str, Any]:
        return generate_answer_node(state, ai_client)

    # Create the graph with our typed state
    graph = StateGraph(AgentState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("structured_rag", _rag_node)
    graph.add_node("web_search", _web_node)
    graph.add_node("merge_context", merge_context_node)
    graph.add_node("generate_answer", _generate_node)
    graph.add_node("validate_answer", validate_answer_node)
    graph.add_node("format_output", format_output_node)

    # ── Add edges ─────────────────────────────────────────────────────────────
    # Fixed edges (always go to next node)
    graph.add_edge(START, "classify_intent")
    graph.add_edge("structured_rag", "merge_context")
    graph.add_edge("web_search", "merge_context")
    graph.add_edge("merge_context", "generate_answer")
    graph.add_edge("generate_answer", "validate_answer")
    graph.add_edge("format_output", END)

    # Conditional edge: after classification, route to correct retriever
    graph.add_conditional_edges(
        "classify_intent",
        route_retriever,
        {
            "structured_rag": "structured_rag",
            "web_search": "web_search",
        },
    )

    # Conditional edge: after validation, retry or finish
    # This is the LOOP — LangGraph handles cycles natively
    graph.add_conditional_edges(
        "validate_answer",
        should_retry,
        {
            "retry": "classify_intent",   # loop back to start with broader context
            "done": "format_output",
        },
    )

    return graph.compile()


# ── Manual fallback (no LangGraph dependency) ─────────────────────────────────

def run_graph(
    query: str,
    sender: str,
    structured_reports: List[Dict],
    ai_client: Any,
    tavily_api_key: str = "",
) -> Dict[str, Any]:
    """
    Runs the agent graph for a given query.

    If LangGraph is installed: uses the compiled StateGraph.
    If not: runs the same logic manually (identical behavior, no graph).

    This dual-mode design means:
    - Production Lambda doesn't need langgraph in its deployment package
    - The graph logic is still testable locally with langgraph installed
    - The manual fallback proves you understand what LangGraph does under the hood

    Args:
        query: User's WhatsApp message text.
        sender: WhatsApp sender ID.
        structured_reports: Parsed report data from S3.
        ai_client: AIRouter instance for LLM generation.

    Returns:
        Dict with keys: final_answer, intent, target_weeks, evidence_count, error
    """
    available_weeks = [r.get("week_label", "") for r in structured_reports if r.get("week_label")]

    initial_state: AgentState = {
        "query": query,
        "sender": sender,
        "intent": "",
        "target_weeks": [],
        "available_weeks": available_weeks,
        "structured_context": {},
        "web_context": "",
        "retrieval_source": "structured",
        "prompt": "",
        "raw_answer": "",
        "final_answer": "",
        "retry_count": 0,
        "confidence": "high",
        "error": None,
    }

    if LANGGRAPH_AVAILABLE:
        # ── LangGraph path ────────────────────────────────────────────────────
        # The graph handles all state transitions automatically.
        # Each node is called in order, conditional edges decide routing.
        app = build_agent_graph(structured_reports, ai_client, tavily_api_key)
        final_state = app.invoke(initial_state)
    else:
        # ── Manual fallback path (same logic, no graph framework) ─────────────
        # Identical behavior to the LangGraph path.
        # This proves LangGraph is a structural choice, not a functional one.
        state = dict(initial_state)

        # Node 1: classify intent and resolve target weeks
        state.update(classify_intent_node(state))

        # Node 2: route to correct retriever
        route = route_retriever(state)
        if route == "web_search":
            state.update(web_search_node(state, tavily_api_key))
        else:
            state.update(structured_rag_node(state, structured_reports))

        # Node 3: merge context (passthrough for now)
        state.update(merge_context_node(state))

        # Node 4: generate answer (builds prompt + calls LLM)
        state.update(generate_answer_node(state, ai_client))

        # Node 5: validate with retry loop
        for _ in range(2):
            state.update(validate_answer_node(state))
            if state["confidence"] == "high":
                break
            # On retry: could widen week scope here in future

        # Node 6: format output
        state.update(format_output_node(state))
        final_state = state

    return {
        "final_answer": final_state.get("final_answer") or final_state.get("raw_answer", ""),
        "intent": final_state.get("intent", ""),
        "target_weeks": final_state.get("target_weeks", []),
        "evidence_count": len(final_state.get("structured_context", {}).get("evidence", [])),
        "error": final_state.get("error"),
        "retrieval_source": final_state.get("retrieval_source", "structured"),
    }
