from __future__ import annotations

import re
import shlex

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

OPTION_RE = re.compile(r"^[A-Za-z0-9_]+$")


def q(value):
    return shlex.quote(str(value))


class ActionModule(ActionBase):
    """Ensure a uci section exists with given options, over `raw`-style exec."""

    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset(
        ("config", "type", "match", "values", "state", "create", "reload")
    )

    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        del tmp

        args = self._task.args
        config = args.get("config", "firewall")
        stype = args.get("type")
        match = args.get("match") or {}
        values = args.get("values") or match
        state = args.get("state", "present")
        create = bool(args.get("create", True))
        reload_cmd = args.get(
            "reload", "/etc/init.d/%s reload >/dev/null 2>&1" % config
        )

        if not stype:
            raise AnsibleActionFail("'type' is required")
        if not match:
            raise AnsibleActionFail("'match' is required")
        if state not in ("present", "absent"):
            raise AnsibleActionFail("'state' must be present or absent")
        for key in list(match) + list(values):
            if not OPTION_RE.match(str(key)):
                raise AnsibleActionFail("invalid option name %r" % key)

        dry = 1 if self._task.check_mode else 0

        lines = [
            "set -eu",
            "cfg=%s" % q(config),
            "typ=%s" % q(stype),
            "dry=%d" % dry,
            'sect=""',
            "i=0",
            'while uci -q get "$cfg.@$typ[$i]" >/dev/null; do',
            "  ok=1",
        ]
        for key, value in match.items():
            lines.append(
                '  [ "$(uci -q get "$cfg.@$typ[$i].%s" || true)" = %s ] || ok=0'
                % (key, q(value))
            )
        lines += [
            '  if [ "$ok" = 1 ]; then sect="@$typ[$i]"; break; fi',
            "  i=$((i + 1))",
            "done",
            "changed=0",
        ]

        if state == "present":
            lines += [
                'if [ -z "$sect" ]; then',
                '  [ %d = 1 ] || { echo "no $typ section matching in $cfg" >&2; exit 1; }'
                % (1 if create else 0),
                "  changed=1",
                '  [ "$dry" = 1 ] || sect=$(uci add "$cfg" "$typ")',
                "fi",
                'if [ -n "$sect" ]; then',
            ]
            for key, value in values.items():
                lines += [
                    '  if [ "$(uci -q get "$cfg.$sect.%s" || true)" != %s ]; then'
                    % (key, q(value)),
                    '    [ "$dry" = 1 ] || uci set "$cfg.$sect.%s"=%s'
                    % (key, q(value)),
                    "    changed=1",
                    "  fi",
                ]
            lines += [
                "fi",
                'if [ "$changed" = 1 ] && [ "$dry" != 1 ]; then',
                '  uci commit "$cfg"',
                "  %s" % reload_cmd,
                "fi",
            ]
        else:
            lines += [
                'if [ -n "$sect" ]; then',
                "  changed=1",
                '  if [ "$dry" != 1 ]; then',
                '    uci delete "$cfg.$sect"',
                '    uci commit "$cfg"',
                "    %s" % reload_cmd,
                "  fi",
                "fi",
            ]

        lines.append(
            'if [ "$changed" = 1 ]; then echo CHANGED; else echo SAME; fi'
        )

        out = self._low_level_execute_command("\n".join(lines))
        if out.get("rc", 0) != 0:
            result["failed"] = True
            result["msg"] = (
                out.get("stderr") or "uci section update failed"
            ).strip()
            return result

        result["changed"] = "CHANGED" in out.get("stdout", "")
        return result
