"""Securely edit encrypted secret files."""
import os
import pathlib
import subprocess
import sys
import tempfile

from .encryption import EncryptedConfigFile


class Editor(object):
    def __init__(self, editor_cmd, environment, edit_file=None):
        self.editor_cmd = editor_cmd
        self.environment = environment
        environment_path = pathlib.Path("environments") / environment
        self.encrypted_configfile = environment_path / "secrets.cfg"

        if edit_file is None:
            self.edit_file = self.encrypted_configfile
        else:
            self.edit_file = environment_path / f"secret-{edit_file}"

    def main(self):
        with EncryptedConfigFile(
            self.encrypted_configfile,
            add_files_for_env=self.environment,
            write_lock=True,
        ) as configfile:
            self.configfile = configfile

            # Add the requested file to edit to the session, this might be
            # a new file.
            self.editing = configfile.add_file(self.edit_file)
            with self.editing as f:
                f.read()
                self.cleartext = self.original_cleartext = f.cleartext

            self.interact()

    def _input(self):
        return input("> ").strip()

    def interact(self):
        cmd = "edit"
        while cmd != "quit":
            try:
                self.process_cmd(cmd)
            except Exception as e:
                print()
                print()
                print("An error occurred: {}".format(e))
                print()
                print("Your changes are still available. You can try:")
                print("\tedit       -- opens editor with current data again")
                print("\tencrypt    -- tries to encrypt current data again")
                print("\tquit       -- quits and loses your changes")
                cmd = self._input()
            else:
                break

    def process_cmd(self, cmd):
        if cmd == "edit":
            self.edit()
            self.encrypt()
        elif cmd == "encrypt":
            self.encrypt()
        else:
            raise ValueError("unknown command `{}`".format(cmd))

    def encrypt(self):
        if (
            self.cleartext == self.original_cleartext
            and not self.editing.is_new
        ):
            print("No changes from original cleartext. Not updating.")
            return
        self.editing.cleartext = self.cleartext
        # In case we are editing the main file, this causes a re-read
        # of the membership and re-serialization, so we are sure the file
        # is syntactically correct.
        self.configfile.read()
        # Write and (re-encrypt) _all_ files, in case the membership has
        # changed.
        self.configfile.write()

    def edit(self):
        _, suffix = os.path.splitext(self.edit_file)
        with tempfile.NamedTemporaryFile(
            prefix="edit", suffix=suffix, mode="w+", encoding="utf-8"
        ) as clearfile:
            clearfile.write(self.cleartext)
            clearfile.flush()

            subprocess.check_call(
                [self.editor_cmd + " " + clearfile.name], shell=True
            )

            with open(clearfile.name, "r") as new_clearfile:
                self.cleartext = new_clearfile.read()


def main(editor, environment, edit_file=None, **kw):
    """Secrets editor console script.

    The main focus here is to avoid having unencrypted files accidentally
    ending up in the deployment repository.

    """
    environments_path = pathlib.Path("environments")
    if not (environments_path / environment / "environment.cfg").exists():
        print(f"Environment {environment!r} does not exist. Typo?")
        print("Existing environments:")
        print("\n".join(x.name for x in environments_path.iterdir()))
        sys.exit(1)

    editor = Editor(editor, environment, edit_file)
    editor.main()
