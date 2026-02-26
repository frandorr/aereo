#!/usr/bin/env bash
set -e

echo "Welcome to the Polylith + uv template setup!"

read -p "Enter your project name: " PROJECT_NAME
if [ -z "$PROJECT_NAME" ]; then
    echo "Project name cannot be empty."
    exit 1
fi

echo "Setting up project: $PROJECT_NAME..."

# Update pyproject.toml
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/^name = .*/name = \"$PROJECT_NAME\"/" pyproject.toml
else
    sed -i "s/^name = .*/name = \"$PROJECT_NAME\"/" pyproject.toml
fi

# Update workspace.toml
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/^namespace = .*/namespace = \"$PROJECT_NAME\"/" workspace.toml
else
    sed -i "s/^namespace = .*/namespace = \"$PROJECT_NAME\"/" workspace.toml
fi

# Install uv if missing
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Try to add to PATH for current session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
else
    echo "uv is already installed."
fi

# Add dev dependencies
echo "Adding polylith-cli as a dev dependency..."
uv add polylith-cli --dev

# Sync the project
echo "Syncing project dependencies with uv..."
uv sync

# Install perk using uv tool
echo "Installing perk..."
uv tool install perk

echo "--------------------------------------------------------"
echo "Setup complete! You're ready to start building."
echo "--------------------------------------------------------"
