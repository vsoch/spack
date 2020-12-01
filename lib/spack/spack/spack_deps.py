# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)
import os
import sys

import llnl.util.filesystem as fs
import llnl.util.tty as tty

import spack.spec
import spack.store
import spack.user_environment as uenv
import spack.util.executable


def get_executable(exe, spec=None, install=False):
    """Find an executable named exe, either in PATH or in Spack

    Args:
        exe (str): needed executable name
        spec (Spec or str): spec to search for exe in (default exe)
        install (bool): install spec if not available

    When ``install`` is True, Spack will use the python used to run Spack as an
    external. The ``install`` option should only be used with packages that
    install quickly (when using external python) or are guaranteed by Spack
    organization to be in a binary mirror (clingo)."""
    # Easy, we found it externally
    # TODO: Add to externals/database?
    runner = spack.util.executable.which(exe)
    if runner:
        return runner

    # Check whether it's already installed
    spec = spack.spec.Spec(spec or exe)
    installed_specs = spack.store.db.query(spec, installed=True)
    for ispec in installed_specs:
        # TODO: make sure run-environment is appropriate
        exe_path = fs.find(ispec.prefix, exe)
        if exe_path:
            ret = spack.util.executable.Executable(exe_path[0])
            ret.add_default_envmod(
                uenv.environment_modifications_for_spec(ispec))
            return ret
        else:
            tty.warn('Exe %s not found in prefix %s' % (exe, ispec.prefix))

    # If we're not allowed to install this for ourselves, we can't find it
    if not install:
        raise Exception  # TODO specify

    # We will install for ourselves, using this python if needed
    # Concretize the spec
    python_cls = type(spack.spec.Spec('python').package)
    python_prefix = os.path.dirname(os.path.dirname(sys.executable))
    externals = python_cls.determine_spec_details(
        python_prefix, [os.path.basename(sys.executable)])
    external_python = externals[0]

    entry = {
        'buildable': False,
        'externals': [
            {'prefix': python_prefix, 'spec': str(external_python)}
        ]
    }

    with spack.config.override('packages:python::', entry):
        spec.concretize()

    spec.package.do_install()
    exe_path = fs.find(spec.prefix, exe)
    if exe_path:
        ret = spack.util.executable.Executable(exe_path[0])
        ret.add_default_envmod(
            uenv.environment_modifications_for_spec(spec))
        return ret

    raise Exception  # TODO specify
