class ClusterMismatchError(Exception):
    def __init__(self, cluster_id: str) -> None:
        self.cluster_id = cluster_id
        super().__init__(f"Cluster ID mismatch, peer cluster_id: {cluster_id!r}")
