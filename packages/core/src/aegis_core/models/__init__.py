"""ORM modelleri — bu paketi import etmek modelleri ``Base.metadata``'ya kaydeder."""

from aegis_core.models.audit_event import AuditAction, AuditEvent
from aegis_core.models.discrepancy import Discrepancy, DiscrepancySeverity, DiscrepancyStatus
from aegis_core.models.document import (
    Document,
    DocumentType,
    ExtractionProposal,
    ExtractionStatus,
    ProposalKind,
    ProposalStatus,
)
from aegis_core.models.entity import (
    Entity,
    EntityAttribute,
    EntitySchema,
    EntityStatus,
    Relationship,
    RelationshipType,
    SourceType,
)
from aegis_core.models.membership import Membership, Role
from aegis_core.models.organization import Organization
from aegis_core.models.sanctions_dataset import SanctionsDataset
from aegis_core.models.screening import (
    MatchCandidate,
    Screening,
    ScreeningStatus,
    SubjectRole,
)
from aegis_core.models.tenant_setting import TenantSetting
from aegis_core.models.user import User

__all__ = [
    "AuditAction",
    "AuditEvent",
    "Discrepancy",
    "DiscrepancySeverity",
    "DiscrepancyStatus",
    "Document",
    "DocumentType",
    "Entity",
    "EntityAttribute",
    "EntitySchema",
    "EntityStatus",
    "ExtractionProposal",
    "ExtractionStatus",
    "MatchCandidate",
    "Membership",
    "Organization",
    "ProposalKind",
    "ProposalStatus",
    "Relationship",
    "RelationshipType",
    "Role",
    "SanctionsDataset",
    "Screening",
    "ScreeningStatus",
    "SourceType",
    "SubjectRole",
    "TenantSetting",
    "User",
]
