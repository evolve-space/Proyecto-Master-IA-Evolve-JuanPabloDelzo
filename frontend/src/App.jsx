import { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Tooltip, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { divIcon } from 'leaflet';
import { Bike, Lock, Zap } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
import './App.css';

const INFORMACION_API = 'http://localhost:5002/api/informacion';
const PREDICCION_API = 'http://localhost:5002/api/predict';

// Servicio público OSRM auto-hospedado por routing.openstreetmap.de con el
// perfil peatonal ("foot") ya procesado. A diferencia del demo oficial de
// project-osrm.org (que solo sirve el perfil "car"), este sí calcula rutas
// y distancias reales para ir caminando por aceras y calles peatonales.
// Nota: por cómo está desplegado el servicio, el segmento de la URL sigue
// llamándose "driving", pero el perfil realmente usado es el peatonal.
const FOOT_NEAREST_URL = 'https://routing.openstreetmap.de/routed-foot/nearest/v1/driving';
const FOOT_TABLE_URL = 'https://routing.openstreetmap.de/routed-foot/table/v1/driving';

// Nominatim: se usa una única vez para obtener el polígono administrativo
// real del municipio de Barcelona, de forma que la ubicación aleatoria del
// usuario caiga dentro de la ciudad y no en otros municipios del área
// metropolitana (l'Hospitalet, Badalona, etc.) que también entran dentro
// del rectángulo (bounding box) usado como filtro rápido.
const BARCELONA_BOUNDARY_URL =
  'https://nominatim.openstreetmap.org/search?city=Barcelona&country=Spain&format=json&polygon_geojson=1&featureType=city&limit=1';

// Nº de estaciones candidatas (por distancia en línea recta) para las que
// se consulta la distancia real caminando. Pedimos unas pocas más de las 3
// finales porque OSRM puede no devolver valor para algunas (por ejemplo, si
// caen en zonas peatonales no conectadas); así garantizamos que las 3 más
// cercanas finales tengan distancia a pie cuando sea posible.
const WALKING_CANDIDATE_COUNT = 8;

// Radio medio de la Tierra en kilómetros, usado en la fórmula de Haversine.
const EARTH_RADIUS_KM = 6371;

const fallbackStations = [
  { id: '1', name: 'Plaça de Catalunya', lat: 41.387015, lon: 2.170047, capacity: 20, postCode: '08002' },
  { id: '2', name: 'Passeig de Gràcia', lat: 41.391055, lon: 2.165064, capacity: 15, postCode: '08007' },
  { id: '3', name: 'Sagrada Família', lat: 41.403629, lon: 2.174356, capacity: 20, postCode: '08013' },
  { id: '4', name: 'Camp Nou', lat: 41.380896, lon: 2.12282, capacity: 17, postCode: '08028' },
  { id: '5', name: 'Barceloneta', lat: 41.380729, lon: 2.18985, capacity: 20, postCode: '08003' },
  { id: '6', name: 'Arc de Triomf', lat: 41.391052, lon: 2.180644, capacity: 15, postCode: '08018' },
  { id: '7', name: "Plaça d'Espanya", lat: 41.374962, lon: 2.149805, capacity: 20, postCode: '08015' },
  { id: '8', name: 'Glòries', lat: 41.402235, lon: 2.188346, capacity: 18, postCode: '08013' },
];

// Área metropolitana de Barcelona (con margen). Sirve para descartar
// estaciones con coordenadas erróneas o de pruebas (p. ej. entradas de test
// en la base de datos con lat/lon de otra ciudad), que de otro modo
// aparecerían como marcadores sueltos fuera del mapa real.
const BCN_BOUNDS = { minLat: 41.15, maxLat: 41.55, minLon: 1.9, maxLon: 2.35 };

// Término municipal de Barcelona: rectángulo que contiene todo el
// municipio real, incluyendo sus "rincones" (Tibidabo, Zona Franca,
// Besòs, Barceloneta, Horta...). Se usa para muestrear la ubicación
// aleatoria del usuario, y luego el polígono real de Nominatim y el
// control de snap a calle descartan agua, montaña sin aceras, etc.
const BCN_CITY_BOUNDS = { minLat: 41.32, maxLat: 41.47, minLon: 2.05, maxLon: 2.23 };

// Zona urbana central segura, usada únicamente como fallback si todo lo
// demás falla. Garantiza que, incluso sin servicios externos, la
// ubicación del usuario caiga en una calle real de Barcelona.
const SAFE_URBAN_BOUNDS = { minLat: 41.36, maxLat: 41.415, minLon: 2.12, maxLon: 2.205 };

// Si OSRM nearest devuelve una calle a más de esta distancia (en metros),
// se considera que el punto cae en una zona no accesible (agua, patio
// cerrado, gran parque...) y se reintenta con otro punto aleatorio.
const MAX_SNAP_DISTANCE_METERS = 180;

// Da formato legible a una distancia en kilómetros: en metros si es corta,
// o en km con dos decimales si es más larga.
const formatDistance = (km) => (km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(2)} km`);

// Convierte el objeto { "<station_id>": { address, capacity, latitud, longitud, post_code } }
// devuelto por la API en un array de estaciones fácil de renderizar en el mapa.
const toStations = (data) => {
  if (!data || typeof data !== 'object') return [];
  return Object.entries(data)
    .map(([id, info]) => ({
      id,
      name: info.address || `Estación ${id}`,
      lat: info.latitud,
      lon: info.longitud,
      capacity: info.capacity,
      postCode: info.post_code,
    }))
    .filter(
      (s) =>
        typeof s.lat === 'number' &&
        typeof s.lon === 'number' &&
        s.lat >= BCN_BOUNDS.minLat &&
        s.lat <= BCN_BOUNDS.maxLat &&
        s.lon >= BCN_BOUNDS.minLon &&
        s.lon <= BCN_BOUNDS.maxLon,
    );
};

const toRad = (deg) => (deg * Math.PI) / 180;

// Distancia en línea recta entre dos puntos geográficos (en km) según la
// fórmula de Haversine, que asume la Tierra como una esfera:
//   d = 2R · arcsin( sqrt( sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2) ) )
// Se usa solo como preselección rápida (sin llamadas de red) para acotar
// las estaciones candidatas antes de pedir la distancia real caminando;
// la distancia final que se muestra y con la que se decide cuáles son las
// "3 más cercanas" es la distancia peatonal real (ver fetchWalkingDistancesTable).
const haversineDistanceKm = (lat1, lon1, lat2, lon2) => {
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
};

// Caché del polígono de Barcelona: en memoria + localStorage para evitar
// descargarlo de Nominatim en cada recarga de la app.
let barcelonaPolygonCache = null;
const POLYGON_CACHE_KEY = 'bicing-barcelona-polygon';
const POLYGON_CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 días

const getCachedBarcelonaPolygon = () => {
  if (barcelonaPolygonCache) return barcelonaPolygonCache;
  try {
    const stored = localStorage.getItem(POLYGON_CACHE_KEY);
    if (!stored) return null;
    const { geojson, timestamp } = JSON.parse(stored);
    if (!geojson || Date.now() - timestamp > POLYGON_CACHE_TTL_MS) {
      localStorage.removeItem(POLYGON_CACHE_KEY);
      return null;
    }
    barcelonaPolygonCache = geojson;
    return geojson;
  } catch {
    return null;
  }
};

const setCachedBarcelonaPolygon = (geojson) => {
  barcelonaPolygonCache = geojson;
  try {
    localStorage.setItem(POLYGON_CACHE_KEY, JSON.stringify({ geojson, timestamp: Date.now() }));
  } catch {
    // localStorage puede estar bloqueado: se ignora.
  }
};

// Descarga el límite administrativo de Barcelona como GeoJSON. Si Nominatim
// no responde rápido, se devuelve `null` y el resto del flujo usa el
// rectángulo BCN_CITY_BOUNDS + el control de snap a calle.
const fetchBarcelonaPolygon = async () => {
  const cached = getCachedBarcelonaPolygon();
  if (cached) return cached;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1500);
    const res = await fetch(BARCELONA_BOUNDARY_URL, { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) return null;
    const data = await res.json();
    const geojson = data?.[0]?.geojson;
    if (!geojson || (geojson.type !== 'Polygon' && geojson.type !== 'MultiPolygon')) return null;
    setCachedBarcelonaPolygon(geojson);
    return geojson;
  } catch {
    return null;
  }
};

// Comprueba si un punto está dentro de un anillo (ring) de coordenadas
// [lon, lat] mediante el algoritmo de "ray casting".
const isPointInRing = (lat, lon, ring) => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersects = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
};

// Comprueba si un punto cae dentro del polígono (o multipolígono) de
// Barcelona. Solo se evalúa el anillo exterior de cada polígono (se
// ignoran agujeros/enclaves), suficiente para descartar puntos fuera del
// término municipal.
const isPointInBarcelona = (lat, lon, geojson) => {
  if (!geojson) return true; // sin polígono disponible: no se descarta el punto
  const polygons = geojson.type === 'MultiPolygon' ? geojson.coordinates : [geojson.coordinates];
  return polygons.some(([outerRing]) => isPointInRing(lat, lon, outerRing));
};

// Punto aleatorio dentro de todo el término municipal de Barcelona, para
// que el usuario pueda aparecer en cualquier rincón de la ciudad.
const randomUserPoint = () => ({
  lat: BCN_CITY_BOUNDS.minLat + Math.random() * (BCN_CITY_BOUNDS.maxLat - BCN_CITY_BOUNDS.minLat),
  lon: BCN_CITY_BOUNDS.minLon + Math.random() * (BCN_CITY_BOUNDS.maxLon - BCN_CITY_BOUNDS.minLon),
});

// Punto aleatorio dentro de una zona urbana segura del centro, usado solo
// como fallback si los servicios externos no responden.
const randomFallbackPoint = () => ({
  lat: SAFE_URBAN_BOUNDS.minLat + Math.random() * (SAFE_URBAN_BOUNDS.maxLat - SAFE_URBAN_BOUNDS.minLat),
  lon: SAFE_URBAN_BOUNDS.minLon + Math.random() * (SAFE_URBAN_BOUNDS.maxLon - SAFE_URBAN_BOUNDS.minLon),
  snapped: false,
});

// Genera un punto aleatorio dentro del centro urbano de Barcelona y lo
// ajusta (snap) a la calle/acera peatonal más cercana usando el servicio
// OSRM "nearest" con perfil peatonal. Se comprueba que:
//   1. el punto esté dentro del polígono municipal real de Barcelona;
//   2. OSRM encuentre una calle a una distancia razonable (no mar/agua);
//   3. el punto ajustado siga dentro del polígono y del área urbana densa.
// Si algún paso falla, se reintenta unos pocos intentos; al final se
// devuelve un punto seguro de respaldo para no bloquear la aplicación.
const generateUserLocationOnStreet = async (attempts = 6) => {
  const barcelonaPolygon = await fetchBarcelonaPolygon();

  for (let i = 0; i < attempts; i += 1) {
    const { lat, lon } = randomUserPoint();
    if (!isPointInBarcelona(lat, lon, barcelonaPolygon)) continue;

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3500);
      const res = await fetch(`${FOOT_NEAREST_URL}/${lon},${lat}?number=1`, {
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!res.ok) continue;
      const data = await res.json();
      const waypoint = data?.waypoints?.[0];
      const snapped = waypoint?.location;
      const snapDistance = waypoint?.distance;

      if (data.code !== 'Ok' || !Array.isArray(snapped)) continue;
      // Si la calle más cercana está lejos (>150 m), probablemente caemos
      // en agua, un gran parque sin aceras o un patio cerrado: se descarta.
      if (typeof snapDistance === 'number' && snapDistance > MAX_SNAP_DISTANCE_METERS) continue;

      const [snappedLon, snappedLat] = snapped;
      // Cerca del límite municipal, el punto ajustado a la calle más
      // cercana podría caer en un municipio vecino: se descarta y se
      // reintenta en ese caso.
      if (isPointInBarcelona(snappedLat, snappedLon, barcelonaPolygon)) {
        return { lat: snappedLat, lon: snappedLon, snapped: true };
      }
    } catch {
      // Se ignora y se reintenta con otro punto aleatorio.
    }
  }
  // Último recurso: un punto aleatorio dentro de una zona urbana segura del
  // centro, para no quedarnos sin ubicación ni caer siempre en el mismo sitio.
  return randomFallbackPoint();
};

// Distancias reales caminando (en metros) desde un punto a varias estaciones
// usando el servicio /table de OSRM en una sola petición. Devuelve `null`
// si el servicio no responde, para que quien llame pueda recurrir a la
// distancia en línea recta.
const fetchWalkingDistancesTable = async (from, stations, retries = 2) => {
  if (stations.length === 0) return null;
  const coordinates = [from, ...stations].map((p) => `${p.lon},${p.lat}`).join(';');
  const destinations = stations.map((_, i) => i + 1).join(';');
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    let timeout;
    try {
      const controller = new AbortController();
      timeout = setTimeout(() => controller.abort(), 10000);
      const res = await fetch(
        `${FOOT_TABLE_URL}/${coordinates}?annotations=distance&sources=0&destinations=${destinations}`,
        { signal: controller.signal },
      );
      // Cualquier fallo transitorio (rate-limit, timeout, error 5xx) se reintenta.
      if ((!res.ok || res.status === 429) && attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
        continue;
      }
      if (!res.ok) return null;
      const data = await res.json();
      if (data.code !== 'Ok') return null;
      const row = data?.distances?.[0];
      if (!Array.isArray(row) || row.length !== stations.length) return null;
      return row;
    } catch {
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
        continue;
      }
      return null;
    } finally {
      if (timeout) clearTimeout(timeout);
    }
  }
  return null;
};

// Icono tipo "pin globo" rosa, similar a un marcador de estación de bicis.
const bikeStationIcon = divIcon({
  className: 'bike-marker',
  html: `
    <div class="bike-marker-head">
      <span class="bike-marker-dot"></span>
    </div>
    <div class="bike-marker-stem"></div>
    <div class="bike-marker-shadow"></div>
  `,
  iconSize: [26, 38],
  iconAnchor: [13, 36],
  popupAnchor: [0, -34],
});

// Icono para la ubicación (simulada) del usuario: un punto azul con halo,
// siguiendo la convención habitual de "mi ubicación" en mapas.
const userLocationIcon = divIcon({
  className: 'user-marker',
  html: `
    <div class="user-marker-halo"></div>
    <div class="user-marker-dot"></div>
  `,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

// Icono atenuado (pequeño punto gris/rosa translúcido) para las estaciones
// que no están entre las dos más cercanas al usuario. Sirve solo de
// contexto visual, sin protagonismo ni interacción.
const dimmedStationIcon = divIcon({
  className: 'dimmed-marker',
  html: `<div class="dimmed-marker-dot"></div>`,
  iconSize: [10, 10],
  iconAnchor: [5, 5],
});

// Icono de "clúster" (grupo de estaciones cercanas) a bajo zoom, con el
// mismo tema rosa/verde Bicing, pero atenuado: agrupa el resto de
// estaciones que no son las dos más cercanas al usuario, mostradas solo
// como contexto. El tamaño crece ligeramente con el nº de estaciones
// agrupadas para dar una pista visual de densidad.
const createDimmedClusterIcon = (cluster) => {
  const count = cluster.getChildCount();
  const size = count < 10 ? 26 : count < 50 ? 32 : 38;
  return divIcon({
    html: `<div class="dimmed-cluster-bubble" style="width:${size}px;height:${size}px;">${count}</div>`,
    className: 'dimmed-cluster',
    iconSize: [size, size],
  });
};

// Leaflet mide el tamaño de su contenedor al montarse. Dentro de un layout
// flexbox (header + mapa + footer) ese tamaño puede terminar de resolverse
// después de que el mapa ya se inicializó, desalineando tiles y marcadores
// (más visible al reducir el zoom). Este componente fuerza un recálculo
// (`invalidateSize`) cada vez que el contenedor cambia de tamaño.
function MapResizeHandler() {
  const map = useMap();
  const containerRef = useRef(null);

  useEffect(() => {
    containerRef.current = map.getContainer();

    // Recalcula en cuanto el contenedor obtiene su tamaño final.
    map.invalidateSize();

    const handleResize = () => map.invalidateSize();

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(containerRef.current);
    window.addEventListener('resize', handleResize);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', handleResize);
    };
  }, [map]);

  return null;
}

// Centra y hace zoom suave sobre una posición cuando esta cambia (se usa
// para llevar el mapa hasta la ubicación aleatoria del usuario en cuanto
// se calcula, sin esperar a que el usuario navegue manualmente).
function FlyToLocation({ position, zoom }) {
  const map = useMap();

  useEffect(() => {
    if (position) {
      map.flyTo(position, zoom, { duration: 1.2 });
    }
  }, [position, zoom, map]);

  return null;
}

function App() {
  const [stations, setStations] = useState([]);
  const [loadingStations, setLoadingStations] = useState(true);
  const [userLocation, setUserLocation] = useState(null);
  const [loadingLocation, setLoadingLocation] = useState(true);
  const [nearestStations, setNearestStations] = useState([]);
  const [computingNearest, setComputingNearest] = useState(false);
  const [predictions, setPredictions] = useState({});
  const [predictionLoading, setPredictionLoading] = useState({});
  const [predictionError, setPredictionError] = useState({});
  const locationInitStarted = useRef(false);

  useEffect(() => {
    fetch(INFORMACION_API)
      .then((res) => res.json())
      .then((data) => {
        const parsed = toStations(data);
        setStations(parsed.length ? parsed : fallbackStations);
      })
      .catch(() => setStations(fallbackStations))
      .finally(() => setLoadingStations(false));

    // Ubicación aleatoria del usuario, generada una única vez al cargar la
    // aplicación, dentro de Barcelona ciudad y ajustada a la calle/acera
    // peatonal más cercana. El flag locationInitStarted evita que React
    // Strict Mode / HMR generen la ubicación varias veces en desarrollo.
    if (locationInitStarted.current) return undefined;
    locationInitStarted.current = true;

    const locationTimeout = setTimeout(() => {
      setUserLocation(randomFallbackPoint());
      setLoadingLocation(false);
    }, 5000);

    generateUserLocationOnStreet()
      .then((location) => {
        clearTimeout(locationTimeout);
        setUserLocation(location);
      })
      .catch(() => {
        clearTimeout(locationTimeout);
        setUserLocation(randomFallbackPoint());
      })
      .finally(() => {
        setLoadingLocation(false);
      });

    return () => clearTimeout(locationTimeout);
  }, []);

  // Una vez hay estaciones y ubicación de usuario: preselecciona las
  // estaciones candidatas por distancia en línea recta (Haversine) y pide
  // al servicio de rutas peatonales la distancia real caminando a cada
  // una, para quedarse con las 3 más cercanas según esa distancia real
  // (no la euclidiana).
  useEffect(() => {
    if (!userLocation || stations.length === 0) return undefined;

    let cancelled = false;
    setComputingNearest(true);

    const run = async () => {
      const candidates = stations
        .map((s) => ({
          ...s,
          straightLineKm: haversineDistanceKm(userLocation.lat, userLocation.lon, s.lat, s.lon),
        }))
        .sort((a, b) => a.straightLineKm - b.straightLineKm)
        .slice(0, WALKING_CANDIDATE_COUNT);

      const walkingMeters = await fetchWalkingDistancesTable(userLocation, candidates);

      const withWalkingDistance = candidates.map((s, i) => {
        const meters = walkingMeters?.[i];
        return {
          ...s,
          distanceKm: meters != null ? meters / 1000 : s.straightLineKm,
          isWalkingDistance: meters != null,
        };
      });

      withWalkingDistance.sort((a, b) => a.distanceKm - b.distanceKm);

      if (!cancelled) {
        setNearestStations(withWalkingDistance.slice(0, 3));
        setComputingNearest(false);
      }
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [stations, userLocation]);

  // Al hacer clic en una estación, llama a la API de predicción LSTM y
  // guarda el resultado para esa station_id. La primera predicción de una
  // estación descarga el modelo desde MLflow (puede tardar ~20-30 s); las
  // siguientes usan el cache del servidor y son casi inmediatas.
  const fetchPrediction = async (stationId) => {
    if (predictionLoading[stationId]) return;

    setPredictionLoading((prev) => ({ ...prev, [stationId]: true }));
    setPredictionError((prev) => ({ ...prev, [stationId]: null }));

    // AbortController para evitar que peticiones antiguas queden colgadas
    // si el usuario cierra el popup; timeout de 2 min por la descarga inicial.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000);

    try {
      const res = await fetch(PREDICCION_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ station_id: Number(stationId) }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Error desconocido');

      // Log de seguridad en consola con los valores no redondeados
      // recibidos desde informacion_api.py (antes de mostrarlos redondeados).
      console.group('Predicción recibida (valores raw) - estación', stationId);
      data.predictions?.forEach((p) => {
        console.log(
          `+${p.horizon_minutes} min → mecánicas: ${p.nbm}, eléctricas: ${p.nbe}`,
        );
      });
      console.log('Último timestamp disponible:', data.last_timestamp);
      console.groupEnd();

      setPredictions((prev) => ({ ...prev, [stationId]: data }));
    } catch (err) {
      if (err.name === 'AbortError') {
        setPredictionError((prev) => ({
          ...prev,
          [stationId]:
            'La petición ha tardado demasiado. Asegúrate de que informacion_api.py esté en ejecución.',
        }));
        return;
      }

      // Detectamos específicamente cuando la API no responde (refused,
      // timeout, etc.) para dar un mensaje más útil al usuario.
      const isConnectionError =
        err.message?.includes('Failed to fetch') ||
        err.message?.includes('NetworkError') ||
        err.message?.includes('connection refused');
      const friendlyMessage = isConnectionError
        ? 'No se pudo conectar con la API. Asegúrate de ejecutar: python backend/api/informacion_api.py'
        : err.message;
      setPredictionError((prev) => ({ ...prev, [stationId]: friendlyMessage }));
    } finally {
      clearTimeout(timeoutId);
      setPredictionLoading((prev) => ({ ...prev, [stationId]: false }));
    }
  };

  // El resto de estaciones (todas menos las 3 más cercanas) se muestran
  // solo como contexto visual, atenuadas.
  const otherStations = useMemo(() => {
    const nearestIds = new Set(nearestStations.map((s) => s.id));
    return stations.filter((s) => !nearestIds.has(s.id));
  }, [stations, nearestStations]);

  const loading = loadingStations || loadingLocation;

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Bicing cerca de mí</h1>
        <p>Ubicación del usuario y las estaciones más cercanas</p>
        {computingNearest && <span className="nearest-loading">Calculando estaciones más cercanas…</span>}
      </header>
      <main className="map-container">
        {loading && (
          <div className="program-loader">
            <div className="hourglass" aria-label="Reloj de arena animado">
              <div className="hourglass-top"></div>
              <div className="hourglass-bottom"></div>
            </div>
            <p className="loader-title">Abriendo el programa…</p>
            <p className="loader-detail">
              {loadingLocation
                ? 'Localizando tu posición en la calle…'
                : 'Cargando estaciones…'}
            </p>
          </div>
        )}
        <MapContainer
          center={[41.3851, 2.1734]}
          zoom={13}
          minZoom={11}
          maxZoom={18}
          maxBounds={[
            [BCN_BOUNDS.minLat, BCN_BOUNDS.minLon],
            [BCN_BOUNDS.maxLat, BCN_BOUNDS.maxLon],
          ]}
          maxBoundsViscosity={1.0}
          scrollWheelZoom
          attributionControl={false}
          className="map"
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />
          <MapResizeHandler />

          {userLocation && <FlyToLocation position={[userLocation.lat, userLocation.lon]} zoom={15} />}

          {/* Resto de estaciones: solo como contexto visual, atenuadas y agrupadas. */}
          <MarkerClusterGroup
            iconCreateFunction={createDimmedClusterIcon}
            maxClusterRadius={70}
            spiderfyOnMaxZoom={false}
            showCoverageOnHover={false}
          >
            {otherStations.map((s) => (
              <Marker key={s.id} position={[s.lat, s.lon]} icon={dimmedStationIcon} interactive={false} />
            ))}
          </MarkerClusterGroup>

          {/* Las tres estaciones más cercanas al usuario, destacadas como antes.
              Al hacer click sobre una de ellas se pide la predicción LSTM y
              se muestra junto a la información de la estación. */}
          {nearestStations.map((s, index) => {
            const pred = predictions[s.id];
            const isLoading = predictionLoading[s.id];
            const hasError = predictionError[s.id];

            const pred5 = pred?.predictions?.find((p) => p.horizon_minutes === 5);
            const pred10 = pred?.predictions?.find((p) => p.horizon_minutes === 10);
            const nbm5 = Math.round(pred5?.nbm ?? 0);
            const nbe5 = Math.round(pred5?.nbe ?? 0);
            const nbm10 = Math.round(pred10?.nbm ?? 0);
            const nbe10 = Math.round(pred10?.nbe ?? 0);
            const capacity = s.capacity ?? 0;
            const docks5 = Math.max(0, capacity - nbm5 - nbe5);
            const docks10 = Math.max(0, capacity - nbm10 - nbe10);

            return (
              <Marker
                key={s.id}
                position={[s.lat, s.lon]}
                icon={bikeStationIcon}
                eventHandlers={{
                  click: () => {
                    console.log('%cEstación seleccionada:', 'color: orange; font-weight: bold;',s.id);
                    fetchPrediction(s.id);
                  },
                }}
              >
                <Tooltip direction="top" offset={[0, -30]} opacity={1}>
                  <div className="tooltip-content">
                    <span>
                      <strong>Dirección:</strong> {s.name}
                    </span>
                    {s.postCode && (
                      <span>
                        <strong>Código postal:</strong> {s.postCode}
                      </span>
                    )}
                    <span>
                      <strong>{s.isWalkingDistance ? 'Distancia a pie:' : 'Distancia aprox.:'}</strong>{' '}
                      {formatDistance(s.distanceKm)}
                      {!s.isWalkingDistance && ' (línea recta)'}
                    </span>
                  </div>
                </Tooltip>
                <Popup>
                  <div className="popup-content">
                    <strong>
                      {index === 0 ? '1ª más cercana' : index === 1 ? '2ª más cercana' : '3ª más cercana'} · {s.name}
                    </strong>
                    <span>Capacidad: {s.capacity} anclajes</span>
                    {s.postCode && <span>Código Postal: {s.postCode}</span>}
                    <span>
                      {s.isWalkingDistance ? 'Distancia caminando: ' : 'Distancia aprox. (línea recta): '}
                      {formatDistance(s.distanceKm)}
                    </span>

                    <div className="prediction-section">
                      {!isLoading && <strong>Predicción</strong>}
                      {isLoading ? (
                        <div className="prediction-spinner">
                          <div className="spinner-wheel" aria-label="Calculando predicción">
                            {Array.from({ length: 8 }).map((_, i) => (
                              <span key={i} className="spinner-dot" style={{ '--i': i }}></span>
                            ))}
                          </div>
                          <span className="prediction-loading">Un momento por favor…</span>
                        </div>
                      ) : hasError ? (
                        <span className="prediction-error">Error: {hasError}</span>
                      ) : pred ? (
                        <table className="prediction-table">
                          <thead>
                            <tr>
                              <th></th>
                              <th>+ 5 min</th>
                              <th>+ 10 min</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <td>
                                <Bike size={14} /> Mecánicas
                              </td>
                              <td>{nbm5}</td>
                              <td>{nbm10}</td>
                            </tr>
                            <tr>
                              <td>
                                <Zap size={14} /> Eléctricas
                              </td>
                              <td>{nbe5}</td>
                              <td>{nbe10}</td>
                            </tr>
                            <tr>
                              <td>
                                <Lock size={14} /> Docks
                              </td>
                              <td>{docks5}</td>
                              <td>{docks10}</td>
                            </tr>
                          </tbody>
                        </table>
                      ) : (
                        <span className="prediction-hint">Haz clic en el marcador para predecir</span>
                      )}
                    </div>
                  </div>
                </Popup>
              </Marker>
            );
          })}

          {/* Ubicación (simulada) del usuario, siempre sobre una calle. */}
          {userLocation && (
            <Marker position={[userLocation.lat, userLocation.lon]} icon={userLocationIcon}>
              <Popup>
                <div className="popup-content">
                  <strong>Tu ubicación</strong>
                  <span>{userLocation.snapped ? 'Ajustada a la calle más cercana' : 'Posición aproximada'}</span>
                </div>
              </Popup>
            </Marker>
          )}
        </MapContainer>
      </main>
      <footer className="dashboard-footer">
        Datos de la API de estaciones de bicicletas públicas de Barcelona · Tema Bicing
      </footer>
    </div>
  );
}

export default App;
