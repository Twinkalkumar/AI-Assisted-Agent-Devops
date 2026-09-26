import os

from .base import LLMProvider


def build_llm(llm_config: dict) -> LLMProvider:
    """Construct the configured LLMProvider from config.yaml's `llm:` block.

    This is the single place that maps `provider:` -> an implementation,
    so adding a new backend only means adding one provider class + one
    branch here.
    """
    provider = llm_config["provider"].lower()
    model = llm_config["model"]
    temperature = llm_config.get("temperature", 0.2)
    max_tokens = llm_config.get("max_tokens", 4096)

    if provider == "openai":
        from .providers.openai_provider import OpenAIProvider

        return OpenAIProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=os.environ["OPENAI_API_KEY"],
        )

    if provider == "anthropic":
        from .providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=os.environ["ANTHROPIC_API_KEY"],
        )

    if provider == "azure_openai":
        from .providers.azure_openai_provider import AzureOpenAIProvider

        return AzureOpenAIProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", model),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        )

    if provider == "ollama":
        from .providers.ollama_provider import OllamaProvider

        return OllamaProvider(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    raise ValueError(
        f"Unknown llm.provider '{provider}'. "
        "Expected one of: openai, anthropic, azure_openai, ollama."
    )
