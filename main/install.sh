#!/bin/bash

cd "$(dirname "$0")"

chmod +x copilot.py

mkdir -p ~/.local/bin
cp copilot.py ~/.local/bin/

if ! grep -Fxq "alias albert='~/.local/bin/copilot.py'" ~/.bashrc; then
    echo "alias albert='~/.local/bin/copilot.py'" >> ~/.bashrc
    echo "Added alias to .bashrc"
else
    echo "Alias already exists in .bashrc"
fi

echo "Installed Albert successfully!"
echo "Restart your terminal or run: source ~/.bashrc"
