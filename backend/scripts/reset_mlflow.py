import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("bicing_lstm_predictions")

# 1. Borrar runs del experimento
experiment = mlflow.get_experiment_by_name("bicing_lstm_predictions")
runs = mlflow.search_runs(experiment_ids=[experiment.experiment_id])

for run_id in runs["run_id"]:
    mlflow.delete_run(run_id)

# 2. Borrar el experimento completo
mlflow.delete_experiment(experiment.experiment_id)

# 3. Borrar modelos registrados del Model Registry
client = mlflow.tracking.MlflowClient()
for rm in client.search_registered_models():
    if rm.name.startswith("est_"):
        client.delete_registered_model(rm.name)