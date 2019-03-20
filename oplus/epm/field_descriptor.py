import re
import unidecode
from .link import Link
from .record_hook import RecordHook
from .exceptions import FieldValidationError


spaces_pattern = re.compile(r"\s+")
not_python_var_pattern = re.compile(r"(^[^\w]+)|([^\w\d]+)")
multiple_underscores_pattern = re.compile(r"[_]{2,}")


def var_name_to_ref(name):
    ref = re.sub(not_python_var_pattern, "_", name.lower())
    return re.sub(multiple_underscores_pattern, "_", ref)


class FieldDescriptor:
    """
    No checks implemented (idd is considered as ok).
    """
    BASIC_FIELDS = ("integer", "real", "alpha", "choice", "node", "external-list")

    def __init__(self, table_descriptor, index, field_basic_type, name=None):
        self.table_descriptor = table_descriptor
        if field_basic_type not in ("A", "N"):
            raise ValueError("Unknown field type: '%s'." % field_basic_type)
        self.index = index
        self.basic_type = field_basic_type  # A -> alphanumeric, N -> numeric
        self.name = name
        self.ref = None if name is None else var_name_to_ref(name)
        self.tags = {}

        self._detailed_type = None
        
    # ----------------------------------------- public api -------------------------------------------------------------
    def deserialize(self, value):
        # manage none
        if value is None:
            return None
        
        # prepare if string
        if isinstance(value, str):
            # change multiple spaces to mono spaces
            value = re.sub(spaces_pattern, lambda x: " ", value.strip())
            
            # see if still not empty
            if value == "":
                return None

            # make ASCII compatible
            value = unidecode.unidecode(value)

            # make lower case if not retaincase
            if "retaincase" not in self.tags:
                value = value.lower()

            # check not too big
            if len(value) >= 100:
                raise FieldValidationError(
                    f"Field has more than 100 characters which is the limit. {self.get_error_location_message(value)}"
                )
            
        # manage numeric types
        if self.detailed_type in ("integer", "real"):
            # special values: auto-calculate, auto-size, use-weather-file
            if value in ("autocalculate", "autosize", "useweatherfile"):
                return value
            
            if self.detailed_type == "integer":
                try:
                    return int(value)
                except:
                    raise FieldValidationError(
                        f"Couldn't parse to integer. {self.get_error_location_message(value)}"
                    )

            try:
                return float(value)
            except:
                raise FieldValidationError(
                    f"Couldn't parse to float. {self.get_error_location_message(value)}"
                )

        # manage simple string types
        if self.detailed_type in ("alpha", "choice", "node", "external-list"):
            # ensure it was str
            if not isinstance(value, str):
                raise FieldValidationError(
                    f"Value must be a string. {self.get_error_location_message(value)}"
                )
            return value

        # manage hooks (eplus reference)
        if self.detailed_type == "reference":
            # reference class name appears in v9.0.1
            references = self.tags.get("reference", [])
            # table_name, index, value, references, class_references
            return RecordHook(references, value)

        # manage links (eplus object-list)
        if self.detailed_type == "object-list":
            reference = self.tags["object-list"][0]
            return Link(reference, value)

        raise RuntimeError("should not be here")

    @property
    def is_required(self):
        return "required-field" in self.tags

    def check_not_required(self):
        if self.is_required:
            raise FieldValidationError(f"Field is required. {self.get_error_location_message()}")

    def append_tag(self, ref, value=None):
        if ref not in self.tags:
            self.tags[ref] = []

        # manage value
        if value is None:
            return

        self.tags[ref].append(value)

    @property
    def detailed_type(self):
        """
        Uses EPlus double approach of type ('type' tag, and/or 'key', 'object-list', 'external-list', 'reference' tags)
        to determine detailed type.
        
        Returns
        -------
        "integer", "real", "alpha", "choice", "reference", "object-list", "external-list", "node"
        """
        if self._detailed_type is None:
            if ("reference" in self.tags) or ("reference-class-name" in self.tags):
                self._detailed_type = "reference"
            elif "type" in self.tags:
                self._detailed_type = self.tags["type"][0].lower()  # idd is not very rigorous on case
            elif "key" in self.tags:
                self._detailed_type = "choice"
            elif "object-list" in self.tags:
                self._detailed_type = "object-list"
            elif "external-list" in self.tags:
                self._detailed_type = "external-list"
            elif self.basic_type == "A":
                self._detailed_type = "alpha"
            elif self.basic_type == "N":
                self._detailed_type = "real"
            else:
                raise ValueError("Can't find detailed type.")
        return self._detailed_type

    def get_error_location_message(self, value=None):
        return f"Table: {self.table_descriptor.table_name}, index: {self.index}, ref: {self.ref}" +\
               ("." if value is None else f", value: {value}.")
