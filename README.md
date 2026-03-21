## Quick Start
- Install dependencies: Ensure you have `python`, `docker`, `uv`, and `pwgen` installed on your system.
- Setup `.env` file by copying `.env.example` and renaming it to `.env` and set secret variables to secure values
- Run node guard: Use the command corresponding to your environment:
```shell
# dev
make dev
# prod
make prod
```

## Known Issues And Limitations
- NTP time is required to system stability. Timestamps are used in GC, alerting scenarios and so on.
- Alert Duplication - system guarantees at-least-once delivery, not exactly-once. This is a deliberate compromise in favor of decentralization and simplicity.
- Notification extensibility: Telegram is currently hardcoded. If a request is created in Issues, I'll move the recipient configuration and support for other platforms (Slack, Webhooks, Email) to State so they can be managed via the cluster-wide API.
- Lack of formal consensus.
  This is neither Raft nor Paxos. The system is built on Gossip and CRDT. It does not guarantee strong consistency, but it does provide high availability and survivability during network partitions.

## Future
- Automatic Node Eviction: Detect and remove inactive nodes from the cluster state to trigger seamless monitoring rebalancing.
- Cover 90+% of the project with tests
- Documentation of 3 levels: code, architecture, math
- Refactor (NodeController): decompose core logic in several classes which will be initialized in node controller
