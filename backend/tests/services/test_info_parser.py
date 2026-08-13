import pytest

from app.services.info_parser import InfoParser


def test_parse_students_valid_xml_returns_ordered_students(sample_info_xml):
    xml_path = sample_info_xml(
        [
            {"student_id": "10000409", "title": "Ms", "name": "M S Dilshanika Perera"},
            {"student_id": "10009301", "title": "Mr", "name": "K A Perera"},
            {"student_id": "10009302", "title": "Mr", "name": "S B Silva"},
        ]
    )

    students = InfoParser().parse_students(str(xml_path))

    assert [s.index for s in students] == ["10000409", "10009301", "10009302"]
    assert [s.row_no for s in students] == [1, 2, 3]
    assert students[0].name == "M S Dilshanika Perera"
    assert students[0].title == "Ms"


def test_parse_students_single_student_not_collapsed_to_dict(sample_info_xml):
    """xmltodict collapses a lone child element to a dict instead of a
    list-of-one; InfoParser must normalize that away.
    """
    xml_path = sample_info_xml([{"student_id": "10000409", "title": "Ms", "name": "Solo Student"}])

    students = InfoParser().parse_students(str(xml_path))

    assert len(students) == 1
    assert students[0].index == "10000409"


def test_parse_students_malformed_xml_raises_value_error(tmp_path):
    xml_path = tmp_path / "info.xml"
    xml_path.write_text("<students><student><name>Broken</students>", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed XML"):
        InfoParser().parse_students(str(xml_path))


def test_parse_students_missing_required_field_raises_value_error(tmp_path):
    xml_path = tmp_path / "info.xml"
    xml_path.write_text(
        "<students><student><title>Mr</title></student></students>", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Malformed <student> entry"):
        InfoParser().parse_students(str(xml_path))


def test_parse_students_empty_roster_raises_value_error(tmp_path):
    xml_path = tmp_path / "info.xml"
    xml_path.write_text("<students></students>", encoding="utf-8")

    with pytest.raises(ValueError, match="No <student> entries"):
        InfoParser().parse_students(str(xml_path))


def test_parse_students_wrong_root_element_raises_value_error(tmp_path):
    xml_path = tmp_path / "info.xml"
    xml_path.write_text("<roster><student_id>1</student_id></roster>", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected a <students> root element"):
        InfoParser().parse_students(str(xml_path))


def test_parse_students_root_with_no_student_key_raises_value_error(tmp_path):
    """A <students> root present but with no <student> child at all (as
    opposed to a self-closing/empty one) still hits the "no entries" path.
    """
    xml_path = tmp_path / "info.xml"
    xml_path.write_text("<students><note>none yet</note></students>", encoding="utf-8")

    with pytest.raises(ValueError, match="No <student> entries"):
        InfoParser().parse_students(str(xml_path))


def test_parse_is_backward_compatible_alias_for_parse_students(sample_info_xml):
    xml_path = sample_info_xml([{"student_id": "1", "title": "Mr", "name": "Alias Test"}])

    students = InfoParser().parse(str(xml_path))

    assert students[0].index == "1"


@pytest.mark.parametrize(
    "method_name, args",
    [
        ("parse_sheets", ("info.xml",)),
        ("find_sheet", ("info.xml", "1.jpeg")),
        ("parse_institution", ("info.xml",)),
        ("parse_ground_truth", ("info.xml", "1.jpeg")),
    ],
)
def test_unsupported_schema_methods_raise_not_implemented(method_name, args):
    """info.xml's actual schema has no <sheets>/<institution>/ground-truth
    section; these legacy methods are kept only to document that explicitly.
    """
    method = getattr(InfoParser(), method_name)

    with pytest.raises(NotImplementedError):
        method(*args)
