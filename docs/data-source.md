# Data Source Record — Chinook

- Record status: SQLite and PostgreSQL artifacts verified and reproducible
- Verification date: 2026-07-21
- Dataset: Chinook Database
- Upstream owner: `lerocha/chinook-database`

## Official Source

- Repository: https://github.com/lerocha/chinook-database
- License file: https://github.com/lerocha/chinook-database/blob/master/LICENSE.md
- Selected release: https://github.com/lerocha/chinook-database/releases/tag/v1.4.5
- Release tag: `v1.4.5`
- Release commit shown by GitHub: `4a944a9`
- Selected asset: `Chinook_Sqlite.sqlite`
- Immutable asset URL:
  https://github.com/lerocha/chinook-database/releases/download/v1.4.5/Chinook_Sqlite.sqlite

The upstream README describes Chinook as a sample digital-media-store database
for demonstrations and ORM testing. It supports both SQLite and PostgreSQL,
which matches the planned MVP-to-final migration.

## License

The upstream `LICENSE.md` contains the standard permissive MIT license text and
copyright notice:

- Copyright: 2008–2024 Luis Rocha
- License classification: MIT
- Requirement: preserve the copyright and permission notice in copies or
  substantial portions of the software.

The project must retain appropriate attribution when redistributing dataset
scripts or database artifacts.

## Selected Usage

- Tahap 2–7: official SQLite release artifact.
- Tahap 8 onward: official `Chinook_PostgreSql.sql` from the same pinned
  release, loaded behind application-facing compatibility views.
- The application repository will distinguish upstream source files from
  generated local database files.

## Reproducibility Policy

Tahap 2 must:

1. Select the exact official release asset names.
2. Record immutable download URLs where available.
3. Download to a temporary or raw-data location.
4. Calculate and record SHA-256 checksums.
5. Reject mismatched files.
6. Document whether source scripts or generated database files are committed.
7. Preserve the upstream license notice.
8. Record row/table sanity checks after initialization.

## Verified Artifact Identity

- File size: `1,067,008` bytes
- SHA-256:
  `bdf635be69850bd3be09c9a2dbeef7ddfb80036bd3ef3381383cd03b61e4a61a`
- Checksum manifest: `data/raw/SHA256SUMS.txt`
- Verification policy: fail closed on a missing file, size mismatch, checksum
  mismatch, SQLite integrity failure, schema drift, or row-count drift.
- Raw binary: generated locally under `data/raw/` and ignored by Git.
- Runtime binary: a byte-identical local copy under `data/processed/` and
  ignored by Git.
- Tracked derivative metadata: `data/schemas/chinook-v1.4.5.json` and
  `configs/security/table_allowlist.json`.

The setup was run twice on 2026-07-19. The first run created the runtime copy;
the second reused it with the same checksum and schema hash, demonstrating the
required idempotency.

## Verified Database Sanity Checks

SQLite `PRAGMA integrity_check` returned `ok`. Exactly 11 user tables were
present with these deterministic counts:

| Table | Rows |
|---|---:|
| Album | 347 |
| Artist | 275 |
| Customer | 59 |
| Employee | 8 |
| Genre | 25 |
| Invoice | 412 |
| InvoiceLine | 2,240 |
| MediaType | 5 |
| Playlist | 18 |
| PlaylistTrack | 8,715 |
| Track | 3,503 |

The normalized schema hash is
`58c6c16d147308c44996f88c3b893c0baa264a9b0ca6d06418f1ba3f199def7c`.

## Verified PostgreSQL Artifact Identity

- Asset: `Chinook_PostgreSql.sql`
- Immutable URL:
  https://github.com/lerocha/chinook-database/releases/download/v1.4.5/Chinook_PostgreSql.sql
- File size: `600,200` bytes
- SHA-256:
  `e3fde5c1a5b51a2a91429a702c9ca6e69ba56e6c7f5e112724d70c3d03db695e`
- Logical snapshot: `data/schemas/chinook-postgresql-v1.4.5.json`
- Normalized logical schema hash:
  `f3569fc49358ddbd50328badf58ac4748cd0ccc60995c741648cb79b2db02e4e`

The bootstrap removes only the upstream database-level commands, loads the
official schema/data into owner-only `chinook_data`, and creates the reviewed
logical contract in `analytics`. Asset and snapshot verification pass offline;
the live role/grant behavior passed the Tahap 8 PostgreSQL gate on 2026-07-21.

## Data Characteristics and Privacy

The upstream README states that the model represents a digital media store. It
also explains that media-related data came from an iTunes library, customer and
employee information was manually created, and sales data was generated. The
project treats the dataset as demonstration data and will not mix it with real
personal or confidential data.

## Dataset Change Policy

Changing the release requires:

1. A new decision record.
2. New checksums and schema snapshot.
3. Evaluation-baseline review.
4. Documentation of schema or content differences.
