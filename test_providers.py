#!/usr/bin/env python3
"""
Example script demonstrating the flexible model configuration.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from librarian.providers import get_embedding_provider, get_llm_provider


def test_ollama_providers():
    """Test Ollama providers (local)."""
    print("\n" + "="*60)
    print("Testing Ollama Providers (Local)")
    print("="*60)

    try:
        # Test embedding
        print("\n1. Testing Ollama Embedding Provider...")
        embed_provider = get_embedding_provider(
            provider="ollama",
            model="nomic-embed-text",
            host=os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        )

        test_text = "def calculate_total(items): return sum(items)"
        embedding = embed_provider.embed_sync(test_text)
        dimension = embed_provider.dimension

        print(f"   ✓ Model: {embed_provider.model}")
        print(f"   ✓ Dimension: {dimension}")
        print(f"   ✓ Embedding preview: [{embedding[0]:.4f}, {embedding[1]:.4f}, ...]")
        print(f"   ✓ Health check: {embed_provider.health_check()}")

        # Test LLM
        print("\n2. Testing Ollama LLM Provider...")
        llm_provider = get_llm_provider(
            provider="ollama",
            model="llama3.2:3b",
            host=os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        )

        test_prompt = "Explain what this code does in one sentence: def add(a, b): return a + b"
        response = llm_provider.generate(test_prompt, max_tokens=100, temperature=0.7)

        print(f"   ✓ Model: {llm_provider.model}")
        print(f"   ✓ Response: {response[:100]}...")
        print(f"   ✓ Health check: {llm_provider.health_check()}")

        return True

    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def test_openai_providers():
    """Test OpenAI providers (cloud)."""
    print("\n" + "="*60)
    print("Testing OpenAI Providers (Cloud)")
    print("="*60)

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("   ⊘ Skipped: OPENAI_API_KEY not set")
        return None

    try:
        # Test embedding
        print("\n1. Testing OpenAI Embedding Provider...")
        embed_provider = get_embedding_provider(
            provider="openai",
            model="text-embedding-3-small",
            api_key=api_key
        )

        test_text = "def calculate_total(items): return sum(items)"
        embedding = embed_provider.embed_sync(test_text)
        dimension = embed_provider.dimension

        print(f"   ✓ Model: {embed_provider.model}")
        print(f"   ✓ Dimension: {dimension}")
        print(f"   ✓ Embedding preview: [{embedding[0]:.4f}, {embedding[1]:.4f}, ...]")

        # Test LLM
        print("\n2. Testing OpenAI LLM Provider...")
        llm_provider = get_llm_provider(
            provider="openai",
            model="gpt-4o-mini",
            api_key=api_key
        )

        test_prompt = "Explain what this code does in one sentence: def add(a, b): return a + b"
        response = llm_provider.generate(test_prompt, max_tokens=100, temperature=0.7)

        print(f"   ✓ Model: {llm_provider.model}")
        print(f"   ✓ Response: {response}")

        return True

    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def test_anthropic_provider():
    """Test Anthropic provider (cloud)."""
    print("\n" + "="*60)
    print("Testing Anthropic LLM Provider (Cloud)")
    print("="*60)

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("   ⊘ Skipped: ANTHROPIC_API_KEY not set")
        return None

    try:
        print("\n1. Testing Anthropic LLM Provider...")
        llm_provider = get_llm_provider(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            api_key=api_key
        )

        test_prompt = "Explain what this code does in one sentence: def add(a, b): return a + b"
        response = llm_provider.generate(test_prompt, max_tokens=100, temperature=0.7)

        print(f"   ✓ Model: {llm_provider.model}")
        print(f"   ✓ Response: {response}")

        return True

    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False


def main():
    """Run all provider tests."""
    print("\n" + "="*60)
    print("RepoLens - Flexible Model Configuration Test")
    print("="*60)

    results = {
        "Ollama": test_ollama_providers(),
        "OpenAI": test_openai_providers(),
        "Anthropic": test_anthropic_provider(),
    }

    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    for provider, result in results.items():
        if result is True:
            status = "✓ PASSED"
        elif result is False:
            status = "✗ FAILED"
        else:
            status = "⊘ SKIPPED"
        print(f"   {provider}: {status}")

    print("\n" + "="*60)
    print("\nTo test cloud providers, set API keys:")
    print("  export OPENAI_API_KEY='sk-...'")
    print("  export ANTHROPIC_API_KEY='sk-ant-...'")
    print("\nFor configuration help, see:")
    print("  docs/MODEL_CONFIGURATION.md")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()

