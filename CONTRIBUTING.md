# Contributing to CRAVE

Thank you for your interest in CRAVE! Please note that this project is released under a **Source-Available License**. You may study and run the code for personal use, but modification and redistribution of modified versions is not permitted without written permission.

## How You Can Help

### 🐛 Bug Reports
If you find a bug, please [open an issue](https://github.com/charanbhargav6/CRAVE/issues) with:
- A clear description of the problem
- Steps to reproduce
- Your system specs (RAM, OS version, Python version)
- Relevant log output from `Logs/crave.log`

### 💡 Feature Suggestions
Have an idea? Open an issue tagged `[Feature Request]` describing:
- What you'd like CRAVE to do
- Why it would be useful
- Any technical suggestions for implementation

### 📖 Documentation
Found a typo or confusing instruction? Open an issue describing what needs clarification.

## Architecture Overview

Before diving in, read these files to understand the system:
- `overview.md` — High-level capabilities
- `PRD.md` — Product requirements and tech stack
- `DEVELOPMENT_LOG.md` — Technical architecture and design decisions

## Code Style

- Python 3.11+
- Docstrings on all public functions
- Type hints encouraged
- All agents must be encapsulated classes in `src/agents/`
- New intents must be wired through `src/core/orchestrator.py`
- Security-sensitive operations must use RBAC gates (`src/security/rbac.py`)

## Questions?

Open an issue or reach out via the repository discussions.
