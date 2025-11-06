
from src.langgraphagenticai.tools.web_search_tool import WebSearchTool 

class InterviewWebSearchTool(WebSearchTool):
    """
    A specialized tool for performing web searches for interview questions.
    It inherits the Tavily-based search functionality from WebSearchTool.
    """
    name: str = "interview_web_search"
    description: str = (
        "Use this tool to find interview questions (technical, behavioral, etc.) based on a search query."
    )
