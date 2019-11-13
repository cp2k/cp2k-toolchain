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

## Usage

```console
$ git clone https://github.com/cp2k/cp2k-toolchain.git
$ cd cp2k-toolchain
$ ./install.py  # this takes some time and will by default build environments for sopt/popt/ssmp/psmp
$ ls arch/  # list generated arch files
```

To get the full list of options:

```console
$ ./install.py --help
usage: install.py [-h] [--openmp | --no-openmp] [--mpi | --no-mpi]
                  [--spack-dir <path-to-spack-dir>]
                  [<feature> [<feature> ...]]

Generate a Spack environment configuration for the desired CP2K configuration

positional arguments:
  <feature>             a CP2K feature. ex.: +cuda ~sirius, passed down to
                        Spack (default: None)

optional arguments:
  -h, --help            show this help message and exit
  --openmp              Whether to build ssmp/psmp environments (default:
                        True)
  --no-openmp
  --mpi                 Whether to build popt/psmp environments (default:
                        True)
  --no-mpi
  --spack-dir <path-to-spack-dir>
                        Path to the Spack environment. If it doesn't exist, a
                        new Spack environment will be fetched there (needs
                        Git). (default: /data/tiziano/cp2k-toolchain/spack)
```

## TODOs

* [x] generate CP2K `arch/` files. Ideal would be if they could activate the corresponding environment automatically.
      In this case we could get away with using simple `$(shell pkg-config --libs libxc ...)` for most dependencies.
* [ ] implement simple way to make Spack use system-provided MPI
* [ ] implement simple way to make Spack use different system compiler
* [ ] implement simple way to override packages with pre-install packages
* [ ] figure out how to automatically set `RPATH` when building CP2K with the generated `arch/` file to avoid having to load the environment just to run CP2K

## Design

* CP2K has 4 main configurations: `sopt`, `popt`, `ssmp`, `psmp`.
  Basically the cross-product of with/without-OpenMP and with/without-MPI.
  We're following this by building a maximum of 4 Spack environments (since
  Spack by default would only build **one** specific variant),
  depending on whether the user wants OpenMP, or MPI.
  If the user disables both OpenMP and MPI, he will only get a `sopt` environment,
  if she disables MPI, the scripts will only build environments for `sopt` and `ssmp`.
* We're using one Spack installation, meaning that packages shared between the
  environments will be built only once if their configuration is compatible.
  This is entirely left to Spack.
* Spack only builds the required packages, not CP2K itself. There are two ways for this:
  Specify the required dependencies explicitly in the respective environment configuration
  (`spack.yaml`), which would mean to replicate to some extend the dependency-logic already
  contained in the Spack CP2K package, or to use a custom Spack package which only contains
  the dependency (and `arch/`-file generation) part of the Spack CP2K package.
* We therefore provide a repository overlay registered in each environment which contains a stripped-down version of
  the Spack CP2K package called `cp2k-deps`. This should be kept in sync with Spack CP2K package wrt to
  dependency specification and `arch/` file generation. The difference to the `cp2k` package is that this
  package does not pull any sources and only installs an `arch/` file. This way we can even re-use the `arch/`
  file generation already done in Spack.
* Building and running **one** CP2K `VERSION` currently requires the activation of the corresponding Spack environment.
  Reason why the Spack environment is required to be loaded for compilation is the usage of `pkg-config`. At runtime the environment must be loaded because the `RPATH` is not set (and the linker loader would not find the libraries)
