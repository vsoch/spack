# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

"""The Clingo analyzer will write complete facts (atoms) for an install, meaning
Dwarf Information Entities (DIEs) that can be generalized, and ELF symbols, for
usage with an ABI analyzer or other."""


import spack.monitor
import spack.binary_distribution
import spack.spec
from spack.util.executable import which
from ..analyzer_base import AnalyzerBase
import llnl.util.tty as tty
import os


class Clingo(AnalyzerBase):

    name = "clingo"

    # This outfile is just used as a prefix
    outfile = "abi-facts"
    description = "Dwarf and ELF Symbols in a logic program for a library."

    def run(self):
        """
        Prepare pyelftools for usage, load the spec, and generate facts.

        We write it out to the analyzers folder, with key as the analyzer name.
        """
        from .asp import generate_facts
        # We need to load the spec in order to find all dependencies
        spec_file = os.path.join(self.meta_dir, "spec.yaml")
        with open(spec_file, 'r') as fd:
            spec = spack.spec.Spec.from_yaml(fd.read())

        # The manifest includes the spec binar(y|(ies)
        # We extract facts for all binaries, even if they get used separately
        # We also keep track of these "main" binaries that are being assessed
        manifest = spack.binary_distribution.get_buildfile_manifest(spec)
        mains = manifest['binary_to_relocate_fullpath']

        # We need the compiler too
        compiler = which(spec.compiler.name).path
        compilers = {compiler}

        # Find all needed libraries and compilers, used for all mains
        libs = []
        for dep in spec.dependencies():
            manifest = spack.binary_distribution.get_buildfile_manifest(dep)
            libs += manifest['binary_to_relocate_fullpath']
            compiler = which(dep.compiler.name).path
            compilers.add(compiler)
        libs += list(compilers)

        # Create the output directory if it doesn't exist.
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Generate a separate set of facts for each main binary
        results = {}
        for main in mains:
            tty.info("Generating facts for %s" % main)
            bn = os.path.basename(main)
            outfile = os.path.join(self.output_dir, "%s-%s.lp" % (self.outfile, bn))
            generate_facts(main, libs, outfile)
            results[main] = outfile
        return {self.name: results}

    def save_result(self, result, overwrite=False):
        """
        Read saved fact results and upload to monitor server.

        We haven't written this yet because we don't know what we would want
        to upload.
        """
        pass
