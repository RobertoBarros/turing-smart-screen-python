#!/bin/zsh

emulate -L zsh
setopt errexit nounset pipefail
unsetopt bg_nice

readonly project_dir="${0:A:h}"
readonly python_path="${project_dir}/.venv/bin/python"
readonly monitor_path="${project_dir}/codex-monitor.py"
readonly log_path="/tmp/codex-monitor.log"
readonly pid_path="/tmp/codex-monitor.pid"
readonly action="${1:-start}"

monitor_is_running() {
  local monitor_pid="$1"
  local process_command

  [[ "${monitor_pid}" == <-> ]] || return 1
  kill -0 "${monitor_pid}" 2>/dev/null || return 1
  process_command="$(ps -p "${monitor_pid}" -o command= 2>/dev/null)" || return 1
  [[ "${process_command}" == *"${monitor_path}"* ]]
}

case "${action}" in
  start)
    if [[ ! -x "${python_path}" ]]; then
      print -u2 "codex-monitor: execute 'python3 -m venv .venv && .venv/bin/pip install -r requirements.txt'"
      exit 1
    fi

    if [[ -r "${pid_path}" ]]; then
      monitor_pid="$(<"${pid_path}")"

      if monitor_is_running "${monitor_pid}"; then
        exit 0
      fi
    fi

    cd "${project_dir}"
    nohup "${python_path}" "${monitor_path}" >>"${log_path}" 2>&1 </dev/null &
    monitor_pid=$!
    print -r -- "${monitor_pid}" >"${pid_path}"
    ;;
  stop)
    if [[ ! -r "${pid_path}" ]]; then
      print "codex-monitor: não está em execução"
      exit 0
    fi

    monitor_pid="$(<"${pid_path}")"

    if monitor_is_running "${monitor_pid}"; then
      kill "${monitor_pid}"
    fi

    rm -f "${pid_path}"
    ;;
  *)
    print -u2 "uso: ${0:t} {start|stop}"
    exit 2
    ;;
esac
