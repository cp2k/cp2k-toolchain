#!/usr/bin/env python3

import pathlib
import argparse
import subprocess
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent

SPACK_DIR = SCRIPT_DIR / "spack"
SPACK_PATH = SPACK_DIR / "bin" / "spack"


class CommandError(Exception):
    pass


class ConfigurationError(Exception):
    pass


# based on https://stackoverflow.com/a/31347222
def argparse_add_bool_arg(parser, name, default, helptxt):
    """Add --<name>/--no-<name> arguments"""
    dname = name.replace("-", "_")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--{}".format(name), dest=dname, action="store_true", help=helptxt
    )
    group.add_argument("--no-{}".format(name), dest=dname, action="store_false")
    parser.set_defaults(**{dname: default})


class SpackCmd:
    def __init__(self, spack_path=SPACK_PATH):
        self._spack_path = spack_path
        self._arch = None

    @staticmethod
    def ensure_installation(spack_dir=SPACK_DIR):
        """Fetch Spack if required and check whether the checkout is ok"""

        if not spack_dir.exists():
            print(f"Setting up new Spack installation to '{spack_dir}'")

            # need Git for now
            try:
                command = [
                    "git",
                    "clone",
                    "--depth=1",
                    "https://github.com/spack/spack.git",
                    str(spack_dir),
                ]
                subprocess.run(
                    command, check=True, capture_output=True, encoding="utf-8"
                )
            except subprocess.CalledProcessError as exc:
                raise CommandError(
                    "cloning the Spack repository failed",
                    " ".join(command),
                    exc.stdout,
                    exc.stderr,
                ) from None

        if not (spack_dir / "bin" / "spack").exists():
            raise ConfigurationError(
                f"the Spack directory '{spack_dir}' exists, but the executable 'bin/spack' could not be found"
            )

    def check(self):
        """Check that the executable on the given path runs"""
        try:
            command = [str(self._spack_path), "help"]
            subprocess.run(command, check=True, capture_output=True, encoding="utf-8")
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                "the Spack installation seems to be broken, calling 'spack help' failed",
                " ".join(command),
                exc.stdout,
                exc.stderr,
            ) from None

    @property
    def arch(self):
        """Get the Spack arch tuple"""
        if self._arch is not None:
            return self._arch

        try:
            command = [str(self._spack_path), "arch"]
            ret = subprocess.run(
                command, check=True, capture_output=True, encoding="utf-8"
            )
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                "the Spack installation seems to be broken, calling 'spack help' failed",
                " ".join(command),
                exc.stdout,
                exc.stderr,
            ) from None

        return ret.stdout.strip()

    def install_env(self, envdir, features, omp, mpi):
        """
        Install cp2k@toolchain in the given Spack environment with the required features.
        :param envdir: path where the Spack env should be created, resp. used
        :param features: Spack spec for the cp2k package, like: +sirius ~cuda_fft
        :param omp: Adds `+openmp` to the Spack spec if True, `~openmp` otherwise.
        :param mpi: Adds `+mpi` to the Spack spec if True, `~mpi` otherwise.
        """

        cp2k_spec = ["cp2k-deps"]
        cp2k_spec += ["+openmp"] if omp else ["~openmp"]
        cp2k_spec += ["+mpi"] if mpi else ["~mpi"]
        cp2k_spec += features  # TODO: validate features

        # pkgconf is build-time dep for CP2K and would not end up
        # in the environment unless explictly mentioned
        spec = ["pkgconf", " ".join(cp2k_spec)]

        if not envdir.exists():
            envdir.mkdir(parents=True)

        spack_yaml_path = envdir / "spack.yaml"
        if not spack_yaml_path.exists():  # or should we always overwrite it?

            print(
                f"Creating environment configuration for '{' '.join(cp2k_spec)}' in '{envdir}'"
            )
            spack_yaml_path.write_text(
                f"""\
# This is a Spack Environment file.
#
# It describes a set of packages to be installed, along with
# configuration settings.
spack:
  # add package specs to the `specs` list
  specs: [{", ".join(spec)}]
  repos: [{SCRIPT_DIR}/repo]
""",
                encoding="utf-8",
            )

        print(f"Installing environment with '{' '.join(spec)}' in '{envdir}'")

        try:
            command = [
                str(self._spack_path),
                "install",
            ]  # the install here pulls the spec from the env. config
            # running Spack in the envdir will automatically enable the environment
            # do not capture the output here to make sure the user sees something, because this takes long
            subprocess.run(command, check=True, cwd=envdir, encoding="utf-8")
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                "could not create the Spack environment at '{}'".format(envdir),
                " ".join(command),
                "",
                "",
            ) from None

        try:
            command = [
                str(self._spack_path),
                "env",
                "activate",
                "--sh",
                "--dir",
                ".",
            ]
            ret = subprocess.run(
                command, check=True, cwd=envdir, encoding="utf-8", capture_output=True
            )
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                "getting environment activation failed for environment '{}'".format(
                    envdir
                ),
                " ".join(command),
                exc.stdout,
                exc.stderr,
            ) from None

        with (envdir / "sh.env").open("w", encoding="utf-8") as fhandle:
            fhandle.write(ret.stdout)


def copy_arch_file(arch_dir, spack_env_dir, spack_env):

    view_dir = spack_env_dir / f"{spack_env}" / ".spack-env" / "view"

    source = next(
        (view_dir / "share" / "data").glob(f"*.{spack_env}")  # only one file here
    )

    dest = arch_dir / source.name

    print(f"Extracting arch file from Spack environment '{spack_env}' to '{dest}'")

    with source.open("r", encoding="utf-8") as orig, dest.open(
        "w", encoding="utf-8"
    ) as out:
        # copy the Spack-generated input file with some modifications
        for line in orig:
            # filter out the DATA_DIR spec, leave that to the user
            if line.startswith("DATA_DIR"):
                continue

            out.write(line)

    # a different way could be to either generate the arch files completely ourselves,
    # or modify the arch-file generation in the Spack cp2k-deps package
    # The advantage of the first alternative is that we could use the Spack environment paths
    # instead of the direct package paths which would make the arch-file cleaner and
    # the arch file would likely not change if the environment gets updated.
    # The latter would avoid replicating existing logic in here.


def install():
    """The base entrypoint for this script"""
    parser = argparse.ArgumentParser(
        description="Generate a Spack environment configuration for the desired CP2K configuration",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    argparse_add_bool_arg(
        parser, "openmp", True, "Whether to build ssmp/psmp environments"
    )
    argparse_add_bool_arg(
        parser, "mpi", True, "Whether to build popt/psmp environments"
    )
    parser.add_argument(
        "--spack-dir",
        metavar="<path-to-spack-dir>",
        help="Path to the Spack environment. If it doesn't exist, a new Spack environment will be fetched there (needs Git).",
        default=SPACK_DIR,
        type=lambda p: pathlib.Path.cwd() / p,
    )

    parser.add_argument(
        "features",
        metavar="<feature>",
        nargs="*",
        type=str,
        help="a CP2K feature. ex.: +cuda ~sirius, passed down to Spack",
    )

    args = parser.parse_args()

    try:
        SpackCmd.ensure_installation(args.spack_dir)

        spack = SpackCmd(args.spack_dir / "bin" / "spack")
        spack.check()

        spec = args.features.copy()

        # if the user does not wish any MPI support, make sure we disable MPI also for some of the
        # dependencies which are not controlled by the package itself and also only for packages
        # which provide multiple sets of the libraries
        if not args.mpi:
            # fftw always builds the non-MPI variant and contains a second set of built with MPI
            spec += ["^fftw~mpi"]

        arch_dir = SCRIPT_DIR / "arch"
        if not arch_dir.exists():
            arch_dir.mkdir()

        # this is the default environment and always gets built
        spack.install_env(SCRIPT_DIR / "envs" / "sopt", spec, omp=False, mpi=False)
        copy_arch_file(arch_dir, SCRIPT_DIR / "envs", "sopt")

        if args.openmp:
            spack.install_env(SCRIPT_DIR / "envs" / "ssmp", spec, omp=True, mpi=False)
            copy_arch_file(arch_dir, SCRIPT_DIR / "envs", "ssmp")

        if args.mpi:
            spack.install_env(SCRIPT_DIR / "envs" / "popt", spec, omp=False, mpi=True)
            copy_arch_file(arch_dir, SCRIPT_DIR / "envs", "popt")

        if args.mpi and args.openmp:
            spack.install_env(SCRIPT_DIR / "envs" / "psmp", spec, omp=True, mpi=True)
            copy_arch_file(arch_dir, SCRIPT_DIR / "envs", "psmp")

    except CommandError as exc:
        print(
            f"ERROR: {exc.args[0]}\nfailed command was: {exc.args[1]}", file=sys.stderr
        )
        if exc.args[2].strip():
            print(
                f"*** stdout: begin\n{exc.args[2].strip()}\n*** stdout: end",
                file=sys.stderr,
            )
        if exc.args[3].strip():
            print(
                f"*** stderr: begin\n{exc.args[3].strip()}\n*** stderr: end",
                file=sys.stderr,
            )
        sys.exit(1)

    except ConfigurationError as exc:
        print(f"ERROR: {exc.args[0]}")
        sys.exit(1)

    print(
        f"""Building toolchain succeeded.

To build CP2K, copy the respective arch file from {arch_dir} to your cp2k/arch directory
and then run:

    source {SCRIPT_DIR / "envs" / "sopt" / "sh.env"}
    make ARCH=... VERSION=sopt

... replace 'sopt' with the version you want to build
    and set ARCH to match the architecture of the generated arch/ files.
"""
    )


if __name__ == "__main__":
    install()
