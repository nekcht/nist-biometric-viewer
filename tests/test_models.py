from pathlib import Path

from nist_biometric_viewer.core.models import (
    BiometricImage,
    ComparisonSession,
    ComparisonSlot,
    NistRecord,
    NistTransaction,
    metadata_display_rows,
)


def test_model_creation_and_defaults() -> None:
    record = NistRecord(record_type=14, idc="3")
    image = BiometricImage(
        record_type=14,
        idc="3",
        finger_position_code="7",
        finger_name="Left Index",
        hand="left",
        width=800,
        height=1000,
    )
    transaction = NistTransaction(
        source_path=Path("sample.an2"),
        records=[record],
        biometric_images=[image],
    )

    assert transaction.records[0].warnings == []
    assert transaction.biometric_images[0].decode_status == "not_present"
    assert ("Dimensions", "800 x 1000") in metadata_display_rows(image)
    assert ("Decode status", "Not Present") in metadata_display_rows(image)

    session = ComparisonSession(
        file_a=transaction,
        comparison_slots=[
            ComparisonSlot(
                position_code="1",
                finger_name="Right Thumb",
                file_a_image=image,
            )
        ],
    )
    assert session.comparison_slots[0].position_code == "1"
    assert session.comparison_slots[0].file_a_image is image


def test_model_representations_omit_sensitive_payloads_and_metadata() -> None:
    record = NistRecord(record_type=14, fields={"14.999": b"RAW-IMAGE"})
    image = BiometricImage(
        record_type=14,
        raw_metadata={"14.004": "SENSITIVE-AGENCY-METADATA"},
    )
    transaction = NistTransaction(
        source_path=Path("sensitive-case-name.nist"),
        records=[record],
        transaction_metadata={"1.009": "CONTROL-NUMBER"},
        descriptive_metadata={"MN1": "REFERENCE-NUMBER"},
    )

    assert "RAW-IMAGE" not in repr(record)
    assert "SENSITIVE-AGENCY-METADATA" not in repr(image)
    assert "sensitive-case-name.nist" not in repr(transaction)
    assert "CONTROL-NUMBER" not in repr(transaction)
    assert "REFERENCE-NUMBER" not in repr(transaction)
    assert "RAW-IMAGE" not in transaction.compatibility_summary.compact_text()
