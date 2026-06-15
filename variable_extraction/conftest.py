# pytest configuration for variable_extraction/
#
# The executable scripts in patientpunk/scripts/ are programs, not test
# modules. Without this setting pytest would try to collect them as tests, fail
# on their argparse-at-import-time calls, and report confusing errors.
collect_ignore_glob = [
    "patientpunk/scripts/*.py",
]
