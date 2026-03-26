# Generador de GTFS Vigo

Este repositorio contiene un script para mejorar los datos del feed GTFS del transporte urbano de Vigo, España. El script descarga los datos oficiales del Open Data municipal y aplica pequeñas correcciones-mejoras.

## Requisitos

- Python 3.12 o superior y `requests`. Con [uv](https://docs.astral.sh/uv) no es necesario instalar dependencias manualmente.
- Clave API del Punto de Acceso Nacional (NAP) de España. Se puede obtener en su portal: <https://nap.transportes.gob.es> registrándose como consumidor de manera gratuita.

## Uso

1. Clona este repositorio:

   ```bash
   git clone https://github.com/tpgalicia/gtfs-vigo.git
   cd gtfs-vigo
   ```

2. Ejecutar el script para generar el feed GTFS estático:

   ```bash
   uv run build_static_feed.py
   ```

El feed GTFS generado se guardará en `gtfs_vigo.zip`.

## Licencia

Este proyecto está cedido como software libre bajo licencia EUPL v1.2 o superior. Más información en el archivo [`LICENCE`](LICENCE) o en [Interoperable Europe](https://interoperable-europe.ec.europa.eu/collection/eupl).

Los datos GTFS originales son propiedad del Concello de Vigo o su proveedor, cedidos bajo los [términos de uso de datos.vigo.org](https://datos.vigo.org/es/condiciones-de-uso-de-los-datos/).
