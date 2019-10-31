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


def argparse_add_with_arg(parser, name, default, helptxt, metavar=None):
    """Add --with-<name> .../--without-<name> arguments"""
    dname = name.replace("-", "_")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--with-{}".format(name),
        dest=dname,
        nargs="?",
        const=default,
        metavar=metavar,
        help="Make sure all dependencies for building MPI-parallel CP2K with the specified provider are installed",
    )
    group.add_argument(
        "--without-{}".format(name), dest=dname, action="store_const", const="off"
    )
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
    """Check that the given executable runs"""
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


def install_spack_env(envdir, features, omp, mpi, spack_path=SPACK_PATH):
    if not (envdir / "spack.yaml").exists():
        try:
            command = [str(spack_path), "env", "create", "--dir", str(envdir)]
            subprocess.run(command, check=True, capture_output=True, encoding="utf-8")
        except subprocess.CalledProcessError as exc:
            raise CommandError(
                f"could not create the Spack environment at '{envdir}'",
                " ".join(command),
                exc.stdout,
                exc.stderr,
            ) from None

    spec = ["cp2k@develop"]
    spec += ["+openmp"] if omp else ["~openmp"]
    spec += ["+mpi"] if mpi else ["~mpi"]
    spec += features  # TODO: validate features

    print(f"Installing dependencies for '{' '.join(spec)}' in '{envdir}'")

    try:
        command = [str(spack_path), "install"] + spec
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


def install():
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

        # this is the default environment and always gets built
        install_spack_env(
            SCRIPT_DIR / "envs" / "sopt", args.features, omp=False, mpi=False
        )

        if args.openmp:
            install_spack_env(
                SCRIPT_DIR / "envs" / "ssmp", args.features, omp=True, mpi=False
            )

        if args.mpi:
            install_spack_env(
                SCRIPT_DIR / "envs" / "popt", args.features, omp=False, mpi=True
            )

        if args.mpi and args.openmp:
            install_spack_env(
                SCRIPT_DIR / "envs" / "psmp", args.features, omp=True, mpi=True
            )

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
