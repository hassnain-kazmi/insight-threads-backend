"""
Run pipeline Celery tasks in the current process to refresh the DB.

Runs for all users (no user_id filter). Order: cluster → timeseries → anomaly
→ insight → umap. Usage: python run_pipeline_sync.py
"""

import importlib
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logging.getLogger("prophet.plot").setLevel(logging.CRITICAL)

JOBS = [
    ("Clustering", "app.tasks.cluster_job", "run_clustering_job"),
    (
        "Timeseries summaries",
        "app.tasks.timeseries_job",
        "compute_timeseries_summaries",
    ),
    ("Anomaly detection", "app.tasks.anomaly_job", "detect_cluster_anomalies"),
    ("Insight generation", "app.tasks.insight_job", "generate_cluster_insights"),
    ("UMAP projections", "app.tasks.umap_job", "compute_umap_projections"),
]

for label, module_path, task_name in JOBS:
    print(f"\n--- {label} ---")
    mod = importlib.import_module(module_path)
    task = getattr(mod, task_name)
    result = task.apply()
    out = result.get() if hasattr(result, "get") else result
    print(f"Result: {out}")

print("\nAll done.")
