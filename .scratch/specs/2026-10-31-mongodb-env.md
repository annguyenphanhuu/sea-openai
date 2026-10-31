# MongoDB connection setup

The shared connection module reads MongoDB configuration from the repository's
`.env`, with operating-system variables taking precedence. `MongoSettings` is a
frozen record. Its URI, username, and password are excluded from its representation.

`MONGODB_URI` is required. `MONGODB_DATABASE` defaults to `sea_openai`.
Credentials can be embedded in the URI or supplied together through
`MONGODB_USERNAME` and `MONGODB_PASSWORD`. Separate credentials override the URI.
The loader preserves raw credentials and does not expand variable references.

`mongo_database()` yields a PyMongo database and closes the client on exit.
Connections decode timezone-aware dates and limit connection, server selection,
and operation timeouts to five seconds. Importing the module does not connect
or change the process environment.

`python -m platform_huy.mongodb` runs a read-only ping. Success exits zero.
Configuration and driver failures exit one without printing connection secrets.
Setup does not create collections, implement a state adapter, or migrate SQLite.

The direct-client alternative requires every caller to repeat configuration and
cleanup. The selected settings record and context manager centralize those duties
without adding an ORM or storage abstraction.

Verify isolated configuration, cleanup, and CLI tests. The parent task owns the
live ping and complete acceptance suite.
