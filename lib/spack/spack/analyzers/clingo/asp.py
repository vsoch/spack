# This is based on asp.py from spack/spack, copyright LLNL and spack developers
# It will eventually be added back to that scope - this script is developing
# new functionality to work with ABI.

import hashlib
import itertools
import os
import re

try:
    import elftools
except ImportError:
    elftools = None

from .corpus import Corpus, et
from spack.solver.asp import AspFunction, AspFunctionBuilder
from spack.util.executable import which
import spack.solver.asp
import spack.main

fn = AspFunctionBuilder()


# only parse these tags
parse_tags = {"dw_tag_subprogram", "dw_tag_formal_parameter", "dw_tag_function"}


class ABIFactGenerator(object):
    """Class to set up and generate corpus ABI facts."""

    def __init__(self, gen):
        self.gen = gen

        # A lookup of DIEs based on corpus path (first key) and id
        # (second key) DIE == Dwarf Information Entry
        self.die_lookup = {}

        # Filter down originally to needed symbols for smaller output
        self.needed_symbols = set()

        # A lookup of DIE children ids
        self.child_lookup = {}
        self.language = None

        global elftools

        if not elftools:
            with spack.bootstrap.ensure_bootstrap_configuration():
                spec = spack.spec.Spec("py-pyelftools")
                spec.concretize()
                spack.bootstrap.make_module_available(
                    'elftools', spec=spec, install=True
                )
                import elftools

    def generate_elf_symbols(self, corpora):
        """For each corpus, write out elf symbols as facts.
        """
        for corpus in corpora:
            self.gen.h2("Corpus symbols: %s" % corpus.path)

            for symbol, meta in corpus.elfsymbols.items():

                # It begins with a NULL symbol, not sure it's useful
                if not symbol or symbol not in self.needed_symbols:
                    continue

                # Prepare variables
                vinfo = meta['version_info']
                vis = meta['visibility']
                defined = meta['defined']

                # If the symbol has @@ in the name, it includes the version.
                if "@@" in symbol and not vinfo:
                    symbol, vinfo = symbol.split('@', 1)

                self.gen.fact(fn.symbol(symbol))
                self.gen.fact(fn.symbol_type(corpus.path, symbol, meta['type']))
                self.gen.fact(fn.symbol_version(corpus.path, symbol, vinfo))
                self.gen.fact(fn.symbol_binding(corpus.path, symbol, meta['binding']))
                self.gen.fact(fn.symbol_visibility(corpus.path, symbol, vis))
                self.gen.fact(fn.symbol_definition(corpus.path, symbol, defined))
                self.gen.fact(fn.has_symbol(corpus.path, symbol))

    def bytes2str(self, item):
        return elftools.common.py3compat.bytes2str(item)

    def _die_hash(self, die, corpus, parent):
        """
        We need a unique id for a die entry based on it's corpus, cu, content
        """
        hasher = hashlib.md5()
        hasher.update(str(die).encode("utf-8"))
        hasher.update(corpus.path.encode("utf-8"))
        hasher.update(str(die.cu.cu_offset).encode('utf-8'))
        if parent:
            hasher.update(parent.encode("utf-8"))
        return hasher.hexdigest()

    def generate_dwarf_information_entries(self, corpora):
        """
        Given a list of corpora, add needed libraries from dynamic tags.
        """
        # We will keep a lookup of die
        for corpus in corpora:

            # Add to child and die lookup, for redundancy check
            if corpus.path not in self.die_lookup:
                self.die_lookup[corpus.path] = {}
            if corpus.path not in self.child_lookup:
                self.child_lookup[corpus.path] = {}

            for die in corpus.iter_dwarf_information_entries():

                # Skip entries without tags
                if not die.tag:
                    continue

                # Parse the die entry!
                self._parse_die_children(corpus, die)

    def _add_children(self, corpus, die):
        """
        Add children ids to the lookup, ensuring we print the relationship
        only once.
        """
        tag = self._get_tag(die)

        def uid(corpus, die):
            return "%s_%s" % (corpus.path, die.abbrev_code)

        lookup = self.child_lookup[corpus.path]

        # Add the child lookup
        if die.unique_id not in lookup:
            lookup[die.unique_id] = set()

        # If it's a DW_TAG_subprogram, keep track of child parameter order
        # We add one each time, so count starts at 0 after that
        parameter_count = -1
        for child in die.iter_children():
            child_id = self._die_hash(child, corpus, die.unique_id)
            if child_id in lookup[die.unique_id]:
                continue
            lookup[die.unique_id].add(child_id)

            # If it's a subprogram, we care about order of parameters
            formal = "DW_TAG_formal_parameter"
            if die.tag == "DW_TAG_subprogram" and child.tag == formal:
                parameter_count += 1
                prefix = "dw_tag_formal_parameter_order"
                self.gen.fact(
                    AspFunction(prefix, args=[corpus.path, child_id, parameter_count])
                )

            # Only add the child if it's a tag to parse
            if child.tag in parse_tags or tag in parse_tags:
                self.gen.fact(fn.has_child(die.unique_id, child_id))

    def _get_tag(self, die):
        """Get a clingo appropriate tag name.

        The die tag needs to be parsed to be all lowercase, and for some
        die tags, we want to remove the "Dwarf specific words." (e.g.,
        a subprogram --> a function
        """
        tag = die.tag.lower()

        # A subprogram is a function
        if "subprogram" in tag:
            tag = re.sub('subprogram', 'function', tag)
        return tag

    def _parse_die_children(self, corpus, die, parent=None):
        """
        Parse die children, writing facts for attributions and relationships.

        Parse die children will loop recursively through dwarf information
        entries, and based on the type, generate facts for it, ensuring that
        we also create facts that represent relationships. For each, we generate:

        - atoms about the die id itself, in lowercase for clingo
        - atoms about having children (die_has_child)
        - atoms about attributes, in the form <tag>_language(corpus, id, value)

        Each die has a unique id scoped within the corpus, so we provide the
        corpus along with the id and the value of the attribute. I've provided
        separate functions less so for good structure, but moreso so that I
        can write notes alongside each. Some functions have notes and just pass.

        TODO: read through http://dwarfstd.org/doc/dwarf_1_1_0.pdf for each type
        and make sure not missing anything. Tags are on page 28.
        """
        # Get the tag for the die
        tag = self._get_tag(die)

        # Keep track of unique id (hash of attributes, parent, and corpus)
        die.unique_id = self._die_hash(die, corpus, parent)

        # Create a top level entry for the die based on it's tag type
        if tag in parse_tags:
            self.gen.fact(AspFunction(tag, args=[corpus.path, die.unique_id]))

        # Children are represented as facts
        self._add_children(corpus, die)

        # Add to the lookup
        self.die_lookup[corpus.path][die.abbrev_code] = die

        # Parse common attributes
        self._parse_common_attributes(corpus, die, tag)

        # Parse the tag if we have a matching function
        function_name = "_parse_%s" % die.tag.replace('DW_TAG_', '')
        if hasattr(self, function_name) and tag in parse_tags:
            getattr(self, function_name)(corpus, die, tag)

        # We keep a handle on the root to return
        if not parent:
            parent = die.unique_id

        if die.has_children:
            for child in die.iter_children():
                self._parse_die_children(corpus, child, parent)

    def _parse_common_attributes(self, corpus, die, tag):
        """
        Many share these attributes, so we have a common function to parse.

        It's actually easier to just check for an attribute, and parse it
        if it's present, and be sure that we don't miss any.
        """
        # We are skipping these tags for now
        if tag not in parse_tags:
            return

        if "DW_AT_name" in die.attributes:
            name = self.bytes2str(die.attributes["DW_AT_name"].value)
            self.gen.fact(
                AspFunction(tag + "_name", args=[corpus.path, die.unique_id, name])
            )

        # DW_AT_type is a reference to another die (the type)
        if "DW_AT_type" in die.attributes:
            self._parse_die_type(corpus, die, tag)

        # Not to be confused with "bite size" :)
        if "DW_AT_byte_size" in die.attributes:
            size_in_bits = die.attributes["DW_AT_byte_size"].value * 8
            self.gen.fact(
                AspFunction(
                    tag + "_size_in_bits",
                    args=[corpus.path, die.unique_id, size_in_bits],
                )
            )

        # The size this DIE occupies in the section (not sure about units)
        if hasattr(die, "size"):
            self.gen.fact(
                AspFunction(
                    tag + "_die_size", args=[corpus.path, die.unique_id, die.size]
                )
            )

        if "DW_AT_linkage_name" in die.attributes:
            name = self.bytes2str(die.attributes["DW_AT_linkage_name"].value)
            args = [corpus.path, die.unique_id, name]
            self.gen.fact(AspFunction(tag + "_mangled_name", args=args))

    def _parse_die_type(self, corpus, die, tag, lookup_die=None):
        """
        Parse the die type.

        We typically get the size in bytes or look it up. If lookup die
        is provided, it means we are digging into layers and are looking
        for a type for "die."

        Might be useful:
        https://www.gitmemory.com/issue/eliben/pyelftools/353/784166976

        """
        type_die = None

        # The die we query for the type is either the die itself, or one we've
        # already found
        query_die = lookup_die or die

        # CU relative offset

        if query_die.attributes["DW_AT_type"].form.startswith("DW_FORM_ref"):
            try:
                type_die = query_die.cu.get_DIE_from_refaddr(
                    query_die.attributes["DW_AT_type"].value
                )
            except Exception:
                pass

        # Absolute offset
        elif query_die.attributes["DW_AT_type"].startswith("DW_FORM_ref_addr"):
            print("ABSOLUTE OFFSET")
            import IPython

            IPython.embed()

        # If we grabbed the type, just explicitly write the size/type
        # In the future we could reference another die, but don't
        # have it's parent here at the moment
        if type_die:

            # If we have another type def, call function again until we find it
            if "DW_AT_type" in type_die.attributes:
                return self._parse_die_type(corpus, die, tag, type_die)

            # If it's a pointer, we have the byte size (no name)
            if type_die.tag == "DW_TAG_pointer_type":
                if "DW_AT_byte_size" in type_die.attributes:
                    size_in_bits = type_die.attributes["DW_AT_byte_size"].value * 8
                    self.gen.fact(
                        AspFunction(
                            tag + "_size_in_bits",
                            args=[corpus.path, die.unique_id, size_in_bits],
                        )
                    )

            # Not sure how to parse non complete types
            # https://stackoverflow.com/questions/38225269/dwarf-reading-not-complete-types
            elif "DW_AT_declaration" in type_die.attributes:
                self.gen.fact(
                    AspFunction(
                        tag + "_non_complete_type",
                        args=[corpus.path, die.unique_id, "yes"],
                    )
                )

            # Here we are supposed to walk member types and calc size with offsets
            # For now let's assume we can just compare all child sizes
            # https://github.com/eliben/pyelftools/issues/306#issuecomment-606677552
            elif "DW_AT_byte_size" not in type_die.attributes:
                return

            else:
                type_size = type_die.attributes["DW_AT_byte_size"].value * 8
                self.gen.fact(
                    AspFunction(
                        tag + "_size_in_bits",
                        args=[corpus.path, die.unique_id, type_size],
                    )
                )
                type_name = None
                if "DW_AT_linkage_name" in type_die.attributes:
                    type_name = self.bytes2str(
                        type_die.attributes["DW_AT_linkage_name"].value
                    )
                elif "DW_AT_name" in type_die.attributes:
                    type_name = self.bytes2str(type_die.attributes["DW_AT_name"].value)

                if type_name:
                    self.gen.fact(
                        AspFunction(
                            tag + "_type_name",
                            args=[corpus.path, die.unique_id, type_name],
                        )
                    )

    def _parse_compile_unit(self, corpus, die, tag):
        """
        Parse a compile unit (usually at the top).
        """
        # Prepare attributes for facts - keep language
        language = et.dwarf.describe_attr_value(
            die.attributes["DW_AT_language"], die, die.offset
        )
        self.language = language

        # The version of this software
        spackv = spack.main.get_version()
        self.gen.fact(fn.spack_version(corpus.path, spackv))

        # Assumes there is one language per binary
        self.gen.fact(fn.language(corpus.path, language))

    def set_needed_symbols(self, corpora, main):
        """
        Set needed symbols that we should filter to.
        """
        for corpus in corpora:
            if corpus.path in main:
                for symbol, meta in corpus.elfsymbols.items():
                    self.needed_symbols.add(symbol)

    def generate_main(self, corpora, main):
        """
        Label a set of corpora as the main ones we are assessing for compatibility.
        """
        # Use ldd to find a needed path. Assume we are on some system compiled on.
        for corpus in corpora:
            if corpus.path in main:
                self.gen.fact(fn.is_main_corpus(corpus.path))
                self.generate_needed(corpus)

    def generate_needed(self, corpus):
        """
        Generate symbols from needed libraries.
        """
        ldd = which('ldd')
        output = ldd(corpus.path, output=str)

        syscorpora = []
        for line in output.split('\n'):
            if "=>" in line:
                lib, path = line.split('=>')
                lib = lib.strip()
                path = path.strip().split(' ')[0]
                if os.path.exists(path) and lib in corpus.needed:
                    syscorpora.append(Corpus(path))

        self.generate_elf_symbols(syscorpora)

    def generate_corpus_metadata(self, corpora):
        """
        Given a list of corpora, create a fact for each one.
        """
        # Use the corpus path as a unique id (ok if binaries exist)
        # This would need to be changed if we don't have the binary handy
        for corpus in corpora:
            hdr = corpus.elfheader

            self.gen.h2("Corpus facts: %s" % corpus.path)

            self.gen.fact(fn.corpus(corpus.path))
            self.gen.fact(fn.corpus_name(corpus.path, os.path.basename(corpus.path)))

            # e_ident is ELF identification
            # https://docs.oracle.com/cd/E19683-01/816-1386/chapter6-35342/index.html
            # Note that we could update these to just be corpus_attr, but I'm
            # starting with testing a more detailed approach for now.

            # If the corpus has a soname:
            if corpus.soname:
                self.gen.fact(fn.corpus_soname(corpus.path, corpus.soname))

            # File class (also at elffile.elfclass or corpus.elfclass
            self.gen.fact(fn.corpus_class(corpus.path, hdr["e_ident"]["EI_CLASS"]))

            # Data encoding
            encoding = hdr["e_ident"]["EI_DATA"]
            self.gen.fact(fn.corpus_data_encoding(corpus.path, encoding))

            # File version
            version = hdr["e_ident"]["EI_VERSION"]
            self.gen.fact(fn.corpus_file_version(corpus.path, version))

            # Operating system / ABI Information
            self.gen.fact(fn.corpus_osabi(corpus.path, hdr["e_ident"]["EI_OSABI"]))

            # Abi Version
            version = hdr["e_ident"]["EI_ABIVERSION"]
            self.gen.fact(fn.corpus_abiversion(corpus.path, version))

            # e_type is the object file type
            self.gen.fact(fn.corpus_type(corpus.path, hdr["e_type"]))

            # e_machine is the required architecture for the file
            self.gen.fact(fn.corpus_machine(corpus.path, hdr["e_machine"]))

            # object file version
            self.gen.fact(fn.corpus_version(corpus.path, hdr["e_version"]))

    def generate(self, driver, corpora, main):
        """
        Generate facts for a set of corpora.

        Arguments:
            corpora: one or more corpora
        """
        # Every fact, entity that we make needs a unique id
        # Note that this isn't actually in use yet!
        self._condition_id_counter = itertools.count()

        # preliminary checks
        for corpus in corpora:
            assert corpus.exists()

        self.gen.h1("Corpus Facts")

        # Figure out needed symbols
        self.set_needed_symbols(corpora, main)

        # Label main libraries we are assessing
        self.generate_main(corpora, main)

        # Generate high level corpus metadata facts (e.g., header)
        self.generate_corpus_metadata(corpora)

        # Generate all elf symbols (might be able to make this smaller set)
        self.generate_elf_symbols(corpora)

        # Generate dwarf information entries
        self.generate_dwarf_information_entries(corpora)


# Functions intended to be called by external clients


def generate_facts(main, libs, outfile):
    """
    A single function to generate facts for one or more corpora.

    Arguments:
      main (list) : the main list of libraries
      libs (list) : dependency libraries to assess
      outfile (str) : the output file to write to as we go
    """
    if not isinstance(libs, list):
        libs = [libs]

    # We use the PyClingoDriver only to write (not to solve)
    driver = spack.solver.asp.PyclingoDriver()
    out = open(outfile, 'w')
    driver.out = out

    # The generator translates corpora to atoms
    gen = ABIFactGenerator(driver)

    corpora = []
    for lib in libs + main:
        corpora.append(Corpus(lib))

    driver.init_control()
    with driver.control.backend() as backend:
        driver.backend = backend
        gen.generate(driver, corpora, main)

    out.close()
