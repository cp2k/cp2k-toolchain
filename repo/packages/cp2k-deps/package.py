# Copyright 2013-2019 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack.pkg.builtin.cp2k import Cp2k


class Cp2kDeps(Cp2k):
    # avoid pulling any sources
    has_code = False

    # use the Git version number here
    version('7.0')

    @property
    def makefile(self):
        # override the makefile path since we don't have the arch/ dir
        return '{s.makefile_architecture}.{s.makefile_version}'.format(s=self)

    def build(self, spec, prefix):
        # don't build anything (makefile gets generated in a different phase)
        pass

    def install(self, spec, prefix):
        # only install the makefile
        install_tree('.', self.prefix.share.data)
