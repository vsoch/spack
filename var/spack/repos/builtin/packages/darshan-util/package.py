# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack import *


class DarshanUtil(Package):
    """Darshan (util) is collection of tools for parsing and summarizing log
    files produced by Darshan (runtime) instrumentation. This package is
    typically installed on systems (front-end) where you intend to analyze
    log files produced by Darshan (runtime)."""

    homepage = "http://www.mcs.anl.gov/research/projects/darshan/"
    url      = "http://ftp.mcs.anl.gov/pub/darshan/releases/darshan-3.1.0.tar.gz"
    git      = "https://github.com/darshan-hpc/darshan.git"

    maintainers = ['shanedsnyder', 'carns']

    version('main', branch='main', submodules='True')
    version('3.3.1', sha256='281d871335977d0592a49d053df93d68ce1840f6fdec27fea7a59586a84395f7')
    version('3.3.0', sha256='2e8bccf28acfa9f9394f2084ec18122c66e45d966087fa2e533928e824fcb57a')
    version('3.3.0-pre2', sha256='0fc09f86f935132b7b05df981b05cdb3796a1ea02c7acd1905323691df65e761')
    version('3.3.0-pre1', sha256='1c655359455b5122921091bab9961491be58a5f0158f073d09fe8cc772bd0812')
    version('3.2.1', sha256='d63048b7a3d1c4de939875943e3e7a2468a9034fcb68585edbc87f57f622e7f7')
    version('3.2.0', sha256='4035435bdc0fa2a678247fbf8d5a31dfeb3a133baf06577786b1fe8d00a31b7e')
    version('3.1.8', sha256='3ed51c8d5d93b4a8cbb7d53d13052140a9dffe0bc1a3e1ebfc44a36a184b5c82')
    version('3.1.7', sha256='9ba535df292727ac1e8025bdf2dc42942715205cad8319d925723fd88709e8d6')
    version('3.1.6', sha256='21cb24e2a971c45e04476e00441b7fbea63d2afa727a5cf8b7a4a9d9004dd856')
    version('3.1.0', sha256='b847047c76759054577823fbe21075cfabb478cdafad341d480274fb1cef861c')
    version('3.0.0', sha256='95232710f5631bbf665964c0650df729c48104494e887442596128d189da43e0')

    variant('bzip2', default=False, description="Enable bzip2 compression")
    variant('shared', default=True, description='Build shared libraries')
    variant('apmpi', default=False, description='Compile with AutoPerf MPI module support')
    variant('apxc', default=False, description='Compile with AutoPerf XC module support')

    depends_on('zlib')
    depends_on('bzip2', when="+bzip2", type=("build", "link", "run"))

    patch('retvoid.patch', when='@3.2.0:3.2.1')

    conflicts('+apmpi', when='@:3.2.1',
              msg='+apmpi variant only available starting from version 3.3.0')
    conflicts('+apxc', when='@:3.2.1',
              msg='+apxc variant only available starting from version 3.3.0')

    def install(self, spec, prefix):

        options = ['CC=%s' % self.compiler.cc,
                   '--with-zlib=%s' % spec['zlib'].prefix]
        if '+shared' in spec:
            options.extend(['--enable-shared'])

        if '+apmpi' in spec:
            options.extend(['--enable-autoperf-apmpi'])
        if '+apxc' in spec:
            options.extend(['--enable-autoperf-apxc'])

        with working_dir('spack-build', create=True):
            configure = Executable('../darshan-util/configure')
            configure('--prefix=%s' % prefix, *options)
            make()
            make('install')
