from __future__ import annotations

import hashlib
import re
import shlex

from ansible.errors import AnsibleActionFail
from ansible.plugins.action import ActionBase

HEREDOC = "ANSIBLE_OPENWRT_EOF"
NUMERIC_MODE = re.compile(r"^0?[0-7]{3,4}$")

# BusyBox here has no stat(1), so permissions are read back from ls -ld.
_RWX = (
    ("r", 0o400),
    ("w", 0o200),
    ("x", 0o100),
    ("r", 0o040),
    ("w", 0o020),
    ("x", 0o010),
    ("r", 0o004),
    ("w", 0o002),
    ("x", 0o001),
)
_SPECIAL = ((2, 0o4000, 0o100), (5, 0o2000, 0o010), (8, 0o1000, 0o001))


def perms_to_octal(listing):
    if len(listing) < 10:
        return None
    bits = listing[1:10]
    value = 0
    for char, (expected, bit) in zip(bits, _RWX):
        if char == expected:
            value |= bit
    for index, special, executable in _SPECIAL:
        if bits[index] in ("s", "S", "t", "T"):
            value |= special
            if bits[index].islower():
                value |= executable
    return value


def probe_command(quoted):
    return (
        "printf 'md5=%s\\n' \"$(md5sum "
        + quoted
        + " 2>/dev/null | cut -d' ' -f1)\"; "
        "printf 'perm=%s\\n' \"$(ls -ld "
        + quoted
        + ' 2>/dev/null | cut -c1-10)"'
    )


def parse_probe(result):
    data = {}
    for line in result.get("stdout", "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            data[key.strip()] = value.strip()
    return data


class ActionModule(ActionBase):
    """Write a file over `raw`-style exec, for targets without Python."""

    TRANSFERS_FILES = False
    _VALID_ARGS = frozenset(("path", "content", "mode", "state"))

    def run(self, tmp=None, task_vars=None):
        result = super().run(tmp, task_vars)
        del tmp

        path = self._task.args.get("path")
        content = self._task.args.get("content")
        mode = self._task.args.get("mode")
        state = self._task.args.get("state", "present")

        if not path:
            raise AnsibleActionFail("'path' is required")
        if state not in ("present", "absent"):
            raise AnsibleActionFail("'state' must be present or absent")

        quoted = shlex.quote(path)
        result["path"] = path

        if state == "absent":
            before = parse_probe(
                self._low_level_execute_command(probe_command(quoted))
            )
            result["changed"] = bool(before.get("perm"))
            if result["changed"] and not self._task.check_mode:
                removed = self._low_level_execute_command("rm -f %s" % quoted)
                if removed.get("rc", 0) != 0:
                    result["failed"] = True
                    result["msg"] = (
                        removed.get("stderr") or "failed to remove %s" % path
                    )
            return result

        if content is None:
            raise AnsibleActionFail(
                "'content' is required when state is present"
            )

        mode = None if mode is None else str(mode)

        # lookup() strips the trailing newline; normalise so the hash matches what we write.
        if not content.endswith("\n"):
            content += "\n"
        if HEREDOC in content:
            raise AnsibleActionFail("content must not contain %s" % HEREDOC)

        digest = hashlib.md5(content.encode("utf-8")).hexdigest()

        before = parse_probe(
            self._low_level_execute_command(probe_command(quoted))
        )
        current_perms = perms_to_octal(before.get("perm", ""))

        content_changed = before.get("md5", "") != digest
        numeric = mode is not None and bool(NUMERIC_MODE.match(mode))
        mode_changed = numeric and current_perms != int(mode, 8)

        result["checksum"] = digest

        if self._task.check_mode:
            result["changed"] = content_changed or mode_changed
            return result

        if content_changed:
            write = self._low_level_execute_command(
                "cat > %s <<'%s'\n%s%s" % (quoted, HEREDOC, content, HEREDOC)
            )
            if write.get("rc", 0) != 0:
                result["failed"] = True
                result["msg"] = (
                    write.get("stderr") or "failed to write %s" % path
                )
                return result

        if mode is not None and (
            mode_changed or content_changed or not numeric
        ):
            chmod = self._low_level_execute_command(
                "chmod %s %s" % (shlex.quote(mode), quoted)
            )
            if chmod.get("rc", 0) != 0:
                result["failed"] = True
                result["msg"] = (
                    chmod.get("stderr") or "failed to chmod %s" % path
                )
                return result
            if not numeric:
                # A symbolic mode cannot be predicted, so detect the change by re-reading.
                after = parse_probe(
                    self._low_level_execute_command(probe_command(quoted))
                )
                mode_changed = (
                    perms_to_octal(after.get("perm", "")) != current_perms
                )

        result["changed"] = content_changed or mode_changed
        return result
