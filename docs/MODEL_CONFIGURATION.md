# 🤖 Model Configuration Guide (For Beginners)

> **Don't know what embeddings or models are?** No worries! This guide explains everything in simple terms.

## Table of Contents
- [What Are AI Models?](#what-are-ai-models)
- [Quick Start](#quick-start)
- [Popular Model Recommendations](#popular-model-recommendations)
- [Switching Models](#switching-models)
- [Troubleshooting](#troubleshooting)

---

## What Are AI Models?

### 🔍 Embedding Models (For Search)

**Simple Explanation:** Think of embeddings like converting your code into a special fingerprint made of numbers. When you search, RepoLens compares these fingerprints to find similar code.

**Real Example:**
```
Your code: "function calculateTotal(items) { ... }"
Embedding: [0.23, 0.87, 0.45, ... 768 numbers total]

When you search: "how to calculate totals"
Search embedding: [0.25, 0.85, 0.47, ... 768 numbers]
RepoLens finds the match! ✅
```

**Why It Matters:**
- Different models create different "fingerprint sizes" (dimensions)
- Small models: 384 numbers (fast, less accurate)
- Medium models: 768 numbers (balanced) ⭐ **Default**
- Large models: 1536 numbers (slower, more accurate)

### 💬 LLM Models (For Summaries)

**Simple Explanation:** These are the "chat" models that read your code and write summaries explaining what it does.

**Real Example:**
```
Your code: 50 lines of complex C# class
LLM Summary: "This service handles user authentication. It injects UserRepository and EmailService..."
```

---

## Quick Start

### ✅ Default Setup (Easiest - No Changes Needed)

RepoLens works out of the box with free, local models:

```yaml
# config.yaml (already set up for you!)
providers:
  embedding:
    provider: "ollama"
    model: "nomic-embed-text"  # Free, runs on your computer
  llm:
    provider: "ollama"
    model: "llama3.2:3b"  # Free, runs on your computer
```

**Pros:**
- ✅ Completely free
- ✅ Private (nothing leaves your computer)
- ✅ No API keys needed

**Cons:**
- ⚠️ Requires Docker
- ⚠️ Uses 4-8GB RAM

---

## Popular Model Recommendations

### 🏠 Local Models (Free, Private)

| Model | Speed | Quality | RAM Usage | Best For |
|-------|-------|---------|-----------|----------|
| **nomic-embed-text** | ⚡⚡⚡ | ⭐⭐⭐ | 1GB | Embedding (Default) ⭐ |
| **llama3.2:3b** | ⚡⚡⚡ | ⭐⭐ | 3GB | Fast summaries |
| **llama3.2:8b** | ⚡⚡ | ⭐⭐⭐ | 8GB | Better summaries ⭐ |
| **qwen3:8b** | ⚡⚡ | ⭐⭐⭐ | 8GB | Code understanding |

**How to use:** Already set up! Just run `docker-compose up`

### ☁️ Cloud Models (Paid, Very Accurate)

| Model | Provider | Speed | Quality | Cost/1M tokens | Best For |
|-------|----------|-------|---------|----------------|----------|
| **text-embedding-3-small** | OpenAI | ⚡⚡⚡ | ⭐⭐⭐ | $0.02 | Embedding ⭐ |
| **text-embedding-3-large** | OpenAI | ⚡⚡ | ⭐⭐⭐⭐ | $0.13 | Best embedding |
| **gpt-4o-mini** | OpenAI | ⚡⚡⚡ | ⭐⭐⭐⭐ | $0.15 | Fast summaries ⭐ |
| **gpt-4o** | OpenAI | ⚡⚡ | ⭐⭐⭐⭐⭐ | $2.50 | Best summaries |
| **claude-3-5-haiku** | Anthropic | ⚡⚡⚡ | ⭐⭐⭐⭐ | $0.80 | Fast summaries |
| **claude-3-5-sonnet** | Anthropic | ⚡⚡ | ⭐⭐⭐⭐⭐ | $3.00 | Best summaries ⭐ |

**Cost Example:** Indexing a 100,000 line codebase might cost $1-5 depending on the model.

---

## Switching Models

### 🎯 Option 1: Use OpenAI (Recommended for Beginners)

**Step 1:** Get an API key
1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-...`)

**Step 2:** Set environment variable
```bash
# On Mac/Linux:
export OPENAI_API_KEY="sk-your-key-here"

# On Windows (PowerShell):
$env:OPENAI_API_KEY="sk-your-key-here"
```

**Step 3:** Update config.yaml
```yaml
providers:
  embedding:
    provider: "openai"  # Changed from ollama
    model: "text-embedding-3-small"
  llm:
    provider: "openai"  # Changed from ollama
    model: "gpt-4o-mini"
```

**Step 4:** Restart and reindex
```bash
docker-compose restart
librarian reindex /path/to/your/code
```

### 🎯 Option 2: Use Anthropic Claude

**Step 1:** Get an API key from https://console.anthropic.com/

**Step 2:** Set environment variable
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export OPENAI_API_KEY="sk-your-key-here"  # Still needed for embeddings
```

**Step 3:** Update config.yaml
```yaml
providers:
  embedding:
    provider: "openai"  # Anthropic doesn't have embedding models
    model: "text-embedding-3-small"
  llm:
    provider: "anthropic"  # Use Claude for summaries
    model: "claude-3-5-sonnet-20241022"
```

### 🎯 Option 3: Mix and Match

You can use different providers for embeddings vs summaries:

```yaml
providers:
  embedding:
    provider: "ollama"  # Free local embeddings
    model: "nomic-embed-text"
  llm:
    provider: "openai"  # Paid cloud summaries (better quality)
    model: "gpt-4o-mini"
```

---

## Understanding Dimensions

### What's a "Dimension"?

Remember the fingerprint analogy? The dimension is how many numbers are in that fingerprint.

**Example:**
- `nomic-embed-text`: 768 numbers (768-dimensional)
- `text-embedding-3-small`: 1536 numbers (1536-dimensional)

### ⚠️ Important: Dimension Mismatches

**The Problem:** You can't compare a 768-number fingerprint with a 1536-number fingerprint!

**What Happens:**
1. You index your code with `nomic-embed-text` (768 dimensions)
2. You switch to `text-embedding-3-small` (1536 dimensions)
3. RepoLens will show an error: "Dimension mismatch!"

**The Solution:** RepoLens automatically handles this by creating separate databases for each dimension!

```
.lancedb/
  codebase_chunks/       # 768-dimensional (default)
  codebase_chunks_1536/  # 1536-dimensional (if you switch)
```

**What You Need To Do:**
```bash
# When switching embedding models, just reindex:
librarian reindex /path/to/your/code
```

RepoLens will automatically:
- ✅ Detect the new dimension
- ✅ Create a new database table
- ✅ Re-index your code with the new model

---

## Troubleshooting

### ❌ "Dimension mismatch" error

**What it means:** You switched embedding models but didn't reindex.

**Fix:**
```bash
librarian reindex /path/to/your/code
```

### ❌ "API key not found" error

**What it means:** You forgot to set the API key environment variable.

**Fix:**
```bash
# Set your API key (replace with your actual key)
export OPENAI_API_KEY="sk-your-key-here"
```

### ❌ "Failed to initialize provider" error

**What it means:** Missing Python package for that provider.

**Fix:**
```bash
# For OpenAI:
pip install openai

# For Anthropic:
pip install anthropic
```

### ❌ Ollama not responding

**What it means:** Docker container isn't running or model not downloaded.

**Fix:**
```bash
# Check if running
docker ps

# Restart
docker-compose restart

# Pull model manually
docker exec -it ollama_server ollama pull nomic-embed-text
```

### 💡 General Tips

1. **Start with defaults** - The free local models work great for learning
2. **Switch to cloud for production** - OpenAI/Anthropic give better results
3. **Mix providers** - Use free embeddings + paid LLM for best value
4. **Always reindex** - When changing embedding models, you must reindex

---

## Next Steps

- [Quick Start Guide](QUICK_START.md)
- [Popular Models Comparison](POPULAR_MODELS.md)
- [Advanced Configuration](ADVANCED_CONFIG.md)

**Still confused?** Open an issue and we'll help: https://github.com/yourusername/RepoLens/issues

