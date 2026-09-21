"""Shared plumbing for the four Google connectors (Calendar/Gmail/Meet/Sheets).

See `google.oauth` for the actual helper functions - this package has no
adapter of its own (unlike `whatsapp/`, `razorpay/`, `cloudflare_r2/`,
which each register exactly one `ConnectorAdapter`); each Google product
is its own adapter package (`connectors.google_calendar`,
`connectors.gmail`, `connectors.google_meet`, `connectors.google_sheets`)
so it gets its own `connector_types` row/category/icon, but all four share
one Google Cloud OAuth app and therefore one token-exchange/refresh
implementation, kept here to avoid four near-identical copies.
"""
