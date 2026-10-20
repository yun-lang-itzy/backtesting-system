# Repository publication policy

The owner requests that this repository retain only one commit representing the latest release.

When the owner authorizes a GitHub sync:
- Prepare and verify the latest complete source and explicitly requested public reports.
- Exclude raw market data, actual ST status data, ST acquisition code, credentials and personal paths.
- Create a root commit with no parent, containing the intended release tree.
- Read the current remote main SHA and use an explicit --force-with-lease for that SHA. Do not overwrite unexpected remote updates.
- Verify remote main matches the new root commit and synchronize local main without discarding uncommitted work.
- Check for other branches or tags retaining history; do not delete unrelated refs without authorization.

This policy does not authorize unrequested publication. A normal incremental push does not satisfy the one-commit publication preference. GitHub caches, previously shared commit URLs and other clones may retain old objects even after branch history is replaced.
