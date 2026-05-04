from langchain_ollama import OllamaLLM


LLM_MODEL = "qwen2.5:3b"


class InferenceEngine:
    def __init__(self, model: str = LLM_MODEL):
        self.llm = OllamaLLM(model=model)

    def generate(self, prompt: str, streaming: bool = False):
        if streaming:
            return self.llm.stream(prompt)
        return self.llm.invoke(prompt)

    def generate_with_context(self, query: str, context_docs: List[str]) -> str:
        context = "\n\n".join(context_docs)
        prompt = f"""Context information:
{context}

Question: {query}

Answer based on the context above:"""
        return self.generate(prompt)


inference_engine = InferenceEngine()