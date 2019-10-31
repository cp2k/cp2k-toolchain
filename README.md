# CP2K Toolchain based on Spack

Advantages over the existing toolchain:

* reduce maintenance of build scripts by leveraging Spack's maintained packages
* re-use Spack expertise on building 3rdparty packages
* re-use existing Spack installations and packages
* automatic mirror generation for source packages to help CP2K users needing offline installation
* build binary packages for caching in CI
* distro/system-independant and reproducible build stack

Disadvantages over the existing toolchain:

* By default everything except a system compiler is installed by Spack. This includes things like OpenSSL, Python.

## Requirements

* Python 3.7+
* git

## TODOs

* [ ] generate CP2K `arch/` files. Ideal would be if they could activate the corresponding environment automatically.
      In this case we could get away with using simple `$(shell pkg-config --libs libxc ...)` for most dependencies.
* [ ] implement simple way to make Spack use system-provided MPI
* [ ] implement simple way to make Spack use different system compiler
* [ ] implement simple way to override packages with pre-install packages
* [ ] query compiler from Spack for using in `arch/` file

## Design

* CP2K has 4 main configurations: `sopt`, `popt`, `ssmp`, `psmp`.
  Basically the cross-product of with/without-OpenMP and with/without-MPI
  We're following this by building a maximum of 4 Spack environments,
  depending on whether the user wants OpenMP or MPI.
  If the user disables OpenMP and MPI, he will only get a `sopt` environment.
* We're using one Spack installation, meaning that packages shared between the
  environments will be built only once.
* Spack only builds the required packages, not CP2K itself
* <s>To re-use the complex build requirements even at the top-level of dependencies,
  we are installing the dependencies by using Spack's "recipe" for building CP2K.
  Ex.:

      spack install --only dependencies cp2k +openmp ~mpi ~sirius

  Should we have to override Spack's CP2K package (for new packages or  we can provide a custom repository
  to override it. There is also the possibility to limit ourselves to a specific version/tag
  of Spack for releases.</s>
  Unfortunately only install dependencies leaves the environment in a rather peculiar state:
  While the dependencies are correctly installed the `spec` contained says `cp2k` which means that a
  `spack install` in that dir will then install the CP2K package itself and other commands like `spack env loads`
  fail because the `cp2k` is not yet available. Therefore:
* We provide a repository overlay registered in each environment which contains a stripped-down version of
  the Spack CP2K package called `cp2k-deps`. This should be kept in sync with Spack CP2K package wrt to
  dependency specification and `arch/` file generation. The difference to the `cp2k` package is that this
  package does not pull any sources and only installs an `arch/` file. This way we can even re-use the `arch/`
  file generation already done in Spack.
