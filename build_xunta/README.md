# Feed GTFS mejorado de la Xunta de Galicia

Este repositorio contendrá un feed GTFS (General Transit Feed Specification) mejorado a partir del feed oficial de la Xunta de Galicia, publicado en el [Punto de Acceso Nacional](https://nap.transportes.gob.es/Files/Detail/1386) del Ministerio de Transportes y Movilidad Sostenible de España.

## Mejoras que se realizan

- **Restricciones de tráfico**: Se marcan las paradas del concello de salida como "solo subida", y las del concello de llegada como "solo bajada", cuando uno u otro son A Coruña, Lugo, Ourense, Santiago o Vigo. De este modo se reduce la probabilidad de calcular rutas que no se pueden realizar por prohibiciones de tráfico (que corresponde al transporte urbano).
- **Añadir nombre de parroquia y concello**: Se añade al campo `stop_desc` el nombre de la parroquia y concello donde se ubica la parada, con datos de OpenStreetMap, separados por ` -- ` para su más fácil transformación y uso en otras aplicaciones. En algunos casos la parroquia puede ser igual al Concello donde se encuentra. Ejemplos: `Salcedo -- Pontevedra`, `Elviña -- A Coruña`.
- **Separación de rutas en agencias**: Se crean agencias separadas para cada operador, asignando las rutas correspondientes a estas. Este proceso incluye añadir los datos manualmente en [agency_mappings.json](./agency_mappings.json) a partir de los adjudicatarios, con sus colores de marca e información de contacto (para aquel cuya web tenga datos más detallados sobre el servicio). Las adjudicaciones están disponibles en estos 4 expedientes de Contratos de Galicia:
  - [XG600-XG743](https://www.contratosdegalicia.gal/licitacion?OP=50&N=501362&lang=gl)
  - [XG603, XG630, XG641, XG686](https://www.contratosdegalicia.gal/licitacion?OP=50&N=573083&lang=gl)
  - [XG800-XG891](https://www.contratosdegalicia.gal/licitacion?OP=50&N=640920&lang=gl)
  - [XG635](https://www.contratosdegalicia.gal/licitacion?OP=50&N=823020&lang=gl)

## Mejoras planificadas

Las mejoras previstas incluyen:

- **Uso de nomenclaturas de líneas de los operadores**: Además, o en lugar de, utilizar la nomenclatura oficial de la Xunta para las líneas `XG<contrato><línea>`, se emplearán las nomenclaturas utilizadas por los operadores en caso de haberlos. Por ejemplo, las líneas operadas por ALSA en los entornos de A Coruña y Ferrol, Lugove en el Val Miñor/Baixo Miño; y Autocares Rías Baixas en Pontevedra.
- **Datos sobre tarifas y precios**: Se añadirán datos relacionados con las tarifas y precios de los billetes, a partir de la información que proporciona la Xunta en Excel y el portal <https://bus.gal>.

## Mejoras no planificadas

No se planea modificar la información de líneas, recorridos, horarios o paradas, dado que estos datos están sujetos a variación por la administración y es una cantidad inmensa de mejoras que habría que realizar, y que no puede ser hecha mediante scripts automáticos.

## Contribuciones

Las contribuciones son bienvenidas. Si deseas colaborar en la mejora del feed GTFS, por favor abre un issue o envía un pull request con tus propuestas o cambios.

## Licencia

El código propio de este proyecto está bajo la [European Union Public License v1.2 o posterior](./LICENCE). El feed GTFS original y el proporcionado por este proyecto están sujetos a la licencia del feed original, disponible en el archivo [`LICENCE-MITRAMS.md`](LICENCE-MITRAMS.md).

Este repositorio utiliza datos de OpenStreetMap, que están bajo licencia [Open Data Commons Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/) y pueden requerir dar crédito por su uso.
