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


def ensure_spack_installation(spack_dir=SPACK_DIR):
    """Fetch Spack if required and check whether the checkout is ok"""

    if not spack_dir.exists():
        # need Git for now
        try:
            command = [
                "git",
                "clone",
                "--depth=1",
                "https://github.com/spack/spack.git",
                str(spack_dir),
            ]
            subprocess.run(command, check=True, capture_output=True, encoding="utf-8")
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


def check_spack(spack_path=SPACK_PATH):
    """Check that the executable on the given path runs"""
    try:
        command = [str(spack_path), "help"]
        subprocess.run(command, check=True, capture_output=True, encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        raise CommandError(
            "the Spack installation seems to be broken, calling 'spack help' failed",
            " ".join(command),
            exc.stdout,
            exc.stderr,
        ) from None


def get_spack_arch(spack_path=SPACK_PATH):
    """Get the Spack arch tuple"""
    try:
        command = [str(spack_path), "arch"]
        ret = subprocess.run(command, check=True, capture_output=True, encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        raise CommandError(
            "the Spack installation seems to be broken, calling 'spack help' failed",
            " ".join(command),
            exc.stdout,
            exc.stderr,
        ) from None

    return ret.stdout.strip()


def install_spack_env(envdir, features, omp, mpi, spack_path=SPACK_PATH):
    """
    Install cp2k@toolchain in the given Spack environment with the required features.
    :param envdir: path where the Spack env should be created, resp. used
    :param features: Spack spec for the cp2k package, like: +sirius ~cuda_fft
    :param omp: Adds `+openmp` to the Spack spec if True, `~openmp` otherwise.
    :param mpi: Adds `+mpi` to the Spack spec if True, `~mpi` otherwise.
    :param spack_path: Path to the Spack binary to be used
    """

    spec = ["cp2k-deps"]
    spec += ["+openmp"] if omp else ["~openmp"]
    spec += ["+mpi"] if mpi else ["~mpi"]
    spec += features  # TODO: validate features

    if not envdir.exists():
        envdir.mkdir(parents=True)

    spack_yaml_path = envdir / "spack.yaml"
    if not spack_yaml_path.exists():  # or should we always overwrite it?

        print(
            f"Creating environment configuration for '{' '.join(spec)}' in '{envdir}'"
        )
        spack_yaml_path.write_text(
            f"""\
# This is a Spack Environment file.
#
# It describes a set of packages to be installed, along with
# configuration settings.
spack:
  # add package specs to the `specs` list
  specs: ["{" ".join(spec)}"]
  repos: ["{SCRIPT_DIR}/repo"]
""",
            encoding="utf-8",
        )

    print(f"Installing environment with '{' '.join(spec)}' in '{envdir}'")

    try:
        command = [
            str(spack_path),
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


def setup_arch_symlink(arch_dir, spack_arch, spack_env_dir, spack_env):
    """TODO: needs some improvement"""
    symdest = arch_dir / f"{spack_arch}.{spack_env}"
    symtarget = (
        spack_env_dir
        / f"{spack_env}"
        / ".spack-env"
        / "view"
        / "share"
        / "data"
        / f"{spack_arch}-gcc.{spack_env}"
    )

    if symdest.exists():
        symdest.unlink()

    symdest.symlink_to(symtarget)


def install():
    """The basic entrypoint for this script"""
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
        "features",
        metavar="<feature>",
        nargs="*",
        type=str,
        help="a CP2K feature. ex.: +cuda ~sirius, passed down to Spack",
    )

    args = parser.parse_args()

    try:
        ensure_spack_installation()
        check_spack()  # TODO: give the user the possibility to use an already installed spack

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

        spack_arch = get_spack_arch()

        # this is the default environment and always gets built
        install_spack_env(SCRIPT_DIR / "envs" / "sopt", spec, omp=False, mpi=False)
        setup_arch_symlink(arch_dir, spack_arch, SCRIPT_DIR / "envs", "sopt")

        if args.openmp:
            install_spack_env(SCRIPT_DIR / "envs" / "ssmp", spec, omp=True, mpi=False)
            setup_arch_symlink(arch_dir, spack_arch, SCRIPT_DIR / "envs", "ssmp")

        if args.mpi:
            install_spack_env(SCRIPT_DIR / "envs" / "popt", spec, omp=False, mpi=True)
            setup_arch_symlink(arch_dir, spack_arch, SCRIPT_DIR / "envs", "popt")

        if args.mpi and args.openmp:
            install_spack_env(SCRIPT_DIR / "envs" / "psmp", spec, omp=True, mpi=True)
            setup_arch_symlink(arch_dir, spack_arch, SCRIPT_DIR / "envs", "psmp")

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


if __name__ == "__main__":
    install()
