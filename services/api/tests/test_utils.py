from __future__ import annotations

import pytest

from app.errors import InvalidBoundingBox, InvalidLayerId, InvalidTileCoordinates
from app.services.utils import (
    humanize_identifier,
    is_integer_type,
    normalize_geometry_type,
    parse_bbox,
    validate_layer_id,
    validate_tile_coordinates,
)


def test_validate_layer_id_accepts_schema_table() -> None:
    assert validate_layer_id("gis.districts") == ("gis", "districts")


@pytest.mark.parametrize(
    "value",
    ["districts", "gis.", ".districts", "gis..districts", "gis.districts;drop", "a-b.c"],
)
def test_validate_layer_id_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(InvalidLayerId):
        validate_layer_id(value)


def test_parse_bbox_returns_ordered_tuple() -> None:
    assert parse_bbox("91.1,23.5,91.9,24.1") == (91.1, 23.5, 91.9, 24.1)


def test_parse_bbox_allows_none() -> None:
    assert parse_bbox(None) is None


@pytest.mark.parametrize(
    "value",
    ["1,2,3", "1,2,3,4,5", "a,b,c,d", "10,20,5,30", "-181,0,1,1", "0,-91,1,1"],
)
def test_parse_bbox_rejects_bad_values(value: str) -> None:
    with pytest.raises(InvalidBoundingBox):
        parse_bbox(value)


def test_tile_coordinates_reject_out_of_range_values() -> None:
    validate_tile_coordinates(0, 0, 0)
    validate_tile_coordinates(10, 1023, 1023)
    with pytest.raises(InvalidTileCoordinates):
        validate_tile_coordinates(10, 1024, 0)
    with pytest.raises(InvalidTileCoordinates):
        validate_tile_coordinates(-1, 0, 0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("POINT", "Point"),
        ("MULTIPOINT", "Point"),
        ("LINESTRING", "LineString"),
        ("MULTILINESTRING", "LineString"),
        ("POLYGON", "Polygon"),
        ("MULTIPOLYGON", "Polygon"),
        ("GEOMETRYCOLLECTION", "Unknown"),
        (None, "Unknown"),
    ],
)
def test_normalize_geometry_type(raw: str | None, expected: str) -> None:
    assert normalize_geometry_type(raw) == expected


def test_humanize_identifier() -> None:
    assert humanize_identifier("land_parcels") == "Land parcels"
    assert humanize_identifier("l03_building_footprints") == "Building footprints"
    assert humanize_identifier("x_agricultural_land") == "Agricultural land"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("integer", True), ("bigint", True), ("uuid", False), (None, False)],
)
def test_is_integer_type(value: str | None, expected: bool) -> None:
    assert is_integer_type(value) is expected
