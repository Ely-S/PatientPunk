# pytest configuration for variable_extraction/
#
# The executable scripts in scripts/ and archived copies in old/ are programs,
# not test modules. Without this setting pytest would try to collect them as
# tests, fail on their argparse-at-import-time calls, and report confusing
# errors.
collect_ignore_glob = [
    "scripts/*.py",
    "old/*.py",
]
