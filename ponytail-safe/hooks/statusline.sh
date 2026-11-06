#!/usr/bin/env bash
# Ponytail Safe statusline badge. Not installed automatically: add it yourself (see README).
flag="${XDG_CONFIG_HOME:-$HOME/.config}/ponytail-safe/active"
[ -f "$flag" ] || exit 0
state=$(head -c 40 "$flag" | tr -cd 'a-z:')
printf '\033[38;5;108m[PONYTAIL-SAFE %s]\033[0m' "$state"
