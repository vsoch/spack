# Copyright 2013-2020 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

"""Schema for a system dump or export of compilers, packages, etc.

.. literalinclude:: _spack_root/lib/spack/spack/schema/export.py
   :lines: 13-
"""


from copy import deepcopy
import spack.schema.spec
from spack.schema.compilers import properties as compilers

# name of package must be required for export of list
package = deepcopy(spack.schema.spec.package)
package['required'].append('name')

properties = {
    'type': 'object',
    'default': {},
    'additionalProperties': False,
    'properties': {
        'compilers': compilers,
        'specs': specs,
    }
}

# name of package is required for export?

specs = {
    'specs': {
        'type': 'array',
        'items': [spack.schema.spec.package]
    }
}

#: Full schema with metadata
schema = {
    '$schema': 'http://json-schema.org/schema#',
    'title': 'Spack export schema',
    'type': 'object',
    'additionalProperties': False,
    'patternProperties': properties,
}
