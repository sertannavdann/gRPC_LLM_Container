"""
Example: Adding ADK-Style Tools to gRPC LLM Container

This file demonstrates how to create tools following Google ADK best practices
while maintaining local inference capabilities.
"""

from typing import Dict, Any
from datetime import datetime, timedelta
import dateparser


# ============================================================================
# EXAMPLE 1: Calendar Tool (ADK-Style)
# ============================================================================

def get_date(x_days_from_today: int) -> Dict[str, str]:
    """
    Retrieves a date for today or a day relative to today.
    
    Args:
        x_days_from_today (int): how many days from today? (use 0 for today)
    
    Returns:
        A dict with the date in a formal writing format. For example:
        {"date": "Wednesday, May 7, 2025"}
    """
    target_date = datetime.today() + timedelta(days=x_days_from_today)
    date_string = target_date.strftime("%A, %B %d, %Y")
    
    return {"date": date_string}


def schedule_meeting(
    person: str,
    start_time_iso8601: str,
    duration_minutes: int
) -> Dict[str, Any]:
    """
    Schedule a meeting with a person using native calendar integration.
    
    Args:
        person (str): Full name of the person to meet with
        start_time_iso8601 (str): Meeting start time in ISO 8601 format
        duration_minutes (int): Duration of the meeting in minutes
    
    Returns:
        A dict with status and event details. For example:
        {"status": "success", "event_id": "evt_123", "message": "Meeting scheduled"}
        or
        {"status": "error", "message": "Calendar access denied"}
    """
    try:
        # Use existing CppLLM bridge for EventKit integration
        from shared.clients.cpp_llm_client import CppLLMClient
        
        client = CppLLMClient(host="localhost", port=50055)
        result = client.trigger_schedule_meeting(
            person=person,
            start_time=start_time_iso8601,
            duration=duration_minutes
        )
        
        return {
            "status": "success",
            "event_id": result.get("event_id", "unknown"),
            "message": f"Meeting with {person} scheduled for {start_time_iso8601}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to schedule meeting: {str(e)}"
        }


# ============================================================================
# EXAMPLE 2: Journal Tool (ADK-Style)
# ============================================================================

def write_journal_entry(entry_date: str, journal_content: str) -> Dict[str, str]:
    """
    Writes a journal entry based on the user's thoughts.
    
    Args:
        entry_date (str): The entry date of the journal entry
        journal_content (str): The body text of the journal entry
    
    Returns:
        A dict with the filename of the written entry. For example:
        {"status": "success", "entry": "2025-05-07.txt"}
        or
        {"status": "error", "message": "Permission denied"}
    """
    import os
    
    try:
        date_for_filename = dateparser.parse(entry_date).strftime("%Y-%m-%d")
        filename = f"{date_for_filename}.txt"
        
        # Create the file if it doesn't already exist
        if not os.path.exists(filename):
            with open(filename, "w") as f:
                f.write("### " + entry_date)
        
        # Append to the dated entry
        with open(filename, "a") as f:
            f.write("\n\n" + journal_content)
        
        return {
            "status": "success",
            "entry": filename,
            "message": f"Journal entry written to {filename}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to write journal: {str(e)}"
        }


# ============================================================================
# EXAMPLE 3: Web Search Tool (Wrapping Existing gRPC Service)
# ============================================================================

def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web using Google Serper API.
    
    Args:
        query (str): The search query
        max_results (int): Maximum number of results to return
    
    Returns:
        A dict with search results. For example:
        {
            "status": "success",
            "results": [
                {"title": "...", "link": "...", "snippet": "..."},
                ...
            ]
        }
        or
        {"status": "error", "message": "API rate limit exceeded"}
    """
    try:
        from shared.clients.tool_client import ToolClient
        
        client = ToolClient()
        result = client.call_tool(
            tool_name="web_search",
            params={"query": query, "max_results": max_results}
        )
        
        if result.success:
            return {
                "status": "success",
                "results": result.data,
                "message": f"Found {len(result.data)} results"
            }
        else:
            return {
                "status": "error",
                "message": result.message
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Search failed: {str(e)}"
        }


# ============================================================================
# EXAMPLE 4: Math Solver Tool
# ============================================================================

def solve_math(expression: str) -> Dict[str, Any]:
    """
    Solve a mathematical expression.
    
    Args:
        expression (str): Mathematical expression to solve (e.g., "2 + 2", "sqrt(16)")
    
    Returns:
        A dict with the solution. For example:
        {"status": "success", "result": "4.0", "expression": "2 + 2"}
        or
        {"status": "error", "message": "Invalid expression"}
    """
    try:
        from sympy import sympify
        
        result = sympify(expression)
        
        return {
            "status": "success",
            "result": str(float(result)),
            "expression": expression,
            "message": f"{expression} = {result}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Cannot solve expression: {str(e)}"
        }


# ============================================================================
# EXAMPLE 5: Vector Search Tool (Wrapping Chroma)
# ============================================================================

def search_knowledge_base(
    query: str,
    collection_name: str = "default",
    max_results: int = 3
) -> Dict[str, Any]:
    """
    Search the vector database for relevant information.
    
    Args:
        query (str): The search query
        collection_name (str): Name of the collection to search
        max_results (int): Maximum number of results to return
    
    Returns:
        A dict with search results. For example:
        {
            "status": "success",
            "results": [
                {"content": "...", "score": 0.95, "metadata": {...}},
                ...
            ]
        }
        or
        {"status": "error", "message": "Collection not found"}
    """
    try:
        from shared.clients.chroma_client import ChromaClient
        
        client = ChromaClient()
        results = client.query(
            collection_name=collection_name,
            query_text=query,
            n_results=max_results
        )
        
        formatted_results = [
            {
                "content": doc,
                "score": score,
                "metadata": meta
            }
            for doc, score, meta in zip(
                results.documents[0],
                results.distances[0],
                results.metadatas[0]
            )
        ]
        
        return {
            "status": "success",
            "results": formatted_results,
            "message": f"Found {len(formatted_results)} relevant documents"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Search failed: {str(e)}"
        }


# ============================================================================
# HOW TO REGISTER THESE TOOLS
# ============================================================================

def register_all_tools():
    """
    Example of registering tools with the agent.
    
    This would typically be called in agent_service/agent_service.py
    """
    from agent_service.agent_service import AgentOrchestrator
    
    # Get orchestrator instance
    orchestrator = AgentOrchestrator()
    registry = orchestrator.tool_registry
    
    # Register function tools
    registry.register(
        name="get_date",
        func=get_date,
        description="Get today's date or a date relative to today"
    )
    
    registry.register(
        name="schedule_meeting",
        func=schedule_meeting,
        description="Schedule a meeting with someone using native calendar"
    )
    
    registry.register(
        name="write_journal",
        func=write_journal_entry,
        description="Write a journal entry to a dated file"
    )
    
    registry.register(
        name="web_search",
        func=web_search,
        description="Search the web for information"
    )
    
    registry.register(
        name="solve_math",
        func=solve_math,
        description="Solve mathematical expressions"
    )
    
    registry.register(
        name="search_kb",
        func=search_knowledge_base,
        description="Search the vector knowledge base"
    )
    
    print(f"Registered {len(registry.tools)} tools")
    print(f"Available tools: {registry.get_available_tools()}")


# ============================================================================
# EXAMPLE: Creating an Agent with Tools (ADK-Style)
# ============================================================================

def create_journaling_agent():
    """
    Example: Create a specialized agent for journaling.
    
    This follows the ADK pattern from the lab documentation.
    """
    from agent_service.agents.local_agent import LocalAgent
    
    agent = LocalAgent(
        name="journaling_agent",
        model_path="./llm_service/models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
        description="Help users practice good daily journalling habits.",
        instruction="""
        Ask the user how their day is going and
        use their response to write a journal entry for them.
        """,
        tools=[get_date, write_journal_entry],
        before_inference_callback=lambda ctx: print(f"Processing: {ctx['query']}"),
        after_inference_callback=lambda resp: print(f"Response: {resp}")
    )
    
    return agent


def create_meeting_agent():
    """
    Example: Create a specialized agent for scheduling.
    """
    from agent_service.agents.local_agent import LocalAgent
    
    agent = LocalAgent(
        name="meeting_agent",
        model_path="./llm_service/models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
        description="Help users schedule meetings and manage calendar.",
        instruction="""
        Help the user schedule meetings using their calendar.
        Always confirm details before scheduling.
        """,
        tools=[get_date, schedule_meeting],
    )
    
    return agent


def create_research_agent():
    """
    Example: Create an agent that combines web search and knowledge base.
    """
    from agent_service.agents.local_agent import LocalAgent
    
    # Following ADK's Agent-as-Tool pattern
    search_agent = LocalAgent(
        name="search_agent",
        model_path="./llm_service/models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
        description="Search specialist",
        instruction="Search the knowledge base for information",
        tools=[search_knowledge_base]
    )
    
    # Root agent uses the search agent as a tool
    research_agent = LocalAgent(
        name="research_agent",
        model_path="./llm_service/models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
        description="Research questions using web search and knowledge base",
        instruction="""
        Research topics thoroughly by:
        1. Searching the knowledge base first
        2. Using web search for recent information
        3. Combining results to provide comprehensive answers
        """,
        tools=[
            AgentTool(search_agent, skip_summarization=False),  # ADK pattern
            web_search,
            solve_math
        ]
    )
    
    return research_agent


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test individual tools
    print("Testing get_date:")
    print(get_date(0))  # Today
    print(get_date(1))  # Tomorrow
    
    print("\nTesting solve_math:")
    print(solve_math("2 + 2"))
    print(solve_math("sqrt(16)"))
    
    print("\nTesting write_journal:")
    print(write_journal_entry("October 8, 2025", "Learned about ADK-style tools today!"))
    
    # Test agent creation
    print("\nCreating agents:")
    journal_agent = create_journaling_agent()
    print(f"Created: {journal_agent.name}")
    
    meeting_agent = create_meeting_agent()
    print(f"Created: {meeting_agent.name}")
    
    research_agent = create_research_agent()
    print(f"Created: {research_agent.name}")
