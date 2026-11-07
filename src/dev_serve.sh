#!/usr/bin/env bash
# dev_serve.sh: local development server for the Kea site, independent of the hub.
#
# Builds report/site/ (no PDF) and serves it on ${DEV_HOST:-127.0.0.1}:${DEV_PORT:-8211}: without a password on
# localhost, with SITE_PASSWORD from .env on any other address (e.g. the VPN, DEV_HOST=10.42.0.3).
# Watches doc/, src/kea/ and kea.yaml:
#   - any change           -> rebuild the site
#   - a change in src/kea/ -> also restart the server, so new server code is loaded
# Comments go to data/feedback/dev/ (gitignored) and never mix with the hub's mirror in data/feedback/.
# Input: the project root as working directory (run via `make dev`). Output: report/site/, a running server.
set -u

dev_port="${DEV_PORT:-8211}"
dev_host="${DEV_HOST:-127.0.0.1}"
password_option=()
case "$dev_host" in
    127.*|localhost) password_option=(--no-password) ;;   # reachable only from this machine
esac
server_pid=""

start_server() {
    uv run --locked kea serve "${password_option[@]}" --host "$dev_host" --port "$dev_port" \
        --events data/feedback/dev/events.jsonl --cycle data/feedback/dev/cycle.jsonl &
    server_pid=$!
    echo "[dev] server pid $server_pid on http://$dev_host:$dev_port/${password_option[*]:+ (no password)}"
}

stop_server() {
    if [ -n "$server_pid" ]; then
        kill "$server_pid" 2>/dev/null
        wait "$server_pid" 2>/dev/null
        server_pid=""
    fi
}

rebuild() {
    echo "[dev] $(date +%H:%M:%S) rebuild: $(uv run --locked kea build --no-pdf 2>&1 | tail -1)"
}

watcher_pid=""
trap 'trap - EXIT; stop_server; [ -n "$watcher_pid" ] && pkill -TERM -P "$watcher_pid" 2>/dev/null; [ -n "$watcher_pid" ] && kill "$watcher_pid" 2>/dev/null; exit 0' INT TERM EXIT

mkdir -p data/feedback/dev
rebuild
start_server

# Watch continuously (-m) so changes made during a rebuild are queued, not lost. The watcher runs on its own file
# descriptor with its pid recorded, so the trap can stop it. Each batch of events is drained (read with a short
# timeout) and handled with one rebuild; a restart happens if any .py file in the batch changed.
# Two watchers on one stream: doc/ and src/kea/ recursively, and the project folder (not recursively) for kea.yaml.
# kea.yaml is watched through its folder, not as a file: `sed -i` and many editors save by writing a new file and
# renaming it over the old one, and a watch on the old file would then see nothing more.
watch_changes() {
    inotifywait -m -q -r -e close_write,create,delete,move \
        --exclude '(__pycache__|\.pyc$|~$|\.swp$|\.tmp$|/sed[A-Za-z0-9]{6}$)' --format '%w%f' doc src/kea &
    inotifywait -m -q -e close_write,moved_to,create --include '(^|/)kea\.yaml$' --format '%w%f' . &
    trap 'kill $(jobs -p) 2>/dev/null' TERM
    wait
}
exec {watch_fd}< <(watch_changes | sed -u 's|^\./||')
watcher_pid=$!
while read -r -u "$watch_fd" changed_path; do
    restart_needed=0
    while :; do
        echo "[dev] change: $changed_path"
        case "$changed_path" in
            src/kea/*.py|src/kea/*/*.py) restart_needed=1 ;;
        esac
        read -r -t 0.5 -u "$watch_fd" changed_path || break
    done
    rebuild
    if [ "$restart_needed" -eq 1 ]; then
        stop_server
        start_server
    fi
done
