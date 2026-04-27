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
  [compress_prompt]          ← Tokemizer MCP: prompt compression before LLM
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


_TOKEMIZER_URL = "https://f1nzc35x0j.execute-api.us-east-1.amazonaws.com/prod/mcp"


def _call_tokemizer(prompt: str, api_key: str) -> str:
    """Calls the Tokemizer MCP server via JSON-RPC over HTTP and returns the compressed prompt."""
    import json as _json
    import requests as _req

    url = f"{_TOKEMIZER_URL}?apiKey={api_key}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    # Initialize session (stateless server — no session ID returned, but required by protocol)
    init = _req.post(url, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "vp-rag-agent", "version": "1.0.0"}},
    }, headers=headers, timeout=10)
    init.raise_for_status()
    session_id = init.headers.get("Mcp-Session-Id", "")
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    # Call optimize_prompt tool
    resp = _req.post(url, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "optimize_prompt",
                   "arguments": {"prompt": prompt, "optimization_mode": "balanced"}},
    }, headers=headers, timeout=15)
    resp.raise_for_status()

    content = resp.json().get("result", {}).get("content", [])
    if content:
        text = content[0].get("text", "")
        try:
            return _json.loads(text).get("optimized_output", prompt)
        except Exception:
            return text or prompt
    return prompt


def compress_prompt_node(state: AgentState, tokemizer_api_key: str = "") -> Dict[str, Any]:
    """
    Node 3.5: Prompt Compression via Tokemizer MCP
    Builds the full prompt from assembled context, then sends it to the
    Tokemizer MCP server (optimize_prompt / balanced mode) to reduce token
    usage before the LLM call.  Falls back silently to the uncompressed
    prompt if the service is unavailable or the key is missing.
    """
    prompt = build_structured_prompt(
        state["query"],
        state["intent"],
        state["structured_context"],
    )
    prompt = apply_prompt_budget(prompt, max_chars=9000)

    if tokemizer_api_key:
        try:
            prompt = _call_tokemizer(prompt, tokemizer_api_key)
        except Exception:
            pass  # uncompressed prompt is the safe fallback

    return {"prompt": prompt}


def generate_answer_node(state: AgentState, ai_client: Any = None) -> Dict[str, Any]:
    """
    Node 4: LLM Generation
    Uses the pre-compressed prompt from compress_prompt_node when available;
    falls back to building the prompt inline (test / dry-run path).
    """
    prompt = state.get("prompt") or apply_prompt_budget(
        build_structured_prompt(state["query"], state["intent"], state["structured_context"]),
        max_chars=9000,
    )

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

    On first retry from structured RAG with low confidence:
      → escalates to web search fallback automatically.
    This means ANY question the reports can't answer gets a web search retry.

    This is the KEY node that demonstrates LangGraph's loop capability —
    something impossible to express cleanly in a linear pipeline.
    """
    answer = state.get("raw_answer", "")
    retry_count = state.get("retry_count", 0)
    retrieval_source = state.get("retrieval_source", "structured")

    # Signals that the structured RAG answer is insufficient
    low_confidence_signals = [
        len(answer.strip()) < 50,
        "not available" in answer.lower() and retry_count == 0,
        "no information" in answer.lower() and retry_count == 0,
        "cannot find" in answer.lower() and retry_count == 0,
        "no details" in answer.lower() and retry_count == 0,
        "i apologize" in answer.lower() and retry_count == 0,
        "recommend checking" in answer.lower() and retry_count == 0,
        answer.strip() == "I don't have enough information.",
    ]

    confidence = "low" if any(low_confidence_signals) else "high"

    updates: Dict[str, Any] = {
        "confidence": confidence,
        "retry_count": retry_count + (1 if confidence == "low" else 0),
    }

    # On first retry from structured RAG: escalate to web search
    if confidence == "low" and retry_count == 0 and retrieval_source == "structured":
        updates["retrieval_source"] = "web_search_fallback"

    return updates


def format_output_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 6: Output Formatting
    Applies source attribution when the answer came from web search fallback.
    """
    answer = state.get("raw_answer", "")
    retrieval_source = state.get("retrieval_source", "structured")

    # Add web search attribution when the answer came from fallback web search
    if retrieval_source == "web_search_fallback" and answer and len(answer.strip()) > 20:
        answer = f"Based on web search:\n\n{answer}"

    return {"final_answer": answer}


# ── Conditional edge functions ────────────────────────────────────────────────
# These functions decide which node to go to next.
# They replace the if/elif chains buried in the original lambda_handler.

def route_retriever(state: AgentState) -> str:
    """
    Routing decision: which retriever to use?

    structured         → report-based questions (most queries)
    web                → explicit external knowledge questions
    web_search_fallback → structured RAG failed, retry with web search
    """
    intent = state.get("intent", "weekly_summary")
    retrieval_source = state.get("retrieval_source", "structured")

    # Fallback from failed structured RAG → web search
    if retrieval_source == "web_search_fallback":
        return "web_search"

    # Explicit web search intents
    web_intents = {"web_search", "external_knowledge", "current_events"}
    if intent in web_intents:
        return "web_search"

    return "structured_rag"


def should_retry(state: AgentState) -> str:
    """
    Loop decision: retry with web search or proceed to output?

    - First retry: structured RAG failed → go to web search (via classify→route)
    - Second retry or web already tried: give up and format output
    """
    if state.get("confidence") == "low" and state.get("retry_count", 0) < 2:
        return "retry"
    return "done"


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

def build_agent_graph(structured_reports: List[Dict], ai_client: Any = None, tavily_api_key: str = "", tokemizer_api_key: str = "") -> Any:
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

    def _compress_node(state: AgentState) -> Dict[str, Any]:
        return compress_prompt_node(state, tokemizer_api_key)

    # Create the graph with our typed state
    graph = StateGraph(AgentState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("structured_rag", _rag_node)
    graph.add_node("web_search", _web_node)
    graph.add_node("merge_context", merge_context_node)
    graph.add_node("compress_prompt", _compress_node)
    graph.add_node("generate_answer", _generate_node)
    graph.add_node("validate_answer", validate_answer_node)
    graph.add_node("format_output", format_output_node)

    # ── Add edges ─────────────────────────────────────────────────────────────
    graph.add_edge(START, "classify_intent")
    graph.add_edge("structured_rag", "merge_context")
    graph.add_edge("web_search", "merge_context")
    graph.add_edge("merge_context", "compress_prompt")
    graph.add_edge("compress_prompt", "generate_answer")
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
    tokemizer_api_key: str = "",
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
        app = build_agent_graph(structured_reports, ai_client, tavily_api_key, tokemizer_api_key)
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

        # Node 3.5: compress prompt via Tokemizer MCP before LLM call
        state.update(compress_prompt_node(state, tokemizer_api_key))

        # Node 4: generate answer (uses pre-compressed prompt)
        state.update(generate_answer_node(state, ai_client))

        # Node 5: validate with retry loop — escalates to web search on low confidence
        for _ in range(2):
            state.update(validate_answer_node(state))
            if state["confidence"] == "high":
                break
            # On retry: if retrieval_source switched to web_search_fallback, do web search
            if state.get("retrieval_source") == "web_search_fallback":
                state.update(web_search_node(state, tavily_api_key))
                state.update(merge_context_node(state))
                web_ctx = state.get("web_context", "")
                if web_ctx:
                    existing = state.get("structured_context", {})
                    existing_evidence = existing.get("evidence", [])
                    existing_evidence.insert(0, f"Web Search | Results | {web_ctx[:1500]}")
                    existing["evidence"] = existing_evidence
                    state["structured_context"] = existing
                # Recompress with updated context, then regenerate
                state["prompt"] = ""
                state.update(compress_prompt_node(state, tokemizer_api_key))
                state.update(generate_answer_node(state, ai_client))

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
