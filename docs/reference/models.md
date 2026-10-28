# Models

Build scripts create models with a `ModelBuilder`, and a model stores only part ids, colors and poses.

::: bricky.builder.ModelBuilder

::: bricky.builder.ComponentBuilder

::: bricky.model
    options:
      members: [Model, Component, Element, Instance]

::: bricky.files
    options:
      members: [load_model, save_model, load_source_map, save_source_map]

::: bricky.fill
    options:
      members: [plan_fill, Placement, BRICKS, PLATES]

::: bricky.analysis.voxels
    options:
      members: [model_voxels, world_voxels, Voxel, VoxelKey]
