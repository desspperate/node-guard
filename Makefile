.PHONY: dev prod install configure

OS := $(shell uname -s)

# ── dependencies ──────────────────────────────────────────────────────────────

.installed:
	@echo "Detected OS: $(OS)"
ifeq ($(OS), Darwin)
	@if ! command -v brew > /dev/null 2>&1; then \
		echo "Installing Homebrew..."; \
		/bin/bash -c "$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; \
	else echo "✓ Homebrew: $$(brew --version | head -1)"; fi
	@if ! command -v python3 > /dev/null 2>&1; then \
		echo "Installing Python..."; brew install python; \
	else echo "✓ Python: $$(python3 --version)"; fi
	@if ! command -v uv > /dev/null 2>&1; then \
		echo "Installing uv..."; brew install uv; \
	else echo "✓ uv: $$(uv --version)"; fi
	@if ! command -v docker > /dev/null 2>&1; then \
		echo "Installing Docker..."; brew install --cask docker; \
	else echo "✓ Docker: $$(docker --version)"; fi
else ifeq ($(OS), Linux)
	@sudo apt update
	@if ! command -v python3 > /dev/null 2>&1; then \
		sudo apt install -y python3; \
	else echo "✓ Python: $$(python3 --version)"; fi
	@if ! command -v uv > /dev/null 2>&1; then \
		echo "Installing uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh; \
	else echo "✓ uv: $$(uv --version)"; fi
	@if ! command -v docker > /dev/null 2>&1; then \
		echo "Installing Docker..."; \
		curl -fsSL https://get.docker.com | sudo sh; \
		sudo usermod -aG docker $$USER; \
		echo "⚠  Docker installed. Log out and back in for group changes."; \
	else echo "✓ Docker: $$(docker --version)"; fi
else
	$(error Unsupported OS: $(OS))
endif
	@uv sync
	@echo "✓ All dependencies installed"
	@touch .installed

install: .installed

# ── env configuration ─────────────────────────────────────────────────────────

.env:
	@$(MAKE) configure

configure:
	@bash -c '\
	  ask() { \
	    local key=$$1 dflt=$$2; \
	    if [ -n "$$dflt" ]; then \
	      read -p "  $$key [$$dflt]: " v; \
	      printf "%s=%s\n" "$$key" "$${v:-$$dflt}"; \
	    else \
	      read -p "  $$key: " v; \
	      printf "%s=%s\n" "$$key" "$$v"; \
	    fi; \
	  }; \
	  echo ""; \
	  echo "=== .env configuration ==="; \
	  echo "Press Enter to accept the default value shown in [brackets]."; \
	  echo ""; \
	  { \
	    ask FASTAPI_TITLE "Node Guard"; \
	    ask DEBUG 0; \
	    ask ADVERTISED_ADDRESS ""; \
	    ask CLUSTER_TOKEN ""; \
	    ask SEED_NODE ""; \
	    ask LOG_LEVEL "DEBUG"; \
	    ask TELEGRAM_BOT_TOKEN ""; \
	    ask TELEGRAM_CHAT_ID ""; \
	  } > .env; \
	  echo ""; \
	  echo "✓ .env written"'

# ── run ───────────────────────────────────────────────────────────────────────

dev: install .env
ifeq ($(OS), Darwin)
	@sed -i '' 's/^DEBUG=.*/DEBUG=1/' .env
else
	@sed -i 's/^DEBUG=.*/DEBUG=1/' .env
endif
	docker compose --profile dev up -d --build

prod: install .env
ifeq ($(OS), Darwin)
	@sed -i '' 's/^DEBUG=.*/DEBUG=0/' .env
else
	@sed -i 's/^DEBUG=.*/DEBUG=0/' .env
endif
	docker compose --profile prod pull
	docker compose --profile prod up -d