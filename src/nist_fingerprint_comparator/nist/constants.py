"""Record and field constants used by the pragmatic parser."""

SUPPORTED_TAGGED_IMAGE_RECORDS = {13, 14, 15}
SUPPORTED_RECORD_TYPES = {1, 2, 4, *SUPPORTED_TAGGED_IMAGE_RECORDS}

TAGGED_IMAGE_FIELDS = {
    "001": "length",
    "002": "idc",
    "003": "impression_type",
    "004": "source_agency",
    "005": "capture_date",
    "006": "width",
    "007": "height",
    "008": "scale_units",
    "009": "horizontal_pixel_scale",
    "010": "vertical_pixel_scale",
    "011": "compression",
    "012": "bit_depth",
    "013": "finger_position",
    "024": "quality",
    "999": "image_data",
}

COMPRESSION_NAMES = {
    "0": "RAW",
    "NONE": "RAW",
    "RAW": "RAW",
    "1": "WSQ",
    "WSQ": "WSQ",
    "2": "JPEG",
    "JPG": "JPEG",
    "JPEG": "JPEG",
    "3": "JPEG2000",
    "JP2": "JPEG2000",
    "JPEG2K": "JPEG2000",
    "JPEG2000": "JPEG2000",
    "4": "PNG",
    "PNG": "PNG",
}
