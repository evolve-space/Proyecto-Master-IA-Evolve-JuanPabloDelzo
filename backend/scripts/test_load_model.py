import sys
import traceback

sys.path.insert(0, r"backend\scripts\silver")
sys.path.insert(0, r"backend\scripts")

import mlflow

mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("bicing_lstm_predictions")

runs = mlflow.search_runs(
    filter_string="tags.`mlflow.runName` = 'est_9'",
    order_by=["start_time DESC"],
    max_results=1,
)

if runs.empty:
    print("No se encontró run para est_9")
else:
    run_id = runs.iloc[0].run_id
    print("run_id:", run_id)
    try:
        model = mlflow.tensorflow.load_model(f"runs:/{run_id}/model")
        print("Modelo cargado OK:", type(model))
    except Exception as e:
        print("ERROR al cargar:")
        traceback.print_exc()
