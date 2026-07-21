# Data Directory

- `raw/` contains downloaded upstream artifacts and their tracked checksum
  manifest. The SQLite binary is ignored by Git and can be reproduced.
- `processed/` contains the generated runtime copy and is ignored by Git except
  for its README.
- `schemas/` contains versioned schema snapshots that are tracked in Git.

Run `python scripts/bootstrap_data.py` from the project environment to download,
verify, initialize, and snapshot Chinook.

