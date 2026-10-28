# Catalog

The catalog resolves part and color ids into shapes, geometry and colors.

::: bricky.catalog
    options:
      members: [Catalog, CatalogFile, load_catalog, default_catalog, catalog_path, SAMPLE_CATALOG, IMPORTED_CATALOG]

::: bricky.catalog.models
    options:
      members: [Part, CatalogPart, Color, ColorType, Connector, ConnectorKind, Family]

::: bricky.catalog.importing
    options:
      members: [import_catalog, Coverage]
