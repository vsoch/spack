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

import os


class Clingo(AnalyzerBase):

    name = "clingo"
    outfile = "abi-facts.lp"
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
        main = manifest['binary_to_relocate_fullpath']

        # We need the compiler too
        compiler = which(spec.compiler.name).path
        compilers = {compiler}

        # Find all needed libraries
        libs = []
        for dep in spec.dependencies():
            manifest = spack.binary_distribution.get_buildfile_manifest(dep)
            libs += manifest['binary_to_relocate_fullpath']
            compiler = which(dep.compiler.name).path
            compilers.add(compiler)

        # Generate facts, writing to file as we go
        outfile = os.path.join(self.output_dir, self.outfile)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        libs += list(compilers)
        generate_facts(main, libs, outfile)
        return {self.name: outfile}

    def save_result(self, result, overwrite=False):
        """
        Read saved fact results and upload to monitor server.

        We haven't written this yet because we don't know what we would want
        to upload.
        """
        pass
