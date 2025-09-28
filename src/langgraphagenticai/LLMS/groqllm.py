import os
from langchain_groq import ChatGroq
from dotenv import load_dotenv

class GroqLLM:
    def __init__(self, model_name: str):
        # The constructor now accepts the model_name
        self.model_name = model_name
        self.llm = self.get_llm_model()

    def get_llm_model(self):
        try:
            load_dotenv()
            groq_api_key = os.getenv("GROQ_API_KEY")
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY environment variable not set.")
            # Use the model_name from the instance variable
            llm = ChatGroq(api_key=groq_api_key, model=self.model_name)
        except Exception as e:
            raise ValueError(f"Error occurred with exception: {e}")
        return llm