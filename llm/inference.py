import random
from typing import List


RESPONSE_TEMPLATES = [
    "Based on the context, the answer relates to distributed computing principles.",
    "The information indicates that load distribution is key to system scalability.",
    "According to the documents, fault tolerance is achieved through redundancy.",
    "The context suggests that parallel processing improves overall throughput.",
    "The query relates to system architecture where components work collaboratively.",
]


class InferenceEngine:
    def __init__(self, model: str = "simulated"):
        pass

    def set_base_url(self, url: str):
        pass

    def generate(self, prompt: str, streaming: bool = False):
        if streaming:
            return self._stream(prompt)
        return f"Simulated response to: {prompt[:80]}..."

    def generate_with_context(self, query: str, context_docs: List[str]) -> str:
        template = random.choice(RESPONSE_TEMPLATES)
        return f"{template} Query was: '{query[:100]}'. Context had {len(context_docs)} document(s)."

    def _stream(self, prompt: str):
        words = f"Simulated streaming response for: {prompt[:50]}...".split()
        for w in words:
            yield w + " "


inference_engine = InferenceEngine()
