# OpenTripPlanner para Galicia

Este repositorio contiene un sistema de configuración de OpenTripPlanner (OTP) adaptado para la región de Galicia, España. OTP es una plataforma de planificación de rutas multimodales que permite a los usuarios encontrar las mejores rutas utilizando diferentes medios de transporte, como caminar, bicicleta, transporte público y automóvil.

Este repositorio incluye:

- Tareas de descarga automáticas:
  - OpenTripPlanner: Descarga de la última versión estable en JAR
  - GeoFabrik: Datos de OpenStreetMap para Galicia
  - GTFS: Transporte Público de Galicia (interurbanos, y urbanos de Ferrol y Pontevedra)
  - GTFS: Renfe (General, FEVE y Cercanías)
  - GTFS: Urbano de A Coruña
  - GTFS: Urbano de Ourense
  - GTFS: Urbano de Vigo
- Feeds "de la comunidad":
  - GTFS: Santiago de Compostela (WIP)
  - GTFS: Ourense (WIP)
  - GTFS: Lugo
- Proxy del GTFS RealTime de Renfe para integración con OTP
- Configuración de OpenTripPlanner para cargar los datos descargados y el tiempo real de Renfe
- Tareas para ejecutar OTP directamente

## Instalación y uso

Para ejecutar los contenidos de este repositorio, es necesario tener descargado:

- **Java 25 LTS**: en sistemas Windows o macOS, se recomienda descargar de [Adoptium](https://adoptium.net/). En sistemas Linux, se puede instalar OpenJDK 25 desde los repositorios oficiales.
- **Task**: Se recomienda tener [Task](https://taskfile.dev/) instalado para gestionar las tareas definidas en el `Taskfile.yml`. Alternativamente, se pueden ejecutar directamente, pero es más sencillo con Task.
- **Python y `uv`**: Para el proxy de tiempo real de Renfe, es necesario tener Python, con los paquetes `Flask`, `requests` y `protobuf` instalados. Utilizando [`uv`](https://docs.astral.sh/uv) se puede con solo una línea. El Taskfile asume que se está utilizando `uv` directamente.
- **Clave de API del NAP del Ministerio de Transportes**: Para poder descargar los feeds disponibles en el Punto de Acceso Nacional (NAP), es necesario registrarse y obtener una clave de API en [https://nap.transportes.gob.es/](https://nap.transportes.gob.es/).

Para descargar los datos y ejecutar OTP, se pueden utilizar las siguientes tareas:

```bash
git clone https://github.com/tpgalicia/opentripplanner-galicia.git
cd opentripplanner-galicia
task setup
task download-feeds NAP_API_KEY=tu_clave_de_api_aqui
```

Iniciar OpenTripPlanner:

```bash
task aio
```

>[!NOTE]
>La tarea `aio` inicia OpenTripPlanner generando el grafo en memoria y utilizándolo directamente. Esto implica que cada vez que se inicie OTP, se generará el grafo desde cero, lo cual puede llevar tiempo dependiendo del tamaño de los datos y del hardware disponible. Alternativamente, se puede utilizar la tarea `build` para generar el grafo (`graph.obj`) una sola vez y luego utilizar la tarea `run` para iniciar OTP utilizando el grafo ya generado, lo que acelera significativamente el tiempo de inicio en ejecuciones posteriores.

## Proxy de tiempo real de Renfe

El operador ferroviario Renfe proporciona datos de tiempo real en formato GTFS-RT para los servicios de Cercanías (aparentemente, no incluyendo los de Ancho Métrico) y Media/Larga Distancia (no incluyendo regionales). El problema es que estos datos son expuestos únicamente en JSON mientras que OTP requiere el formato GTFS-RT en protobuf. Además, expresan el retraso en segundos con el campo `delay` para todo el trip en lugar de mediante un `StopTimeUpdate` con una parada de referencia.

Para solucionar esto, se incluye un proxy simple implementado en Python utilizando Flask que convierte las peticiones de GTFS-RT de Renfe al formato esperado por OTP. El proxy escucha en el puerto 5000 y expone un único endpoint `/proxy` que realiza una petición al endpoint real de Renfe, transforma la respuesta y la devuelve.

El proxy aún es muy básico, no maneja todos los trip updates y no gestiona otro tipo de entidades de actualización de estado (por ejemplo, `VehiclePosition` o `Alert`). Sin embargo, es suficiente para que OTP pueda utilizar los datos de tiempo real de Renfe en las rutas planificadas.

## Submódulos Git

Este repositorio utiliza submódulos de Git para incluir el script de descarga y parcheo de los feeds de Renfe. Al clonar el repositorio, es importante inicializar y actualizar los submódulos para asegurarse de que se descarguen correctamente.

### Desarrollo: actualizar submódulos

Para actualizar los submódulos a la última versión disponible en sus respectivos repositorios, se puede utilizar el siguiente comando:

```bash
git submodule foreach git pull origin main
git commit -am "Update submodules"
```

## Licencia

Este proyecto está cedido como software libre bajo licencia EUPL v1.2 o superior. Más información en el archivo [`LICENCE`](./LICENCE) o en [Interoperable Europe](https://interoperable-europe.ec.europa.eu/collection/eupl).

Los datos GTFS originales están cedidos por sus propietarios bajo sus respectivas licencias, aunque siempre bajo licencias abiertas y gratuitas. Al no distribuir directamente los datos, sino scripts para descargarlos, entendemos que no es necesario incluir las licencias de los datos directamente en este repositorio, quedando a criterio del usuario final el cumplimiento de las mismas.
