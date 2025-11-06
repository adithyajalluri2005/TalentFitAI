import os
from typing import Optional, Type
from pydantic import BaseModel, Field
from langchain.tools import BaseTool
from dotenv import load_dotenv
from tavily import TavilyClient  # Import the Tavily client

load_dotenv()  # Load environment variables

class WebSearchToolInput(BaseModel):
    """Input schema for the WebSearchTool."""
    query: str = Field(description="The search query to perform.")

class WebSearchTool(BaseTool):
    """
    A tool for performing a web search using the Tavily Search API.
    """
    name: str = "web_search"
    description: str = "Use this tool to search the web for information."
    args_schema: Type[BaseModel] = WebSearchToolInput
    
    # Initialize the TavilyClient instance
    _tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    def _run(self, query: str) -> str:
        """Perform a synchronous web search."""
        try:
            # Perform the Tavily search
            search_results = self._tavily_client.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_answer=False
            )

            # The response is a dict — iterate over the "results" key
            results = search_results.get("results", [])
            if not results:
                return "No search results found."

            # Combine the snippets for LLM context
            result_snippets = []
            for result in results:
                content = result.get("content", "")
                url = result.get("url", "")
                result_snippets.append(f"Content: {content}\nSource: {url}")

            # Join results with separators
            result_string = "\n---\n".join(result_snippets)
            return result_string

        except Exception as e:
            # Handle API key errors or network issues gracefully
            return f"An error occurred during web search with Tavily: {e}"

    def _arun(self, query: str) -> str:
        """Asynchronous version (not implemented)."""
        raise NotImplementedError("Asynchronous version not implemented for this tool.")
