<div align="center">

# 🔍 RepoLens

### **AI-Powered Codebase Understanding Made Simple**

*Transform any repository into an AI-ready knowledge base in seconds*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Stars](https://img.shields.io/github/stars/OrShmuel22/RepoLens?style=social)](https://github.com/OrShmuel22/RepoLens)

[📖 Documentation](#-usage) • [🚀 Quick Start](#-installation) • [💡 Examples](#-use-cases) • [🤝 Contributing](CONTRIBUTING.md)

</div>

---

## 🎯 Why RepoLens?

Ever struggled to understand a large codebase? Want to chat with your code using AI? **RepoLens** is your solution.

- ⚡ **Lightning Fast** - Process entire repositories in seconds
- 🎯 **Smart Context** - Automatically generates AI-optimized summaries
- 🔧 **Zero Config** - Works out of the box with sensible defaults
- 🌳 **Intelligent Filtering** - Respects .gitignore and skips binaries
- 📊 **Rich Output** - Beautiful tree views and structured markdown
- 🤖 **AI-Ready** - Perfect for ChatGPT, Claude, and other LLMs

## 🎬 See It In Action

```bash
# Analyze any GitHub repository instantly
repolens https://github.com/user/project --output analysis.md

# Done! Feed analysis.md to your favorite AI
```

**Before RepoLens:** Copy-pasting files one by one, losing context 😓  
**After RepoLens:** One command, complete codebase understanding ✨

## 🚀 Installation

```bash
pip install repolens
```

Or install from source:
```bash
git clone https://github.com/yourusername/RepoLens.git
cd RepoLens
pip install -e .
```

## 📖 Usage

### Basic Usage

```bash
# Analyze current directory
repolens .

# Analyze a specific path
repolens /path/to/project

# Clone and analyze a GitHub repo
repolens https://github.com/user/repo
```

### Advanced Options

```bash
# Custom output file
repolens . --output my-analysis.md

# Analyze with different detail levels
repolens . --detail minimal    # Just structure
repolens . --detail standard   # Structure + summaries (default)
repolens . --detail full       # Everything including content

# Include/exclude patterns
repolens . --include "*.py,*.js" --exclude "test_*"

# Process specific file types only
repolens . --include "*.py"
```

## 💡 Use Cases

### 🎓 **Learning New Codebases**
Quickly understand unfamiliar projects before contributing
```bash
repolens https://github.com/django/django --output django-overview.md
```

### 🤖 **AI-Assisted Development**
Feed your entire codebase to ChatGPT/Claude for intelligent suggestions
```bash
repolens . --output for-ai.md
# Upload for-ai.md to your AI chat
```

### 📝 **Documentation Generation**
Create instant project overviews for documentation
```bash
repolens . --detail full --output CODEBASE.md
```

### 🔍 **Code Reviews**
Get a bird's-eye view before diving into PRs
```bash
repolens https://github.com/user/repo/tree/feature-branch
```

### 🏢 **Onboarding New Developers**
Help teammates understand the codebase structure instantly
```bash
repolens . --output onboarding-guide.md
```

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🌐 **GitHub Integration** | Clone and analyze repos directly from URLs |
| 📁 **Smart Filtering** | Respects .gitignore, skips binaries & common artifacts |
| 🎨 **Beautiful Output** | Clean markdown with syntax highlighting |
| 🌳 **Tree Visualization** | ASCII tree structure of your project |
| 📊 **File Statistics** | Line counts, file types, project metrics |
| 🔍 **Content Analysis** | Intelligent code summarization |
| ⚙️ **Configurable** | Extensive options for customization |
| 🚀 **Fast** | Efficient processing even for large repos |
| 🤖 **Flexible AI Models** | Use local (free) or cloud AI models |

## 🤖 AI Models (Simple Explanation)

RepoLens uses two types of AI:
1. **Embedding Models** - Convert your code to searchable "fingerprints" 🔍
2. **LLM Models** - Read code and write human-friendly summaries 💬

### Default Setup (Free & Private)
Works out of the box with local models:
- ✅ Completely free
- ✅ Runs on your computer (private)
- ✅ No API keys needed

### Upgrade to Cloud Models (Better Quality)
Switch to OpenAI or Anthropic for professional-quality results:
- ⭐ Better search accuracy
- ⭐ More detailed summaries
- 💰 Small cost ($0.50-2 per 100k lines)

### 📊 Popular Models

| Use Case | Recommended Setup | Cost |
|----------|------------------|------|
| **Learning/Testing** | Local: `nomic-embed-text` + `llama3.2:3b` | Free |
| **Professional** | Cloud: `text-embedding-3-small` + `gpt-4o-mini` | ~$0.60/100k lines |
| **Best Quality** | Cloud: `text-embedding-3-large` + `claude-3-5-sonnet` | ~$10/100k lines |
| **Best Value** | Mixed: `nomic-embed-text` (local) + `gpt-4o-mini` (cloud) | ~$0.50/100k lines |

**New to AI models?** Check out our [Beginner-Friendly Guide](docs/MODEL_CONFIGURATION.md) 📖

**Want details?** See the [Popular Models Comparison](docs/POPULAR_MODELS.md) 📊

## 📊 Output Example

RepoLens generates clean, structured markdown:

```markdown
# Codebase Summary

## Project Structure
```
my-project/
├── src/
│   ├── main.py          # Application entry point
│   └── utils.py         # Helper functions
├── tests/
│   └── test_main.py     # Unit tests
└── README.md
```

## File Details

### src/main.py
**Lines:** 150 | **Language:** Python

Main application file containing core business logic...
```
## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🌟 Star History

If you find RepoLens useful, please consider giving it a star! ⭐

It helps others discover the project and motivates continued development.

## 💬 Get Help

- 📖 [Documentation](https://github.com/yourusername/RepoLens/wiki)
- 💬 [Discussions](https://github.com/yourusername/RepoLens/discussions)
- 🐛 [Issue Tracker](https://github.com/yourusername/RepoLens/issues)
- 🐦 [Twitter](https://twitter.com/yourusername)

---

<div align="center">

**Made with ❤️ by developers, for developers**

[⭐ Star us on GitHub](https://github.com/yourusername/RepoLens) • [🐦 Follow for updates](https://twitter.com/yourusername)

</div>
