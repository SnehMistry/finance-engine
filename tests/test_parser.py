from pathlib import Path

import pytest

from finance_engine.parser import FileFormatError, parse_file, read_rows


def test_reads_rows_with_line_numbers(write_csv):
    path = write_csv(
        "2026-09-01,expense,housing,Rent,1500.00,,,,",
        "2026-09-02,income,salary,Pay,2100.00,3000.00,600.00,150.00,150.00",
    )
    rows = read_rows(path)
    assert [row.row for row in rows] == [2, 3]
    assert rows[0].fields["category"] == "housing"
    assert rows[1].fields["gross"] == "3000.00"


def test_row_numbers_stay_correct_after_blank_lines(write_csv):
    path = write_csv("2026-09-01,expense,housing,Rent,1500.00", "", "2026-09-02,expense,dining,Taco,9.00")
    assert [row.row for row in read_rows(path)] == [2, 4]


def test_header_is_case_and_space_insensitive_and_optional_columns_can_be_omitted(write_csv):
    path = write_csv("2026-09-01,expense,housing,Rent,1500.00", header=" Date ,TYPE,Category,Description,Amount")
    result = parse_file(path)
    assert not result.errors
    assert result.entries[0].description == "Rent"


def test_cells_are_stripped(write_csv):
    path = write_csv("  2026-09-01 , expense , housing , Rent , 1500.00 ")
    assert read_rows(path)[0].fields["description"] == "Rent"


def test_handles_utf8_bom_from_excel(tmp_path):
    path = tmp_path / "excel.csv"
    path.write_bytes("﻿date,type,category,description,amount\n2026-09-01,expense,dining,Café,4.50\n".encode())
    result = parse_file(path)
    assert result.entries[0].description == "Café"


def test_quoted_fields_with_commas(write_csv):
    path = write_csv('2026-09-01,expense,dining,"Tacos, chips and salsa",12.00')
    assert parse_file(path).entries[0].description == "Tacos, chips and salsa"


def test_counts_extra_values_beyond_header(write_csv):
    path = write_csv("2026-09-01,expense,housing,Rent,1500.00,,,,,surprise,")
    assert read_rows(path)[0].extra_values == 1


def test_empty_file_has_no_rows(write_csv):
    assert read_rows(write_csv(header=None)) == []


def test_file_with_only_blank_lines_has_no_rows(tmp_path):
    path = tmp_path / "blank.csv"
    path.write_text("\n\n\n")
    assert read_rows(path) == []


def test_header_only_file_has_no_rows(write_csv):
    result = parse_file(write_csv())
    assert result.entries == [] and result.errors == [] and result.rows_read == 0


def test_missing_required_column(write_csv):
    path = write_csv("2026-09-01,expense,Rent,1500.00", header="date,type,description,amount")
    with pytest.raises(FileFormatError, match="missing required column\\(s\\): category"):
        read_rows(path)


def test_duplicate_column(write_csv):
    path = write_csv(header="date,type,category,description,amount,amount")
    with pytest.raises(FileFormatError, match="duplicate column"):
        read_rows(path)


def test_missing_file():
    with pytest.raises(FileFormatError, match="file not found"):
        read_rows(Path("does/not/exist.csv"))


def test_directory_instead_of_file(tmp_path):
    with pytest.raises(FileFormatError, match="cannot read"):
        read_rows(tmp_path)


def test_binary_file_is_rejected(tmp_path):
    path = tmp_path / "image.csv"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x00")
    with pytest.raises(FileFormatError, match="not a UTF-8 text file"):
        read_rows(path)


@pytest.mark.parametrize(
    ("limit", "line"),
    [(15, "line 2"), (5, "line 1")],  # a too-long cell in a data row, then in the header
)
def test_csv_library_errors_become_file_format_errors(write_csv, limit, line):
    import csv

    path = write_csv("2026-09-01,expense,housing,A very long description indeed,1500.00")
    old_limit = csv.field_size_limit(limit)
    try:
        with pytest.raises(FileFormatError, match=line):
            read_rows(path)
    finally:
        csv.field_size_limit(old_limit)
