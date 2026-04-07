# pytest configuration for demographic_extraction/
#
# The legacy scripts in old/ are executable programs, not test modules.
# Without this setting pytest would try to collect them as tests, fail on
# their argparse-at-import-time calls, and report confusing errors.
#
# collect_ignore_glob is the glob-based variant of collect_ignore; it tells
# pytest to skip every .py file inside old/ during collection.
collect_ignore_glob = [
    "old/*.py",
]
