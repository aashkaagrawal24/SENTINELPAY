import json
from typing import Any, ClassVar

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.phase9 import ProvenanceCreate


class ProvenanceService:
    AUTHORITY_TRUST: ClassVar[set[str]] = {
        "USER_SIGNED",
        "MERCHANT_SIGNED",
        "RAZORPAY_VERIFIED",
    }

    @classmethod
    def validate_authority(cls, trust_class: str, financial_authority: bool) -> None:
        if financial_authority and trust_class not in cls.AUTHORITY_TRUST:
            raise PermissionError(
                f"{trust_class} provenance cannot create financial authority"
            )

    def create(self, db: Session, record: ProvenanceCreate) -> dict:
        self.validate_authority(record.trust_class, record.financial_authority)
        row = (
            db.execute(
                text(
                    """insert into provenance_records(entity_type,entity_id,field_name,value_snapshot,unit,value_type,trust_class,method,model_name,model_version,source,source_reference,source_date,confidence,assumption,financial_authority,user_id,merchant_id)
                    values(:entity_type,:entity_id,:field_name,cast(:value_snapshot as jsonb),:unit,:value_type,:trust_class,:method,:model_name,:model_version,:source,:source_reference,:source_date,:confidence,:assumption,:financial_authority,:user_id,:merchant_id) returning *"""
                ),
                {
                    **record.model_dump(exclude={"value_snapshot"}),
                    "value_snapshot": json.dumps(record.value_snapshot, default=str),
                },
            )
            .mappings()
            .one()
        )
        db.commit()
        return dict(row)

    @classmethod
    def safe_view(cls, row: dict[str, Any]) -> dict[str, Any]:
        trust = row["trust_class"]
        authority = bool(row["financial_authority"] and trust in cls.AUTHORITY_TRUST)
        return {
            key: row.get(key)
            for key in (
                "id",
                "entity_type",
                "entity_id",
                "field_name",
                "value_snapshot",
                "unit",
                "value_type",
                "trust_class",
                "method",
                "model_name",
                "model_version",
                "source",
                "source_reference",
                "source_date",
                "confidence",
                "assumption",
                "created_at",
                "updated_at",
            )
        } | {"financial_authority": "ALLOWED" if authority else "NONE"}
