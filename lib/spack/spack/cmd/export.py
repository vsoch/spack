# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from __future__ import print_function

import os
import sys

import llnl.util.tty as tty
import spack.repo
import spack.cmd as cmd
from spack.cmd.find import query_arguments

import spack.user_environment as uenv
import spack.util.spack_json as sjson

description = "export installed packages"
section = "basic"
level = "short"


def export(parser, args):
    """export is similar to find, except we map packages to an export schema,
    which also includes compilers and some metadata, and instead of a lookup
    (dict) of packages, we have a list with an added name attribute
    """
    q_args = query_arguments(args)
    results = args.specs(**q_args)

    # Exit early with an error code if no package matches the constraint
    if not results and args.constraint:
        msg = "No packages match the query: {0}"
        msg = msg.format(' '.join(args.constraint))
        tty.msg(msg)
        return 1

    # Generate the export, includes _meta, compilers, specs
    export = generate_export(
        results,
        loaded=args.loaded,
        tags=args.tags,
    )

    # Display the result
    sjson.dump(export, sys.stdout)


def generate_export_metadata():
    return {"spack-version": spack.spack_version}


def generate_export(results, loaded=False, tags=None, scope=None):
    """Generate an export based on the exports.py schema. This means a dict.
    with keys for compilers, specs, and _meta. A starting set of results
    must be provided.
    """
    # If tags have been specified on the command line, filter by tags
    if tags:
        packages_with_tags = spack.repo.path.packages_with_tags(*tags)
        results = [x for x in results if x.name in packages_with_tags]

    if loaded:
        hashes = os.environ.get(uenv.spack_loaded_hashes_var, '').split(':')
        results = [x for x in results if x.dag_hash() in hashes]

    # Include metadata, specs, and compilers
    return {
        "_meta": generate_export_metadata(),
        "specs": cmd.get_specs_as_dict(results, deps=True),
        "compilers": spack.compilers.all_compilers_list(scope=scope)
    }
