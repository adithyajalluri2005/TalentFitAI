import os
import re
from typing import List, Optional

from langchain_groq import ChatGroq
from dotenv import load_dotenv


def groq_api_keys() -> List[str]:
    """GROQ_API_KEY plus any GROQ_API_KEY_1, GROQ_API_KEY_2, ... (in number
    order), without duplicates. Each key has its own Groq quota."""
    load_dotenv()
    numbered = sorted(
        ((int(m.group(1)), v) for k, v in os.environ.items() if (m := re.fullmatch(r"GROQ_API_KEY_(\d+)", k))),
        key=lambda kv: kv[0],
    )
    keys = [os.getenv("GROQ_API_KEY", "")] + [v for _, v in numbered]
    return list(dict.fromkeys(k.strip() for k in keys if k and k.strip()))


class GroqLLM:
    def __init__(self, model_name: str, api_key: Optional[str] = None):
        self.model_name = model_name
        self.api_key = api_key
        self.llm = self.get_llm_model()

    def get_llm_model(self):
        try:
            load_dotenv()
            groq_api_key = self.api_key or os.getenv("GROQ_API_KEY")
            if not groq_api_key:
                raise ValueError("GROQ_API_KEY environment variable not set.")
            # Use the model_name from the instance variable
            # No SDK retries: on a 429 the Groq client sleeps out retry-after
            # (tens of seconds) before raising. CoachNodes._ask handles rate
            # limits itself and switches to another key or model at once.
            llm = ChatGroq(api_key=groq_api_key, model=self.model_name, max_retries=0)
        except Exception as e:
            raise ValueError(f"Error occurred with exception: {e}")
        return llm