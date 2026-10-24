// Types TypeScript du contrat SourcedAnswer (v1).
// Source de vérité : packages/contracts/schemas/SourcedAnswer.schema.json,
// générée depuis les modèles Pydantic. Génération automatique : backlog WEB-03.

export type SupportStatus = "FONDEE" | "INCERTAINE" | "BLOQUEE";
export type CheckOutcome = "OK" | "ECHEC" | "INDETERMINE" | "NON_EVALUE";
export type Verdict = "CONFORME" | "INCERTAIN" | "NON_CONFORME";

export interface SourceReference {
  source_code: string;
  official_id: string;
  document_official_id: string;
  document_title: string;
  provision_number: string;
  valid_from: string;
  valid_to: string | null;
  source_status: string;
  source_path: string;
  source_file_sha256: string;
  source_archive: string;
  connector_version: string;
}

export interface CitationCheck {
  check: string;
  outcome: CheckOutcome;
  detail: string;
}

export interface CitationVerification {
  official_id: string;
  verdict: Verdict;
  checks: CitationCheck[];
  uncertainties: string[];
  quote_start: number | null;
  quote_end: number | null;
  version_in_force_at_date: string | null;
  engine_version: string;
  contract_version: string;
}

export interface SourcedStatement {
  kind: "FAIT" | "HYPOTHESE" | "DROIT_APPLICABLE" | "INTERPRETATION" | "RECOMMANDATION";
  text: string;
  citation: SourceReference | null;
  quote: string | null;
  verification: CitationVerification | null;
  support: SupportStatus;
}

export interface SourcedAnswer {
  question_sha256: string;
  as_of: string;
  mode: string;
  status: SupportStatus;
  summary: string;
  statements: SourcedStatement[];
  uncertainties: string[];
  disclaimer: string;
}
