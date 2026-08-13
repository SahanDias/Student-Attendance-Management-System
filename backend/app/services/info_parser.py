import xmltodict

from app.models.schemas import SheetMeta, Student


class InfoParser:
    """Reads the roster info.xml schema:

    <students>
      <student>
        <student_id>10000409</student_id>
        <title>Ms</title>
        <name>M S Dilshanika Perera</name>
      </student>
      ...
    </students>

    Fields are child elements, not attributes, and there is no <sheets>,
    <institution>, or ground-truth section in this schema -- row_no comes
    from each <student>'s position in document order (1-indexed), not from
    a source attribute.

    xmltodict collapses a single child element to a dict instead of a
    list-of-one -- every place that matters below goes through _children()
    to normalize that away.
    """

    def _load(self, xml_path: str) -> dict:
        try:
            with open(xml_path, "rb") as f:
                data = xmltodict.parse(f.read())
        except Exception as exc:
            raise ValueError(f"Malformed XML in {xml_path}: {exc}") from exc

        try:
            return data["students"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Expected a <students> root element in {xml_path}") from exc

    @staticmethod
    def _children(node: dict | None, tag: str) -> list[dict]:
        """Fetch `tag` off `node`, coercing xmltodict's dict-vs-list ambiguity
        to a list. Returns [] for a missing or self-closing/empty parent.
        """
        if not node:
            return []
        child = node.get(tag)
        if child is None:
            return []
        if isinstance(child, list):
            return child
        return [child]

    def parse_students(self, xml_path: str) -> list[Student]:
        root = self._load(xml_path)
        raw_students = self._children(root, "student")
        if not raw_students:
            raise ValueError(f"No <student> entries found under <students> in {xml_path}")

        students: list[Student] = []
        for row_no, raw in enumerate(raw_students, start=1):
            try:
                students.append(
                    Student(
                        index=raw["student_id"],
                        name=raw["name"],
                        batch="",
                        row_no=row_no,
                        title=raw.get("title"),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Malformed <student> entry in {xml_path}: {exc}") from exc

        return students

    def parse_sheets(self, xml_path: str) -> list[SheetMeta]:
        raise NotImplementedError(
            "info.xml has no <sheets> section in this schema -- sheet metadata "
            "(subject_code/session_date) now comes from the upload form instead"
        )

    def find_sheet(self, xml_path: str, image_filename: str) -> SheetMeta | None:
        raise NotImplementedError(
            "info.xml has no <sheets> section in this schema -- there is no "
            "sourceImage to match an uploaded image against"
        )

    def parse_institution(self, xml_path: str) -> dict:
        raise NotImplementedError("info.xml has no <institution> section in this schema")

    def parse_ground_truth(self, xml_path: str, source_image: str) -> dict[str, bool]:
        raise NotImplementedError(
            "info.xml has no ground truth in this schema -- see Evaluator, which "
            "reads a separate tests/ground_truth.json instead"
        )

    def parse(self, xml_path: str) -> list[Student]:
        """Backward-compatible alias for parse_students(), kept so callers
        outside this rewrite's scope (cli/sams.py) don't break.
        """
        return self.parse_students(xml_path)
