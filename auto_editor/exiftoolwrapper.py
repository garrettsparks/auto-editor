from __future__ import annotations

import os.path
import subprocess
import sys
from re import search
from subprocess import PIPE, Popen
from typing import Any

from auto_editor.utils.func import get_stdout
from auto_editor.utils.log import Log


class ExifTool:
    __slots__ = ("debug", "show_cmd", "path", "version")

    def __init__(
        self,
        show_cmd: bool = False,
        debug: bool = False,
    ):
        self.show_cmd = show_cmd
        self.debug = debug
        self.path = "exiftool"

        try:
            _version = get_stdout([self.path, "-ver"]).split("\n")[0]
            self.version = _version
        except FileNotFoundError:
            if sys.platform == "darwin":
                Log().error("No exiftool found. Download via homebrew.")
            if sys.platform == "win32":
                Log().error("No exiftool found. Go download it.")

            Log().error("exiftool must be installed an on PATH")

    def print(self, message: str) -> None:
        if self.debug:
            sys.stderr.write(f"ExifTool: {message}\n")

    def print_cmd(self, cmd: list[str]) -> None:
        if self.show_cmd:
            sys.stderr.write(f"{' '.join(cmd)}\n\n")

    def run(self, cmd: list[str]) -> None:
        cmd = [self.path, "-m", "-overwrite_original"]
        if not self.debug:
            cmd.extend(["-quiet"])
        self.print_cmd(cmd)
        subprocess.run(cmd)

    def run_check_errors(
        self,
        cmd: list[str],
        log: Log,
        show_out: bool = False,
        path: str | None = None,
    ) -> None:
        process = self.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        _, stderr = process.communicate()

        if process.stdin is not None:
            process.stdin.close()
        output = stderr.decode("utf-8", "replace")

        error_list = (r"Permission denied",)

        if self.debug:
            print(f"stderr: {output}")

        for item in error_list:
            if check := search(item, output):
                log.error(check.group())

        if path is not None and not os.path.isfile(path):
            log.error(f"The file {path} was not created.")
        elif show_out and not self.debug:
            print(f"stderr: {output}")

    def Popen(
        self, cmd: list[str], stdin: Any = None, stdout: Any = PIPE, stderr: Any = None
    ) -> Popen:
        cmd = [self.path] + cmd
        self.print_cmd(cmd)
        return Popen(
            " ".join(cmd), shell=True, stdin=stdin, stdout=stdout, stderr=stderr
        )

    def pipe(self, cmd: list[str]) -> str:
        cmd = [self.path] + cmd

        self.print_cmd(cmd)
        output = get_stdout(cmd)
        self.print(output)
        return output
