from pathlib import Path

from bricky import ModelBuilder, save_model
from bricky.files import load_source_map, save_source_map, source_map_path
from bricky.provenance import Frame, Source, capture, is_script_file

HERE = Path(__file__).name


def wall(builder: ModelBuilder, x: int) -> str:
    return builder.place("3001", at=(x, 0, 0), color="Red")


def test_capture_records_the_script_stack_innermost_first():
    source = capture()
    assert source is not None
    assert source.site.function == "test_capture_records_the_script_stack_innermost_first"
    assert Path(source.site.file).name == HERE


def test_bricky_and_library_frames_are_not_script_frames():
    import pydantic  # noqa: PLC0415 - any installed library will do

    assert is_script_file(__file__)
    assert not is_script_file(str(Path(capture.__code__.co_filename)))
    assert not is_script_file(pydantic.__file__)
    assert not is_script_file("<frozen runpy>")


def test_placements_remember_the_helper_and_its_caller():
    builder = ModelBuilder()
    element = wall(builder, 0)
    source = builder.provenance().model.elements[element]
    assert [frame.function for frame in source.frames[:2]] == [
        "wall",
        "test_placements_remember_the_helper_and_its_caller",
    ]
    assert "in wall(), called from" in str(source)


def test_traces_follow_instances_to_the_element():
    builder = ModelBuilder()
    column = builder.component("column")
    column.place("3003", at=(0, 0, 0), color="Tan", id="block")
    builder.instance("column", at=(4, 0, 0), id="west")
    model = builder.build()
    trace = builder.provenance().trace(model, "west/block")
    assert trace.component == "column"
    assert trace.source is not None
    assert [step.id for step in trace.via] == ["west"]
    assert trace.via[0].source is not None
    assert trace.via[0].source.site.line > trace.source.site.line
    assert builder.provenance().trace(model, "nowhere/at/all").source is None


def test_relative_paths_keep_files_outside_the_root():
    source = Source(frames=(Frame(file=__file__, line=3, function="f"),))
    inside = source.relative_to(Path(__file__).parent)
    assert inside.site.file == HERE
    outside = source.relative_to(Path("/nonexistent"))
    assert outside.site.file == __file__


def test_source_maps_are_ignored_once_the_model_changes(tmp_path):
    builder = ModelBuilder("m")
    wall(builder, 0)
    path = tmp_path / "m.bricky.json"
    save_model(builder.build(), path)
    written = save_source_map(builder.provenance(), script=Path("m.py"), model_path=path)
    assert written == source_map_path(path) == tmp_path / "m.bricky.map.json"
    assert load_source_map(path) == builder.provenance()
    path.write_text(path.read_text().replace('"m"', '"edited"'))
    assert load_source_map(path) is None
    assert load_source_map(tmp_path / "missing.bricky.json") is None
