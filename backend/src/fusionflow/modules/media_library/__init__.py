"""Media Library — a read-only catalog of media assets uploaded through
existing connector upload endpoints (currently only Cloudflare R2's
`/connectors/{instance_id}/media`). This module does not perform any
uploads or storage itself; it only records metadata about objects that
another module has already stored.
"""
