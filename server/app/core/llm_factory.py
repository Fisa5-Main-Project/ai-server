from langchain_core.messages import AIMessage
from app.gateway.runtime import get_gateway


class ManagedLLM:
    """Every physical LLM request goes through shared admission and metering."""

    def __init__(self, temperature):
        self.temperature = temperature

    async def ainvoke(self, messages):
        result = await get_gateway().invoke(messages, temperature=self.temperature)
        usage = None
        if all(x is not None for x in (result.input_tokens, result.output_tokens, result.total_tokens)):
            usage = {'input_tokens': result.input_tokens, 'output_tokens': result.output_tokens,
                     'total_tokens': result.total_tokens}
        return AIMessage(content=result.content, usage_metadata=usage)

def get_llm(temperature: float = 0.3, streaming: bool = False):
    """Return an async ainvoke adapter for the server-configured managed provider."""
    if streaming:
        raise ValueError('Use the existing chat SSE endpoint; provider token streaming is not supported')
    return ManagedLLM(temperature)
