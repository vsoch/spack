# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from __future__ import print_function

import argparse
import os
import re
import sys

import llnl.util.tty as tty
import llnl.util.tty.color as color
from llnl.util.filesystem import working_dir

import spack.bootstrap
import spack.paths
from spack.util.executable import which

if sys.version_info < (3, 0):
    from itertools import izip_longest  # novm

    zip_longest = izip_longest
else:
    from itertools import zip_longest  # novm


description = "runs source code style checks on spack"
section = "developer"
level = "long"


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    for group in zip_longest(*args, fillvalue=fillvalue):
        yield filter(None, group)


#: directory where spack style started, for relativizing paths
initial_working_dir = None

#: List of directories to exclude from checks.
exclude_directories = [spack.paths.external_path]

#: order in which tools should be run. flake8 is last so that it can
#: double-check the results of other tools (if, e.g., --fix was provided)
tool_order = ["isort", "mypy", "black", "flake8"]
tool_versions = {"isort": "4.3.5", "mypy": "0.910"}

#: tools we run in spack style
tools = {}


def is_package(f):
    """Whether flake8 should consider a file as a core file or a package.

    We run flake8 with different exceptions for the core and for
    packages, since we allow `from spack import *` and poking globals
    into packages.
    """
    return f.startswith("var/spack/repos/") or "docs/tutorial/examples" in f


#: decorator for adding tools to the list
class tool(object):
    def __init__(self, name, required=False):
        self.name = name
        self.required = required

    def __call__(self, fun):
        tools[self.name] = (fun, self.required)
        return fun


def changed_files(base=None, untracked=True, all_files=False):
    """Get list of changed files in the Spack repository."""

    git = which("git", required=True)

    # GITHUB_BASE_REF is set to the base branch for pull request actions
    if base is None:
        base = os.environ.get("GITHUB_BASE_REF", "develop")

    range = "{0}...".format(base)

    git_args = [
        # Add changed files committed since branching off of develop
        ["diff", "--name-only", "--diff-filter=ACMR", range],
        # Add changed files that have been staged but not yet committed
        ["diff", "--name-only", "--diff-filter=ACMR", "--cached"],
        # Add changed files that are unstaged
        ["diff", "--name-only", "--diff-filter=ACMR"],
    ]

    # Add new files that are untracked
    if untracked:
        git_args.append(["ls-files", "--exclude-standard", "--other"])

    # add everything if the user asked for it
    if all_files:
        git_args.append(["ls-files", "--exclude-standard"])

    excludes = [os.path.realpath(f) for f in exclude_directories]
    changed = set()

    for arg_list in git_args:
        files = git(*arg_list, output=str).split("\n")

        for f in files:
            # Ignore non-Python files
            if not (f.endswith(".py") or f == "bin/spack"):
                continue

            # Ignore files in the exclude locations
            if any(os.path.realpath(f).startswith(e) for e in excludes):
                continue

            changed.add(f)

    return sorted(changed)


def setup_parser(subparser):
    subparser.add_argument(
        "-b",
        "--base",
        action="store",
        default=None,
        help="select base branch for collecting list of modified files",
    )
    subparser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="check all files, not just changed files",
    )
    subparser.add_argument(
        "-r",
        "--root-relative",
        action="store_true",
        default=False,
        help="print root-relative paths (default: cwd-relative)",
    )
    subparser.add_argument(
        "-U",
        "--no-untracked",
        dest="untracked",
        action="store_false",
        default=True,
        help="exclude untracked files from checks",
    )
    subparser.add_argument(
        "-f",
        "--fix",
        action="store_true",
        default=False,
        help="format automatically if possible (e.g., with isort, black)",
    )
    subparser.add_argument(
        "--no-isort",
        dest="isort",
        action="store_false",
        help="do not run isort (default: run isort if available)",
    )
    subparser.add_argument(
        "--no-flake8",
        dest="flake8",
        action="store_false",
        help="do not run flake8 (default: run flake8 or fail)",
    )
    subparser.add_argument(
        "--no-mypy",
        dest="mypy",
        action="store_false",
        help="do not run mypy (default: run mypy if available)",
    )
    subparser.add_argument(
        "--black",
        dest="black",
        action="store_true",
        help="run black if available (default: skip black)",
    )
    subparser.add_argument(
        "files", nargs=argparse.REMAINDER, help="specific files to check"
    )


def cwd_relative(path):
    """Translate prefix-relative path to current working directory-relative."""
    return os.path.relpath(os.path.join(spack.paths.prefix, path), initial_working_dir)


def rewrite_and_print_output(
    output, args, re_obj=re.compile(r"^(.+):([0-9]+):"), replacement=r"{0}:{1}:"
):
    """rewrite ouput with <file>:<line>: format to respect path args"""
    # print results relative to current working directory
    def translate(match):
        return replacement.format(
            cwd_relative(match.group(1)), *list(match.groups()[1:])
        )

    for line in output.split("\n"):
        if not line:
            continue
        if not args.root_relative and re_obj:
            line = re_obj.sub(translate, line)
        print("  " + line)


def print_style_header(file_list, args):
    tools = [tool for tool in tool_order if getattr(args, tool)]
    tty.msg("Running style checks on spack:", "selected: " + ", ".join(tools))

    # translate modified paths to cwd_relative if needed
    paths = [filename.strip() for filename in file_list]
    if not args.root_relative:
        paths = [cwd_relative(filename) for filename in paths]

    tty.msg("Modified files:", *paths)
    sys.stdout.flush()


def print_tool_header(tool):
    sys.stdout.flush()
    tty.msg("Running %s checks" % tool)
    sys.stdout.flush()


def print_tool_result(tool, returncode):
    if returncode == 0:
        color.cprint("  @g{%s checks were clean}" % tool)
    else:
        color.cprint("  @r{%s found errors}" % tool)


@tool("flake8", required=True)
def run_flake8(flake8_cmd, file_list, args):
    returncode = 0
    output = ""
    # run in chunks of 100 at a time to avoid line length limit
    # filename parameter in config *does not work* for this reliably
    for chunk in grouper(file_list, 100):

        output = flake8_cmd(
            # use .flake8 implicitly to work around bug in flake8 upstream
            # append-config is ignored if `--config` is explicitly listed
            # see: https://gitlab.com/pycqa/flake8/-/issues/455
            # "--config=.flake8",
            *chunk,
            fail_on_error=False,
            output=str
        )
        returncode |= flake8_cmd.returncode

        rewrite_and_print_output(output, args)

    print_tool_result("flake8", returncode)
    return returncode


@tool("mypy")
def run_mypy(mypy_cmd, file_list, args):
    mpy_args = ["--package", "spack", "--package", "llnl", "--show-error-codes"]
    # not yet, need other updates to enable this
    # if any([is_package(f) for f in file_list]):
    #     mpy_args.extend(["--package", "packages"])

    output = mypy_cmd(*mpy_args, fail_on_error=False, output=str)
    returncode = mypy_cmd.returncode

    rewrite_and_print_output(output, args)

    print_tool_result("mypy", returncode)
    return returncode


@tool("isort")
def run_isort(isort_cmd, file_list, args):
    check_fix_args = () if args.fix else ("--check", "--diff")

    pat = re.compile("ERROR: (.*) Imports are incorrectly sorted")
    replacement = "ERROR: {0} Imports are incorrectly sorted"
    returncode = 0
    for chunk in grouper(file_list, 100):
        packed_args = check_fix_args + tuple(chunk)
        output = isort_cmd(*packed_args, fail_on_error=False, output=str, error=str)
        returncode |= isort_cmd.returncode

        rewrite_and_print_output(output, args, pat, replacement)

    print_tool_result("isort", returncode)
    return returncode


@tool("black")
def run_black(black_cmd, file_list, args):
    check_fix_args = () if args.fix else ("--check", "--diff", "--color")

    pat = re.compile("would reformat +(.*)")
    replacement = "would reformat {0}"
    returncode = 0
    output = ""
    # run in chunks of 100 at a time to avoid line length limit
    # filename parameter in config *does not work* for this reliably
    for chunk in grouper(file_list, 100):
        packed_args = check_fix_args + tuple(chunk)
        output = black_cmd(*packed_args, fail_on_error=False, output=str, error=str)
        returncode |= black_cmd.returncode

        rewrite_and_print_output(output, args, pat, replacement)

    print_tool_result("black", returncode)
    return returncode


def style(parser, args):
    # save initial working directory for relativizing paths later
    global initial_working_dir
    initial_working_dir = os.getcwd()

    file_list = args.files
    if file_list:

        def prefix_relative(path):
            return os.path.relpath(
                os.path.abspath(os.path.realpath(path)), spack.paths.prefix
            )

        file_list = [prefix_relative(p) for p in file_list]

    returncode = 0
    with working_dir(spack.paths.prefix):
        if not file_list:
            file_list = changed_files(args.base, args.untracked, args.all)
        print_style_header(file_list, args)

        # run tools in order defined in tool_order
        returncode = 0
        for tool_name in tool_order:
            if getattr(args, tool_name):
                run_function, required = tools[tool_name]
                print_tool_header(tool_name)
                tool_binary = tool_name

                # Some tools have a required version
                if tool_name in tool_versions:
                    tool_name = "%s@%s" % (tool_name, tool_versions[tool_name])

                # Bootstrap tools so we don't need to require install
                with spack.bootstrap.ensure_bootstrap_configuration():
                    spec = spack.spec.Spec("py-%s" % tool_name)
                    cmd = spack.bootstrap.get_executable(tool_binary, spec=spec,
                                                         install=True)
                    if not cmd:
                        color.cprint("  @y{%s not in PATH, skipped}" % tool_name)
                        continue

                returncode |= run_function(cmd, file_list, args)

    if returncode == 0:
        tty.msg(color.colorize("@*{spack style checks were clean}"))
    else:
        tty.error(color.colorize("@*{spack style found errors}"))

    return returncode
