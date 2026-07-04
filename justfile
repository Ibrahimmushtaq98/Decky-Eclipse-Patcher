# Set your Deck's address once:  just deck_ip=192.168.1.50 deploy
deck_ip := env_var_or_default("DECK_IP", "steamdeck")
deck_user := "deck"
plugin_dir := "~/homebrew/plugins/decky-eclipse-patcher"

default:
    @just --list

# Run backend unit tests locally
test:
    python3 -m pytest tests/ -v

# Build the frontend bundle
build:
    npm install && npm run build

# Deploy plugin to the Deck over SSH (requires sshd on the Deck)
deploy: build
    rsync -azp --delete \
      --exclude node_modules --exclude .git --exclude src --exclude tests \
      --exclude __pycache__ --exclude .github --exclude "*.map" \
      --rsync-path="sudo rsync" \
      ./ {{deck_user}}@{{deck_ip}}:{{plugin_dir}}/
    ssh {{deck_user}}@{{deck_ip}} 'sudo systemctl restart plugin_loader'

# Tail Decky loader logs from the Deck
logs:
    ssh {{deck_user}}@{{deck_ip}} 'journalctl -u plugin_loader -f'

# Package a zip for sideloading via Decky developer mode
zip: build
    rm -rf out && mkdir -p out/decky-eclipse-patcher
    cp -r dist main.py plugin.json package.json LICENSE README.md py_modules out/decky-eclipse-patcher/
    find out -name __pycache__ -type d -exec rm -rf {} +
    cd out && zip -r "decky-eclipse-patcher.zip" decky-eclipse-patcher
