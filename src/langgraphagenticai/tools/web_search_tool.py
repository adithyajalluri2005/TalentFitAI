import os
from typing import Optional, Type
from pydantic import BaseModel, Field, PrivateAttr
from langchain.tools import BaseTool
from ddgs import DDGS
from dotenv import load_dotenv

load_dotenv() # Load environment variables here

class WebSearchToolInput(BaseModel):
    """Input schema for the WebSearchTool."""
    query: str = Field(description="The search query to perform.")

class WebSearchTool(BaseTool):
    """
    A tool for performing a web search using DuckDuckGo.
    """
    name: str = "web_search"
    description: str = "Use this tool to search the web for information."
    args_schema: Type[BaseModel] = WebSearchToolInput
    
    # We no longer need the private attribute for DuckDuckGoSearchRun,
    # as we will use the DDGS class directly in the _run method.

    def _run(self, query: str) -> str:
        """Use the tool."""
        try:
            # Using the `with` statement ensures the search session is properly closed.
            with DDGS() as ddgs:
                # The text method returns a generator, so we collect the results.
                results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
                # Join the results into a single string.
                result_string = " ".join([r['body'] for r in results])
            return result_string if result_string else "No search results found."
        except Exception as e:
            return f"An error occurred during web search: {e}"

    def _arun(self, query: str) -> str:
        """Use the tool asynchronously."""
        raise NotImplementedError("Asynchronous version not implemented for this tool.")