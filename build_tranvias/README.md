# Generador de GTFS Transporte Urbano de A Coruña

Este repositorio contiene un script para mejorar los datos del feed GTFS del transporte urbano de A Coruña, España. El script descarga los datos oficiales del Punto de Acceso Nacional (NAP) de España y aplica pequeñas correcciones-mejoras.

## Requisitos

- Python 3.12 o superior y `requests`. Con [uv](https://docs.astral.sh/uv) no es necesario instalar dependencias manualmente.
- Clave API del Punto de Acceso Nacional (NAP) de España. Se puede obtener en su portal: <https://nap.transportes.gob.es> registrándose como consumidor de manera gratuita.

## Uso

1. Clona este repositorio:

   ```bash
   git clone https://github.com/tpgalicia/gtfs-coruna.git
   cd gtfs-coruna
   ```

2. Ejecutar el script para generar el feed GTFS estático:

   ```bash
   uv run build_static_feed.py <NAP API KEY>
   ```

El feed GTFS generado se guardará en `gtfs_coruna.zip`.

## Licencia

Este proyecto está cedido como software libre bajo licencia EUPL v1.2 o superior. Más información en el archivo [`LICENCE`](LICENCE) o en [Interoperable Europe](https://interoperable-europe.ec.europa.eu/collection/eupl).

Los datos GTFS originales son propiedad de Compañía de Tranvías de La Coruña (sic.), cedidos bajo la [licencia de uso libre del NAP](https://nap.transportes.gob.es/licencia-datos).
