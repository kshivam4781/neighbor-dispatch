import os
from typing import Optional, Any


def build_model() -> Optional[Any]:
    """Return a configured Strands model instance based on env vars, or None for offline/mock mode.

    MODEL_PROVIDER: one of "mock" (default), "bedrock", "anthropic", "openai".
    mock -> returns None (callers must fall back to deterministic logic; no network, no API key needed).
    bedrock -> strands.models.BedrockModel(model_id=os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0"), temperature=float(os.environ.get("MODEL_TEMPERATURE", "0.3")))
    anthropic -> requires ANTHROPIC_API_KEY env var; strands.models.anthropic.AnthropicModel(client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]}, model_id=os.environ.get("ANTHROPIC_MODEL_ID","claude-sonnet-4-6"), max_tokens=int(os.environ.get("MODEL_MAX_TOKENS","1024")), params={"temperature": float(os.environ.get("MODEL_TEMPERATURE","0.3"))})
    openai -> requires OPENAI_API_KEY env var; strands.models.openai.OpenAIModel(client_args={"api_key": os.environ["OPENAI_API_KEY"]}, model_id=os.environ.get("OPENAI_MODEL_ID","gpt-4o"), params={"temperature": float(os.environ.get("MODEL_TEMPERATURE","0.3")), "max_tokens": int(os.environ.get("MODEL_MAX_TOKENS","1024"))})
    Any other value raises ValueError(f"Unknown MODEL_PROVIDER: {provider}").
    Import the provider-specific classes INSIDE each branch (lazy import) so that e.g. missing anthropic extras don't break mock mode.
    """
    provider = os.environ.get("MODEL_PROVIDER", "mock")

    if provider == "mock":
        return None

    if provider == "bedrock":
        from strands.models import BedrockModel

        return BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0"),
            temperature=float(os.environ.get("MODEL_TEMPERATURE", "0.3")),
        )

    if provider == "anthropic":
        from strands.models.anthropic import AnthropicModel

        return AnthropicModel(
            client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
            model_id=os.environ.get("ANTHROPIC_MODEL_ID", "claude-sonnet-4-6"),
            max_tokens=int(os.environ.get("MODEL_MAX_TOKENS", "1024")),
            params={"temperature": float(os.environ.get("MODEL_TEMPERATURE", "0.3"))},
        )

    if provider == "openai":
        from strands.models.openai import OpenAIModel

        return OpenAIModel(
            client_args={"api_key": os.environ["OPENAI_API_KEY"]},
            model_id=os.environ.get("OPENAI_MODEL_ID", "gpt-4o"),
            params={
                "temperature": float(os.environ.get("MODEL_TEMPERATURE", "0.3")),
                "max_tokens": int(os.environ.get("MODEL_MAX_TOKENS", "1024")),
            },
        )

    raise ValueError(f"Unknown MODEL_PROVIDER: {provider}")
