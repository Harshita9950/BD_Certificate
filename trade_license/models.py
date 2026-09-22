"""
trade_license/models.py
=======================
Trade Licence business domain models.

This file is intentionally minimal at the foundation stage.
Models will be added incrementally in subsequent development phases,
following the confirmed lifecycle:

  Phase 2 — Application & Workflow
  ─────────────────────────────────
  Application
    The core application record. Tracks applicant, business details,
    premises details, selected trade/sub-trade, and current status.
    Once submitted, the record is never deleted — only status-transitioned.

  ApplicationStatusHistory
    Immutable log of every status change with actor, timestamp, and remarks.
    Provides the full audit trail for the application lifecycle.

  DeficiencyNote
    A deficiency raised during scrutiny. Links to specific documents
    or fields that the applicant must rectify.

  Phase 3 — Master Catalogues (configurable — no hard-coded values)
  ─────────────────────────────────────────────────────────────────
  TradeCategory   — top-level grouping (Manufacturing, Retail, Services, …)
  Trade           — a specific trade type within a category
  SubTrade        — granular sub-classification within a trade
  DocumentType    — allowed document types, configurable per trade/ULB
  TradeDocumentRule — which documents are required for each trade/sub-trade

  Phase 4 — Inspection
  ─────────────────────
  InspectionSchedule
  InspectionReport
  InspectionChecklist   (configurable per trade type)

  Phase 5 — Finance
  ──────────────────
  FeeRule         — configurable fee schedule; no hard-coded rates
  DemandNote      — generated financial demand; immutable once issued
  Payment         — payment events against a demand note

  Phase 6 — Licensing
  ────────────────────
  TradeLicence        — the issued licence; immutable except via lifecycle events
  LicenceRenewal
  LicenceModification
  LicenceTransfer
  LicenceSuspension
  EnforcementAction

Architecture principles
-----------------------
- All configuration (trade names, fee rates, document requirements,
  workflow rules) lives in master tables — never in code.
- Financial and legal records (DemandNote, Payment, TradeLicence) are
  append-only and must never be hard-deleted.
- Every significant state change writes an immutable history record.
- The system must be reusable across different ULBs and states by
  parameterising all ULB-specific configuration.
"""
