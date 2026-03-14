.PHONY: dev prod

OS := $(shell uname -s)

.installed:
	@echo "Detected OS: $(OS)"

ifeq ($(OS), Darwin)
	@if ! command -v brew > /dev/null 2>&1; then \
		echo "Installing Homebrew..."; \
		/bin/bash -c "$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; \
	else \
		echo "✓ Homebrew already installed"; \
	fi

	@if ! command -v python3 > /dev/null 2>&1; then \
		echo "Installing Python..."; \
		brew install python; \
	else \
		echo "✓ Python already installed: $$(python3 --version)"; \
	fi

	@if ! command -v uv > /dev/null 2>&1; then \
		echo "Installing uv..."; \
		brew install uv; \
	else \
		echo "✓ uv already installed: $$(uv --version)"; \
	fi

	@if ! command -v docker > /dev/null 2>&1; then \
		echo "Installing Docker..."; \
		brew install --cask docker; \
	else \
		echo "✓ Docker already installed: $$(docker --version)"; \
	fi

else ifeq ($(OS), Linux)
	@echo "Updating apt..."
	sudo apt update

	@if ! command -v python3 > /dev/null 2>&1; then \
		echo "Installing Python..."; \
		sudo apt install -y python3; \
	else \
		echo "✓ Python already installed: $$(python3 --version)"; \
	fi

	@if ! command -v uv > /dev/null 2>&1; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	else \
		echo "✓ uv already installed: $$(uv --version)"; \
	fi

	@if ! command -v docker > /dev/null 2>&1; then \
		echo "Installing Docker..."; \
		curl -fsSL https://get.docker.com | sudo sh; \
		sudo usermod -aG docker $$USER; \
		echo "⚠ Docker installed. Log out and back in for group changes to take effect."; \
	else \
		echo "✓ Docker already installed: $$(docker --version)"; \
	fi

else
	@echo "Unsupported OS: $(OS)"
	@exit 1
endif

	@echo "Installing Python dependencies..."
	uv sync

	@echo "✓ All dependencies installed"
	@touch .installed

install: .installed

.env:
	@echo "Generating .env..."
	@echo "FASTAPI_TITLE=\"Node Guard\"" >> .env
	@echo "DEBUG=1" >> .env
	@echo "ADVERTISED_ADDRESS=" >> .env
	@echo "CLUSTER_TOKEN=" >> .env
	@echo "SEED_NODE=" >> .env
	@echo "✓ .env generated"

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
	docker compose --profile prod up -d
