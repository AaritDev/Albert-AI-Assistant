***Albert – Your Local Terminal AI Copilot*** 🤖

Albert is a **local AI terminal assistant** powered by Ollama (https://ollama.com).  
It remembers your conversations, runs completely offline, and integrates smoothly with your Linux shell.

✨ Features
- Local LLM integration (Ollama)
- Per-session conversation history (stored as JSONL)
- Friendly banner and environment detection
- Configurable sessions ("--session" / "-s")
- Clear history with "--clear-history"
- Markdown-rendered answers with Rich (https://pypi.org/project/rich)
- tested on Arch Linux, Fedora, Ubuntu

⚙️ Requirements
- **Python 3.8+**
- **Ollama** (running locally on port 11434)
- Python dependencies:
  bash
  pip install requests rich
- Strong system able to run 8B param models locally

To remove Albert:
1. run "rm ~/.local/bin/albert"
2. Delete the alias from your ~/.bashrc (if added manually).

Developed by Aarit Pandey
Built with ❤️ using Python + Ollama + Rich
