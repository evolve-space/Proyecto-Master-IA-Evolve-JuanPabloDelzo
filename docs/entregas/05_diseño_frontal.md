# Diseño del Frontend de Bicing Cerca de Mí

## 1. Objetivo

El frontend del proyecto ofrece una interfaz cartográfica sencilla para:

- Localizar una posición de usuario dentro de Barcelona.
- Mostrar las tres estaciones de Bicing más cercanas.
- Consultar la predicción de disponibilidad de bicicletas mecánicas, eléctricas y anclajes libres a 5 y 10 minutos vista.

## 2. Tecnologías

- **React 19 + Vite**: generado con `pnpm create vite@latest frontend -- --template react`.
- **react-leaflet + Leaflet**: mapa interactivo con marcadores, popups, tooltips y agrupación en clústeres.
- **lucide-react**: iconografía de la tabla de predicciones.
- **CSS personalizado**: estilos globales en `frontend/src/App.css`.

## 3. Vista principal

La interfaz se divide en tres zonas verticales:

1. **Cabecera**: título "Bicing cerca de mí" y subtítulo "Ubicación del usuario y las tres estaciones más cercanas".
2. **Mapa**: ocupa el cuerpo principal y muestra la ubicación del usuario y las estaciones.
3. **Pie**: leyenda con el origen de los datos y el tema Bicing.

La siguiente imagen ilustra el resultado visual actual del frontend:

![Mockup frontal](../assets/05_mockup_frontal.png)

## 4. Pasos implementados

### 4.1 Carga de estaciones

Al iniciar la aplicación se consulta el endpoint `GET /api/informacion` del backend Flask. La respuesta, un diccionario de estaciones, se convierte a un array y se filtra descartando coordenadas fuera del área metropolitana de Barcelona.

### 4.2 Localización del usuario

En fase de desarrollo, se genera un punto aleatorio dentro del término municipal de Barcelona y se ajusta (snap) a la calle o acera peatonal más cercana:

- Se descarga y cachea el polígono administrativo de Barcelona desde Nominatim.
- Se usa `OSRM /routed-foot/nearest` para obtener el punto de la vía pública más cercano a pie.
- Si falla tras varios intentos, se recurre a un punto de respaldo en una zona urbana segura ( *felizmente hasta ahora no se ha recurrido a este punto*).

### 4.3 Selección de las tres estaciones más cercanas

1. Se ordenan las estaciones por distancia en línea recta (Haversine) y se toman las 8 primeras como candidatas.
2. Se consulta la distancia real caminando mediante el endpoint `OSRM /routed-foot/table` en una sola petición (timeout de 10 s y reintentos ante errores transitorios).
3. Se ordenan por distancia peatonal y se conservan las 3 más cercanas.
4. Si OSRM no devuelve distancia para alguna candidata, se conserva la distancia en línea recta como aproximación y se indica visualmente.

### 4.4 Renderizado del mapa

- La capa base se obtiene de OpenStreetMap.
- Las tres estaciones más cercanas se destacan con un marcador rosa tipo pin.
- El resto de estaciones se muestran como puntos atenuados y se agrupan en clústeres al reducir el zoom.
- La ubicación del usuario se representa con un punto azul con halo de pulso.
- Al hacer clic en una estación destacada se dispara la consulta de predicción.

### 4.5 Predicción

Al hacer clic en una estación destacada se llama a `POST /api/predict` enviando el `station_id`. La API carga el modelo `est_{station_id}` y los escaladores desde MLflow, prepara la última ventana disponible y devuelve la predicción en segundos. Al recibir la respuesta se muestra una tabla con:

- Bicicletas mecánicas a +5 y +10 minutos.
- Bicicletas eléctricas a +5 y +10 minutos.
- Anclajes libres a +5 y +10 minutos.

Cada fila de la tabla lleva un icono de `lucide-react` para facilitar la lectura: bicicleta para mecánicas, rayo para eléctricas y candado para anclajes.

### 4.6 Estilos e iconos

- Paleta de colores verde y rosa, inspirada en la identidad visual de Bicing.
- Tooltips al pasar el ratón sobre las estaciones destacadas, con dirección, código postal y distancia.
- Popups al hacer clic, con capacidad, distancia y tabla de predicción.
- Iconos de `lucide-react` en la tabla de predicción.

## 5. Integración con el backend

El frontend espera el backend Flask en `http://127.0.0.1:5002`:

- `GET /api/informacion`: listado de estaciones con coordenadas, dirección, código postal y capacidad. Solo se devuelven las estaciones que tienen un modelo registrado en MLflow.
- `POST /api/predict`: predicción para un `station_id` concreto, cargando el modelo desde MLflow.

MLflow debe estar ejecutándose previamente en `http://127.0.0.1:5000` con el comando:

```bash
mlflow server --backend-store-uri sqlite:///C:/Users/juand/mlflow.db --default-artifact-root C:/Users/juand/mlartifacts --serve-artifacts --host 127.0.0.1 --port 5000
```

## 6. Consideraciones

- El control de atribución de Leaflet está oculto en el mapa.
- La predicción carga un modelo ya entrenado desde MLflow. La primera petición de una estación descarga los artifacts en el servidor (~20-30 s); las siguientes usan el cache en memoria y son casi inmediatas. El entrenamiento previo se realiza una sola vez con `backend/scripts/train_all_stations.py`.
- Las distancias a pie se calculan con OSRM; si el servicio falla se muestra una distancia aproximada en línea recta.
- Desde la consola del navegador también se puede ver los resultados originales que arroja el modelo LSTM.
