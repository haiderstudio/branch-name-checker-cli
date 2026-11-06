# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the branch names you name (or the local branches of the repo you run it in), and it never renames, deletes, or creates a branch, and never changes a file. It writes nothing except the report on standard output (and usage errors on standard error).

If you find a case where the tool changes a branch or a file, or reports a pass for a name git would reject, please open an issue describing the exact commands and input. Do not include any real secret in the report.
