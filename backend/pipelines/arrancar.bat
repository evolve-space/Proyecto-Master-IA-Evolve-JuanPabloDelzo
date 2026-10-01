@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: Lanza los tres servicios del proyecto Bicing en terminales separadas.
:: MLflow debe arrancar primero, ya que la API descarga los modelos desde él.

echo Iniciando MLflow (base de datos y artifact store)...
start "MLflow - Bicing" cmd /k "cd /d C:\Users\juand && mlflow server --backend-store-uri sqlite:///C:/Users/juand/mlflow.db --default-artifact-root C:/Users/juand/mlartifacts --serve-artifacts --host 127.0.0.1 --port 5000"

echo Iniciando API Flask de estaciones y predicciones...
start "API Bicing" cmd /k "cd /d C:\Users\juand\OneDrive\Documentos\Evolve\Proyecto-Bicing && python backend/api/informacion_api.py"

echo Iniciando dashboard React...
start "Frontend Bicing" cmd /k "cd /d C:\Users\juand\OneDrive\Documentos\Evolve\Proyecto-Bicing\frontend && pnpm run dev"

echo.
echo Los tres servicios se han lanzado en ventanas independientes.
echo   - MLflow:        http://127.0.0.1:5000
echo   - API Flask:     http://127.0.0.1:5002/api/informacion
echo   - Frontend:      http://localhost:5173  (o el puerto que indique Vite)
pause
