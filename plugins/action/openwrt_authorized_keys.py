from __future__ import annotations

import shlex

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):
    """Append missing authorized keys. Existing entries are never removed."""

    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset(("path", "keys"))

    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        del tmp

        path = self._task.args.get("path")
        keys = self._task.args.get("keys")

        if not path:
            raise AnsibleActionFail("'path' is required")
        if not keys:
            raise AnsibleActionFail("'keys' is required")
        if isinstance(keys, str):
            keys = [keys]

        entries = []
        for key in keys:
            key = str(key).strip()
            if not key or key.startswith("#"):
                continue
            fields = key.split()
            if len(fields) < 2:
                raise AnsibleActionFail("malformed public key: %r" % key)
            # Identify by the base64 blob so a differing comment is not a second key.
            entries.append((fields[1], key))

        if not entries:
            result["changed"] = False
            return result

        dry = 1 if self._task.check_mode else 0
        lines = [
            "set -eu",
            "dest=%s" % shlex.quote(path),
            "dry=%d" % dry,
            'if [ "$dry" != 1 ]; then',
            '  mkdir -p "$(dirname "$dest")"',
            '  [ -e "$dest" ] || : > "$dest"',
            # Command substitution strips a trailing newline, so non-empty means it lacks one.
            '  if [ -s "$dest" ] && [ -n "$(tail -c 1 "$dest")" ]; then echo >> "$dest"; fi',
            "fi",
            "changed=0",
        ]
        for blob, key in entries:
            lines += [
                'if ! grep -qF %s "$dest" 2>/dev/null; then'
                % shlex.quote(blob),
                '  [ "$dry" = 1 ] || printf \'%%s\\n\' %s >> "$dest"'
                % shlex.quote(key),
                "  changed=1",
                "fi",
            ]
        lines += [
            # Enforce the mode on every run: sshd's StrictModes rejects a loose
            # authorized_keys, and that must be repaired even when no key was added.
            'if [ "$dry" != 1 ]; then',
            '  before=$(ls -ld "$dest" | cut -c1-10)',
            '  chmod 0600 "$dest"',
            '  [ "$before" = "$(ls -ld "$dest" | cut -c1-10)" ] || changed=1',
            "fi",
            'if [ "$changed" = 1 ]; then echo CHANGED; else echo SAME; fi',
        ]

        out = self._low_level_execute_command("\n".join(lines))
        if out.get("rc", 0) != 0:
            result["failed"] = True
            result["msg"] = (
                out.get("stderr") or "failed to update %s" % path
            ).strip()
            return result

        result["path"] = path
        result["changed"] = "CHANGED" in out.get("stdout", "")
        return result
