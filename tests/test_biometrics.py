from pathlib import Path

from nist_biometric_viewer.core.biometrics import (
    FINGERPRINT_REVIEW,
    NON_FINGERPRINT_RECORDS_SKIPPED,
    SKIPPED_FROM_FINGERPRINT_REVIEW,
    apply_biometric_workflow_filter,
    classify_nist_fields,
)
from nist_biometric_viewer.core.fingerprint_filter import filter_fingerprint_source_paths
from nist_biometric_viewer.core.models import BiometricImage, NistRecord, NistTransaction
from nist_biometric_viewer.nist.separators import FS_BYTES, GS_BYTES


def _tagged_record(record_type: int, fields: list[tuple[str, bytes]]) -> bytes:
    length = 0
    while True:
        parts = [f"{record_type}.001:{length}".encode()]
        parts.extend(f"{record_type}.{number}:".encode() + value for number, value in fields)
        record = GS_BYTES.join(parts) + FS_BYTES
        if len(record) == length:
            return record
        length = len(record)


def _image(record_type: int, position_code: str | None = None) -> BiometricImage:
    return BiometricImage(
        record_type=record_type,
        finger_position_code=position_code,
        biometric_classification=classify_nist_fields(record_type, position_code),
    )


def test_nist_modality_classification_uses_record_types_and_fields() -> None:
    assert classify_nist_fields(4).modality == "fingerprint"
    assert classify_nist_fields(14, "7").modality == "fingerprint"
    assert classify_nist_fields(13, "21").modality == "palm"
    assert classify_nist_fields(15, "21").modality == "palm"
    assert classify_nist_fields(10).modality == "photo"
    assert classify_nist_fields(17).modality == "iris"


def test_fingerprint_workflow_filter_skips_non_fingerprint_biometrics() -> None:
    secret_payload = b"RAW-BIOMETRIC-DATA"
    transaction = NistTransaction(
        source_path=Path("mixed.nist"),
        records=[
            NistRecord(
                record_type=14,
                fields={"14.013": "2"},
                biometric_classification=classify_nist_fields(14, "2"),
            ),
            NistRecord(
                record_type=15,
                fields={"15.013": "21", "15.999": secret_payload},
                biometric_classification=classify_nist_fields(15, "21"),
            ),
            NistRecord(
                record_type=10,
                fields={"10.999": secret_payload},
                support_status="unsupported",
                warnings=["Unsupported Type-10 record."],
                biometric_classification=classify_nist_fields(10),
            ),
        ],
        biometric_images=[
            _image(14, "2"),
            _image(15, "21"),
        ],
        warnings=["Unsupported Type-10 record."],
    )

    apply_biometric_workflow_filter(transaction, FINGERPRINT_REVIEW)

    assert [image.record_type for image in transaction.biometric_images] == [14]
    assert [record.record_type for record in transaction.skipped_biometric_records] == [
        15,
        10,
    ]
    assert {record.reason for record in transaction.skipped_biometric_records} == {
        SKIPPED_FROM_FINGERPRINT_REVIEW
    }
    assert transaction.records[1].review_skip_reason == SKIPPED_FROM_FINGERPRINT_REVIEW
    assert transaction.records[2].review_skip_reason == SKIPPED_FROM_FINGERPRINT_REVIEW
    summary = transaction.compatibility_summary
    assert summary.status == "Compatible"
    assert summary.unsupported_record_count == 0
    assert transaction.warnings == []
    assert summary.skipped_biometric_record_count == 2
    assert NON_FINGERPRINT_RECORDS_SKIPPED in summary.compact_text()
    assert secret_payload.decode() not in summary.compact_text()
    assert secret_payload.decode() not in repr(transaction.skipped_biometric_records)


def test_unknown_latent_position_remains_fingerprint_review_compatible() -> None:
    transaction = NistTransaction(
        source_path=Path("latent.nist"),
        records=[
            NistRecord(
                record_type=13,
                fields={"13.013": "99"},
                biometric_classification=classify_nist_fields(13, "99"),
            )
        ],
        biometric_images=[_image(13, "99")],
    )

    apply_biometric_workflow_filter(transaction, FINGERPRINT_REVIEW)

    assert len(transaction.biometric_images) == 1
    assert transaction.skipped_biometric_records == []


def test_source_filter_keeps_only_files_with_fingerprint_impressions(
    tmp_path: Path,
) -> None:
    fingerprint = tmp_path / "fingerprint.nist"
    photo = tmp_path / "face.nist"
    secret_payload = b"SECRET-FACE-BIOMETRIC-PAYLOAD"
    fingerprint.write_bytes(
        _tagged_record(14, [("002", b"1"), ("013", b"7"), ("999", b"fingerprint")])
    )
    photo.write_bytes(
        _tagged_record(10, [("002", b"2"), ("003", b"FACE"), ("999", secret_payload)])
    )

    result = filter_fingerprint_source_paths([photo, fingerprint])

    assert result.fingerprint_paths == [fingerprint]
    assert result.skipped_paths == [photo]
    assert secret_payload.decode() not in repr(result)
