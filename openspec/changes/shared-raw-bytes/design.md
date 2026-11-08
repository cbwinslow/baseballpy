# Design: shared-raw-bytes

## Decisions

- **D1 Content-addressed blob store with strict backward compatibility:**
  Shared raw payloads reside under `<lake>/raw/_blobs/<sha256[:2]>/<sha256>.json.gz`. Existing files in `<lake>/raw/<source>/<dataset>/season=<season>/<chunk>.json.gz` remain fully readable without modification. A manifest entry containing `blob_ref` directs readers to `_blobs`, while an entry without `blob_ref` resolves to its traditional partition path.
- **D2 Two-phase verification before unlinking duplicate copies:**
  The deduplication migration tool (`baseballpy deduplicate-raw`) MUST NEVER delete an original file until the shared blob in `raw/_blobs/` exists, its sha256 hash matches the original file exactly, and the dataset manifest checkpoint has been atomically committed with the new `blob_ref`.
- **D3 In-memory hash deduplication during extraction:**
  When `MlbGenericExtractor` downloads an endpoint that produces multiple datasets (e.g. `feed/live`), it stores the raw bytes once in `_blobs`. Subsequent datasets derived from that payload register their manifest entry pointing to the same `blob_ref` with zero disk I/O.
- **D4 Cache check and integrity preservation:**
  `baseballpy cache check` verifies the sha256 of `blob_ref` targets against the manifest checksum, guaranteeing end-to-end data integrity across all datasets.

## Disk Arithmetic
- Live feed duplication: 4 datasets × ~3.02 MB = 12.08 MB per game. Stored once: 3.02 MB (saving 9.06 MB/game).
- Boxscore duplication: 6 datasets × ~0.57 MB = 3.42 MB per game. Stored once: 0.57 MB (saving 2.85 MB/game).
- Total savings per game: ~11.91 MB uncompressed (~2.4 MB gzipped).
- Across 16 seasons (~38,880 games): Saves **~93 GB** uncompressed (~18.6 GB gzipped).

## Evidence
- Measured in `finish-mlb-history`: `raw/mlb_api` held 23.3 GB, of which ~12 GB was exact duplicate copies of live feeds and boxscores.
