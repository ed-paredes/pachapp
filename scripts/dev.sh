#!/usr/bin/env bash
# Run the whole local stack (API + worker + Expo) in one terminal.
#
#   scripts/dev.sh web     start the three processes with prefixed logs
#   scripts/dev.sh phone   same, bound to the LAN IP of EXPO_PUBLIC_API_BASE_URL,
#                          then check the phone can reach the PC
#   scripts/dev.sh check   only the LAN preflight against running services
#
# Normally called through `make dev`, `make dev-phone` and `make dev-phone-check`,
# which pass the settings below (already resolved from the ENV_FILE).
#
# Settings (environment):
#   DEV_ENV_FILE       dotenv file the child `make` targets read (default .env)
#   DEV_API_PORT       API port (default 8000)
#   DEV_EXPO_PORT      Metro/Expo port (default 8081)
#   DEV_API_URL        EXPO_PUBLIC_API_BASE_URL; its host is the LAN IP (phone/check)
#   DEV_API_CMD, DEV_WORKER_CMD, DEV_UI_CMD
#                      override the child commands (default: make run, run-worker,
#                      run-ui); used to test this script without the real stack.
set -uo pipefail

mode="${1:-web}"
env_file="${DEV_ENV_FILE:-.env}"
api_port="${DEV_API_PORT:-8000}"
expo_port="${DEV_EXPO_PORT:-8081}"
api_url="${DEV_API_URL:-}"
ready_timeout="${DEV_READY_TIMEOUT:-300}"

make_cmd() { printf 'make --no-print-directory %s ENV_FILE=%q EXPO_PORT=%q' "$1" "$env_file" "$expo_port"; }
api_cmd="${DEV_API_CMD:-$(make_cmd run)}"
worker_cmd="${DEV_WORKER_CMD:-$(make_cmd run-worker)}"
ui_cmd="${DEV_UI_CMD:-$(make_cmd run-ui)}"

if [[ -t 1 ]]; then
	c_api=$'\033[36m'; c_worker=$'\033[35m'; c_ui=$'\033[33m'
	c_ok=$'\033[32m'; c_bad=$'\033[31m'; c_bold=$'\033[1m'; c_off=$'\033[0m'
else
	c_api=''; c_worker=''; c_ui=''; c_ok=''; c_bad=''; c_bold=''; c_off=''
fi

say() { printf '%s\n' "$*"; }

# --- LAN helpers ---------------------------------------------------------

lan_ip() {
	# http://192.168.1.41:8000 -> 192.168.1.41
	local rest="${api_url#*://}"
	rest="${rest%%/*}"
	printf '%s' "${rest%%:*}"
}

lan_api_port() {
	local rest="${api_url#*://}"
	rest="${rest%%/*}"
	if [[ "$rest" == *:* ]]; then printf '%s' "${rest##*:}"; else printf '80'; fi
}

http_ok() { curl -fsS -m 3 -o /dev/null "$1" 2>/dev/null; }

print_fix() {
	local ip="$1" wsl_ip
	wsl_ip="$(hostname -I | awk '{print $1}')"
	cat <<FIX

${c_bad}${c_bold}The phone cannot reach this PC yet.${c_off} Open PowerShell as Administrator on Windows and run:

  Set-NetConnectionProfile -InterfaceAlias "Ethernet 3" -NetworkCategory Private
  netsh interface portproxy reset
  netsh interface portproxy add v4tov4 listenaddress=$ip listenport=$api_lan_port connectaddress=$wsl_ip connectport=$api_lan_port
  netsh interface portproxy add v4tov4 listenaddress=$ip listenport=$expo_port connectaddress=$wsl_ip connectport=$expo_port
  Restart-Service iphlpsvc
  netstat -ano | Select-String "$ip:80"

(WSL IP right now: $wsl_ip. It changes when WSL restarts, so re-run this after a Windows reboot.)
The stack keeps running, so the web app on http://localhost:$expo_port still works.
Check again any time with: make dev-phone-check
FIX
}

# Prints the banner and returns 0 when both ports answer on the LAN IP; otherwise
# prints the fix and returns 1.
preflight() {
	local ip="$1" ok=0
	api_lan_port="$(lan_api_port)"
	say "Checking the phone route via $ip ..."
	if http_ok "http://$ip:$api_lan_port/health"; then
		say "  ${c_ok}ok${c_off}   http://$ip:$api_lan_port/health"
	else
		say "  ${c_bad}FAIL${c_off} http://$ip:$api_lan_port/health"; ok=1
	fi
	if http_ok "http://$ip:$expo_port/status"; then
		say "  ${c_ok}ok${c_off}   http://$ip:$expo_port"
	else
		say "  ${c_bad}FAIL${c_off} http://$ip:$expo_port"; ok=1
	fi
	if ((ok == 0)); then
		cat <<BANNER

${c_ok}${c_bold}Phone ready.${c_off} In Expo Go choose "Enter URL manually" and type:

    ${c_bold}exp://$ip:$expo_port${c_off}

(or scan the QR code Expo prints). Phone and PC must be on the same Wi-Fi.
BANNER
		return 0
	fi
	print_fix "$ip"
	return 1
}

# --- modes ---------------------------------------------------------------

case "$mode" in
web | phone | check) ;;
*) say "usage: $0 web|phone|check" >&2; exit 2 ;;
esac

if [[ "$mode" != web ]]; then
	ip="$(lan_ip)"
	if [[ -z "$ip" ]]; then
		say "error: EXPO_PUBLIC_API_BASE_URL is empty in $env_file; it must be http://<LAN IP>:<port>." >&2
		exit 1
	fi
fi

if [[ "$mode" == check ]]; then
	preflight "$ip"
	exit $?
fi

[[ "$mode" == phone ]] && export REACT_NATIVE_PACKAGER_HOSTNAME="$ip"
export PYTHONUNBUFFERED=1

# --- process management --------------------------------------------------

names=()
pids=()
watcher=""
stopping=0

# Starts "$2" in its own session (so one signal reaches uvicorn's reloader,
# npm and node alike) with every output line prefixed by "[$1]".
start() {
	local name="$1" cmd="$2" color="$3"
	setsid bash -c "$cmd" > >(sed -u "s|^|${color}[${name}]${c_off} |") 2>&1 &
	names+=("$name")
	pids+=("$!")
}

stop_all() {
	((stopping)) && return
	stopping=1
	trap '' INT TERM
	[[ -n "$watcher" ]] && kill "$watcher" 2>/dev/null
	local pid
	for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null; done
	# Give them a few seconds, then force what is left.
	local i
	for i in {1..50}; do
		local alive=0
		for pid in "${pids[@]}"; do kill -0 -- "-$pid" 2>/dev/null && alive=1; done
		((alive)) || break
		sleep 0.1
	done
	for pid in "${pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null; done
	wait 2>/dev/null
}

on_signal() {
	say ""
	say "Stopping api, worker and ui ..."
	stop_all
	exit 130
}
trap on_signal INT TERM

start api "$api_cmd" "$c_api"
start worker "$worker_cmd" "$c_worker"
start ui "$ui_cmd" "$c_ui"

if [[ "$mode" == phone ]]; then
	(
		deadline=$((SECONDS + ready_timeout))
		until http_ok "http://localhost:$api_port/health" && http_ok "http://localhost:$expo_port/status"; do
			((SECONDS > deadline)) && { say "[dev] api/ui did not answer on localhost in ${ready_timeout}s; run make dev-phone-check once they are up."; exit 1; }
			sleep 1
		done
		preflight "$ip"
	) &
	watcher=$!
fi

# Wait until any of the three exits, then stop the rest and return its code.
while :; do
	for i in "${!pids[@]}"; do
		if ! kill -0 "${pids[$i]}" 2>/dev/null; then
			wait "${pids[$i]}"
			code=$?
			say "${c_bad}[dev] ${names[$i]} exited (code $code); stopping the others.${c_off}"
			stop_all
			exit "$code"
		fi
	done
	sleep 1
done
