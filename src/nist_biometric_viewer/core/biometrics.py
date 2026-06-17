"""Biometric modality classification and workflow filtering."""

from __future__ import annotations

from nist_biometric_viewer.core.models import (
    BiometricClassification,
    BiometricImage,
    BiometricModality,
    BiometricWorkflow,
    ClassificationBasis,
    NistRecord,
    NistTransaction,
    SkippedBiometricRecord,
)

FINGERPRINT_REVIEW: BiometricWorkflow = "fingerprint_review"
SKIPPED_FROM_FINGERPRINT_REVIEW = "Skipped from fingerprint review."
NON_FINGERPRINT_RECORDS_SKIPPED = "Non-fingerprint records skipped."

FINGERPRINT_POSITION_CODES = frozenset(str(code) for code in range(0, 16))
PALM_POSITION_CODES = frozenset(str(code) for code in range(20, 29))

_BIOMETRIC_RECORD_TYPES = {
    4,
    8,
    10,
    13,
    14,
    15,
    17,
}


def classify_nist_record(record: NistRecord) -> BiometricClassification:
    """Classify a parsed ANSI/NIST record without inspecting filenames."""
    return classify_nist_fields(
        record.record_type,
        _first_component(_scalar_text(record.fields.get(f"{record.record_type}.013"))),
    )


def classify_nist_fields(
    record_type: int,
    position_code: str | None = None,
) -> BiometricClassification:
    """Return modality and compatible workflows for common ANSI/NIST records."""
    position = (position_code or "").strip()
    if record_type == 4:
        return _classification("fingerprint", FINGERPRINT_REVIEW, "record_type")
    if record_type == 14:
        if position in PALM_POSITION_CODES:
            return _classification("palm", "palm_review", "record_type_and_field")
        return _classification("fingerprint", FINGERPRINT_REVIEW, "record_type")
    if record_type == 13:
        if position in FINGERPRINT_POSITION_CODES:
            return _classification("fingerprint", FINGERPRINT_REVIEW, "field")
        if position in PALM_POSITION_CODES:
            return _classification("palm", "palm_review", "field")
        if position:
            return BiometricClassification(
                modality="unknown",
                compatible_workflows=(FINGERPRINT_REVIEW,),
                basis="record_type_and_field",
            )
        return BiometricClassification(
            modality="unknown",
            compatible_workflows=(FINGERPRINT_REVIEW,),
            basis="record_type",
        )
    if record_type == 15:
        return _classification("palm", "palm_review", "record_type")
    if record_type == 10:
        return _classification("photo", "photo_review", "record_type")
    if record_type == 17:
        return _classification("iris", "iris_review", "record_type")
    if record_type == 8:
        return _classification("signature", "other_review", "record_type")
    return BiometricClassification()


def classify_biometric_image(image: BiometricImage) -> BiometricClassification:
    """Classify an image model from its parsed record type and position field."""
    return classify_nist_fields(image.record_type, image.finger_position_code)


def apply_biometric_workflow_filter(
    transaction: NistTransaction,
    workflow: BiometricWorkflow,
) -> NistTransaction:
    """Mutate a transaction so the active workflow sees only compatible images."""
    transaction.review_workflow = workflow
    skipped_records: list[SkippedBiometricRecord] = []
    skipped_warning_texts: set[str] = set()
    for record in transaction.records:
        classification = record.biometric_classification
        if classification.basis == "unknown":
            classification = classify_nist_record(record)
            record.biometric_classification = classification
        record.review_skip_reason = None
        if not _is_known_biometric_record(record, classification):
            continue
        if workflow in classification.compatible_workflows:
            continue
        if classification.modality == "unknown":
            continue
        record.review_skip_reason = _skip_reason(workflow)
        skipped_warning_texts.update(
            _transaction_warning(record.record_type, warning)
            for warning in record.warnings
        )
        skipped_records.append(
            SkippedBiometricRecord(
                record_type=record.record_type,
                modality=classification.modality,
                reason=record.review_skip_reason,
            )
        )

    transaction.biometric_images = [
        image
        for image in transaction.biometric_images
        if workflow in _image_classification(image).compatible_workflows
    ]
    transaction.skipped_biometric_records = skipped_records
    if skipped_warning_texts:
        transaction.warnings = [
            warning
            for warning in transaction.warnings
            if warning not in skipped_warning_texts
        ]
    return transaction


def _image_classification(image: BiometricImage) -> BiometricClassification:
    classification = image.biometric_classification
    if classification.basis != "unknown":
        return classification
    classification = classify_biometric_image(image)
    image.biometric_classification = classification
    return classification


def _classification(
    modality: BiometricModality,
    workflow: BiometricWorkflow,
    basis: ClassificationBasis,
) -> BiometricClassification:
    return BiometricClassification(
        modality=modality,
        compatible_workflows=(workflow,),
        basis=basis,
    )


def _is_known_biometric_record(
    record: NistRecord,
    classification: BiometricClassification,
) -> bool:
    if classification.modality != "unknown":
        return True
    if record.record_type in _BIOMETRIC_RECORD_TYPES:
        return True
    return any(key.endswith(".999") for key in record.fields)


def _skip_reason(workflow: BiometricWorkflow) -> str:
    if workflow == FINGERPRINT_REVIEW:
        return SKIPPED_FROM_FINGERPRINT_REVIEW
    return "Skipped from review."


def _transaction_warning(record_type: int, warning: str) -> str:
    if record_type <= 0 or warning.startswith("Unsupported Type-"):
        return warning
    return f"Type-{record_type}: {warning}"


def _scalar_text(value: object | None) -> str | None:
    if value is None or isinstance(value, bytes):
        return None
    return str(value).strip() or None


def _first_component(value: str | None) -> str | None:
    if not value:
        return None
    for separator in (" | ", ",", ":", ";"):
        value = value.split(separator, maxsplit=1)[0]
    return value.strip() or None
