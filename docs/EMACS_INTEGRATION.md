# Emacs Integration (Spacemacs + Claude Code)

## Setup

### Binary
- Emacs: `/opt/homebrew/Cellar/emacs-plus@30/30.2/Emacs.app`
- Launch: `open /opt/homebrew/Cellar/emacs-plus@30/30.2/Emacs.app`
- emacsclient: `/opt/homebrew/Cellar/emacs-plus@30/30.2/bin/emacsclient`
- **NOT** `/opt/homebrew/bin/emacsclient` — that's a different binary that talks to a background server, not the visible Spacemacs instance

### server-start
Added to `dotspacemacs/user-config` in `~/.spacemacs`:
```elisp
(require 'server)
(unless (server-running-p)
  (when (file-exists-p (expand-file-name server-name server-socket-dir))
    (delete-file (expand-file-name server-name server-socket-dir)))
  (server-start))
```

- Stale socket cleanup handles crashes — socket lives at `/var/folders/42/b_1q5t0n1xgb_05h2067y8hh0000gn/T/emacs501/server`
- If emacsclient stops working after a crash: `rm -f` that socket path and restart Emacs

### Opening files from Claude Code
```bash
/opt/homebrew/Cellar/emacs-plus@30/30.2/bin/emacsclient -e '(progn (find-file "/path/to/file") (raise-frame))'
```

## Yabai / Window Management

### Key lessons (learned the hard way 2026-03-18)
- **Do NOT add `manage=off` for Emacs in yabairc** — Emacs tiles fine with yabai BSP
- emacs-plus@30 has a `round-undecorated-frame` patch but it still renders a title bar unless you explicitly set `(undecorated . t)` in frame params
- **Do NOT set `ns-use-native-fullscreen`, `default-frame-alist` fullscreen params, or `undecorated` frame params** — these all conflict with yabai's management and cause the window to go fullscreen or lose its title bar
- If Emacs goes fullscreen or loses title bar: revert any frame param changes, restart Emacs, and let yabai handle layout
- The yabai rule file is at `~/src/config/dotfiles/.config/yabai/yabairc` (sourced through a wrapper chain from `~/.yabairc`)

### What works
- yabai manages Emacs in BSP tiling mode — title bar present, tiled alongside other windows
- `server-start` in user-config is the only addition needed in `.spacemacs`
- emacsclient talks to the running instance so Claude Code can open files directly

## Sketchybar / Barista
- Barista has an emacs module (`~/src/lab/barista/emacs.lua`) integrated into sketchybar
- Top padding for sketchybar: `yabai -m config external_bar all:28:0` (28px)
- Don't mess with emacs frame decorations — let the WM stack (yabai + sketchybar) handle positioning

## Config Paths
| File | Purpose |
|------|---------|
| `~/.spacemacs` | Main Spacemacs config (87k, heavily customized) |
| `~/.emacs.d/early-init.el` | Spacemacs early init (don't touch) |
| `~/src/config/emacs/scawful-config.el` | Personal config loaded by user-config |
| `~/src/config/dotfiles/.config/yabai/yabairc` | Canonical yabai config |
| `~/.config/yabai/yabairc` | Wrapper that sources dotfiles config |
| `~/.yabairc` | Wrapper that sources ~/.config/yabai/yabairc |
