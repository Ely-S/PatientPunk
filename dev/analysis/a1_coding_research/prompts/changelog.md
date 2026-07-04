# Prompt Changelog

## comment_coder_v0.1

Initial A1 baseline.

- Defines TARGET_COMMENT as the only extractable evidence source.
- Allows context only for resolving references in the target comment.
- Adds hard-case rules for same-here replies, parent-only claims, other-person
  claims, quoted text, general advice, negation, ambiguity, and deleted/removed
  comments.
- Uses the `comment_coding_v0.1` structured response schema.

